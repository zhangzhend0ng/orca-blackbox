"""check_ops_against_atlas.py - offline ops-label validation.

Every PARAM_OPS label variant is checked against the source-mined
param_label_atlas.json (version-exact from the SUT's own C++ source):
  1. does the variant match SOME row on the op's claimed tab, using the
     engine's own matching semantics (single word: substring containment;
     multi-word: first word prefix + phrase prefix on the joined tail)?
  2. is the scenario's pilot VALUES key actually placed on a page (tab) at
     all, and does it agree with the ops' tab routing?

This turns label calibration from "one GUI run per guess" into an offline
table check (the census/atlas play, 2026-11-23).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.native_script_baseline import PARAM_OPS  # noqa: E402

ATLAS = json.loads((Path(__file__).resolve().parent.parent
                    / "harness/param_label_atlas.json").read_text(encoding="utf-8"))
ROWS = ATLAS["rows"]
# What the 2.4.0 build really paints as group titles (census run c101c0f4).
# The atlas comes from the host's source tree and is NOT the build: it lists
# 'Initial layer speed' where the page says 'First layer speed', and a
# 'Tree supports' group the Support page does not have - both passed the
# atlas check and both failed in the GUI (queue18, 2026-11-23).
CENSUS = json.loads((Path(__file__).resolve().parent.parent
                     / "harness/param_ui_titles_2.4.0.json").read_text(encoding="utf-8"))


def label_matches(variant, label):
    """Engine semantics: single word -> substring; multi-word -> the label's
    word sequence must have some word starting the variant's first word and
    the joined tail must start with the variant."""
    # A leading '^' anchors the label to the start of its row (engine
    # semantics, _find_phrase_row): only the row's first word may start it.
    anchored = variant.startswith("^")
    want = variant.lstrip("^").lower().split()
    words = label.lower().split()
    if len(want) == 1:
        return (want[0] in words[0]) if anchored else any(want[0] in w for w in words)
    for i in range(0 if anchored else len(words), len(words)):
        if words[i].startswith(want[0]):
            if " ".join(words[i:i + len(want)]).startswith(" ".join(want)):
                return True
    return False


def tab_rows(tab):
    out = []
    for row in ROWS.values():
        if tab in row.get("tabs", []) and (row.get("label") or row.get("line_label")):
            r = dict(row)
            if r.get("line_label"):
                r["label"] = r["line_label"]  # the painted multi-field row label
            out.append(r)
    return out


def import_pilot_values():
    """scenario -> VALUES dict, from every pilot module on disk."""
    import importlib
    import glob
    import re
    from harness import native_pilots
    mapping = getattr(native_pilots, "SCENARIO_PILOTS", None) or {}
    # native_pilots exposes scenario -> module name differently per revision;
    # discover by filename convention instead.
    out = {}
    for path in glob.glob(str(Path(__file__).resolve().parent.parent
                              / "harness/pilot_param_*.py")):
        name = Path(path).stem
        try:
            mod = importlib.import_module("harness." + name)
        except Exception:
            continue
        vals = getattr(mod, "VALUES", None)
        cid = getattr(mod, "CASE_ID", name)
        if isinstance(vals, dict):
            out[cid] = vals
    return out


def main():
    problems = []
    for scenario, ops in sorted(PARAM_OPS.items()):
        for i, op in enumerate(ops):
            tab = op.get("tab")
            labels = op.get("label")
            labels = [labels] if isinstance(labels, str) else labels
            if op.get("op") in ("float", "checkbox", "rowcombo", "combo") and labels:
                if tab:
                    rows = tab_rows(tab)
                else:
                    rows = []
                    for r in ROWS.values():
                        r2 = dict(r)
                        if r2.get("line_label"):
                            r2["label"] = r2["line_label"]
                        if r2.get("label"):
                            rows.append(r2)
                for variant in labels:
                    hits = [r for r in rows if label_matches(variant, r["label"])]
                    if hits:
                        break
                else:
                    best = []
                    for r in ROWS.values():
                        lab = r.get("line_label") or r.get("label")
                        if lab and label_matches(variant, lab):
                            best.append(f"{lab}@{r.get('tab')}")
                    # path-override rows render through the webui i18n and
                    # can legitimately differ from the def label - downgrade
                    # to 'verify-with-census' instead of a hard fail.
                    path_uncertain = any(r.get("label_path") for r in rows) or (
                        best and any(
                            ROWS.get(b.split("@")[0], {}).get("label_path")
                            for b in best))
                    tag = "UNCERTAIN(path-row, needs census)" if path_uncertain else "NO match"
                    problems.append(
                        f"{scenario} op[{i}] label {variant!r}: {tag} on tab "
                        f"{tab!r}" + (f" (atlas elsewhere: {best[:3]})" if best else
                                      " (nowhere in atlas)"))
            if op.get("op") == "combo" and op.get("target"):
                # popup target should exist as an enum label of SOME def
                tgt = op["target"].lower()
                found = any(tgt in (lbl or "").lower()
                            for r in ROWS.values()
                            for lbl in (r.get("enum_labels") or []))
                if not found:
                    problems.append(f"{scenario} op[{i}] combo TARGET {op['target']!r}: "
                                    f"not found in any enum_labels")
    # pilot VALUES keys must exist as config defs at all
    for cid, values in sorted(import_pilot_values().items()):
        for key in values:
            if key not in ROWS:
                problems.append(f"pilot {cid}: VALUES key {key!r} NOT a config def "
                                f"(key-name error, precedent infill_wall_overlap)")
    # op 'group' must be a real group title on that page: a missing title
    # made scroll_group_into_view wheel until its 420s timeout (#263 'Bridge'
    # vs 'Bridging', #276 'Advanced' on Quality). A combo 'current' given as
    # a multi-word STRING can never be inside one OCR word - it must be a
    # word-sequence tuple.
    for scenario, ops in sorted(PARAM_OPS.items()):
        tab = None
        for i, op in enumerate(ops):
            tab = op.get("tab") or tab
            group = op.get("group")
            if group and tab:
                # The painted titles of the build decide; the source atlas
                # is only the fallback for a tab the census did not cover.
                titles = [r["title"] for r in CENSUS["tabs"].get(tab, [])] or \
                    [g.get("title") for g in ATLAS["pages"].get(tab, [])]
                if titles and not any(group.lower() in (t or "").lower() for t in titles):
                    problems.append(f"{scenario} op[{i}] group {group!r}: no such group title on "
                                    f"tab {tab!r} (titles: {titles})")
            current = op.get("current")
            if op.get("op") == "combo" and isinstance(current, str) and " " in current.strip():
                problems.append(f"{scenario} op[{i}] combo current {current!r}: a multi-word string "
                                f"never matches one OCR word - use a tuple")
    print(f"checked {len(PARAM_OPS)} scenarios")
    if problems:
        print(f"{len(problems)} label problems:")
        for p in problems:
            print("  -", p)
    else:
        print("all labels validate against the atlas")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
