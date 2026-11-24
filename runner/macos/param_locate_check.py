"""Offline, no GUI, no save: one reading of a page judges every label candidate of an op.

  python3 runner/macos/param_locate_check.py

A Panel is built without its constructor and its screen reads give canned OCR rows: the Speed
page as run 042843 read it (group title 'Travel speed', the row 'Travel' and '500 mm/s' as its
own value token) and the same row read as one token 'Travel 500 mm/s'. The three candidates of
uia_param_travel_speed are located together and each one alone; the reads and the find_row
evaluations are counted. Step 10 replays saved readings of the step-9 runs (readings-step10.json
over the panel shots it names, panel-relative px, the window at 0,0): group titles are told by
their fold glyph, not by the x of their text (runs 050208 / 050552); scroll_to is replayed on run
051203's scroll steps and on the page one press on. Step 11: the chain of decision 2 is replayed
on the same pages - it goes on past the page run 051203 stopped at and takes the row on the next
one as a row of the group whose title is above the page; op0's locate is replayed whole over
those pages (its find_row and both locates of the op - the edit is not replayed: the saved
reading of that page has no value token on the row); a reading without the chain's state still
refuses the row; the ops' time limits are checked as numbers. Step 12: set_float's
value cell is taken by the row's label on run 063651's own page reading - its row 'X-Y hole
compensation' carries 'mm' and no number - and by a page that paints no number at all; the edit
itself (the AX tree) is the GUI run's to judge. Step 13: a row OCR reads without its word space
('Firstlayer', run 075830) is taken by its label before a prefix hit on another row. Step 15: a combo
op is located by the value it paints (op['current']) on three saved pages, its label handed to
pick_combo, and the refusals; the pick itself is not replayed. Exit status 1 when a check fails."""

import json
import re
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
    panel.entered, panel.tab_open = None, None  # step 11
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
    stop, trail = None, None
    try:
        trail = panel.scroll_to("Precision", hole, "replay", "replay")
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
    last = (trail or {}).get("steps", [{}])[-1]
    taken, edit = None, None
    if trail is not None:  # locate_row reads the page again after its chain and judges it once more
        panel.last_shot = shots[3]
        row = panel.find_row(seen[3], "Precision", hole)
        taken = {"row": row["text"], "y": int(row["y"]), "group_by": panel.last_match["group_by"],
                 "candidate": panel.last_match["label"], "level": panel.last_match["level"]}

    # --- step 11, decision 2: the chain goes on and the row is the entered group's ---
    check("the page one press on (050208 scroll-3) shows the wanted row 'X-Y hole compensation' at "
          "y 725 with no 'Precision' title on it (only 'C Ironing' y 943)",
          wanted == [("X-Y hole compensation", 725)] and on_after == [("C Ironing", 943)])
    check("a reading without the chain's state still refuses that row: find_row needs the group's "
          "title and it is not on the page (step 10's refusal, kept)",
          refused is not None and "Precision" in refused and "not visible" in refused)
    check("step 11, 051203 replay: the chain does not stop where run 051203 stopped (the page with "
          "'E5 Precision' y 849, the last title on it, no wanted row); it presses on once more",
          at_stop == [("E5 Precision", 849)] and stop is None and len(presses) == 3)
    check("step 11: the row is taken on the next page ('X-Y hole compensation' y 725) as a row of the "
          "group entered - its title above the page - and the page read again after the chain gives "
          "the same row by the candidate 'X-Y hole compensation' (exact)",
          bool(trail) and trail.get("row_by_group_entered") is True and last.get("row_y") == 725
          and last.get("titles") == ["C Ironing"]
          and taken == {"row": "X-Y hole compensation", "y": 725, "group_by": "entered",
                        "candidate": "X-Y hole compensation", "level": "exact"})

    # op0's locate, whole, over the same pages: locate_row, its chain, the page read again, and
    # the locate set_float does itself (the tab that is already open keeps the page and the state)
    op0, current = panels[1], [0]
    knob[0], presses[:] = 0, []
    op0.knob_at, op0.scroll_top, op0.press_scroll = (
        lambda: 40 * knob[0], lambda button, limit=30: {"presses": 0}, press)

    def find_buttons():  # the real one forgets nothing; a tab click does (click_tab), as on the GUI
        op0.scroll_down_buttons, op0.scroll_up_button = [0], 1
        return {"down": [0], "up": 1}

    op0.find_scroll_buttons = find_buttons
    op0.click_tab = lambda name, seen_rows: po.Panel.click_tab(op0, name, seen_rows)

    def locate_read(tag, full=False):
        op0.reads.append(tag)
        step = re.search(r"-scroll-(\d+)$", tag)
        current[0] = min(int(step.group(1)), 3) if step else current[0]
        op0.last_shot = shots[current[0]]
        return seen[current[0]]

    op0.read = locate_read
    label, found, matched = pc.locate(op0, {"label": hole, "group": "Precision"}, "Quality")
    first = {"label": label, "y": int(found["readback"]["box"]["y"]), "presses": len(presses),
             "pages_read": len(found["evidence"]["notes"][-1]["scrolled"]["steps"]) if found["evidence"]["notes"] else 0,
             "group_by": found["readback"]["match"]["group_by"],
             "chain": [(list(x)[0], bool(x.get("scrolled", {}).get("row_by_group_entered")))
                       for x in found["evidence"]["notes"] if "scrolled" in x]}
    before = len(op0.reads)
    rows2, row2, notes2, tag2 = op0.locate_row("Quality", "Precision", label, "float")
    second = {"y": int(row2["y"]), "scroll_reads": sum("-scroll-" in t for t in op0.reads[before:]),
              "tag": tag2, "group_by": op0.last_match["group_by"]}
    clicks = []
    op0.click = lambda gx, gy, guard=True: clicks.append([round(gx), round(gy)])

    class NoDesktop:  # the AX tree is not replayed offline: the GUI run's to read
        def descendants(self, window):
            raise RuntimeError("offline: no AX tree")
    op0.desktop = NoDesktop()
    try:
        po.op_set_float(op0, {"tab": "Quality", "group": "Precision", "label": label, "value": "-0.1"})
    except RuntimeError as error:
        edit = po.brief(error, 120)

    # guards of the state: another group, another tab
    guards = {}
    other = replay("case-050208-op0-find-page-full-scroll-3")
    other.entered = "line width"
    try:
        other.find_row(seen[3], "Precision", hole)
        guards["another_group_entered"] = "row taken"
    except RuntimeError as error:
        guards["another_group_entered"] = po.brief(error, 60)
    other.entered, other.tab_open = "precision", "Speed"
    po.Panel.click_tab(other, "Quality", seen[3])
    guards["other_tab_to_quality"] = other.entered
    po.Panel.click_tab(other, "Quality", seen[3])
    guards["quality_again"] = other.entered
    other.entered = "precision"  # a group entered while Quality is the open tab
    po.Panel.click_tab(other, "Quality", seen[3])
    guards["quality_once_more"] = other.entered
    po.Panel.click_tab(other, "Strength", seen[3])
    guards["quality_to_strength"] = other.entered
    try:
        other.find_row(seen[3], "Precision", hole)
        guards["after_the_tab_change"] = "row taken"
    except RuntimeError as error:
        guards["after_the_tab_change"] = po.brief(error, 60)

    # 050208 and 050552 through scroll_to: found at once under their titles, nothing entered
    kept = {}
    for name, group, labels in (("case-050208-op0-find-page-full-scroll-4", "Walls and surfaces",
                                 ["Top surface flow ratio", "Top surface flow"]),
                                ("case-050552-op1-find-page-full", "Line width",
                                 ["Outer wall line width", "^Outer wall"])):
        one, pressed_one = replay(name), []
        one.knob_at, one.find_scroll_buttons, one.scroll_top = (lambda: 0), (lambda: {"down": [0], "up": 1}), (
            lambda button, limit=30: {"presses": 0})
        one.press_scroll = lambda index, times=1, pause=0.45: pressed_one.append(index)
        theirs = one.scroll_to(group, labels, "kept", "kept")
        kept[name] = {"row_y": theirs["steps"][-1].get("row_y"), "pages_read": len(theirs["steps"]),
                      "presses": len(pressed_one), "by_group_entered": theirs.get("row_by_group_entered", False),
                      "match": {k: one.last_match[k] for k in ("label", "level", "row", "group_by")}}
    out["step11_chain"] = {"stop": stop, "presses": len(presses), "titles_at_the_stop": at_stop,
                           "trail": trail, "taken_after_the_chain": taken, "op0_find": first,
                           "op0_set_float_locate": second, "op0_edit_offline": edit, "guards": guards}
    out["step11_kept"] = kept
    check("step 11, op0 whole: param_case.locate runs one chain (4 pages read: 051203's three and "
          "the page one press on; 3 presses) and names 'X-Y hole compensation' at y 725",
          label == "X-Y hole compensation" and first["y"] == 725 and first["presses"] == 3
          and first["pages_read"] == 4 and first["group_by"] == "entered"
          and first["chain"] == [("scrolled", True)])
    check("step 11, op0 whole: the locate set_float does itself reads the row on the page as it is, "
          "no chain, after a click on the tab that is already open",
          second == {"y": 725, "scroll_reads": 0, "tag": "float-page", "group_by": "entered"})
    out["step12_op0"] = {"clicks": clicks, "stopped": edit}  # the first: the tab, already open
    check("step 12, op0 whole: the op no longer refuses the row that paints no number - it clicks the "
          "value cell on the row's line at the page's value column and stops only where the AX tree "
          "begins (not replayed offline)",
          clicks[-1:] == [[253, 733]] and edit == "RuntimeError: offline: no AX tree")
    check("step 11 guards: a group other than the wanted one entered, or another tab opened, leaves "
          "the row refused; a click on the tab that is already open keeps the state",
          guards["another_group_entered"].startswith("RuntimeError: Group title")
          and guards["other_tab_to_quality"] is None and guards["quality_again"] is None
          and guards["quality_once_more"] == "precision" and guards["quality_to_strength"] is None
          and guards["after_the_tab_change"].startswith("RuntimeError: Group title"))
    check("050208 scroll-4 replayed through scroll_to: the row 'Top surface flow ratio' y 945 is found "
          "at once under its title, one page read, no press, nothing by an entered group (unchanged)",
          kept["case-050208-op0-find-page-full-scroll-4"] == {
              "row_y": 945, "pages_read": 1, "presses": 0, "by_group_entered": False,
              "match": {"label": "Top surface flow ratio", "level": "exact",
                        "row": "Top surface flow ratio", "group_by": "title"}})
    check("050552 page-full replayed through scroll_to: the row 'Outer wall' y 897 is found at once "
          "under 'Line width' by '^Outer wall' (the row text is exactly 'Outer wall': exact), one page "
          "read, no press (unchanged)",
          kept["case-050552-op1-find-page-full"] == {
              "row_y": 897, "pages_read": 1, "presses": 0, "by_group_entered": False,
              "match": {"label": "^Outer wall", "level": "exact", "row": "Outer wall", "group_by": "title"}})

    # --- step 12: the value cell by the row's label, where the row paints no number ---
    own = replay("case-063651-op0-float-page")
    own.entered = po.norm("Precision")  # the state run 063651 was in (its chain had gone through the title)
    seen_own = own.read("x")
    own_row = own.find_row(seen_own, "Precision", hole)
    gx, gy, own_numbered, own_by = po.float_cell(own, seen_own, own_row)
    own_line = [(t["text"], int(t["x"])) for t in own.line_values(seen_own, own_row)]
    columns = sorted({int(t["x"]) for r in own.page_rows(seen_own) for t in po.numbered(own.line_values(seen_own, r))
                      if t["x"] >= po.VALUE_X - 20})
    bare_rows = [r for r in seen_own if r["text"] != "0.15"]  # the page paints no number at all
    bare = fake_panel(bare_rows)
    bare.entered = po.norm("Precision")
    bare_row = bare.find_row(bare_rows, "Precision", hole)
    bare_cell = po.float_cell(bare, bare_rows, bare_row)
    painted = fake_panel(quality_page())
    painted_rows = quality_page()  # the row 'Layer height' (y 136) and its value '0.2' (x 330)
    painted_cell = po.float_cell(painted, painted_rows, painted_rows[2])
    out["step12_value_cell"] = {"run_063651": {"row": [own_row["text"], int(own_row["y"])], "line": own_line,
                                               "click": [round(gx), round(gy)], "by": own_by,
                                               "number_columns": columns},
                                "no_number_on_the_page": [round(bare_cell[0]), round(bare_cell[1]), bare_cell[3]],
                                "number_on_the_row": [round(painted_cell[0]), painted_cell[3]]}
    check("step 12, run 063651's own page: the row 'X-Y hole compensation' (y 725) is found by its label "
          "in the group entered and its line carries only 'mm' - no numbered token",
          own_row["text"] == "X-Y hole compensation" and int(own_row["y"]) == 725 and own_line == [("mm", 336)]
          and own_numbered == [] and own.last_match["group_by"] == "entered")
    check("step 12: that row's value cell is clicked on its line (y 733 = 725 + 16 / 2) at x 253 - the "
          "left edge (250) of the number the page paints elsewhere ('0.15'), where a readable number "
          "on this row would have been clicked",
          [round(gx), round(gy), own_by] == [253, 733, "column"] and columns == [250])
    # step 12, the rerun of uia_param_wall_thin (run 074033): an op without a group crashed in
    # find_row - `by` was set inside `if group:` only (3117e51); no case without a group had run on it
    whole = fake_panel(seen_own)
    whole_row = whole.find_row(seen_own, None, "X-Y hole compensation")
    out["step12_no_group"] = {"row": whole_row["text"], "y": int(whole_row["y"]),
                              "group_by": whole.last_match["group_by"]}
    check("step 12: an op without a group (uia_param_wall_thin's 'Wall loops') is found on the whole page "
          "and its match names group_by 'page' - run 074033 crashed here (UnboundLocalError: by)",
          whole_row["text"] == "X-Y hole compensation" and int(whole_row["y"]) == 725
          and whole.last_match["group_by"] == "page")
    check("step 12 guards: a page that paints no number at all falls back to VALUE_X (x 256, 'VALUE_X'); "
          "a row that paints its number is clicked 3 px right of it as before ('token', x 333)",
          [round(bare_cell[0]), round(bare_cell[1]), bare_cell[3]] == [256, 733, "VALUE_X"]
          and [round(painted_cell[0]), painted_cell[3]] == [333, "token"])
    # step 13, run 075830 (uia_param_first_speeds, op0): OCR read the row 'First layer' as
    # 'Firstlayer'. On the code before step 13 no level took that row, and the prefix hit of
    # '^First layer' on 'First layer infill' (value 55) took it - 30 was written there and saved
    first = replay("case-075830-op0-find-page")
    first_rows = first.read("x")
    first_row = first.find_row(first_rows, "First layer speed", ["^First layer 35", "^First layer"])
    first_match = {k: first.last_match[k] for k in ("label", "level", "row", "group_by")}
    first_hits = {c["label"]: c["hits"] for c in first.last_match["candidates"]}
    first_numbered = [t["text"] for t in po.numbered(first.line_values(first_rows, first_row))]
    spaced_rows = [{**r, "text": "First layer"} if r["text"] == "Firstlayer" else r for r in first_rows]
    spaced = replay("case-075830-op0-find-page")  # the same page with the space read
    spaced.read = lambda tag, full=False: spaced_rows
    spaced_row = spaced.find_row(spaced_rows, "First layer speed", ["^First layer 35", "^First layer"])
    off_by_one = replay("case-075830-op0-find-page")
    refused = None
    try:
        off_by_one.find_row(first_rows, "First layer speed", ["^First layer 30", "^First laye"])
    except RuntimeError as error:
        refused = po.brief(error, 200)
    out["step13_nospace"] = {"run_075830": first_match, "numbered_on_the_row": first_numbered,
                             "hits": first_hits, "row_read_with_its_space": spaced_row["text"],
                             "level_then": spaced.last_match["level"], "off_by_one": refused}
    check("step 13, run 075830's own page: op0 of uia_param_first_speeds takes the row OCR reads "
          "'Firstlayer' (its value 35) by '^First layer' at level 'nospace' in the group "
          "'First layer speed' - not 'First layer infill' (55), the prefix hit that took it on the GUI",
          first_match == {"label": "^First layer", "level": "nospace", "row": "Firstlayer",
                          "group_by": "title"} and int(first_row["y"]) == 751 and first_numbered == ["35"]
          and first_hits["^First layer 35"] == [])
    check("step 13 guards: the same page read with its space takes the row at 'exact'; '^First layer' "
          "still lists 'First layer infill' as its prefix hit and loses to nospace; a label that is "
          "not the row's letters ('^First laye') is refused - nospace forgives spaces only",
          spaced_row["text"] == "First layer" and spaced.last_match["level"] == "exact"
          and first_hits["^First layer"] == [{"level": "nospace", "row": "Firstlayer"},
                                             {"level": "prefix", "row": "First layer infill"}]
          and refused is not None and "not visible" in refused)
    # step 14, run 080428 (uia_param_feature_speeds, op 4): the label 'Small perimeters threshold'
    # is painted over two lines (757 and 773) and its value box, spanning both, paints no number.
    # On the code before step 14 only 'threshold' hit the second line; the click at its middle
    # (782, the box's bottom edge) opened nothing on the row, and the next row's editor had the
    # nearer top. The page is read with its group title above it: the run's scroll chain had
    # entered the group.
    def on_wrapped_page():
        panel = replay("case-080428-op4-float-page")
        panel.entered = "other layers speed"
        return panel, panel.read("x")

    both, both_rows = on_wrapped_page()
    op4 = both.find_row(both_rows, "Other layers speed", ["^Small perimeters threshold", "threshold"])
    op4_match = {k: both.last_match[k] for k in ("label", "level", "row", "group_by")}
    op4_hits = {c["label"]: [(h["level"], h["row"]) for h in c["hits"]] for c in both.last_match["candidates"]}
    op4_values = [t["text"] for t in po.numbered(both.line_values(both_rows, op4))]
    whole, whole_rows = on_wrapped_page()
    op4_edit = whole.find_row(whole_rows, "Other layers speed", "Small perimeters threshold")  # the edit's own locate
    op4_cell = po.float_cell(whole, whole_rows, op4_edit)
    speed, speed_rows = on_wrapped_page()
    op5 = speed.find_row(speed_rows, "Other layers speed", "^Small perimeters")
    op5_values = [t["text"] for t in speed.line_values(speed_rows, op5)]  # the number and its unit
    op5_numbered = [t["text"] for t in po.numbered(speed.line_values(speed_rows, op5))]
    tail, tail_rows = on_wrapped_page()
    tail_row = tail.find_row(tail_rows, "Other layers speed", "threshold")
    out["step14_wrapped"] = {"op4": op4_match, "hits": op4_hits, "box": {k: round(op4[k]) for k in ("x", "y", "w", "h")},
                             "lines": op4.get("lines"), "numbered_on_the_row": op4_values,
                             "edit_locate_level": whole.last_match["level"], "click": [round(op4_cell[0]), round(op4_cell[1]), op4_cell[3]],
                             "op5": {"row": op5["text"], "y": int(op5["y"]), "h": int(op5["h"]), "wrapped": op5.get("wrapped"),
                                     "values": op5_values, "numbered": op5_numbered},
                             "tail_alone": {"y": int(tail_row["y"]), "h": int(tail_row["h"]), "wrapped": tail_row.get("wrapped")}}
    check("step 14, run 080428's own page: op4 of uia_param_feature_speeds takes 'Small perimeters "
          "threshold' as one row of both its lines (y 757, h 34; 'threshold' at exact, the whole "
          "label at wrapped), paints no number on it, and the edit's own locate with the whole label "
          "reads it back at 'wrapped' and clicks the box's middle (y 774, x 256 by VALUE_X)",
          op4_match == {"label": "threshold", "level": "exact", "row": "Small perimeters threshold", "group_by": "entered"}
          and {k: round(op4[k]) for k in ("x", "y", "w", "h")} == {"x": 28, "y": 757, "w": 110, "h": 34}
          and op4.get("lines") == ["Small perimeters", "threshold"] and op4_values == []
          and op4_hits["^Small perimeters threshold"] == [("wrapped", "Small perimeters threshold")]
          and op4_hits["threshold"] == [("exact", "threshold")]
          and whole.last_match["level"] == "wrapped"
          and [round(op4_cell[0]), round(op4_cell[1]), op4_cell[3]] == [256, 774, "VALUE_X"])
    check("step 14 guards: op5's '^Small perimeters' still takes the speed row above (y 729, h 18, "
          "'50%' and 'mm/s or %'), not the wrapped label's first line, and is not widened; 'threshold' "
          "alone stays its own second line - a row is widened only when its lines join into one of "
          "the op's own label candidates",
          op5["text"] == "Small perimeters" and int(op5["y"]) == 729 and int(op5["h"]) == 18
          and op5.get("wrapped") is None and op5_values == ["50%", "mm/s or %"] and op5_numbered == ["50%"]
          and tail_row["text"] == "threshold" and int(tail_row["y"]) == 773 and int(tail_row["h"]) == 18
          and tail_row.get("wrapped") is None)
    # the hand-off of param_case.locate (run 144419 stopped at op 4 on it: the whole label was
    # read from a key the readback does not have)
    hand, hand_rows = on_wrapped_page()
    hand.locate_row = lambda tab, group, label, prefix: (hand_rows, hand.find_row(hand_rows, group, label),
                                                         [], prefix + "-page")
    op4_handed, op4_found, _ = pc.locate(hand, {"op": "float", "group": "Other layers speed", "value": "10",
                                                "label": ["^Small perimeters threshold", "threshold"]}, "Speed")
    op5_handed, op5_found, _ = pc.locate(hand, {"op": "float", "group": "Other layers speed", "value": "50",
                                                "label": "^Small perimeters"}, "Speed")
    out["step14_wrapped"]["handed"] = [op4_handed, op5_handed]
    check("step 14, param_case.locate hands the edit the whole label ('Small perimeters threshold'; the row "
          "read back as wrapped, both its lines) and op5's '^Small perimeters' as itself",
          op4_handed == "Small perimeters threshold" and op4_found["readback"]["wrapped"] is True
          and op4_found["readback"]["lines"] == ["Small perimeters", "threshold"]
          and op5_handed == "^Small perimeters" and op5_found["readback"]["wrapped"] is False)
    # --- step 15: a combo op names no label. Its row is the one painting op['current'], found by
    # find_combo while op_find_row's chain runs, and that row's label is what pick_combo then
    # locates. Run 152849 (uia_param_skirt, op 3, PASS) read 'Draft shield' painting '~ Disabled';
    # run 152406 (uia_param_ironing_top, op 0) 'Ironing type' painting '~ No ironing'; run 022226's
    # proven Print sequence page paints '~ By layer'. The pick itself (the click, the popup, the
    # painted readback) is the GUI run's to judge: not replayed here.
    def combo_page(name, entered):
        panel = replay(name)
        panel.entered = entered
        return panel, panel.read("x")

    def refusal(what):
        try:
            return None, what()
        except RuntimeError as error:
            return po.brief(error, 220), None

    def combo(current, tab, group, target="Enabled"):
        return {"op": "combo", "tab": tab, "tab_hint": "x", "group": group, "current": current, "target": target}

    paints = lambda text: [token(250, 774, 70, 18, text)]
    words = {"a string inside the painted text": pc.paints(paints("~ By layer"), "By layer"),
             "one word of it": pc.paints(paints("~ By layer"), "layer"),
             "another value": pc.paints(paints("~ By layer"), "object"),
             "the other glyph": pc.paints(paints("v By object"), "By object"),
             "a list, as painted": pc.paints(paints("~ No ironing"), ["No", "ironing"]),
             "a list, any case": pc.paints(paints("~ By layer"), ["by", "LAYER"]),
             "a list over two tokens": pc.paints([token(0, 0, 20, 14, "No"), token(30, 0, 60, 14, "ironing")],
                                                 ["No", "ironing"]),
             "a run inside the value": pc.paints(paints("~ No ironing"), ["ironing"]),
             "not a run of whole words": pc.paints(paints("~ No ironing"), ["No", "iron"]),
             "another order": pc.paints(paints("~ By layer"), ["Layer", "By"]),
             "nothing painted": pc.paints([], "By layer"),
             "no current": pc.paints(paints("~ By layer"), "")}
    out["step15_paints"] = words
    check("step 15, paints: a combo op's `current` is read as the Windows engine reads a choice's value - "
          "a string inside the painted text, a list a run of whole words - behind the one dropdown "
          "glyph OCR glues in front; another value, another order, half a word, nothing painted and no "
          "current are no hit",
          [k for k, ok in words.items() if ok] == ["a string inside the painted text", "one word of it",
                                                   "the other glyph", "a list, as painted", "a list, any case",
                                                   "a list over two tokens", "a run inside the value"])
    skirt, _ = combo_page("case-152849-op3-combo-page", "skirt")
    skirt_label, skirt_found = pc.locate_combo(skirt, combo("Disabled", "Others", "Skirt"), "Others")
    iron, iron_rows = combo_page("case-152406-op0-combo-page", "ironing")
    iron_op = combo(["No", "ironing"], "Quality", "Ironing", "Topmost")
    iron_label, iron_found = pc.locate_combo(iron, iron_op, "Quality")

    def no_chain(page):  # a refusal goes on to the scroll chains: counted, not simulated
        def start(group, label, tag, why, budget=None):
            page.scroll_chains.append(tag)
            raise RuntimeError("scroll chain is not simulated offline")
        page.scroll_to = start
    sequence, _ = combo_page("pick_combo-022226-combo-page", None)
    sequence_label, sequence_found = pc.locate_combo(sequence, combo("By layer", "Others", "Special mode", "By object"),
                                                     "Others")
    painting = [r["text"] for r in iron_rows if pc.paints(iron.line_values(iron_rows, r), ["No", "ironing"])]
    for page in (iron, sequence):  # the refusals below are asked of these two pages
        no_chain(page)
    # the hand-off: pick_combo's own locate, by the label handed to it, is the Panel's find_row again
    # and lands on the same row with its value token in place (the head of op_pick_combo)
    hand_rows, hand_row, _, _ = iron.locate_row("Quality", "Ironing", iron_label, "combo")
    handed = {"label": iron_label, "row": hand_row["text"], "level": iron.last_match["level"],
              "values": [t["text"] for t in iron.line_values(hand_rows, hand_row)],
              "own_find_row_back": all("find_row" not in p.__dict__ for p in (skirt, iron, sequence))}
    out["step15_combo"] = {
        "skirt": {"label": skirt_label, "row": skirt_found["readback"]["label"],
                  "value_text": skirt_found["readback"]["value_text"],
                  "level": skirt_found["readback"]["match"]["level"],
                  "group_by": skirt_found["readback"]["match"]["group_by"]},
        "ironing": {"label": iron_label, "row": iron_found["readback"]["label"],
                    "value_text": iron_found["readback"]["value_text"],
                    "level": iron_found["readback"]["match"]["level"],
                    "group_by": iron_found["readback"]["match"]["group_by"], "rows_painting_it": painting,
                    "handed": handed},
        "print_sequence": {"label": sequence_label, "row": sequence_found["readback"]["label"],
                           "value_text": sequence_found["readback"]["value_text"],
                           "group_by": sequence_found["readback"]["match"]["group_by"]},
        "refused": {"'Disabled' on the Ironing page": refusal(lambda: pc.locate_combo(iron, {**iron_op, "current": "Disabled"}, "Quality"))[0],
                    "'By object' on the Special mode page": refusal(lambda: pc.locate_combo(sequence, combo("By object", "Others", "Special mode"), "Others"))[0],
                    "the hit in another group, find_combo": refusal(lambda: pc.find_combo(iron, iron_rows, "Wall generator", ["No", "ironing"]))[0],
                    "the hit in another group, whole locate": refusal(lambda: pc.locate_combo(iron, {**iron_op, "group": "Wall generator"}, "Quality"))[0],
                    "scroll chains started": [len(p.scroll_chains) for p in (iron, sequence)]},
        # the primitive's own proof, recorded for the step that decides on it (not judged here)
        "pick_combo_proof": {"'~ Enabled' for 'Enabled'": po.painted_is("~ Enabled", "Enabled"),
                             "'5 ~Enabled' for 'Enabled' (run 152849's own readback)": po.painted_is("5 ~Enabled", "Enabled"),
                             "'~ Topmost surface only' for 'Topmost'": po.painted_is("~ Topmost surface only", "Topmost")}}
    check("step 15, run 152849's own page (uia_param_skirt, op 3): the combo is located by the value it "
          "paints - 'Disabled' - and the row handed on is 'Draft shield' (exact, by its group's title, "
          "the row painting '~ Disabled')",
          skirt_label == "Draft shield" and out["step15_combo"]["skirt"]["row"] == "Draft shield"
          and out["step15_combo"]["skirt"]["value_text"] == "~ Disabled"
          and out["step15_combo"]["skirt"]["level"] == "exact"
          and out["step15_combo"]["skirt"]["group_by"] == "title")
    check("step 15, run 152406's own page (uia_param_ironing_top, op 0): 'No ironing' (a list) takes "
          "'Ironing type', the one row painting it, exact, as a row of the group whose title is above "
          "the page; pick_combo's own locate then finds that label on the same row, its value '~ No "
          "ironing' in place, and the Panel's find_row is back on every page",
          painting == ["Ironing type"] and iron_label == "Ironing type"
          and out["step15_combo"]["ironing"]["row"] == "Ironing type"
          and out["step15_combo"]["ironing"]["value_text"] == "~ No ironing"
          and out["step15_combo"]["ironing"]["level"] == "exact"
          and out["step15_combo"]["ironing"]["group_by"] == "entered"
          and handed == {"label": "Ironing type", "row": "Ironing type", "level": "exact",
                         "values": ["~ No ironing"], "own_find_row_back": True})
    check("step 15, run 022226's proven page: a string `current` ('By layer') takes 'Print sequence', "
          "which paints '~ By layer'",
          sequence_label == "Print sequence" and out["step15_combo"]["print_sequence"]["row"] == "Print sequence"
          and out["step15_combo"]["print_sequence"]["value_text"] == "~ By layer")
    check("step 15 refusals: a value no row paints ('Disabled' on the Ironing page) is refused with the "
          "value, the tab and the group named, after the locate went on to its scroll chain",
          "No choice painting 'Disabled' found in tab 'Quality', group 'Ironing': " in (
              out["step15_combo"]["refused"]["'Disabled' on the Ironing page"] or "")
          and "No choice painting 'By object' found in tab 'Others', group 'Special mode'" in (
              out["step15_combo"]["refused"]["'By object' on the Special mode page"] or "")
          and len(iron.scroll_chains) >= 1 and len(sequence.scroll_chains) >= 1)
    check("step 15 refusal: a row that paints the value but is outside the op's group is not handed on "
          "- find_combo refuses it in the Panel's find_row's own words ('Ironing type' asked of 'Wall "
          "generator') and so does the whole locate",
          "not visible in group 'Wall generator'" in (out["step15_combo"]["refused"]["the hit in another group, find_combo"] or "")
          and "No choice painting ['No', 'ironing'] found in tab 'Quality', group 'Wall generator'" in (
              out["step15_combo"]["refused"]["the hit in another group, whole locate"] or ""))
    # the op limits (step 10): each op gets min(OP_FUSE, the case's time left before the save)
    now = 1_000_000.0
    at = (50, 160, 270, 381)
    sizes = [pc.op_limit(now + pc.CASE_FUSE, now + t) for t in at]
    out["op_limits"] = {"case": pc.CASE_FUSE, "per_op": pc.OP_FUSE, "save": pc.SAVE,
                        "seconds_at": dict(zip(at, sizes))}
    check("op limits: 150 s for an op that starts 50 s and 160 s into the case, 110 s at 270 s, "
          "none at 381 s (the save's 40 s kept inside the case's 420 s)",
          sizes == [150, 150, 110, -1])
    # --- step 11: 150 s per op, 420 s per case (surface_flow's op0 needs about 135 s, run 060903)
    full_until = pc.CASE_FUSE - pc.SAVE - pc.OP_FUSE  # an op started this far in still gets OP_FUSE
    edge = [pc.op_limit(now + pc.CASE_FUSE, now + t) for t in (0, full_until, full_until + 1)]
    needs = 135  # surface_flow op0: tab switch 41 + find chain 63 + set_float about 30
    fits = pc.op_limit(now + pc.CASE_FUSE, now + 5) - needs
    three = [pc.op_limit(now + pc.CASE_FUSE, now + t) for t in (0, needs, 2 * needs)]
    out["op_limits_150_420"] = {"full_op_until": full_until, "at": [0, full_until, full_until + 1],
                                "seconds": edge, "surface_flow_op0_margin": fits,
                                "three_ops_of_135_s": three}
    check("step 11 limits: 150 s per op and 420 s per case",
          pc.OP_FUSE == 150 and pc.CASE_FUSE == 420 and pc.SAVE == 40)
    check("an op gets the whole 150 s up to 230 s into the case, 149 s one second later",
          full_until == 230 and edge == [150, 150, 149])
    check("surface_flow's op0 (about 135 s by run 060903) fits its limit with 15 s to spare",
          fits == 15)
    check("three ops of 135 s each do not fit: the third starts at 270 s and gets 110 s",
          three == [150, 150, 110])
    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"ok": not failed, "checks": len(checks), "failed": failed, "out": out},
                     indent=1, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
