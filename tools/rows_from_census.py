"""Stitch the census's overlapping page views into one ordered line list per
tab - the offline row fixture the ops are checked against.

    python tools/rows_from_census.py <harvest-run-dir> <out.json>

Input: native_worker.log of a `uia_param_census` run (CENSUS_ROWS_ALL), with
lines `[census] ROWDUMP <tab> <view> ["<client y>:<text>", ...]` (JSON) and
`[census] TAB <tab> ... titles=["'<title>'@<y>", ...]`.

The census wheels two notches (120px) between views, so a line seen in view
v at client y is the SAME line as one seen in view v-1 at client y + 120.
A view's line is joined to the previous view's line when the position agrees
(+/- 8px) and the texts agree (OCR reads the same line slightly differently
from view to view); otherwise it is a new line. Page y = client y + 120 * view.

Why this exists: the ops were calibrated against the source atlas, which is
not the build. Ten of queue20's fifteen failures were labels, groups or
targets that one page of real text rules out without a GUI run.
"""
import difflib
import json
import re
import sys
from pathlib import Path

STEP = 120          # px between views (two wheel notches)
TOL = 8


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def same_text(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 4 and len(nb) >= 4 and (na.startswith(nb) or nb.startswith(na)):
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.75


def parse(log_path):
    dumps, titles = {}, {}
    for raw in Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.startswith("[census] "):
            continue
        m = re.match(r"\[census\] ROWDUMP (\S+) (\d+) (\[.*\])$", raw)
        if m:
            lines = []
            for item in json.loads(m.group(3)):
                y, _sep, text = item.partition(":")
                lines.append((int(y), text))
            dumps.setdefault(m.group(1), {})[int(m.group(2))] = lines
            continue
        m = re.match(r"\[census\] TAB (\S+) clicked=\S+ titles=\[(.*)\]$", raw)
        if m:
            titles[m.group(1)] = [(t, int(y)) for t, y in
                                  re.findall(r"'([^']*)'@(-?\d+)", m.group(2))]
    return dumps, titles


def stitch(views):
    """Ordered unique lines [(page_y, text, reads)] for one tab."""
    out = []            # (page_y, text, reads) in page order
    for view in sorted(views):
        for y, text in views[view]:
            page_y = y + STEP * view
            joined = False
            for i, (py, kept, _reads) in enumerate(out):
                if abs(py - page_y) <= TOL and same_text(kept, text):
                    # keep the longer reading: more of the line came through
                    if len(text) > len(kept):
                        out[i] = (py, text, out[i][2] + 1)
                    else:
                        out[i] = (py, kept, out[i][2] + 1)
                    joined = True
                    break
            if not joined:
                out.append((page_y, text, 1))
    out.sort(key=lambda row: row[0])
    return out


def main():
    run_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    dumps, titles = parse(run_dir / "native_worker.log")
    if not dumps:
        sys.exit("no ROWDUMP lines in %s (CENSUS_ROWS_ALL must be on)" % (run_dir / "native_worker.log"))
    # Group titles: from the run's own TAB lines when it printed them, else
    # from the title fixture (titles are windows; their y is measured with
    # the page at its top, in frame coordinates = client y + 7).
    titles_file = Path(__file__).resolve().parent.parent / "harness" / "param_ui_titles_2.4.0.json"
    if not titles and titles_file.exists():
        for tab, rows in json.loads(titles_file.read_text(encoding="utf-8"))["tabs"].items():
            titles[tab] = [(r["title"], r["y"]) for r in rows]
    fixture = {"meta": {
        "source": "census run %s (2.4.0 guest build)" % run_dir.name,
        "note": "Every painted line of every process tab in page order, as OCR read it "
                "(spellings are OCR's: 'lroning', 'linespacing'). page_y grows downward and is "
                "only meaningful for ordering. A group's rows are the lines after its title's "
                "page_y and before the next title's. Re-run scenario uia_param_census to refresh.",
    }, "tabs": {}}
    for tab, views in dumps.items():
        lines = stitch(views)
        groups = [{"title": title, "page_y": ly - 7} for title, ly in titles.get(tab, [])]
        groups.sort(key=lambda g: g["page_y"])
        # a title whose text is not among the stitched lines is still a boundary
        fixture["tabs"][tab] = {
            "groups": groups,
            "lines": [{"page_y": py, "text": text, "reads": reads} for py, text, reads in lines],
        }
        print("%-13s views %2d -> lines %3d, titles %d: %s" % (
            tab, len(views), len(lines), len(groups), [g["title"] for g in groups]))
    out_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
