"""Offline simulation tests for the param-engine search logic (no GUI).

The OCR band, the wheel, the viewport and the focus reset are replaced by a
tiny fake page, so the decisions the engine makes - which row a label
resolves to, when it gives up, when it resets focus - can be asserted.

Usage: python -B tools/test_param_engine_sim.py [repo-root]   (exit 1 on any failure)

Covers the decisions that made most param scenarios fail before the r3
engine batch (2026-11-23): the API surface of the entry points, start-of-row
anchoring, group confinement, the wheel stall guard / focus reset, and
scroll_group_into_view giving up or accepting in bounded time. Run it after
every change to param_case_lib.py / process_panel.py. It proved itself by
going red 8 times on the unpatched tree while staying green on the patched one.
"""
import sys

root = sys.argv[1]
sys.path.insert(0, root)
from harness import process_panel as pp  # noqa: E402
from harness import param_case_lib as pcl  # noqa: E402

BAND = (700, 1000)          # visible options band, client y
ROW_H = 30
# The genuine functions, captured before anything is stubbed.
REAL_SGIV = pp.scroll_group_into_view
REAL_SPAN = getattr(pp, "group_span", None)
REAL_TITLE_LINE = getattr(pp, "on_title_line", None)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


# API surface: every entry point run_ops uses must exist with the expected
# parameters. Run b4d1c596 showed why: the r3 patcher dropped the
# `def uia_set_float` line, the file still compiled, and the checks below -
# which only exercise the search helpers - stayed green.
import inspect  # noqa: E402
API = {
    pcl: {"uia_set_float": ["ui", "label_substr", "value", "group_substr", "field_index", "below"],
          "_find_phrase_row": ["app", "phrase", "group_substr"],
          "run_ops": ["ui", "ops"],
          "make_verify": ["case_id", "values"]},
    pp: {"find_option_row": ["session", "label_substr", "group_substr"],
         "scroll_group_into_view": ["session", "substr", "timeout_s"],
         "set_combo_by_popup": ["session", "locate", "target_substr"],
         "set_option_checkbox": ["session", "label_substr", "want_checked"],
         # r3c (census c101c0f4 + queue18): absent on r3b and earlier.
         "on_title_line": ["session", "y", "tol"],
         "scroll_signature": ["session"],
         "park_for_popup": ["session", "rect"],
         "popup_hit_clickable": ["popup_hwnd", "x", "y"],
         "close_popup": ["session", "popup_hwnd", "combo_point"],
         "work_area": []},
}
for module, funcs in API.items():
    for fname, params in funcs.items():
        fn = getattr(module, fname, None)
        got = list(inspect.signature(fn).parameters)[:len(params)] if callable(fn) else None
        check("%s.%s exists, params %s" % (module.__name__.split(".")[-1], fname, params),
              got == params, "got %r" % (got,))
if hasattr(pp, "SCAN_NOTCHES"):
    check("scan budget covers a whole page; measured wheel step and popup room are recorded",
          pp.SCAN_NOTCHES >= 100 and pp.SCAN_SECONDS >= 60 and pp.WHEEL_STEP_PX == 60
          and pp.POPUP_ROOM >= 200,
          "notches=%r seconds=%r step=%r room=%r" % (
              pp.SCAN_NOTCHES, pp.SCAN_SECONDS, pp.WHEEL_STEP_PX, pp.POPUP_ROOM))


# (check() is defined at the top, before the API-surface block)


# ---------------------------------------------------------------- fake page
class Page:
    def __init__(self, rows, spans, dead=False, revive_works=True, titles=None,
                 row_h=ROW_H):
        self.rows = rows            # [(text, page_y)]
        self.spans = spans          # group -> (y_top, y_bottom) page coords
        self.offset = 0
        self.dead = dead
        self.revive_works = revive_works
        self.row_h = row_h          # px per wheel notch (60 on the real page)
        # [(title, page_y_top, height)] - stand-ins for the title WINDOWS:
        # their y moves with the page, which is what the engine reads.
        self.titles = titles if titles is not None else [("Group", 600, 18)]
        self.wheels = 0
        self.focus_resets = 0

    def band(self):
        out = []
        for text, y in self.rows:
            sy = y - self.offset
            if not (BAND[0] - 5 <= sy <= BAND[1] - 5):
                continue
            x = 30
            for w in text.split(" "):
                out.append((w, x, sy, 9 * len(w) + 4, 12))
                x += 9 * len(w) + 8
        return out

    def on_title(self, y):
        """Is client y on a group-title line (like pp.on_title_line)?"""
        return any(top - self.offset - 3 <= y <= top + height - self.offset + 3
                   for _t, top, height in self.titles)

    def live_span(self, sub):
        """(y_top, y_bottom) of the group in client coords, from the title
        windows' CURRENT position (what pp.group_span reads on the page)."""
        for i, (t, top, height) in enumerate(self.titles):
            if sub.lower() in t.lower():
                nxt = self.titles[i + 1][1] if i + 1 < len(self.titles) else top + 4000
                return (top + height - self.offset, nxt - self.offset)
        return None

    def wheel(self, _session, _vp, notches, delta=-120):
        self.wheels += 1
        if self.dead:
            return
        # delta -120 = wheel DOWN = the content moves UP = the offset grows
        step = self.row_h * notches * (-1 if delta > 0 else 1)
        self.offset = max(0, self.offset + step)

    def focus_reset(self, _session, why=""):
        self.focus_resets += 1
        if self.revive_works:
            self.dead = False


def install(page):
    pp.ocr_band = lambda session, y0=None, y1=None, psm=3: page.band()
    pp.options_viewport = lambda session: ((0, BAND[0], 420, BAND[1]), 4321)
    pp.wheel_viewport = page.wheel
    pp.focus_off_edit = page.focus_reset
    pp.group_span = lambda session, sub: page.spans.get(sub)
    pp.scroll_group_into_view = lambda session, sub, timeout_s=420.0: (
        (0, 0, 0) if sub in page.spans else None)
    pp.on_title_line = lambda session, y, tol=3: page.on_title(y)
    pp.scroll_signature = lambda session: tuple(
        (t, top - page.offset) for t, top, _h in page.titles)


# ------------------------------------------------------------- pure helpers
# Only the patched engine has these; on an unpatched tree they are N/A.
words = [("Role", 30, 900, 30, 12), ("based", 70, 900, 38, 12), ("wipe", 120, 900, 28, 12),
         ("speed", 160, 900, 40, 12), ("Wipe", 30, 930, 30, 12), ("speed", 70, 930, 40, 12),
         ("80%", 250, 930, 24, 12)]
if hasattr(pp, "leftmost_on_line"):
    check("leftmost_on_line: row-start word", pp.leftmost_on_line(words, 4))
    check("leftmost_on_line: mid-row word", not pp.leftmost_on_line(words, 2))
    check("leftmost_on_line: second word", not pp.leftmost_on_line(words, 5))

    hits = pp.popup_line_hits([("By", 10, 50, 20, 10), ("Layer", 34, 50, 36, 10),
                               ("By", 10, 80, 20, 10), ("Object", 34, 80, 40, 10)], "by object")
    check("popup_line_hits: two-word target on its line", len(hits) == 1 and abs(hits[0][1] - 85) <= 2, repr(hits))
    check("popup_line_hits: no hit when only the other row exists",
          pp.popup_line_hits([("By", 10, 50, 20, 10), ("Layer", 34, 50, 36, 10)], "By Object") == [])
else:
    print("N/A  new helpers (leftmost_on_line / popup_line_hits) absent on this tree")

# 1. '^' keeps a label off the previous row (run 13613ac7).
page = Page([("Role based wipe speed", 900), ("Wipe speed 80%", 930)], {"Seam": (880, 1000)})
install(page)
anchored = pcl._find_phrase_row(None, "^Wipe speed", "Seam")
page2 = Page([("Role based wipe speed", 900), ("Wipe speed 80%", 930)], {"Seam": (880, 1000)})
install(page2)
loose = pcl._find_phrase_row(None, "Wipe speed", "Seam")
check("'^Wipe speed' resolves to the value row (y=936)", anchored == 936, "got %r" % anchored)
check("plain 'Wipe speed' resolves to the checkbox row above (the old bug)", loose == 906, "got %r" % loose)

# 2. With a group, only that group's row counts (run f0e683fb screenshot).
spans = {"Other layers speed": (480, 880), "Acceleration": (880, 1100), "Jerk(XY)": (1100, 1300)}
page = Page([("Outer wall 120", 500), ("Outer wall 5000", 900), ("Outer wall 9", 1200)], spans)
install(page)
y = pcl._find_phrase_row(None, "^Outer wall", "Acceleration")
check("'^Outer wall' in Acceleration -> that group's row (y=906)", y == 906, "got %r" % y)
page = Page([("Travel 500", 500), ("Travel 10000", 900)], {"Travel speed": (480, 880), "Acceleration": (880, 1100)})
install(page)
y = pcl._find_phrase_row(None, "^Travel", "Acceleration")
check("'^Travel' in Acceleration skips 'Travel speed' above (y=906)", y == 906, "got %r" % y)
# find_option_row matches inside ONE word, so the same check with a
# single-word label and both rows visible at once.
page = Page([("Travel 500", 750), ("Travel 10000", 900)],
            {"Travel speed": (700, 800), "Acceleration": (880, 1100)})
install(page)
y = pp.find_option_row(None, "Travel", "Acceleration")[1]
check("find_option_row: 'Travel' in Acceleration skips the visible row above (y=906)", y == 906, "got %r" % y)

# 3. Dead wheel: the scan notices, resets focus, and still finds the row
#    (runs 99a53a80 / f149c3da).
page = Page([("First layer speed 35", 700), ("Travel 12", 1100)], {"Acceleration": (900, 1300)}, dead=True)
install(page)
y = pcl._find_phrase_row(None, "^Travel", "Acceleration")
check("dead wheel -> focus reset -> row found", y is not None and page.focus_resets >= 1,
      "y=%r resets=%d wheels=%d" % (y, page.focus_resets, page.wheels))

# 4. Page end with a wheel that stays dead: stop early instead of 38 blind
#    notches.
page = Page([("Only row 1", 700), ("Only row 2", 730)], {}, dead=True, revive_works=False)
install(page)
y = pcl._find_phrase_row(None, "^Absent", None)
check("dead wheel + absent label -> None, and far fewer than 38 wheels",
      y is None and page.wheels < 20 and page.focus_resets == 4,
      "y=%r wheels=%d resets=%d" % (y, page.wheels, page.focus_resets))

# 5. scroll_group_into_view gives up on a title that does not exist (#263).
# Call the REAL function: install() has replaced the module attribute with a
# stub, and calling that stub is how this check first "passed" without
# testing anything.
page = Page([("x", 700)], {})
install(page)
_real = (pp.group_title, pp.time.sleep, pp.frect, pp.neutralize_focus)
# The unpatched engine calls neutralize_focus straight from
# scroll_group_into_view; with a fake session it would raise before the
# later sections ever run - stub it so the RED proof reaches them too.
pp.neutralize_focus = lambda session: True
pp.time.sleep = lambda s: None
pp.frect = lambda session: (0, 0, 0, 0)
pp.group_title = lambda session, sub: None
try:
    # A short deadline keeps an unpatched tree (which wheels until the
    # deadline) from spinning for the full 420s inside this test.
    hit = REAL_SGIV(None, "Bridge", timeout_s=3.0)
    wheels_missing = page.wheels
    # positive control: an existing title already sitting inside the visible
    # band (bottom at 720, band 700..1000) is returned without any wheel, so
    # the fast path for real groups is intact.
    pp.group_title = lambda session, sub: ((0, 0, 400, 720), 77) if sub == "Seam" else None
    pp.view_band = lambda session: BAND
    hit2 = REAL_SGIV(None, "Seam", timeout_s=3.0)
    wheels_present = page.wheels - wheels_missing
finally:
    pp.group_title, pp.time.sleep, pp.frect, pp.neutralize_focus = _real
check("scroll_group_into_view: missing title -> None after exactly 16 bursts",
      hit is None and wheels_missing == 16, "hit=%r wheels=%d" % (hit, wheels_missing))
check("scroll_group_into_view: existing title in band -> returned, no wheel",
      hit2 == ((0, 0, 400, 720), 77) and wheels_present == 0, "hit2=%r wheels=%d" % (hit2, wheels_present))

# 6. The FIRST group of a page sits at the page top with its title just
#    above the visible band (run 0b7886bc: #270 looked wedged on every run
#    because the title could never enter the band and each op wheeled for
#    2 x 420s). The wheel is alive but the page cannot scroll further up.
#    The wheel precedes the stuck check in each loop, so acceptance comes
#    on the 7th notch (~5s), versus 840s before.
page = Page([("First layer speed 35", 700), ("First layer 55", 730)], {})
install(page)
wheels_before = page.wheels
pp.time.sleep = lambda s: None
pp.frect = lambda session: (0, 0, 0, 0)
pp.neutralize_focus = lambda session: True  # again: the base engine reaches it from here
pp.group_title = lambda session, sub: ((0, 0, 400, 690), 99) if sub == "Initial layer" else None
pp.view_band = lambda session: BAND
try:
    hit3 = REAL_SGIV(None, "Initial layer", timeout_s=60.0)
    wheels_top = page.wheels - wheels_before
finally:
    pp.group_title, pp.time.sleep, pp.frect, pp.neutralize_focus = _real
check("scroll_group_into_view: first group's title stuck above the band -> accepted quickly",
      hit3 == ((0, 0, 400, 690), 99) and 0 < wheels_top <= 8, "hit3=%r wheels=%d" % (hit3, wheels_top))

# 7. focus_info is a REAL Win32 call - nothing here is stubbed. Python 3.11
#    has no ctypes.wintypes.GUITHREADINFO: run 7834c486 died on that the
#    first time the stall guard reset the focus, and the previous revision
#    of this test had stubbed the reset, so it stayed green.
import ctypes  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
if hasattr(pp, "_GUITHREADINFO"):
    check("GUITHREADINFO struct is 72 bytes on 64-bit", ctypes.sizeof(pp._GUITHREADINFO) == 72,
          "got %d" % ctypes.sizeof(pp._GUITHREADINFO))
    try:
        info = pp.focus_info(types.SimpleNamespace(hwnd=pp.user32.GetForegroundWindow(), pid=0))
        ok, detail = isinstance(info, tuple) and len(info) == 2, "foreground -> %r" % (info,)
    except Exception as exc:  # the guest raised exactly this way
        ok, detail = False, "raised %s: %s" % (type(exc).__name__, exc)
    check("focus_info makes the real GetGUIThreadInfo call without raising", ok, detail)
else:
    print("N/A  focus_info (absent on this tree)")

# 8. topbar_util._topbar must ignore descendants scrolled ABOVE the frame.
#    _children() enumerates every descendant; rows that moved above the
#    options viewport keep windows above the frame, and taking the global
#    minimum of all tops made the toolbar "vanish" - the whole
#    file_toolbar_missing family (every case whose edit sits deep down a
#    page: run 33d875d3, and before it bridge / jerk / tree supports).
from harness import topbar_util as tb  # noqa: E402
FRAME = (100, 200, 1400, 1100)
TOOLBAR = ("", (100, 200, 1400, 232), 111, "BBLTopbar")
TABS = ("", (100, 240, 900, 275), 222, "wxWindowNR")
ROWS_ABOVE = [("", (120, 200 - 500 + 30 * i, 400, 200 - 500 + 30 * i + 24), 900 + i, "Edit")
              for i in range(8)]
_real_children, _real_rect = tb._children, tb.user32.GetWindowRect


def _topbar_with(children):
    tb._children = lambda parent, _c=children: list(_c)

    def _rect(_h, rc):
        rc._obj.left, rc._obj.top, rc._obj.right, rc._obj.bottom = FRAME
        return 1

    tb.user32.GetWindowRect = _rect
    try:
        return tb._topbar(1)
    finally:
        tb._children, tb.user32.GetWindowRect = _real_children, _real_rect


hit = _topbar_with([TOOLBAR, TABS])
check("_topbar: page at top -> toolbar found", hit == TOOLBAR[:3], "got %r" % (hit,))
hit = _topbar_with(ROWS_ABOVE + [TOOLBAR, TABS])
check("_topbar: rows scrolled above the frame -> toolbar still found", hit == TOOLBAR[:3], "got %r" % (hit,))

# ------------------------------------------------------------------ r3c
# Everything below comes from queue18 (10 scenarios, 1 SHADOW, 9 NON_GREEN
# on the r3b engine) and the census run c101c0f4 that explained it.

# 9. group_titles(): ONLY real group titles (393 wide at x 13, 18 high).
#    The unit labels ('mm/s', 120 wide at x 203) are titled windows too and
#    counted as 'the next title' - group_span() then shrank to the ~10px
#    between a group's title and its first unit label, and every row but the
#    first was rejected as 'a neighbouring group' (accelerations op 2+,
#    seam_wipe 'Wipe speed', overhang_bridge). A title scrolled above the
#    Process row must still be found when it belongs to the options
#    viewport: after an edit commit the page lands anywhere, and the title
#    being invisible made scroll_group_into_view wheel AWAY from it
#    (feature_speeds op 3: 68 notches, 'no such group title').
if hasattr(pp, "group_titles"):
    FRAME = (0, 0, 1920, 1046)   # frame-relative == screen in this fake
    KIDS = [
        ("panel", "wxWindowNR", (8, 725, 428, 1038), 5, 16, 732),          # the viewport
        ("First layer speed", "wxWindowNR", (20, 300, 413, 318), 10, 33, 307),  # title, scrolled up
        ("mm/s", "wxWindowNR", (210, 328, 330, 354), 12, 223, 335),        # unit label
        ("Other layers speed", "wxWindowNR", (20, 400, 413, 418), 21, 33, 407),  # above 'Process'
        ("mm/s or %", "wxWindowNR", (210, 440, 330, 466), 13, 223, 447),  # its first unit label
        ("Acceleration", "wxWindowNR", (20, 1600, 413, 1618), 22, 33, 1607),
        ("mm/s²", "wxWindowNR", (210, 1628, 330, 1654), 24, 223, 1635),    # unit label
        ("Jerk(XY)", "wxWindowNR", (20, 1970, 413, 1988), 23, 33, 1977),
        ("Jerk(XY)", "wxWindowNR", (20, 990, 413, 1008), 909, 33, 997),    # a hidden page's copy
        ("Snapmaker U1 (0.8 nozzle)(fixture.3mf)", "wxWindowNR", (77, 159, 415, 185), 31, 84, 166),
    ]
    _real9 = (pp.kids, pp.process_row_y, pp.options_viewport, pp.user32, pp.frect)
    pp.kids = lambda session: list(KIDS)
    pp.process_row_y = lambda session: 614
    pp.options_viewport = lambda session: ((8, 725, 428, 1038), 5)
    # IsChild is true for the viewport's descendants (titles 10/21/22/23),
    # false for the preset panel's windows and the hidden copy.
    pp.user32 = types.SimpleNamespace(
        IsWindowVisible=lambda h: h != 909,
        IsChild=lambda parent, h: h in (10, 21, 22, 23))
    pp.frect = lambda session: FRAME
    try:
        titles = pp.group_titles(None)
        # the REAL functions: earlier checks replace the module attributes
        span_acc = REAL_SPAN(None, "Acceleration")
        span_top = REAL_SPAN(None, "Other layers speed")
        line = ((REAL_TITLE_LINE(None, 404), REAL_TITLE_LINE(None, 430),
                 REAL_TITLE_LINE(None, 960)) if REAL_TITLE_LINE else "absent")
    finally:
        pp.kids, pp.process_row_y, pp.options_viewport, pp.user32, pp.frect = _real9
    check("group_titles: unit labels, containers, preset windows and hidden copies are not titles",
          [t for t, _r, _h in titles] == ["First layer speed", "Other layers speed", "Acceleration", "Jerk(XY)"],
          repr(titles))
    check("group_span: a group runs to the NEXT GROUP TITLE, not to its first unit label",
          span_acc == (1618, 1970), "got %r" % (span_acc,))
    check("group_span: a title scrolled above the Process row still bounds its group",
          span_top == (418, 1600), "got %r" % (span_top,))
    check("on_title_line: the title line yes, the row under it no, elsewhere no",
          line == (True, False, False), "got %r" % (line,))
else:
    print("N/A  group_titles (absent on this tree)")

# 10. A title spelled like its first row is not that row. 'Layer height'
#     heads the Quality page and labels its first row: the OCR scan took the
#     title (y 732) and found no Edit on it (speed_limits run fc5b643c,
#     layer height:0).
page = Page([("Layer height", 735), ("Layer height 0.4 mm", 763), ("First layer height 0.4 mm", 793)],
            {}, titles=[("Layer height", 732, 18)])
install(page)
y = pcl._find_phrase_row(None, "Layer height", None)
check("a label spelled like the group title resolves to the ROW, not the title",
      y == 769, "got %r (title line is 741, row is 769)" % (y,))

# 11. The span follows the page. A group's title sits low in the band
#     (bottom 978); the target row is 152px further down; the wheel is dead
#     for the first three notches. When the row comes into view the page has
#     moved 180px and a span frozen at the start (top 978) rejects it.
page = Page([("Target row", 1130), ("Filler a", 1010), ("Filler b", 1190)], {"Deep": (0, 0)},
            dead=True, revive_works=True, row_h=60, titles=[("Deep", 960, 18)])
install(page)
pp.group_span = lambda session, sub: page.live_span(sub)   # the real thing reads live rects
y = pcl._find_phrase_row(None, "^Target", "Deep")
check("the group span is re-read while scanning: a row that scrolled past the title's start is still found",
      y == 956 and page.offset == 180, "got y=%r offset=%r (r3b: None)" % (y, page.offset))

# 12. The stall guard must not read a MOVING page as stuck. One notch = 60px
#     = two rows; over identical rows the band shows the same word y layout
#     step after step. The old signature (the set of OCR word y) saw 'no
#     change', reset the focus twice and stopped after 9 wheels with 'end of
#     page' - in the middle of a group (seam_wipe, overhang_bridge,
#     feature_speeds). The group titles' window y and the OCR text move with
#     the page, so an absent label now scans the full budget with no reset.
rows = [("Same same 9", 700 + 60 * k) for k in range(80)]
page = Page(rows, {}, row_h=60, titles=[("T", 600, 18)])
install(page)
_real_time, _real_notches = sys.modules["time"], getattr(pp, "SCAN_NOTCHES", None)
sys.modules["time"] = types.SimpleNamespace(monotonic=time.monotonic, sleep=lambda s: None)
pp.SCAN_NOTCHES = 12          # 10+ wheels must pass without a false 'end of page'
assert page.offset == 0
try:
    y = pcl._find_phrase_row(None, "^Absent", None)
    wheels, resets = page.wheels, page.focus_resets
finally:
    sys.modules["time"] = _real_time
    setattr(pp, "SCAN_NOTCHES", _real_notches)
check("stall guard: uniform rows moving 60px a notch are not 'end of page'",
      y is None and wheels == 24 and resets == 0,
      "y=%r wheels=%d resets=%d (r3b: 18 wheels, 4 resets)" % (y, wheels, resets))
# and a page that really stops (the end) is still recognised: the offset is
# capped and the signature stops changing.
class EndPage(Page):
    MAX = 400

    def wheel(self, _session, _vp, notches, delta=-120):
        Page.wheel(self, _session, _vp, notches, delta=delta)
        self.offset = min(self.offset, self.MAX)
page = EndPage(rows, {}, row_h=60, titles=[("T", 600, 18)])
install(page)
_real_time, _real_notches = sys.modules["time"], getattr(pp, "SCAN_NOTCHES", None)
sys.modules["time"] = types.SimpleNamespace(monotonic=time.monotonic, sleep=lambda s: None)
pp.SCAN_NOTCHES = 30          # 7 moving + 9 unchanged wheels per direction
try:
    y = pcl._find_phrase_row(None, "^Absent", None)
    end_wheels, end_resets = page.wheels, page.focus_resets
finally:
    sys.modules["time"] = _real_time
    setattr(pp, "SCAN_NOTCHES", _real_notches)
check("stall guard: a page that really stopped is still the page end (9 unchanged wheels, 2 resets per direction)",
      y is None and end_wheels == 32 and end_resets == 4,
      "y=%r wheels=%d resets=%d (expect 16 + 16 wheels)" % (y, end_wheels, end_resets))

# 13. run_ops: a rowcombo label list is tried candidate by candidate
#     (filament_features passed ['^Wipe tower', 'tower'] straight through
#     and died on list.startswith, run 6b399e48).
import harness.param_combo_row as pcr  # noqa: E402
from harness.agent_protocol import ProtocolError  # noqa: E402
calls = []
_real13 = (pcr.pick_combo_at_label, pp.ensure_advanced, pp.click_tab)


def _fake_pick(_ui, label, target, group_substr=None):
    calls.append(label)
    if label != "tower":
        raise ProtocolError("param_combo_row:" + str(label))


pcr.pick_combo_at_label = _fake_pick
pp.ensure_advanced = lambda app, want=True: True
pp.click_tab = lambda app, tab, hint="": True
try:
    fake_ui = types.SimpleNamespace(app=None, main_input=lambda: None, pause=lambda s: None)
    try:
        pcl.run_ops(fake_ui, [{"tab": "Multimaterial", "op": "rowcombo",
                               "label": ["^Wipe tower", "tower"], "target": "1",
                               "group": "Filament for Features"}])
    except ProtocolError:   # r3b hands the list straight to the picker
        pass
    tried = list(calls)
    calls = []
    try:
        pcl.run_ops(fake_ui, [{"op": "rowcombo", "label": ["^Nope", "^Also nope"], "target": "x"}])
        raised = "nothing"
    except ProtocolError as exc:
        raised = str(exc)
finally:
    pcr.pick_combo_at_label, pp.ensure_advanced, pp.click_tab = _real13
check("run_ops: rowcombo tries each label candidate until one works",
      tried == ["^Wipe tower", "tower"], "calls %r" % (tried,))
check("run_ops: when every candidate fails the last error is raised, not swallowed",
      calls == ["^Nope", "^Also nope"] and raised.startswith("param_combo_row"), "calls %r raised %r" % (calls, raised))

# 14. A popup opens straight below its combo and is not kept off the
#     taskbar: 'Print sequence' at y 961-987 had its popup at 993-1049 with
#     the work area ending at 1032; the click on 'By object' (304,1035)
#     resolved to Shell_TrayWnd (by_object run 6640e4a9, census c101c0f4).
if hasattr(pp, "park_for_popup"):
    sent = []
    _real14 = (pp.work_area, pp.options_viewport, pp.wheel_viewport,
               pp.winutil.window_from_screen_point, pp.user32)
    pp.work_area = lambda: (0, 0, 1920, 1032)
    pp.options_viewport = lambda session: ((1, 718, 421, 1031), 9)
    pp.wheel_viewport = lambda session, vp, notches, delta=-120: sent.append((notches, delta))
    try:
        n_edge = pp.park_for_popup(None, (246, 961, 366, 987))
        n_mid = pp.park_for_popup(None, (246, 834, 366, 860))
        n_high = pp.park_for_popup(None, (246, 700, 366, 726))
    finally:
        pp.work_area, pp.options_viewport, pp.wheel_viewport = _real14[:3]
    pp.winutil.window_from_screen_point = lambda x, y: (
        777 if y >= 1032 else (999 if x > 340 else 444))
    pp.user32 = types.SimpleNamespace(IsChild=lambda parent, h: h == 444)
    try:
        under_taskbar = pp.popup_hit_clickable(333, 304, 1035)
        inside = pp.popup_hit_clickable(333, 304, 1007)
        other = pp.popup_hit_clickable(333, 350, 1007)
    finally:
        pp.winutil.window_from_screen_point, pp.user32 = _real14[3], _real14[4]
    check("park_for_popup: the by_object combo (bottom 987) is 175px short -> 4 notches down",
          n_edge == 4 and sent[0] == (4, -120), "notches=%r sent=%r" % (n_edge, sent))
    check("park_for_popup: bottom 860 is 48px short -> 2 notches; bottom 807 has room -> the page is left alone",
          n_mid == 2 and n_high == 0 and sent == [(4, -120), (2, -120)], "mid=%r high=%r sent=%r" % (n_mid, n_high, sent))
    check("popup_hit_clickable: 'By object' at y=1035 is under the taskbar -> not clickable",
          under_taskbar is False, "got %r" % (under_taskbar,))
    check("popup_hit_clickable: a row inside the popup is clickable, another window is not",
          inside is True and other is False, "inside=%r other=%r" % (inside, other))
else:
    print("N/A  popup parking (absent on this tree)")

failed = [n for n, ok in results if not ok]
print("\n%d checks, %d failed" % (len(results), len(failed)))
sys.exit(1 if failed else 0)
