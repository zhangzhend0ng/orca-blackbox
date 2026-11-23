"""mine_label_atlas.py - build the version-exact parameter label atlas from
the SUT's own C++ source (read-only upstream tree).

Sources of truth:
  PrintConfig.cpp  def blocks: key -> label / category / enum_values +
                   enum_labels (popup display strings) / comAdvanced flag
  Tab.cpp          page construction order: which PAGE and GROUP each key's
                   row actually appears on, plus label_path overrides (rows
                   whose displayed label comes from the webui i18n key, not
                   def->label - flagged, not resolved).

Output: harness/param_label_atlas.json
Usage: python tools/mine_label_atlas.py [path-to-orca-source] [--out FILE]
"""
import argparse
import json
import re
import sys
from pathlib import Path


def strip_l(expr):
    # L("...") -> the inner literal, joining C++ adjacent string literals
    inner = expr.strip()
    m = re.fullmatch(r'L\((.*)\)', inner, re.S)
    if not m:
        return None
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
    return "".join(parts) if parts else None


def mine_printconfig(src_text):
    atlas = {}
    # def lines come in shapes: 'def = this->add("', 'def   =   this->add("',
    # and 'auto x = def = this->add("' (e.g. top_surface_pattern) - split on
    # any of them; a false negative here wrongly flags correct pilot keys.
    blocks = re.split(r'\n\s*(?:auto\s+\w+\s*=\s*)?def\s*=\s*this->add\("', src_text)
    for block in blocks[1:]:
        key = block.split('"', 1)[0]
        row = {"key": key}
        m = re.search(r'def->label\s*=\s*(L\(.*?\)|"[^"]*")\s*;', block, re.S)
        if m:
            row["label"] = strip_l(m.group(1)) or m.group(1).strip('"')
        m = re.search(r'def->category\s*=\s*(L\(.*?\))\s*;', block, re.S)
        if m:
            row["category"] = strip_l(m.group(1))
        m = re.search(r'def->sidetext\s*=\s*L\("(.*?)"\)', block, re.S)
        if m:
            row["sidetext"] = m.group(1)
        vals = re.findall(r'enum_values\.push_back\("([^"]*)"\)', block)
        labels = re.findall(r'enum_labels\.push_back\((L\("[^"]*"\))\)', block)
        if vals:
            row["enum_values"] = vals
            row["enum_labels"] = [strip_l(x) for x in labels]
        row["advanced"] = "comAdvanced" in block
        m = re.search(r'def->mode\s*=\s*com(\w+)', block)
        if m and m.group(1) != "Advanced":
            row["mode"] = m.group(1)
        atlas[key] = row
    return atlas


def mine_tab(src_text, atlas):
    pages = {}          # page title -> [{title, rows:[keys]}]
    seen_titles = {}
    page_order = []
    # split by page creation; keep only the print-settings tab build (the
    # big one with add_options_page)
    chunks = re.split(r'page = add_options_page\(|auto page = add_options_page\(', src_text)
    for chunk in chunks[1:]:
        title_m = re.match(r'\s*L\("([^"]+)"\)', chunk)
        if not title_m:
            continue
        page = title_m.group(1)
        # Tab.cpp builds several settings tabs and page titles repeat
        # ('Multimaterial' is on both the print and the printer tab). Keying
        # by title alone let the later page overwrite the earlier one and hid
        # the print tab's Flush options / Ooze prevention / Advanced groups
        # (2026-11-23, a false "group not found" report) - number repeats.
        seen_titles[page] = seen_titles.get(page, 0) + 1
        if seen_titles[page] > 1:
            page = "%s#%d" % (page, seen_titles[page])
        pages[page] = []
        page_order.append(page)
        # groups inside this page: new_optgroup titles + subsequent appends
        group_chunks = re.split(r'optgroup = page->new_optgroup\(|page->new_optgroup\(', chunk)
        for g in group_chunks[1:]:
            g_title_m = re.match(r'\s*L\("([^"]+)"\)', g)
            g_title = g_title_m.group(1) if g_title_m else "?"
            rows = []
            def place(key, label_path, line_label=None):
                rows.append({"key": key, "label_path": label_path})
                if key in atlas:
                    atlas[key].setdefault("tabs", [])
                    if page not in atlas[key]["tabs"]:
                        atlas[key]["tabs"].append(page)
                    # 'Frequent' is the simple-mode aggregate; the advanced
                    # placement (if any) is the authoritative one.
                    if page != "Frequent" or "tab" not in atlas[key]:
                        atlas[key]["tab"] = page
                        atlas[key]["group"] = g_title
                    if label_path:
                        atlas[key]["label_path"] = label_path
                    if line_label:
                        atlas[key]["line_label"] = line_label
            for m in re.finditer(
                    r'append_single_option_line\("([^"]+)"(?:,\s*"([^"]+)")?\)', g):
                place(m.group(1), m.group(2))
            # multi-field Lines carry their OWN painted label, e.g.
            # Line line = {L("Overhang speed"), ...}; the five inline edits
            # below it share that one label.
            line_label = None
            for m in re.finditer(
                    r'Line\s+\w+\s*=\s*\{\s*L\("([^"]+)"\)|get_option\("([^"]+)"\)', g):
                if m.group(1):
                    line_label = m.group(1)
                else:
                    place(m.group(2), None, line_label)
            if rows:
                pages[page].append({"title": g_title, "rows": rows})
    return pages, page_order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default=r"C:\coil\Projects\SnapmakerOrca")
    ap.add_argument("--out", default="harness/param_label_atlas.json")
    args = ap.parse_args()
    root = Path(args.source)
    pc = (root / "src/libslic3r/PrintConfig.cpp").read_text(encoding="utf-8", errors="replace")
    tab = (root / "src/slic3r/GUI/Tab.cpp").read_text(encoding="utf-8", errors="replace")
    atlas = mine_printconfig(pc)
    pages, order = mine_tab(tab, atlas)
    n_lab = sum(1 for v in atlas.values() if v.get("label"))
    n_tab = sum(1 for v in atlas.values() if v.get("tab"))
    out = {
        "meta": {
            "source": str(root),
            "stats": {"defs": len(atlas), "with_label": n_lab,
                      "placed_on_page": n_tab, "pages": order},
        },
        "rows": atlas,
        "pages": pages,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"atlas: {len(atlas)} defs, {n_lab} labels, {n_tab} placed on pages "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
