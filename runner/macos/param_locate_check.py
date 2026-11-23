"""Offline, no GUI, no save: one reading of a page judges every label candidate of an op.

  python3 runner/macos/param_locate_check.py

A Panel is built without its constructor and its screen reads give canned OCR rows: the Speed
page as run 042843 read it (group title 'Travel speed', the row 'Travel' and '500 mm/s' as its
own value token) and the same row read as one token 'Travel 500 mm/s'. The three candidates of
uia_param_travel_speed are located together and each one alone; the reads and the find_row
evaluations are counted. Step 10 replays saved readings of the step-9 runs (readings-step10.json
over the panel shots it names, panel-relative px, the window at 0,0): group titles are told by
their fold glyph, not by the x of their text (runs 050208 / 050552); scroll_to is replayed on run
051203's scroll steps and on the page one press on - it is not changed, its stop is reproduced
and the blocker of stopping on the row itself is named as such (NOT VERIFIED); the ops' time
limits are checked as numbers. Exit status 1 when a check fails."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import param_ops as po  # noqa: E402
import param_case as pc  # noqa: E402

SPEED_CANDIDATES = ["Travel 500", "Travel speed", "Travel"]  # uia_param_travel_speed's label
TRAVEL_PAGE = "own value token", "one token"


class Point:
    x, y = 100.0, 50.0


class Size:
    y = 971  # the full-height window of the step-9 runs


EVIDENCE = po.EVIDENCE
READINGS = EVIDENCE / "readings-step10.json"


def replay(name):
    """A Panel over a saved reading: its rows and its panel shot (group_titles reads the fold
    glyphs' strip from that shot). The reading is panel-relative, so the window sits at 0,0."""
    rows = json.loads(READINGS.read_text())["readings"][name]
    panel = fake_panel(rows)
    panel.last_shot = EVIDENCE / "shots" / f"{name}.panel.png"
    panel.geometry = lambda: (Point(), Size())
    Point.x, Point.y = 0.0, 0.0
    panel.glyphs, panel.deadline = (None, []), None
    panel.scroll_to = lambda *args: po.Panel.scroll_to(panel, *args)
    return panel


def token(x, y, w, h, text):
    return {"x": x, "y": y, "w": w, "h": h, "text": text}


def speed_page(reading):
    """Tab band at y 80; titles left of TITLE_X (x < 126); rows right of it."""
    rows = [token(x, 80, 60, 16, name) for x, name in ((140, "Quality"), (210, "Strength"),
                                                        (290, "Speed"), (350, "Support"), (430, "Others"))]
    for name, y in (("Extruder", 110), ("Other layers speed", 320), ("Acceleration", 520),
                    ("Travel speed", 700)):  # no short title that 'Travel speed' contains
        rows.append(token(108, y, 140, 14, name))
    for name, y in (("Inner wall speed", 346), ("Outer wall speed", 372)):
        rows += [token(130, y, 110, 14, name), token(330, y, 50, 14, "200 mm/s")]
    if reading == TRAVEL_PAGE[0]:
        rows += [token(130, 726, 50, 14, "Travel"), token(330, 726, 70, 14, "500 mm/s")]
    else:
        rows.append(token(130, 726, 110, 14, "Travel 500 mm/s"))
    return rows


def quality_page():
    """The rows the Layer height and Precision groups of the Quality tab paint."""
    return [token(140, 80, 60, 16, "Quality"), token(108, 110, 120, 14, "Layer height"),
            token(130, 136, 80, 14, "Layer height"), token(330, 136, 40, 14, "0.2"),
            token(130, 162, 110, 14, "First layer height"), token(330, 162, 40, 14, "0.35"),
            token(108, 200, 120, 14, "Precision"), token(130, 226, 70, 14, "Arc fitting"),
            token(130, 252, 110, 14, "Precise Z height")]


def fake_panel(rows):
    panel = po.Panel.__new__(po.Panel)
    panel.desktop, panel.pid, panel.window = None, 0, None
    panel.shots, panel.last_notes = {}, []
    panel.trial, panel.scroll_up_button, panel.scroll_down_buttons = None, None, None
    panel.bar_cache, panel.full = None, True
    panel.last_shot, panel.glyphs, panel.deadline = None, (None, []), None
    panel.reads = []
    panel.read = lambda tag, full=False: (panel.reads.append(tag), rows)[1]
    panel.click_tab = lambda name, seen: [0, 0]
    panel.ensure_advanced = lambda tag: {"already_on": True}
    panel.geometry = lambda: (Point(), None)
    panel.scroll_chains = []

    def no_scroll(group, label, tag, why, budget=None):  # counted, not simulated
        panel.scroll_chains.append(tag)
        raise RuntimeError(f"scroll chain {tag} is not simulated offline")
    panel.scroll_to, panel.click = no_scroll, (lambda gx, gy, guard=True: None)
    return panel


def main():
    evaluations, checks, out = [], [], {}

    def check(name, ok):
        checks.append((name, bool(ok)))

    plain = po.Panel.find_row

    def counted(self, rows, group, label):
        evaluations.append(label)
        return plain(self, rows, group, label)

    po.Panel.find_row = counted
    for reading in TRAVEL_PAGE:
        rows, seen = speed_page(reading), {}
        for name, label in [("all three", SPEED_CANDIDATES)] + [(c, c) for c in SPEED_CANDIDATES]:
            panel = fake_panel(rows)
            evaluations.clear()
            try:
                found = po.op_find_row(panel, {"tab": "Speed", "group": "Travel speed", "label": label})
                readback = found["readback"]
                result = {"row": readback["label"], "value": readback["value_text"],
                          "candidate": readback["label_candidate"], "level": readback["match"]["level"]}
            except RuntimeError as error:
                result = {"error": po.brief(error, 90)}
            seen[name] = {**result, "page_reads": len(panel.reads) - 1,  # less the tab's own read
                          "find_row_evaluations": len(evaluations),
                          "scroll_chains_started": len(panel.scroll_chains)}
        out[reading] = seen
        together, alone, speed = seen["all three"], seen["Travel"], seen["Travel speed"]
        check(f"{reading}: the three together and 'Travel' alone give the same row",
              together.get("row") is not None and together.get("row") == alone.get("row"))
        check(f"{reading}: the three together read the page once and judge it once",
              together.get("page_reads") == 1 and together.get("find_row_evaluations") == 1)
        check(f"{reading}: 'Travel speed' alone finds no row", "error" in speed)
        check(f"{reading}: the three together start no scroll chain on a page that has the row",
              together.get("scroll_chains_started") == 0)
        if reading == TRAVEL_PAGE[0]:
            check("'Travel 500' alone finds no row while the value is its own token",
                  "error" in seen["Travel 500"])
            check("the hit is exact", together.get("level") == "exact" and together.get("candidate") == "Travel")
        else:
            check("one token: the hit is a prefix of the row text and 'Travel speed' matched no row",
                  together.get("level") == "prefix" and together.get("candidate") in SPEED_CANDIDATES[:1] + SPEED_CANDIDATES[2:]
                  and "error" in speed)
    page = quality_page()
    panel = fake_panel(page)
    strict = plain(panel, page, "Layer height", ["^Layer height"])["text"]
    try:
        plain(panel, page[:2] + page[4:], "Layer height", ["^Layer height"])  # no 'Layer height' row
        refused = False
    except RuntimeError:
        refused = True
    substring = plain(panel, page, "Precision", ["fitting"])["text"]
    prefix = plain(panel, speed_page(TRAVEL_PAGE[0]), "Other layers speed",
                   ["Outer wall speed", "^Outer wall"])["text"]
    out["other_forms"] = {"^Layer height": {"row": strict, "substring_only_refused": refused},
                          "fitting": substring, "^Outer wall": prefix}
    check("'^Layer height' takes the row 'Layer height', not 'First layer height'", strict == "Layer height")
    check("'^Layer height' refuses a page where only 'First layer height' is on it", refused)
    check("'fitting' (no '^') still takes 'Arc fitting'", substring == "Arc fitting")
    check("'^Outer wall' takes a row that starts with it", prefix == "Outer wall speed")
    case = {"label": SPEED_CANDIDATES, "group": "Travel speed"}
    panel = fake_panel(speed_page(TRAVEL_PAGE[0]))
    evaluations.clear()
    label, found, matched = pc.locate(panel, case, "Speed")
    po.Panel.find_row = plain
    out["locate"] = {"label": label, "find_row_evaluations": len(evaluations), "matched": matched}
    check("param_case.locate runs one chain for the op and names the candidate that hit",
          len(evaluations) == 1 and label == "Travel")
    # --- step 10: the readings the step-9 runs saved ---
    import tempfile
    po.OUT = Path(tempfile.mkdtemp(prefix="orca-step10-check."))  # ink_runs' working crops
    titles, rows_found = {}, []
    panel = replay("case-050208-op0-find-page-full-scroll-4")
    page, reading = panel.page_rows(panel.read("x")), panel.read("x")
    titles["050208 scroll-4"] = [(t["text"], int(t["x"])) for t in panel.group_titles(page)]
    row = plain(panel, reading, "Walls and surfaces", ["Top surface flow ratio", "Top surface flow"])
    rows_found.append(("050208 scroll-4", row["text"], int(row["x"]), int(row["y"])))
    left = [(r["text"], int(r["x"])) for r in json.loads(READINGS.read_text())
            ["readings"]["case-050208-op0-find-page-full-scroll-4"] if r["x"] < 40 and r["y"] > 700]
    panel = replay("case-050552-op1-find-page-full")
    page, reading = panel.page_rows(panel.read("x")), panel.read("x")
    titles["050552 page-full"] = [(t["text"], int(t["x"])) for t in panel.group_titles(page)]
    row = plain(panel, reading, "Line width", ["Outer wall line width", "^Outer wall"])
    rows_found.append(("050552 page-full", row["text"], int(row["x"]), int(row["y"])))

    flow, width = titles["050208 scroll-4"], titles["050552 page-full"]
    check("050208 scroll-4: 'Walls and surfaces' (text at x 28) is judged a group title",
          [t for t, _ in flow] == ["Wall generator", "Walls and surfaces"])
    check("050208 scroll-4: the row 'Top surface flow ratio' is found under it",
          rows_found[0][1] == "Top surface flow ratio")
    check("050552 page-full: 'Line width' (text at x 26) is judged a group title",
          [t for t, _ in width] == ["L Layer height", "Line width"])
    check("050552 page-full: the row 'Outer wall' is found under it by '^Outer wall'",
          rows_found[1][1] == "Outer wall")
    check("a plain row is not judged a title: 'Wall generator' the row (x 30, y 796) is left out while "
          "its title (x 30, y 767) is taken - 2 titles among 8 left-column tokens",
          len(flow) == 2 and len(left) == 8 and [t for t, _ in left].count("Wall generator") == 2)
    out["step10_titles"] = {"titles": titles, "rows": rows_found, "left_column_050208_scroll-4": left}

    # scroll_to, replayed on 051203's scroll-0 .. scroll-2 and on the page one press on
    # (050208's scroll-3: 051203 stopped at its scroll-2 and saved no scroll-3 of its own)
    panels = [replay(f"case-051203-op0-find-page-full-scroll-{i}") for i in range(3)]
    panels.append(replay("case-050208-op0-find-page-full-scroll-3"))
    seen = [other.read("x") for other in panels]  # the raw readings, tab band included
    shots = [other.last_shot for other in panels]  # taken first: `panel` below is panels[2] itself
    panel, knob, presses, pages = panels[0], [0], [], [0]
    hole = ["X-Y hole compensation", "hole compensation"]

    def next_page(tag, full=False):
        page = min(pages[0], 3)
        pages[0] += 1
        panel.reads.append(tag)
        panel.last_shot = shots[page]  # each page's own shot
        return seen[page]

    def press(index, times=1, pause=0.45):
        knob[0] += 1
        presses.append(knob[0])

    panel.read, panel.scroll_up_button, panel.scroll_down_buttons = next_page, 1, [0]
    panel.knob_at = lambda: 40 * knob[0]
    panel.find_scroll_buttons = lambda: {"down": [0], "up": 1}
    panel.scroll_top = lambda button, limit=30: {"presses": 0}
    panel.press_scroll = press
    stop = None
    try:
        panel.scroll_to("Precision", hole, "replay", "replay")
    except RuntimeError as error:
        stop = po.brief(error, 400)
    stopped = replay("case-051203-op0-find-page-full-scroll-2")
    at_stop = [(t["text"], int(t["y"])) for t in stopped.group_titles(stopped.page_rows(seen[2]))]
    after = replay("case-050208-op0-find-page-full-scroll-3")
    page3 = after.page_rows(seen[3])
    on_after = [(t["text"], int(t["y"])) for t in after.group_titles(page3)]
    wanted = [(r["text"], int(r["y"])) for r in page3 if "hole compensation" in po.norm(r["text"])]
    refused = None
    try:
        after.find_row(seen[3], "Precision", hole)
    except RuntimeError as error:
        refused = po.brief(error, 200)
    out["step10_scroll"] = {"stop": stop, "presses": len(presses), "titles_at_the_stop": at_stop,
                            "page_one_press_on": {"titles": on_after, "wanted_row": wanted,
                                                  "find_row": refused},
                            "stop_on_the_row_itself": "NOT VERIFIED"}
    check("051203 replay: scroll_to stops where run 051203 stopped, after 2 presses, with the title "
          "'E5 Precision' on the page at y 849",
          len(presses) == 2 and at_stop == [("E5 Precision", 849)] and stop is not None)
    check("the page one press on (050208 scroll-3) shows the wanted row 'X-Y hole compensation' at "
          "y 725 with no 'Precision' title on it (only 'C Ironing' y 943) and find_row refuses it: "
          "the blocker of 'stop on the row itself' (NOT VERIFIED - rows of a group whose title "
          "left the page have no attribution)",
          wanted == [("X-Y hole compensation", 725)] and on_after == [("C Ironing", 943)]
          and refused is not None and "Precision" in refused)

    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"ok": not failed, "checks": len(checks), "failed": failed, "out": out},
                     indent=1, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
