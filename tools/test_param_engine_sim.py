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
_real = (pp.group_title, pp.time.sleep, pp.frect, pp.neutralize_focus,
         getattr(pp, "client_origin", None))   # r4 reads the client origin here
# The unpatched engine calls neutralize_focus straight from
# scroll_group_into_view; with a fake session it would raise before the
# later sections ever run - stub it so the RED proof reaches them too.
pp.neutralize_focus = lambda session: True
pp.time.sleep = lambda s: None
pp.frect = lambda session: (0, 0, 0, 0)
pp.client_origin = lambda session: (0, 0)
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
    (pp.group_title, pp.time.sleep, pp.frect, pp.neutralize_focus, pp.client_origin) = _real
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
pp.client_origin = lambda session: (0, 0)
pp.neutralize_focus = lambda session: True  # again: the base engine reaches it from here
pp.group_title = lambda session, sub: ((0, 0, 400, 690), 99) if sub == "Initial layer" else None
pp.view_band = lambda session: BAND
try:
    hit3 = REAL_SGIV(None, "Initial layer", timeout_s=60.0)
    wheels_top = page.wheels - wheels_before
finally:
    (pp.group_title, pp.time.sleep, pp.frect, pp.neutralize_focus, pp.client_origin) = _real
check("scroll_group_into_view: first group's title stuck above the band -> accepted quickly",
      hit3 == ((0, 0, 400, 690), 99) and 0 < wheels_top <= 8, "hit3=%r wheels=%d" % (hit3, wheels_top))

# 6b. A title far outside the band gets ONE wheel call with just as many
#     notches as the 1-notch steps would have needed, and lands where they
#     landed (2026-11-25). The checkbox 'Detect overhang' of #264 spent 20 of
#     its 27 s on 27 single notches: 'Overhangs' is the last group of Quality
#     (census c101c0f4, page at top: title top 2560, 18 high).
page = Page([("x", 700)], {}, row_h=pp.WHEEL_STEP_PX)
install(page)
_saved6b = (pp.group_title, pp.view_band, pp.time.sleep, pp.client_origin)
TOP6b, HEIGHT6b = 2560, 18
pp.time.sleep = lambda s: None
pp.client_origin = lambda session: (0, 0)
pp.view_band = lambda session: BAND


def _title6b(session, sub):          # the title window: its rect follows the page
    top = TOP6b - page.offset
    return ((13, top, 406, top + HEIGHT6b), 4321)


pp.group_title = _title6b
try:
    # what the loop did before: one notch a turn until the title's bottom
    # passed the band edge
    offset6b = 0
    while TOP6b + HEIGHT6b - offset6b > BAND[1] - 24:
        offset6b += pp.WHEEL_STEP_PX
    wheels6b = offset6b // pp.WHEEL_STEP_PX
    hit6b = REAL_SGIV(None, "Overhangs", timeout_s=30.0)
    burst_calls, burst_offset = page.wheels, page.offset
    # the same function on a page that moves ONE notch per call however many
    # it is asked for: the 1-notch loop, turn by turn
    page.wheels, page.offset = 0, 0
    _wheel6b = pp.wheel_viewport
    pp.wheel_viewport = lambda session, vp, notches, delta=-120: _wheel6b(session, vp, 1, delta)
    hit6b_single = REAL_SGIV(None, "Overhangs", timeout_s=30.0)
    single_calls, single_offset = page.wheels, page.offset
    pp.wheel_viewport = _wheel6b
finally:
    (pp.group_title, pp.view_band, pp.time.sleep, pp.client_origin) = _saved6b
check("scroll_group_into_view: a title 27 notches under the band -> the rect and the page offset of the 1-notch loop",
      wheels6b == 27 and hit6b == ((13, TOP6b - offset6b, 406, TOP6b + HEIGHT6b - offset6b), 4321)
      and burst_offset == offset6b and single_offset == offset6b and hit6b_single == hit6b,
      "wheels=%d hit=%r offset=%r single=%r hit_single=%r" % (wheels6b, hit6b, burst_offset, single_offset, hit6b_single))
check("scroll_group_into_view: ... reached in at most 2 wheel calls where the 1-notch loop took 27",
      single_calls == 27 and burst_calls <= 2,
      "single calls=%d burst calls=%d" % (single_calls, burst_calls))

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
    # The maximized guest frame (census c101c0f4) and its client origin: a
    # window-rect-relative y is the client y + 7. OCR coordinates are client
    # coordinates (the capture is the client area), so comparing the two
    # directly is 7px off (speed_limits 1e944276: the 'Layer height' title's
    # text top 726 client, its window 723-741 screen = 730-748 frame).
    FRAME = (-7, -7, 1927, 1039)
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
    _real9 = (pp.kids, pp.process_row_y, pp.options_viewport, pp.user32, pp.frect,
              getattr(pp, "client_origin", None))
    pp.kids = lambda session: list(KIDS)
    pp.process_row_y = lambda session: 614
    pp.options_viewport = lambda session: ((8, 725, 428, 1038), 5)
    # IsChild is true for the viewport's descendants (titles 10/21/22/23),
    # false for the preset panel's windows and the hidden copy.
    pp.user32 = types.SimpleNamespace(
        IsWindowVisible=lambda h: h != 909,
        IsChild=lambda parent, h: h in (10, 21, 22, 23))
    pp.frect = lambda session: FRAME
    pp.client_origin = lambda session: (0, 0)
    try:
        titles = pp.group_titles(None)
        # the REAL functions: earlier checks replace the module attributes
        span_acc = REAL_SPAN(None, "Acceleration")
        span_top = REAL_SPAN(None, "Other layers speed")
        line = ((REAL_TITLE_LINE(None, 404), REAL_TITLE_LINE(None, 430),
                 REAL_TITLE_LINE(None, 960)) if REAL_TITLE_LINE else "absent")
        # the title's painted text starts ~3px under its window top
        near = REAL_TITLE_LINE(None, 403) if REAL_TITLE_LINE else "absent"
    finally:
        (pp.kids, pp.process_row_y, pp.options_viewport, pp.user32, pp.frect,
         pp.client_origin) = _real9
    check("group_titles: unit labels, containers, preset windows and hidden copies are not titles",
          [t for t, _r, _h in titles] == ["First layer speed", "Other layers speed", "Acceleration", "Jerk(XY)"],
          repr(titles))
    check("group_span (client coords): a group runs to the NEXT GROUP TITLE, not to its first unit label",
          span_acc == (1618, 1970), "got %r" % (span_acc,))
    check("group_span (client coords): a title scrolled above the Process row still bounds its group",
          span_top == (418, 1600), "got %r" % (span_top,))
    check("on_title_line: the title line yes, the row under it no, elsewhere no",
          line == (True, False, False), "got %r" % (line,))
    check("on_title_line: the title text 3px under its window top counts despite the 7px frame/client gap",
          near is True, "got %r" % (near,))
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
import harness.native_script_baseline as nsb  # noqa: E402
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
    # Exactly enough notches. r3c added a spare one: a row that sat at the
    # very bottom (bottom 1009 / 1030) then went 300px up - above the
    # viewport top, where its label could no longer be read (brim 5a73aee3,
    # filament_features f27ba25c).
    check("park_for_popup: the by_object combo (bottom 987) is 175px short -> 3 notches, no spare",
          n_edge == 3 and sent[0] == (3, -120), "notches=%r sent=%r" % (n_edge, sent))
    check("park_for_popup: bottom 860 is 48px short -> 1 notch; bottom 807 has room -> the page is left alone",
          n_mid == 1 and n_high == 0 and sent == [(3, -120), (1, -120)], "mid=%r high=%r sent=%r" % (n_mid, n_high, sent))
    check("popup_hit_clickable: 'By object' at y=1035 is under the taskbar -> not clickable",
          under_taskbar is False, "got %r" % (under_taskbar,))
    check("popup_hit_clickable: a row inside the popup is clickable, another window is not",
          inside is True and other is False, "inside=%r other=%r" % (inside, other))
else:
    print("N/A  popup parking (absent on this tree)")

# ------------------------------------------------------------------ r4
# From two static reviews of 2026-11-23 (fa706g3: the row-locating half of
# the engine; Mac: whether these very checks can go red) and from queue20.

# 15. uia_set_float REALLY runs: a fake win32gui enumerates the Edits, a fake
#     ui.edit answers with the readback. Before this the whole function was
#     never executed by any test.
REAL_FIND_PHRASE = pcl._find_phrase_row
REAL_FIND_ANY = getattr(pcl, "_find_phrase_row_any", None)   # r4.1: all candidates in one scan
REAL_CANVAS = pcl._canvas_hwnd
REAL_ROW_SEQ = getattr(pp, "find_option_row_seq", None)


class _FakeWin32gui(types.ModuleType):
    def __init__(self, edits):
        super().__init__("win32gui")
        self.edits = dict(edits)      # hwnd -> (rect, enabled); accepts a set of pairs too

    def EnumChildWindows(self, _parent, cb, _lparam):
        for h in self.edits:
            cb(h, _lparam)

    def IsWindowVisible(self, _h):
        return True

    def IsWindowEnabled(self, h):
        return self.edits[h][1]


class _FakeUI:
    def __init__(self, edits, readback=None):
        self.app = types.SimpleNamespace(pid=7, hwnd=99)
        self.edits = dict(edits)      # a set of (hwnd, (rect, enabled)) pairs is fine
        self.readback = readback or (lambda text: text)
        self.typed = []
        ui = self

        class _WU:
            @staticmethod
            def window_class(_h):
                return "Edit"

            @staticmethod
            def window_rect(h):
                return ui.edits[h][0] if h in ui.edits else (426, 0, 1900, 1031)

            @staticmethod
            def _window_pid(_h):
                return 7

            @staticmethod
            def client_to_screen(_h, _x, _y):
                return (0, 0)
        self.wu = _WU()

    def edit(self, x, y, text):
        handle = next(h for h, (rect, _e) in self.edits.items()
                      if rect[0] <= x < rect[2] and rect[1] <= y < rect[3])
        self.typed.append((handle, text))
        return {"target_hwnd": handle, "after_text": self.readback(text)}


def _edit_at(cy, enabled=True, hwnd=None):
    return (hwnd or cy, ((246, cy - 13, 366, cy + 13), enabled))


def _raises(fn, *args, **kwargs):
    """ProtocolError message the call raised with, or None if it did not raise."""
    try:
        fn(*args, **kwargs)
    except ProtocolError as exc:
        return str(exc)
    except Exception as exc:  # a crash is not the protocol error we assert
        return "CRASH %s: %s" % (type(exc).__name__, exc)
    return None


def _with_float_env(edits, y_row):
    # r4.1: uia_set_float searches all label candidates in ONE scan and gets
    # (y, matched) back; older trees call _find_phrase_row and get y.
    if REAL_FIND_ANY is not None:
        pcl._find_phrase_row_any = lambda app, label, group=None: (
            y_row, label if isinstance(label, str) else label[0])
    pcl._find_phrase_row = lambda app, label, group=None: y_row
    pcl._canvas_hwnd = lambda ui: 55
    sys.modules["win32gui"] = _FakeWin32gui(dict(edits))


_fake_before = sys.modules.get("win32gui")
try:
    # a) the sign is part of the value
    _with_float_env({_edit_at(800)}, 800)
    ui = _FakeUI({_edit_at(800)}, readback=lambda text: text.lstrip("-"))
    msg = _raises(pcl.uia_set_float, ui, "X-Y hole compensation", "-0.1", "Precision")
    check("uia_set_float: a readback that lost the minus sign is rejected",
          isinstance(msg, str) and msg.startswith("param_uia_readback"), "got %r" % (msg,))
    # b) a declared field index must exist
    e = {_edit_at(834, hwnd=11)}
    _with_float_env(e, 800)
    msg = _raises(pcl.uia_set_float, _FakeUI(e), "Overhang speed", "10", "Overhang", field_index=3)
    check("uia_set_float: field_index=3 with ONE Edit on the row is refused "
          "(runs 7f9beea4/50798c59 typed into that Edit)",
          isinstance(msg, str) and msg.startswith("param_uia_field"), "got %r" % (msg,))
    ui = _FakeUI(e)
    _raises(pcl.uia_set_float, ui, "Overhang speed", "10", "Overhang", field_index=0)
    check("uia_set_float: field_index=0 with one Edit drives it",
          ui.typed == [(11, "10")], "typed %r" % (ui.typed,))
    # c) a two-line label: the control is half a row-pitch off the matched line
    e = {_edit_at(815, hwnd=12)}
    _with_float_env(e, 800)
    ui = _FakeUI(e)
    _raises(pcl.uia_set_float, ui, "Initial layer travel speed", "150%", None)
    check("uia_set_float: an undeclared Edit 15px below the matched line (two-line label) is driven",
          ui.typed == [(12, "150%")], "typed %r" % (ui.typed,))
    e = {_edit_at(830, hwnd=13)}
    _with_float_env(e, 800)
    msg = _raises(pcl.uia_set_float, _FakeUI(e), "some label", "1", None)
    check("uia_set_float: the NEXT single-line row's Edit (30px) is never taken for a missing one",
          isinstance(msg, str) and msg.startswith("param_uia_field"), "got %r" % (msg,))
    # d) a greyed field says so
    e = {_edit_at(800, enabled=False, hwnd=14)}
    _with_float_env(e, 800)
    msg = _raises(pcl.uia_set_float, _FakeUI(e), "Brim width", "5", "Brim")
    check("uia_set_float: a disabled Edit on the row reports param_uia_field_disabled",
          isinstance(msg, str) and msg.startswith("param_uia_field_disabled"), "got %r" % (msg,))
finally:
    pcl._find_phrase_row, pcl._canvas_hwnd = REAL_FIND_PHRASE, REAL_CANVAS
    if REAL_FIND_ANY is not None:
        pcl._find_phrase_row_any = REAL_FIND_ANY
    if _fake_before is None:
        sys.modules.pop("win32gui", None)
    else:
        sys.modules["win32gui"] = _fake_before

# 16. A group name that matches no title is a wrong op, not a licence to
#     search the whole page (fa review D2): with a wrong group the engine
#     scanned unconstrained and edited the first same-named row it met.
def _no_ocr(*_a, **_k):
    raise AssertionError("the engine scanned the page although the group does not exist")


_pp_ocr = pp.ocr_band
pp.scroll_group_into_view = lambda session, sub, timeout_s=420.0: None
pp.ocr_band = _no_ocr
pp.wheel_viewport = _no_ocr
try:
    try:
        y = REAL_FIND_PHRASE(None, "^Outer wall", "No Such Group")
    except AssertionError:
        y = "scanned"
finally:
    pp.ocr_band, pp.wheel_viewport = _pp_ocr, page.wheel
check("_find_phrase_row: a group without a title returns None without scanning",
      y is None, "got %r" % (y,))

# 16b. All label candidates are looked for in ONE scan. The per-candidate
#      scans this replaces paged the whole page, both directions, for every
#      candidate that is not on the page (line_width_all run 4149046c: three
#      atlas labels, ten minutes, then the plain ones were found at once).
if REAL_FIND_ANY is not None:
    _wheels16 = []
    _s16 = (pp.ocr_band, pp.wheel_viewport, pp.options_viewport, pp.group_span, pp.on_title_line,
            pp.scroll_group_into_view, pp.focus_off_edit, pp.scroll_signature)
    pp.ocr_band = lambda session, y0=None, y1=None, psm=3: [
        ("Outer", 30, 900, 40, 12), ("wall", 78, 900, 34, 12), ("120", 260, 900, 30, 12)]
    pp.wheel_viewport = lambda *_a, **_k: _wheels16.append(1)
    pp.options_viewport = lambda session: ((0, 700, 420, 1000), 1)
    pp.group_span = lambda session, sub: None
    pp.on_title_line = lambda session, y, tol=3: False
    pp.scroll_group_into_view = lambda session, sub, timeout_s=420.0: (0, 0, 0)
    pp.focus_off_edit = lambda session, why="": None
    pp.scroll_signature = lambda session: (("T", 900),)
    try:
        res = REAL_FIND_ANY(None, ["Outer wall line width", "Outer wall"], "Line width")
    finally:
        (pp.ocr_band, pp.wheel_viewport, pp.options_viewport, pp.group_span, pp.on_title_line,
         pp.scroll_group_into_view, pp.focus_off_edit, pp.scroll_signature) = _s16
    check("_find_phrase_row_any: ['Outer wall line width', 'Outer wall'] resolves to 'Outer wall' "
          "without one wheel",
          res == (906, "Outer wall") and not _wheels16, "got %r wheels=%d" % (res, len(_wheels16)))
else:
    print("N/A  _find_phrase_row_any (absent on this tree)")

# 16c. run_ops hands EACH float op its own label. r4.1 looked the candidates
#      up under a name that only the rowcombo branch defined: a float op
#      after a rowcombo op searched for the rowcombo's label, any other
#      float op died on a NameError (fa run f4b87b67) - and no test ran
#      run_ops with a float op at all (the Mac audit said so the same hour).
if hasattr(pcl, "_find_phrase_row_any"):
    seen = []
    _saved16c = (pcl.uia_set_float, pcr.pick_combo_at_label, pp.ensure_advanced, pp.click_tab,
                 pp.neutralize_focus)
    pcl.uia_set_float = lambda ui, label, value, group_substr=None, field_index=None, below=False: (
        seen.append(("float", label, value, group_substr)) or _raises_float())
    pcr.pick_combo_at_label = lambda ui, label, target, group_substr=None: seen.append(
        ("rowcombo", label, target, group_substr))
    pp.ensure_advanced = lambda app, want=True: True
    pp.click_tab = lambda app, tab, hint="", *a, **k: True
    pp.neutralize_focus = lambda app: None

    def _raises_float():
        return None
    fake_ui = types.SimpleNamespace(app=None, main_input=lambda: None, pause=lambda s: None)
    try:
        pcl.run_ops(fake_ui, [
            {"tab": "Others", "op": "rowcombo", "label": "Fuzzy skin", "target": "Contour", "group": "Fuzzy"},
            {"op": "float", "label": "point distance", "value": "0.6", "group": "Fuzzy"},
        ])
    except Exception as exc:  # NameError on r4.1
        seen.append(("crash", type(exc).__name__))
    try:
        pcl.run_ops(fake_ui, [{"tab": "Quality", "op": "float", "label": ["Layer height"], "value": "0.2"}])
    except Exception as exc:
        seen.append(("crash", type(exc).__name__))
    finally:
        (pcl.uia_set_float, pcr.pick_combo_at_label, pp.ensure_advanced, pp.click_tab,
         pp.neutralize_focus) = _saved16c
    floats = [s for s in seen if s[0] == "float"]
    check("run_ops: a float op after a rowcombo op gets ITS OWN label (not the rowcombo's)",
          floats and tuple(floats[0][1]) == ("point distance",), "seen %r" % (seen,))
    check("run_ops: a float op with no rowcombo before it does not crash",
          len(floats) == 2 and floats[1][1] == ["Layer height"], "seen %r" % (seen,))

# 17. find_option_row_seq scans like find_option_row, in the value column.
#     Until r4 it looked at the start view and 5 notches down: a value deeper
#     than ~10 rows below its group title was unreachable (fa review D1), and
#     the first word run anywhere in the band counted, label column included
#     (D3).
if REAL_ROW_SEQ is not None:
    state = {"offset": 0}

    def _words():
        out = [("Label", 30, 800 - state["offset"], 40, 12),        # a label line
               ("By", 60, 800 - state["offset"], 20, 12), ("layer", 84, 800 - state["offset"], 40, 12)]
        deep = 1400 - state["offset"]                               # needs 7 notches
        if 700 <= deep <= 1000:
            out += [("By", 266, deep, 20, 12), ("layer", 290, deep, 40, 12)]
        return out

    _saved17 = (pp.ocr_band, pp.wheel_viewport, pp.options_viewport, pp.group_span,
                pp.on_title_line, pp.focus_off_edit, pp.scroll_group_into_view, pp.scroll_signature)
    pp.ocr_band = lambda session, y0=None, y1=None, psm=3: _words()
    pp.wheel_viewport = lambda session, vp, notches, delta=-120: state.__setitem__(
        "offset", max(0, state["offset"] + 60 * notches * (1 if delta < 0 else -1)))
    pp.options_viewport = lambda session: ((0, 700, 420, 1000), 1)
    pp.group_span = lambda session, sub: None
    pp.on_title_line = lambda session, y, tol=3: False
    pp.focus_off_edit = lambda session, why="": None
    pp.scroll_group_into_view = lambda session, sub, timeout_s=420.0: (0, 0, 0)
    pp.scroll_signature = lambda session: (("T", 900 - state["offset"]),)
    try:
        hit = REAL_ROW_SEQ(None, ("by", "layer"), None)
    finally:
        (pp.ocr_band, pp.wheel_viewport, pp.options_viewport, pp.group_span, pp.on_title_line,
         pp.focus_off_edit, pp.scroll_group_into_view, pp.scroll_signature) = _saved17
    check("find_option_row_seq: a value 7 notches down is found (the old scan stopped at 5), "
          "the label-column copy ignored",
          hit[0] is not None and hit[0][0] == 266, "got %r" % (hit,))
else:
    print("N/A  find_option_row_seq (absent on this tree)")

# 18. The ops checker must be able to match an unanchored multi-word label at
#     all (range(len(words), len(words)) was an empty loop: 60 of its 62
#     "UNCERTAIN" lines were that bug).
from pathlib import Path as _Path  # noqa: E402
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "check_ops", str(_Path(__file__).resolve().parent / "check_ops_against_atlas.py"))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
check("checker: an unanchored multi-word label matches its row",
      _mod.label_matches("Wall loops", "Wall loops") is True
      and _mod.label_matches("Detect overhang", "Detect overhang walls") is True
      and _mod.label_matches("^Wipe speed", "Role based wipe speed") is False,
      "got %r" % (_mod.label_matches("Wall loops", "Wall loops"),))

# ------------------------------------------------------------------ r5
# From the first two-line run (2026-11-23 23:44, fa706g3 + guest in parallel).

# 19. A `field` row is ONE label with its Edits stacked vertically around it
#     (VM run 210446b4: 'Overhang speed', four boxes at a 27px pitch, the
#     label centred on the block; the stack below ends with the next row's
#     Edit). Field i is the i-th Edit from the top.
REAL_FIELD_UI = pcl.uia_set_float
_fake_before19 = sys.modules.get("win32gui")
try:
    stack = {}
    for i, cy in enumerate((924, 950, 976, 1002, 1032)):
        stack.update({_edit_at(cy, hwnd=100 + i)})
    _with_float_env(stack, 965)
    got = []
    for idx in (0, 1, 3):
        ui = _FakeUI(stack)
        _raises(pcl.uia_set_float, ui, "Overhang speed", "10", "Overhang", field_index=idx)
        got.append(ui.typed[0][0] if ui.typed else None)
    check("uia_set_float: field 0/1/3 of a vertical stack drive the 1st/2nd/4th Edit from the top",
          got == [100, 101, 103], "got %r" % (got,))
    ui = _FakeUI(stack)
    msg = _raises(pcl.uia_set_float, ui, "Overhang speed", "10", "Overhang", field_index=7)
    # 1032 is 67px below the label: the NEXT row's Edit (bridge speed), not a fifth field
    check("uia_set_float: field index beyond the stack is refused",
          isinstance(msg, str) and msg.startswith("param_uia_field"), "got %r" % (msg,))

    # r10 (fa706g3 run 4491e40, 2026-11-24): a stacked field whose bottom is
    # within EDIT_ROOM of the work-area bottom is not driven where it sits -
    # the page is wheeled down and the row located again.
    _saved19b = (pp.work_area, pp.options_viewport, pp.wheel_viewport)
    wheels = []
    pp.work_area = lambda: (0, 0, 1920, 1032)
    pp.options_viewport = lambda session: (10, 700, 400, 330)
    pp.wheel_viewport = lambda session, vp, notches, delta=-120: wheels.append((notches, delta))
    try:
        ui = _FakeUI(stack)
        n = pcl._park_field(ui, [246, 1019, 366, 1045])
        check("r10 _park_field: an Edit 13px under the work-area bottom gets one notch",
              n == 1 and wheels == [(1, -120)], "got %r %r" % (n, wheels))
        wheels.clear()
        n = pcl._park_field(ui, [246, 996, 366, 1020])
        check("r10 _park_field: an Edit with 12px of room is left alone",
              n == 0 and wheels == [], "got %r %r" % (n, wheels))
        n = pcl._park_field(ui, [246, 1080, 366, 1106])
        check("r10 _park_field: 86px short is two notches",
              n == 2 and wheels == [(2, -120)], "got %r %r" % (n, wheels))
        wheels.clear()
        pp.work_area = lambda: None
        check("r10 _park_field: no work area measured -> nothing wheeled",
              pcl._park_field(ui, [246, 1080, 366, 1106]) == 0 and wheels == [],
              "got %r" % (wheels,))
        bottom = [1024]                              # the 4th box keeps 9px: too little
        pp.work_area = lambda: (0, 0, 1920, bottom[0])

        def _wheel_moves_page(session, vp, notches, delta=-120):
            wheels.append((notches, delta))
            bottom[0] = 1200                         # the fake page moved the box up
        pp.wheel_viewport = _wheel_moves_page
        ui = _FakeUI(stack)
        pcl.uia_set_float(ui, "Overhang speed", "10", "Overhang", field_index=3)
        check("r10 uia_set_float: a stack box 9px above the bottom is wheeled into view once, then driven",
              wheels == [(1, -120)] and [t[0] for t in ui.typed] == [103],
              "got %r %r" % (wheels, ui.typed))
        wheels.clear()
        ui = _FakeUI(stack)
        pcl.uia_set_float(ui, "Overhang speed", "10", "Overhang", field_index=3)
        check("r10 uia_set_float: the same box is driven without a wheel once the page has room",
              wheels == [] and [t[0] for t in ui.typed] == [103], "got %r %r" % (wheels, ui.typed))
        bottom[0] = 1024
        pp.wheel_viewport = lambda session, vp, notches, delta=-120: wheels.append((notches, delta))
        ui = _FakeUI(stack)
        pcl.uia_set_float(ui, "Overhang speed", "10", "Overhang", field_index=3)
        check("r10 uia_set_float: a page that does not move is given up after three wheels, then driven",
              wheels == [(1, -120)] * 3 and [t[0] for t in ui.typed] == [103],
              "got %r %r" % (wheels, ui.typed))
        wheels.clear()
        bottom[0] = 1200
        ui = _FakeUI(stack)
        pcl.uia_set_float(ui, "Overhang speed", "10", "Overhang", field_index=2)
        check("r10 uia_set_float: a stack box with room above the bottom is driven without a wheel",
              wheels == [] and [t[0] for t in ui.typed] == [102], "got %r %r" % (wheels, ui.typed))
    finally:
        pp.work_area, pp.options_viewport, pp.wheel_viewport = _saved19b
finally:
    # restore EVERYTHING _with_float_env stubbed: until 2026-11-24 the
    # canvas anchor and the phrase scan stayed stubbed after this block,
    # and the text-field test (28) read the canvas from the stub.
    pcl._find_phrase_row = REAL_FIND_PHRASE
    if REAL_FIND_ANY is not None:
        pcl._find_phrase_row_any = REAL_FIND_ANY
    pcl._canvas_hwnd = REAL_CANVAS
    if _fake_before19 is None:
        sys.modules.pop("win32gui", None)
    else:
        sys.modules["win32gui"] = _fake_before19

# 20. The control under a painted combo VALUE is found by enumeration and
#     judged by IsWindowEnabled - not by the size of WindowFromPoint's answer,
#     which refused an enabled 254x39 combo on fa706g3 (run 744a5451) and
#     needs a size guess for the disabled case.
if hasattr(pp, "value_control_at"):
    def _win(text, rect, enabled=True, cls="wxWindowNR", hwnd=1):
        lx, ly = rect[0] + 7, rect[1] + 7
        return (text, cls, rect, hwnd, lx, ly)
    _k20 = pp.kids
    _u20 = pp.user32
    pp.user32 = types.SimpleNamespace(IsWindowVisible=lambda h: True, IsWindowEnabled=lambda h: h != 7)
    row = _win("", (6, 749, 399, 1019), hwnd=5)
    off = _win("", (254, 781, 508, 820), hwnd=6)                 # fa's 254x39 window
    try:
        pp.kids = lambda session: [row, _win("Tree (auto)", (246, 781, 366, 807), enabled=False, hwnd=7)]
        r = pp.value_control_at(None, 289, 794, "Tree")
        check("value_control_at: a disabled value window is reported as not clickable (no size guess)",
              r == (None, None, None), "got %r" % (r,))
        pp.kids = lambda session: [row, _win("Tree (auto)", (246, 781, 366, 807), hwnd=8)]
        r = pp.value_control_at(None, 289, 794, "Tree")
        check("value_control_at: the enabled value window under the painted word is returned",
              r[1] == 8 and r[2] == "Tree (auto)", "got %r" % (r,))
        pp.kids = lambda session: [row, off, _win("Tree (auto)", (246, 781, 366, 807), hwnd=9)]
        r = pp.value_control_at(None, 289, 794, "Tree")
        check("value_control_at: the smallest window with text wins over the 254x39 one around it (fa)",
              r[1] == 9, "got %r" % (r,))
        pp.kids = lambda session: [row, _win("Tree (auto)", (254, 781, 508, 820), hwnd=10)]
        r = pp.value_control_at(None, 289, 794, "Tree")
        check("value_control_at: a 254x39 enabled combo is accepted (fa run 744a5451 was refused)",
              r[1] == 10, "got %r" % (r,))
        pp.kids = lambda session: [row]
        r = pp.value_control_at(None, 289, 794, "Tree")
        check("value_control_at: only the row container under the value -> not a combo",
              r == (None, None, None), "got %r" % (r,))
    finally:
        pp.kids, pp.user32 = _k20, _u20
else:
    print("N/A  value_control_at (absent on this tree)")

# 21. The rowcombo readback reads the VALUE. fa run 4ec54abd: the click had
#     worked and the row painted '[1] PETG', but the band OCR returned the
#     label alone and the readback raised. Measured on that screenshot: the
#     swatch empties the OCR of the whole value zone, the zone cut past the
#     swatch reads 'PETG' - and garbles a plain value ('Yefault').
from harness import mix_dialog_util as _mdu21  # noqa: E402

import numpy as _np21  # noqa: E402


def _fake_ocr21(crop, scale=3, psm=6):
    hgt, wid = crop.shape[:2]
    if wid == pp.SB_W:                       # the whole band: label only
        return [("Support/raft", 13, 776 - 718 - 7, 96, 14), ("base", 115, 776 - 718 - 7, 40, 14)]
    if wid == 140:                           # value zone, with the swatch
        return _case21["zone"]
    if wid == 90:                            # zone cut past the swatch
        return _case21["past"]
    return []


def _run21():
    ui21 = types.SimpleNamespace(
        app=types.SimpleNamespace(hwnd=4, pid=3), wu=types.SimpleNamespace(client_to_screen=lambda *a: (0, 0)))
    read = getattr(pcr, "_row_value", None)
    if read is not None:
        return read(ui21, "^Support/raft base")
    line = pcr._row_line(ui21, "^Support/raft base")
    return line, line                       # the r4.2 rule: target in the label line


_case21 = {"zone": [], "past": [("PETG", 4, 3, 42, 12)]}
_saved21 = (pcr._find_phrase_row, pp.client_origin, pp.kids, pp.user32, pp.capture_bgr,
            pp.options_viewport, _mdu21.ocr_words_img)
_row21 = ("", "panel", (6, 749, 399, 1019), 5, 13, 756)
try:
    pcr._find_phrase_row = lambda app, label, group_substr=None: 776
    pp.client_origin = lambda app: (0, 0)
    pp.user32 = types.SimpleNamespace(IsWindowVisible=lambda h: True)
    pp.capture_bgr = lambda app: _np21.zeros((1032, 1920, 3), _np21.uint8)
    pp.options_viewport = lambda app: ((1, 718, 421, 1031),)
    _mdu21.ocr_words_img = _fake_ocr21
    pp.kids = lambda app: [_row21, ("1", "wxWindowNR", (246, 764, 366, 788), 8, 253, 771)]
    value, line = _run21()
    check("rowcombo readback: the value of a swatch combo is read (fa run 4ec54abd: 'Support/raft base' alone)",
          "petg" in value.lower() and line.lower() == "support/raft base",
          "value %r line %r" % (value, line))
    pp.kids = lambda app: [_row21]       # no value window, nothing to read from
    value, line = _run21()
    check("rowcombo readback: with no value window and an empty zone the cut still reads the value",
          "petg" in value.lower(), "value %r line %r" % (value, line))
    _case21 = {"zone": [("~", 14, 10, 12, 14), ("Default", 30, 10, 62, 14)],
               "past": [("Yefault", 4, 3, 52, 12)]}
    pp.kids = lambda app: [_row21, ("Default", "wxWindowNR", (246, 825, 366, 849), 9, 253, 832)]
    pcr._find_phrase_row = lambda app, label, group_substr=None: 837
    value, line = _run21()
    check("rowcombo readback: a plain value is read from the window text and the whole zone",
          "default" in value.lower(), "value %r line %r" % (value, line))
    _case21 = {"zone": [], "past": []}
    pp.kids = lambda app: [_row21]
    pcr._find_phrase_row = lambda app, label, group_substr=None: 776
    value, line = _run21()
    check("rowcombo readback: an unreadable value is '' with the label line kept for the log",
          value == "" and line.lower() == "support/raft base", "value %r line %r" % (value, line))
    check("rowcombo readback: the target is not looked for in the label line",
          "base" in line.lower() and "base" not in value.lower(), "value %r" % (value,))
finally:
    (pcr._find_phrase_row, pp.client_origin, pp.kids, pp.user32, pp.capture_bgr,
     pp.options_viewport, _mdu21.ocr_words_img) = _saved21

# 22. A modal the app opens after a checkbox is found and answered, and the
#     answer is checked. Spiral vase (VM run 49723134): the Yes/No box stayed
#     open - wait_popup only knows the combo popup - and the next guard raised
#     main_window_modal_blocked. On the guest the box is wx's own dialog with
#     owner-drawn wxWindowNR buttons (runs eab35b9a / 4d9731ec / 9ef272d0 /
#     d8cec0d4). The fa review of 36cbb8c added: the box is taken by class and
#     owner, only the expected question is answered, and the answer is not
#     believed until the box is gone and the page has settled.
from harness import export_util as _eu22  # noqa: E402
from harness import mix_dialog_util as _mdu22, mixing_util as _mu22, winutil as _wu22  # noqa: E402
import harness.param_case_lib as _pcl22  # noqa: E402

if hasattr(_pcl22, "settle_dialog"):
    _clicks22, _posted22, _keys22 = [], [], []
    # main window 4 is disabled while 'open' (box 99). 'closes_with' = the
    # message that answers the box in the fake; 'click_closes' = a real click
    # on a button does; 'enter_closes' = a real Enter does.
    _modal22 = {"open": False, "closes_with": None, "enter_closes": False, "fg": False,
                "click_closes": True}
    BOX22 = ("#32770", "Orca", (800, 400, 1120, 560), 99)
    TIP22 = ("tooltips_class32", "", (900, 300, 1000, 320), 98)
    _windows22 = [BOX22]

    class _U22:
        """stands in for user32: PostMessageW is recorded, not called"""

        @staticmethod
        def PostMessageW(h, msg, w, _l):
            _posted22.append((h, msg, w))
            if msg == _modal22["closes_with"]:
                _modal22["open"] = False       # the box answered: the modal is gone

        @staticmethod
        def IsWindowEnabled(h):
            return not (h == 4 and _modal22["open"])

        @staticmethod
        def IsWindow(h):
            return h == 99 and _modal22["open"]

        @staticmethod
        def GetWindow(h, cmd):
            return 4 if (h == 99 and cmd == 4) else 0     # GW_OWNER: the main window

    def _click22(x, y):
        _clicks22.append((x, y))
        if _modal22["click_closes"]:
            _modal22["open"] = False

    def _enter22(keys):
        _keys22.append(keys)
        if _modal22["enter_closes"]:
            _modal22["open"] = False

    _saved22 = (_mu22.toplevel, pp.dialog_body, pp.kids, _mu22.children, _eu22.wait_popup,
                _wu22.real_click_screen, _wu22.user32, _wu22.force_set_foreground, _mdu22._send_keys)
    try:
        _wu22.user32 = _U22
        _wu22.real_click_screen = _click22
        _wu22.force_set_foreground = lambda h: _modal22["fg"]
        _mdu22._send_keys = _enter22
        ui22 = types.SimpleNamespace(app=types.SimpleNamespace(pid=3, hwnd=4), pause=lambda s: None)
        # NOT #32770-only: the box is found by its effect on the main window
        _mu22.toplevel = lambda pid: list(_windows22)
        _eu22.wait_popup = lambda pid, timeout_s=0: (None, "panel", (1, 2, 3, 4), 77)
        r = _pcl22.settle_dialog(ui22, set())
        check("settle_dialog: no dialog but a combo popup -> WM_CLOSE to the popup, nothing clicked",
              r == (None, "") and _posted22 == [(77, 0x0010, 0)] and not _clicks22,
              "%r %r" % (r, _posted22))
        _posted22.clear()
        _eu22.wait_popup = lambda pid, timeout_s=0: None
        r = _pcl22.settle_dialog(ui22, set())
        check("settle_dialog: nothing opened -> (None, ''), nothing clicked",
              r == (None, "") and not _clicks22 and not _posted22, "%r %r" % (_clicks22, _posted22))
        SPIRAL = ("Spiral mode only works when wall loops is 1, support is disabled, top shell "
                  "layers is 0 ... Change these settings automatically? Yes - Change ... No - Give up")
        pp.dialog_body = lambda pid, dlg: SPIRAL
        pp.kids = lambda app: []                       # the rebuilt page: stable at once
        STATIC22 = ("...", "Static", (1, 1, 2, 2), 5)
        YES_NO22 = [("&Yes", "Button", (100, 200, 160, 222), 11),
                    ("&No", "Button", (180, 200, 240, 222), 12)]
        _mu22.children = lambda dlg: [STATIC22] + YES_NO22
        _modal22["open"] = True
        r = _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: the spiral box is answered Yes - the Yes button is clicked, not closed",
              r[0] == 99 and _clicks22 == [(130, 211)] and not _posted22 and not _modal22["open"],
              "%r %r" % (_clicks22, _posted22))
        _clicks22.clear()
        _modal22.update(open=True, click_closes=False)
        try:
            _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
            raised22 = "nothing"
        except ProtocolError as exc22:
            raised22 = str(exc22)
        check("settle_dialog: a click that does not close the box is an error, not a silent next op "
              "(fa review: 'clicked' and 'closed' could not be told apart)",
              raised22 == "param_dialog_not_closed:Yes" and _clicks22 == [(130, 211)],
              "%r %r" % (raised22, _clicks22))
        _clicks22.clear()
        _modal22.update(open=True, click_closes=True)
        _mu22.children = lambda dlg: [STATIC22, ("\u662f(&Y)", "Button", (100, 200, 160, 222), 11),
                                      ("\u5426(&N)", "Button", (180, 200, 240, 222), 12)]
        _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: a box labelled in the Windows language - Yes is the first of two "
              "(the op named the question)",
              _clicks22 == [(130, 211)], "%r" % (_clicks22,))
        _clicks22.clear()
        _modal22["open"] = True
        _mu22.children = lambda dlg: [("OK", "Button", (100, 200, 160, 222), 11),
                                      ("Cancel", "Button", (180, 200, 240, 222), 12)]
        _pcl22.settle_dialog(ui22, set(), "Yes")          # no expected question named
        check("settle_dialog: two buttons that do not say Yes and no named question -> closed, "
              "the left one is NOT clicked for 'Yes' (fa review)",
              not _clicks22 and _posted22 == [(99, 0x0010, 0)], "%r %r" % (_clicks22, _posted22))
        _posted22.clear()
        _modal22["open"] = True
        _mu22.children = lambda dlg: [STATIC22] + YES_NO22
        _pcl22.settle_dialog(ui22, set(), "Yes", "Delete the project?")   # another question
        check("settle_dialog: a box that is not the expected question is never answered",
              not _clicks22 and _posted22 == [(99, 0x0010, 0)], "%r %r" % (_clicks22, _posted22))
        _posted22.clear()
        _modal22["open"] = True
        _mu22.children = lambda dlg: list(YES_NO22)
        _pcl22.settle_dialog(ui22, set())          # no answer named
        check("settle_dialog: an unnamed dialog is closed, never answered",
              _posted22 == [(99, 0x0010, 0)] and not _clicks22, "%r %r" % (_clicks22, _posted22))
        _posted22.clear()
        _modal22["open"] = True
        _windows22[:] = [TIP22, BOX22]             # a tooltip window is listed BEFORE the box
        _mu22.children = lambda dlg: [STATIC22] + YES_NO22
        r = _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: the box is the #32770 owned by the main window, not the first new window "
              "(fa review)",
              r[0] == 99 and _clicks22 == [(130, 211)], "%r %r" % (r, _clicks22))
        _clicks22.clear()
        _modal22["open"] = True
        _windows22[:] = [TIP22]                    # nothing owned: the only new window is taken
        r = _pcl22.settle_dialog(ui22, set())
        check("settle_dialog: with no owned box the only new window is still handled (and closed)",
              r[0] == 98 and _posted22 == [(98, 0x0010, 0)], "%r %r" % (r, _posted22))
        _windows22[:] = [BOX22]
        LADDER22 = [(99, 0x046A, 6), (99, 0x0111, 6), (99, 0x0100, 0x0D), (99, 0x0101, 0x0D)]
        # VM run d8cec0d4: owner-drawn wx buttons (wxWindowNR with the label)
        _posted22.clear()
        _modal22["open"] = True
        _mu22.children = lambda dlg: [STATIC22, ("&Yes", "wxWindowNR", (100, 200, 160, 222), 11),
                                      ("&No", "wxWindowNR", (180, 200, 240, 222), 12),
                                      ("", "wxWindowNR", (20, 40, 300, 120), 13)]
        _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: owner-drawn wx buttons (wxWindowNR with the label) are found and clicked "
              "(VM run d8cec0d4)", _clicks22 == [(130, 211)] and not _posted22, "%r %r" % (_clicks22, _posted22))
        _modal22["open"] = True
        _mu22.children = lambda dlg: [STATIC22, ("", "wxWindowNR", (180, 200, 240, 222), 12),
                                      ("", "wxWindowNR", (100, 200, 160, 222), 11),
                                      ("", "wxWindowNR", (20, 40, 300, 120), 13)]
        _clicks22.clear()
        _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: two small untitled children are the Yes/No pair, left one is Yes",
              _clicks22 == [(130, 211)], "%r" % (_clicks22,))
        _modal22["open"] = True
        _clicks22.clear()
        _pcl22.settle_dialog(ui22, set(), "No", "Spiral mode")
        check("settle_dialog: ... and No is the right one",
              _clicks22 == [(210, 211)], "%r" % (_clicks22,))
        _posted22.clear()
        _clicks22.clear()
        _modal22["open"] = True
        _mu22.children = lambda dlg: [("OK", "Button", (100, 200, 160, 222), 11)]
        _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: a one-button box with a Yes named - nothing answers it, closed "
              "(the ladder is only tried for a native box without Button windows)",
              _posted22 == [(99, 0x0010, 0)] and not _clicks22, "%r" % (_posted22,))
        _mu22.children = lambda dlg: [STATIC22]           # the task dialog: no Button window
        for closes, want, name in (
                (0x046A, [(99, 0x046A, 6)], "TDM_CLICK_BUTTON answers the task dialog (first in the ladder)"),
                (0x0111, [(99, 0x046A, 6), (99, 0x0111, 6)], "a classic box answers WM_COMMAND"),
                (0x0100, LADDER22, "a posted Enter answers it (down and up are posted, then checked)")):
            _posted22.clear()
            _modal22.update(open=True, closes_with=closes)
            _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
            check("settle_dialog: " + name,
                  _posted22 == want and not _modal22["open"] and not _keys22, "%r" % (_posted22,))
        _posted22.clear()
        _keys22.clear()
        _modal22.update(open=True, closes_with=None, fg=True, enter_closes=True)
        _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: ... then a real Enter, but only once the box is the foreground window",
              _keys22 == [[(0x0D, False), (0x0D, True)]] and not _modal22["open"]
              and _posted22 == LADDER22, "%r %r" % (_posted22, _keys22))
        _posted22.clear()
        _keys22.clear()
        _modal22.update(open=True, fg=False)
        _pcl22.settle_dialog(ui22, set(), "Yes", "Spiral mode")
        check("settle_dialog: ... and when the box is not in front nothing is typed; it is closed",
              _posted22 == LADDER22 + [(99, 0x0010, 0)] and not _keys22, "%r %r" % (_posted22, _keys22))
        _posted22.clear()
        _modal22.update(open=True, closes_with=None)
        _pcl22.settle_dialog(ui22, set(), "No", "Spiral mode")
        check("settle_dialog: 'No' never types an Enter; unanswered -> closed",
              _posted22 == [(99, 0x046A, 7), (99, 0x0111, 7), (99, 0x0010, 0)] and not _keys22,
              "%r %r" % (_posted22, _keys22))
    finally:
        (_mu22.toplevel, pp.dialog_body, pp.kids, _mu22.children, _eu22.wait_popup,
         _wu22.real_click_screen, _wu22.user32, _wu22.force_set_foreground, _mdu22._send_keys) = _saved22
else:
    print("N/A  settle_dialog (absent on this tree)")

# 23. The readback anchors on the line that was CLICKED. fa run e9071eba:
#     'Fuzzy skin ~ Contour' was set, but the just-changed row (orange label
#     in a teal focus border) dropped out of the band OCR and the phrase
#     scan resolved 'Fuzzy skin' to the next row ('... generator mode ~
#     Displacement') - reported as a failed readback.
if hasattr(pcr, "_read_row"):
    _scan23 = []
    _saved23 = (pcr._find_phrase_row, pp.client_origin, pp.kids, pp.user32, pp.capture_bgr,
                pp.options_viewport, _mdu21.ocr_words_img)
    try:
        pcr._find_phrase_row = lambda app, label, group_substr=None: (_scan23.append(label), 835)[1]
        pp.client_origin = lambda app: (0, 0)
        pp.user32 = types.SimpleNamespace(IsWindowVisible=lambda h: True)
        pp.capture_bgr = lambda app: _np21.zeros((1032, 1920, 3), _np21.uint8)
        pp.options_viewport = lambda app: ((1, 718, 421, 1031),)
        _mdu21.ocr_words_img = lambda crop, scale=3, psm=6: []      # nothing OCR-able
        pp.kids = lambda app: [("Contour", "wxWindowNR", (246, 788, 366, 812), 8, 253, 795),
                               ("Displacement", "wxWindowNR", (246, 818, 366, 842), 9, 253, 825)]
        ui23 = types.SimpleNamespace(app=types.SimpleNamespace(hwnd=4, pid=3))
        value, line = pcr._row_value(ui23, "Fuzzy skin", anchor=(306, 800))
        check("rowcombo readback: the value is read on the clicked line, no phrase scan",
              value == "Contour" and not _scan23, "value %r scans %r" % (value, _scan23))
        _scan23.clear()
        value, line = pcr._row_value(ui23, "Fuzzy skin", anchor=(306, 900))
        check("rowcombo readback: nothing on the clicked line -> the phrase scan places the row",
              value == "Displacement" and _scan23 == ["Fuzzy skin"], "value %r scans %r" % (value, _scan23))
        _scan23.clear()
        value, line = pcr._row_value(ui23, "Fuzzy skin")
        check("rowcombo readback: without an anchor the phrase scan is used once",
              value == "Displacement" and _scan23 == ["Fuzzy skin"], "value %r scans %r" % (value, _scan23))
    finally:
        (pcr._find_phrase_row, pp.client_origin, pp.kids, pp.user32, pp.capture_bgr,
         pp.options_viewport, _mdu21.ocr_words_img) = _saved23
else:
    print("N/A  readback anchor (absent on this tree)")

# 24. A negative value reaches the field WITH its sign. fa run d134da1b:
#   '-100' typed over '-150' read back '100' (the sign-aware readback of r4
#   caught it; before r4 the same edit "passed"). The numeric edit drops a
#   lone '-', so the digits go in first and the minus at the front last.
import harness.agent_business_ui as _abu24  # noqa: E402


class _NumEdit24:
    """The control as run d134da1b showed it: a lone '-' is dropped."""

    def __init__(self):
        self.text, self.caret, self.all = "-150", 0, False
        self.msgs = []

    def setsel(self, start, end):
        self.msgs.append(("setsel", start, end))
        self.all = end == -1
        if not self.all:
            self.caret = start

    def chars(self, piece):
        self.msgs.append(("chars", piece))
        if piece == "\r":
            return
        if self.all:
            self.text, self.all = "", False
            self.caret = 0
        for ch in piece:
            candidate = self.text[:self.caret] + ch + self.text[self.caret:]
            if candidate == "-":
                continue
            self.text, self.caret = candidate, self.caret + 1


def _ui24(ctl):
    wu = types.SimpleNamespace(
        client_to_screen=lambda h, x, y: (x, y), deepest_child_at=lambda h, x, y: 55,
        window_class=lambda h: "Edit",
        user32=types.SimpleNamespace(IsChild=lambda a, b: True, IsWindowEnabled=lambda h: True),
        edit_text=lambda h: ctl.text, msg_click_screen=lambda *a: None,
        _send_msg=lambda t, msg, w, l: (ctl.setsel(w, l) if msg == 0x00B1
                                         else ctl.key(w) if msg == 0x0100 else None),
        msg_text=lambda t, s: ctl.chars(s))
    ui = _abu24.BusinessUI.__new__(_abu24.BusinessUI)
    ui.wu, ui.app = wu, types.SimpleNamespace(hwnd=4)
    ui.guard, ui.owned, ui.pause = (lambda: None), (lambda h: True), (lambda s: None)
    ui.main_input = lambda: ({"width": 1920, "height": 1040}, None)
    return ui


ctl = _NumEdit24()
receipt = _ui24(ctl).edit(10, 20, "-100")
check("edit: a negative value keeps its sign (fa run d134da1b read back '100')",
      receipt["after_text"] == "-100", "after %r msgs %r" % (receipt["after_text"], ctl.msgs))
check("edit: the minus is typed after the digits, at the front",
      ctl.msgs == [("setsel", 0, -1), ("chars", "100"), ("setsel", 0, 0), ("chars", "-"),
                   ("chars", "\r")], "msgs %r" % (ctl.msgs,))
ctl = _NumEdit24()
receipt = _ui24(ctl).edit(10, 20, "150%")
check("edit: a non-negative value is typed in one piece, as before",
      receipt["after_text"] == "150%" and ctl.msgs[1] == ("chars", "150%"),
      "after %r msgs %r" % (receipt["after_text"], ctl.msgs))


import re as _re24  # noqa: E402


class _SpinEdit24(_NumEdit24):
    """fa run 9d2369fb: the minus is dropped wherever it is typed; Down
    steps the value by the control's own amount (5 here)."""

    step = 5

    def chars(self, piece):
        super().chars(piece.replace("-", ""))

    def key(self, vk):
        self.msgs.append(("key", vk))
        found = _re24.search(r"-?\d+", self.text)
        value = int(found.group(0)) if found else 0
        self.text = str(value - self.step)


ctl = _SpinEdit24()
receipt = _ui24(ctl).edit(10, 20, "-100")
downs = [m for m in ctl.msgs if m == ("key", 0x28)]
check("edit: when the minus is refused, the spin's Down key walks the field to the target "
      "(fa run 9d2369fb committed +100)", receipt["after_text"] == "-100",
      "after %r msgs %r" % (receipt["after_text"], ctl.msgs[:8]))
check("edit: the walk is one Down press per step and stops on the target (100 -> -100 by 5 = 40)",
      len(downs) == 40, "downs %d" % len(downs))

# 25. App config per scenario (#296: the 'Add line number' row exists only
#     in develop mode). The conf is seeded with the edit session's profile
#     and nothing else may depend on it; a scenario that needs nothing must
#     not be listed.
if hasattr(nsb, "SCENARIO_CONF"):
    import inspect as _insp25  # noqa: E402
    from harness import agent_business_ui as _abu25, agent_guest as _ag25, native_matrix as _nm25  # noqa: E402
    check("SCENARIO_CONF: every listed scenario is registered",
          set(nsb.SCENARIO_CONF) <= set(_nm25.SCENARIOS), "%r" % (sorted(nsb.SCENARIO_CONF),))
    check("SCENARIO_CONF: lists exactly the cases whose rows need develop mode",
          set(nsb.SCENARIO_CONF) == {"uia_param_gcode_output", "uia_param_census_develop"},
          "%r" % (sorted(nsb.SCENARIO_CONF),))
    check("SCENARIO_CONF: user_mode sits in the conf's app section, where the app reads it "
          "(at the top level the app started in simple mode - fa run 2adcf5cd)",
          all(v.get("app", {}).get("user_mode") == "develop" and set(v) == {"app"}
              for v in nsb.SCENARIO_CONF.values()), "%r" % (nsb.SCENARIO_CONF,))
    check("SCENARIO_CONF: the conf reaches profile.seed_profile (the guest UI and BusinessUI take conf_extra)",
          "conf_extra" in _insp25.signature(_ag25._WindowsUI.__init__).parameters
          and "conf_extra" in _insp25.signature(_abu25.BusinessUI.__init__).parameters)
    src25 = (_Path(nsb.__file__).resolve().parent.parent / "tools" / "native_save_guest.py").read_text(encoding="utf-8")
    check("SCENARIO_CONF: the worker hands it to ProjectUI and records it in its report",
          "SCENARIO_CONF.get(base_scenario(scenario))" in src25 and "conf_extra=conf_extra" in src25
          and 'report["app_conf_extra"]' in src25)
else:
    print("N/A  SCENARIO_CONF (absent on this tree)")

# 26. The Advanced switch is never touched in develop mode. Every click of
#     it saves mode 'advanced' or 'simple' (ParamsPanel.cpp save_mode) and
#     takes the app out of develop mode - fa run 17d2db91 was seeded
#     user_mode=develop and its conf read 'advanced' after the census.
if hasattr(pp, "ADVANCED_SWITCH"):
    _sw26, _on26, _clicks26 = pp.ADVANCED_SWITCH, pp.advanced_on, []
    _rc26, _asw26 = pp.real_click, pp.advanced_switch
    try:
        pp.advanced_on = lambda session: (0.9, 0.1)        # reads as OFF
        pp.advanced_switch = lambda session: ((0, 0, 40, 20), 5)
        pp.real_click = lambda rect: _clicks26.append(rect)
        pp.ADVANCED_SWITCH = True
        pp.ensure_advanced(None, want=True)
        check("ensure_advanced: a switch that reads OFF is flipped in a normal run", len(_clicks26) == 1,
              "%r" % (_clicks26,))
        _clicks26.clear()
        pp.ADVANCED_SWITCH = False
        check("ensure_advanced: in develop mode the switch is left alone and the page counts as advanced",
              pp.ensure_advanced(None, want=True) is True and not _clicks26, "%r" % (_clicks26,))
    finally:
        pp.ADVANCED_SWITCH, pp.advanced_on, pp.real_click, pp.advanced_switch = _sw26, _on26, _rc26, _asw26
    src26 = (_Path(nsb.__file__).resolve().parent.parent / "tools" / "native_save_guest.py").read_text(encoding="utf-8")
    check("the worker turns the switch off for a scenario seeded with user_mode=develop",
          'process_panel.ADVANCED_SWITCH = False' in src26
          and '(conf_extra or {}).get("app", {}).get("user_mode") == "develop"' in src26)
else:
    print("N/A  ADVANCED_SWITCH (absent on this tree)")

# 27. The fa review of 36cbb8c (2026-11-24 02:35): a substring readback
#     passes the wrong pick, the value band took two stacked boxes, an
#     unchecked anchor reading was believed, and the negative walk could
#     overshoot and commit.
if hasattr(pcr, "_shows"):
    check("readback: the target must BE the value's words - 'Rib' is not 'Rectangle'",
          not pcr._shows("Rectangle | ~ Rectangle", "Rib") and pcr._shows("Rib", "Rib"))
    check("readback: 'Rectilinear' does not accept 'Rectilinear Interlaced' (its own popup's next entry)",
          not pcr._shows("Rectilinear Interlaced", "Rectilinear") and pcr._shows("Rectilinear", "Rectilinear"))
    check("readback: digits and signs are ignored - '1 PETG' is PETG, readings are checked one by one",
          pcr._shows("PETG | PETG", "PETG") and pcr._shows("1 PETG | ~ 1 PETG", "PETG")
          and pcr._shows("Outer brim only | ~ Outer brim only", "Outer brim only"))
    check("line names: an empty line counts (a just-changed row drops out of the OCR), "
          "a line without the label does not",
          pcr._line_names("", "^Fuzzy skin") and pcr._line_names("Support/raft base", "^Support/raft base")
          and not pcr._line_names("Fuzzy skin generator mode ~ Displacement", "Interface pattern"))

    _saved27 = (pcr._find_phrase_row, pp.client_origin, pp.kids, pp.user32, pp.capture_bgr,
                pp.options_viewport, _mdu21.ocr_words_img)
    try:
        pcr._find_phrase_row = lambda app, label, group_substr=None: 835
        pp.client_origin = lambda app: (0, 0)
        pp.user32 = types.SimpleNamespace(IsWindowVisible=lambda h: True)
        pp.capture_bgr = lambda app: _np21.zeros((1032, 1920, 3), _np21.uint8)
        pp.options_viewport = lambda app: ((1, 718, 421, 1031),)
        _mdu21.ocr_words_img = lambda crop, scale=3, psm=6: []
        # two value windows 27 px apart (the overhang stack): only the one
        # on the asked line is read
        pp.kids = lambda app: [("10", "wxWindowNR", (246, 774, 366, 800), 8, 253, 781),
                               ("20", "wxWindowNR", (246, 801, 366, 827), 9, 253, 808)]
        ui27 = types.SimpleNamespace(app=types.SimpleNamespace(hwnd=4, pid=3))
        check("read row: of two boxes 27 px apart only the one on the asked line is read "
              "(old band +/-14 took both)",
              pcr._read_row(ui27, 787, 0, 0)[0] == "10" and pcr._read_row(ui27, 814, 0, 0)[0] == "20",
              "%r %r" % (pcr._read_row(ui27, 787, 0, 0)[0], pcr._read_row(ui27, 814, 0, 0)[0]))
        # the anchor line names ANOTHER row: the phrase scan places the row
        _scan27 = []
        pcr._find_phrase_row = lambda app, label, group_substr=None: (_scan27.append(label), 814)[1]
        pp.kids = lambda app: [("Displacement", "wxWindowNR", (246, 774, 366, 800), 8, 253, 781),
                               ("Contour", "wxWindowNR", (246, 801, 366, 827), 9, 253, 808)]
        _ocr27 = {"calls": 0}

        def _words27(crop, scale=3, psm=6):
            # the band (424 wide, starting at viewport y 718) reads the ANCHOR
            # line (y 787) as the generator-mode row; the label row itself
            # sits above it. y is relative to the band: 12 -> 737, 56 -> 781,
            # 83 -> 808.
            if crop.shape[1] == pp.SB_W:
                return [("Fuzzy", 13, 12, 50, 14), ("skin", 70, 12, 40, 14),
                        ("generator", 13, 56, 80, 14), ("mode", 100, 56, 40, 14),
                        ("Contour", 26, 83, 70, 14)]
            return [("Displacement", 4, 3, 90, 12)] if crop.shape[0] < 40 else [("Contour", 4, 3, 70, 12)]
        _mdu21.ocr_words_img = _words27
        value, line = pcr._row_value(ui27, "Fuzzy skin", anchor=(306, 787))
        check("readback: an anchor whose line names another row is not believed - the row the "
              "phrase scan places is read",
              _scan27 == ["Fuzzy skin"], "scans %r value %r" % (_scan27, value))
    finally:
        (pcr._find_phrase_row, pp.client_origin, pp.kids, pp.user32, pp.capture_bgr,
         pp.options_viewport, _mdu21.ocr_words_img) = _saved27

    import re as _re27  # noqa: E402

    class _Spin27(_NumEdit24):
        step = 0.5
        dead = False                             # a dead control ignores Down

        def chars(self, piece):
            super().chars(piece.replace("-", ""))

        def key(self, vk):
            self.msgs.append(("key", vk))
            if self.dead:
                return
            found = _re27.search(r"-?\d+(?:\.\d+)?", self.text)
            self.text = "%.2f" % (float(found.group(0)) - self.step) if found else self.text
    ctl = _Spin27()
    ctl.text = "0.2"
    ctl.dead = False
    ui = _ui24(ctl)
    raised = _raises(ui.edit, 10, 20, "-0.1")
    check("negative edit: a target off the control's grid (0.2 -> -0.1 by 0.5) is refused, "
          "nothing is committed",
          isinstance(raised, str) and raised.startswith("param_negative_off_grid")
          and ("chars", "\r") not in ctl.msgs, "raised %r msgs %r" % (raised, ctl.msgs[-3:]))
    ctl = _Spin27()
    ctl.text = "100"
    ctl.dead = True                      # the control ignores Down
    ui = _ui24(ctl)
    raised = _raises(ui.edit, 10, 20, "-100")
    check("negative edit: a control that does not step is refused before anything is committed",
          isinstance(raised, str) and raised.startswith("param_negative_no_spin")
          and ("chars", "\r") not in ctl.msgs, "raised %r" % (raised,))
    ctl = _Spin27()
    ctl.text = "-150"
    ctl.step = 7                                   # 50 is not a multiple of 7
    ui = _ui24(ctl)
    raised = _raises(ui.edit, 10, 20, "-100")
    check("negative edit: the real field (-150 by 7) cannot reach -100 - refused, nothing committed",
          isinstance(raised, str) and raised.startswith("param_negative_off_grid")
          and ("chars", "\r") not in ctl.msgs, "raised %r" % (raised,))
    ctl = _Spin27()
    ctl.text = "-150"
    ctl.step = 5
    ui = _ui24(ctl)
    ui.edit(10, 20, "-100")
    check("negative edit: the typed digits leave +100; by 5 it walks to -100 in 40 presses and commits",
          ctl.text == "-100.00" and ("chars", "\r") in ctl.msgs
          and len([m for m in ctl.msgs if m == ("key", 40)]) == 40,
          "field %r keys %d" % (ctl.text, len([m for m in ctl.msgs if m == ("key", 40)])))
else:
    print("N/A  readback/negative hardening (absent on this tree)")

# 28. A TEXT field is not committed with Enter. fa run a9cce05e (#296, the
#     filename format): Enter is a newline in a multi-line field - the saved
#     project read '{input_filename_base}_{plate_name}.gcode\n'. The value
#     commits when the field loses focus; the readback is the whole text.
if "enter" in inspect.signature(_abu24.BusinessUI.edit).parameters:
    ctl = _NumEdit24()
    ui = _ui24(ctl)
    receipt = ui.edit(10, 20, "{input_filename_base}_{plate_name}.gcode", enter=False)
    check("edit(enter=False): the text is typed, no Enter is sent, nothing is committed",
          ctl.text == "{input_filename_base}_{plate_name}.gcode" and ("chars", "\r") not in ctl.msgs
          and receipt["committed"] is False, "%r %r" % (ctl.text, ctl.msgs))
    VALUE28 = "{input_filename_base}_{plate_name}.gcode"
    _focus28 = []

    class _UI28:
        def __init__(self, field, newline=False):
            self.app = types.SimpleNamespace(pid=7, hwnd=99)
            self.field, self.typed = field, []
            self.newline = newline            # a field that keeps a stray newline
            ui = self

            class _WU:
                @staticmethod
                def window_class(h):
                    return "wxGLCanvas" if h == 7 else "Edit"       # 7 = the 3D canvas

                @staticmethod
                def window_rect(h):
                    return (246, 787, 366, 813) if h == 55 else (426, 0, 1900, 1031)   # edit : canvas

                @staticmethod
                def _window_pid(_h):
                    return 7

                @staticmethod
                def client_to_screen(_h, _x, _y):
                    return (0, 0)

                @staticmethod
                def edit_text(_h):
                    return ui.field.text
            self.wu = _WU()

        def edit(self, x, y, text, *, enter=True):
            self.typed.append((text, enter))
            # typed; committed only by the caller. `newline`: what Enter used to leave behind
            self.field.text = text + ("\n" if self.newline else "")
            return {"target_hwnd": 55, "after_text": self.field.text, "committed": enter}

        def pause(self, seconds):
            pass

    _fake28 = types.SimpleNamespace(EnumChildWindows=lambda parent, cb, l: (cb(7, l), cb(55, l)),
                                    IsWindowVisible=lambda h: True, IsWindowEnabled=lambda h: True)
    _saved28 = (sys.modules.get("win32gui"), "_win32gui" in sys.modules, pcl._find_phrase_row_any, pp.focus_off_edit)
    try:
        sys.modules["win32gui"] = _fake28
        pcl._find_phrase_row_any = lambda app, phrase, group_substr=None: (800, "Filename format")
        pp.focus_off_edit = lambda session, why="": _focus28.append(why)
        ctl = _NumEdit24()
        ui = _UI28(ctl)
        pcl.uia_set_float(ui, "Filename format", VALUE28, "G-code output")
        check("uia_set_float: a text value is typed without Enter and committed by moving the focus off",
              ui.typed == [(VALUE28, False)] and _focus28 == ["text field commit"], "%r %r" % (ui.typed, _focus28))
        msg = _raises(pcl.uia_set_float, _UI28(_NumEdit24(), newline=True), "Filename format",
                      VALUE28, "G-code output")
        check("uia_set_float: a trailing newline in the field is a readback error, not a pass "
              "(the old numeric readback compared None with None)",
              isinstance(msg, str) and msg.startswith("param_uia_readback:Filename format"), "got %r" % (msg,))
    finally:
        (pcl._find_phrase_row_any, pp.focus_off_edit) = _saved28[2], _saved28[3]
        if _saved28[1]:
            sys.modules["win32gui"] = _saved28[0]
        else:
            sys.modules.pop("win32gui", None)
else:
    print("N/A  text field commit (absent on this tree)")

# 29. A tick that brings up a modal at once counts as done. fa run 6da8ec2c
#     (Spiral vase): the tick took effect and the app asked its question
#     before the frame read back - a modal owns the main window, every
#     further click is blocked and the box never paints as checked, so four
#     attempts read 0.00 and the op was reported failed; on the guest the
#     same tick read 0.88 by timing luck (run 680d5426).
if hasattr(pp, "set_option_checkbox"):
    _state29 = {"modal": False, "clicks": 0}
    _saved29 = (pp.find_option_checkbox, pp.checked_state, pp.real_click, pp.user32, pp.winutil)
    try:
        RECT29 = ((100, 800, 118, 818), 5)
        pp.find_option_checkbox = lambda session, label, group=None: [RECT29]
        pp.checked_state = lambda session, rect: 0.0          # never paints as checked
        pp.real_click = lambda rect: _state29.update(clicks=_state29["clicks"] + 1, modal=True)
        pp.user32 = types.SimpleNamespace(IsWindowEnabled=lambda h: not _state29["modal"])
        got = pp.set_option_checkbox(types.SimpleNamespace(hwnd=1), "Spiral", True, "Special mode")
        check("checkbox: a tick after which the main window is owned by a modal is taken as done "
              "(the state is the opposite of before)",
              got == (True, RECT29[0]) and _state29["clicks"] == 1, "%r clicks %d" % (got, _state29["clicks"]))
        _state29.update(modal=False, clicks=0)
        pp.real_click = lambda rect: _state29.update(clicks=_state29["clicks"] + 1)   # nothing happens
        pp.winutil = types.SimpleNamespace(user32=pp.user32, SetCursorPos=lambda x, y: None,
                                           msg_click_screen=lambda x, y, root=None: None)
        got = pp.set_option_checkbox(types.SimpleNamespace(hwnd=1), "Nope", True, None, tries=2)
        check("checkbox: without a modal a tick that changes nothing is still a failure",
              got == (None, None), "%r" % (got,))
    finally:
        pp.find_option_checkbox, pp.checked_state, pp.real_click, pp.user32, pp.winutil = _saved29
else:
    print("N/A  checkbox modal (absent on this tree)")

# 30. The fa review of 53278b8. (a) a modal that was already up before the
#     click swallowed it - the "state flipped" verdict was a lie; (b) a box
#     answered No puts the setting back while the op said True; (c) a text
#     field whose focus could not be moved off never committed; (d) a text
#     with a digit in it took the Enter branch - the CONTROL decides now.
if hasattr(pcl, "_is_multiline"):
    RECT30 = ((100, 800, 118, 818), 5)
    _saved30 = (pp.find_option_checkbox, pp.checked_state, pp.real_click, pp.user32, pp.winutil,
                pp.ensure_advanced, pp.click_tab, pp.top_dialog_set, pcl.settle_dialog)
    _state30 = {"enabled": True, "modal_after_click": True, "paint": 0.0}
    pp.find_option_checkbox = lambda session, label, group=None: [RECT30]
    pp.checked_state = lambda session, rect: _state30["paint"]
    pp.real_click = lambda rect: _state30.update(enabled=not _state30["modal_after_click"])
    pp.user32 = types.SimpleNamespace(IsWindowEnabled=lambda h: _state30["enabled"])
    pp.winutil = types.SimpleNamespace(user32=pp.user32, SetCursorPos=lambda x, y: None,
                                       msg_click_screen=lambda x, y, root=None: None)
    session30 = types.SimpleNamespace(hwnd=1)
    try:
        _state30.update(enabled=True, modal_after_click=True, paint=0.0)
        got = pp.set_option_checkbox(session30, "Spiral", True, "Special mode")
        check("checkbox: enabled before the click, a modal after it -> taken as toggled",
              got == (True, RECT30[0]), "%r" % (got,))
        _state30.update(enabled=False, modal_after_click=True, paint=0.0)   # somebody else's modal
        got = pp.set_option_checkbox(session30, "Nope", True, None, tries=2)
        check("checkbox: a main window that was disabled BEFORE the click is not evidence of a tick "
              "(the click was swallowed)",
              got == (None, None), "%r" % (got,))
        # (b) run_ops reads the box again after the box was settled
        fake_ui30 = types.SimpleNamespace(app=None, main_input=lambda: None, pause=lambda s: None)
        pp.ensure_advanced = lambda app, want=True: True
        pp.click_tab = lambda app, tab, hint="": True
        pp.top_dialog_set = lambda app: set()
        pp.set_option_checkbox = lambda *a, **k: (True, RECT30[0])
        pcl.settle_dialog = lambda ui, known, answer=None, expect=None: (99, "Spiral mode ...")
        _state30.update(paint=0.0)                    # the app put it back
        msg = _raises(pcl.run_ops, fake_ui30, [{"op": "checkbox", "label": "Spiral", "value": True,
                                                "group": "Special mode", "answer": "Yes"}])
        check("run_ops checkbox: a box that reads OFF after its dialog was settled is "
              "param_checkbox:...:reverted, not a pass",
              isinstance(msg, str) and msg == "param_checkbox:Spiral:reverted", "got %r" % (msg,))
        _state30.update(paint=0.9)
        pcl.run_ops(fake_ui30, [{"op": "checkbox", "label": "Spiral", "value": True,
                                 "group": "Special mode", "answer": "Yes"}])
        check("run_ops checkbox: a box that reads ON after its dialog passes", True)
        # (c) the text field's focus must have left the Edit
        _wu30 = types.SimpleNamespace(user32=types.SimpleNamespace(GetWindowLongW=lambda h, i: 0x0004))
        check("uia_set_float: a multi-line control is a text field whatever the value looks like",
              pcl._is_multiline(_wu30, 55, "v2") and not pcl._is_multiline(
                  types.SimpleNamespace(user32=types.SimpleNamespace(GetWindowLongW=lambda h, i: 0x0080)), 55))
        check("uia_set_float: without a readable style the old rule holds (a value with no digit is text)",
              pcl._is_multiline(types.SimpleNamespace(), 55, "{input_filename_base}") and not pcl._is_multiline(
                  types.SimpleNamespace(), 55, "12"))
        ctl = _NumEdit24()
        ui = _UI28(ctl)
        ui.wu.user32 = _wu30.user32
        _focus28[:] = []
        _saved_focus30 = (pp.focus_off_edit, pcl._find_phrase_row_any, sys.modules.get("win32gui"),
                          "_fake28" in globals())
        pp.focus_off_edit = lambda session, why="": "Edit"       # could not move the focus off
        if "_fake28" in globals():
            pcl._find_phrase_row_any = lambda app, phrase, group_substr=None: (800, "Filename format")
            sys.modules["win32gui"] = _fake28                     # the edit and the canvas anchor
        try:
            msg = _raises(pcl.uia_set_float, ui, "Filename format", "v2 {a}", "G-code output")
        finally:
            pp.focus_off_edit, pcl._find_phrase_row_any = _saved_focus30[0], _saved_focus30[1]
            if _saved_focus30[3]:
                sys.modules["win32gui"] = _saved_focus30[2]
        check("uia_set_float: a text field whose focus stays in the Edit is an error "
              "(its text would read equal without a commit)",
              isinstance(msg, str) and msg.startswith("param_text_field_focus_stuck"), "got %r" % (msg,))
    finally:
        (pp.find_option_checkbox, pp.checked_state, pp.real_click, pp.user32, pp.winutil,
         pp.ensure_advanced, pp.click_tab, pp.top_dialog_set, pcl.settle_dialog) = _saved30
else:
    print("N/A  r9 review (absent on this tree)")


def _code31(fn, *args):
    """The message a call raised with (any ValueError: _require's _InvalidEvidence is
    not the ProtocolError _raises waits for), or None."""
    try:
        fn(*args)
    except ValueError as exc:
        return str(exc)
    return None


# 31. The `_std02` suffix rule (2026-11-24): `<uia_param_x>_std02` is `uia_param_x` on
#     fixtures/feishu_std_cube.3mf - the same ops, pilot, goal, tab spec, app conf and
#     edit_project dispatch, another fixture - for every param scenario the matrix
#     knows. Offline: the dispatch is read through recorders, nothing opens the app.
import hashlib as _h31  # noqa: E402
import io as _io31  # noqa: E402
import json as _json31  # noqa: E402
import zipfile as _zip31  # noqa: E402
import harness.param_mix_census as _mix31  # noqa: E402
from harness import agent_protocol as _ap31, native_pilots as _np31  # noqa: E402
from harness.native_matrix import SCENARIOS as _ALL31  # noqa: E402
from harness.native_matrix import scenario_names as _names31, scenario_spec as _tab31  # noqa: E402
from harness.native_save_session import native_contract as _contract31, native_spec as _found31  # noqa: E402
from harness.run_verdict import contract_digest as _digest31  # noqa: E402

_SUFFIX31, _BASELINE31 = _ap31.STD_SUFFIX, _ap31.STD_SCENARIO
_CUBE31 = (_ap31.LAYER_FIXTURE, _ap31.LAYER_FIXTURE_SHA256)
_STD31 = (_ap31.STD_FIXTURE, _ap31.STD_FIXTURE_SHA256)
_sha31 = lambda pair: _h31.sha256((_Path(root) / pair[0]).read_bytes()).hexdigest()
check("std02: both fixtures on disk are the pinned bytes",
      _sha31(_CUBE31) == _CUBE31[1] and _sha31(_STD31) == _STD31[1])


def _ops31(ops):
    """Ops as the fixture sees them: a rowcombo's target is the one part that may differ."""
    return None if ops is None else [dict(op, target=None) if op.get("op") == "rowcombo" else op for op in ops]


def _route31(scenario):
    """The edit_project branches a scenario takes, as (function, scenario it was handed)."""
    calls = []
    owners = [(nsb, name) for name in ("edit_param_cases", "edit_param_layer_pair", "edit_layer", "move_x",
                                       "edit_process_combo", "edit_quality_enums", "add_mix_recipes",
                                       "assign_filament_slot2")] + [(pcl, "census_param_pages"), (_mix31, "census_mix_dialog")]
    saved = [(owner, name, owner.__dict__[name]) for owner, name in owners]
    try:
        for owner, name in owners:
            def spy(ui, *rest, name=name):
                calls.append((name, rest[0] if name == "edit_param_cases" else None))
            owner.__dict__[name] = spy
        nsb.edit_project(None, scenario, None)
    finally:
        for owner, name, genuine in saved:
            owner.__dict__[name] = genuine
    return calls


def _same_pilot31(name, twin):
    """One pilot object and one goal for both; a probe has none, and so has its twin."""
    try:
        return (_np31.pilot_module(twin) is _np31.pilot_module(name)
                and _np31.business_goal(twin) == _np31.business_goal(name))
    except ValueError:
        return (_code31(_np31.pilot_module, name) is not None
                and _code31(_np31.pilot_module, twin) is not None)


def _holds31(name, suffix=_SUFFIX31, pair=_STD31):
    twin = name + suffix
    try:
        route, twin_route = _route31(name), _route31(twin)
        return (_tab31("script", twin) == _tab31("script", name)
                and _tab31("zcode", twin) == _tab31("zcode", name)
                and _ops31(nsb.scenario_ops(twin)) == _ops31(nsb.scenario_ops(name))
                and _same_pilot31(name, twin)
                and _np31.native_fixture(name) == _CUBE31 and _np31.native_fixture(twin) == pair
                and nsb.SCENARIO_CONF.get(_ap31.base_scenario(twin)) == nsb.SCENARIO_CONF.get(name)
                and [what for what, _scenario in twin_route] == [what for what, _scenario in route]
                and all(scenario in (None, twin) for _what, scenario in twin_route)
                and _found31(_digest31(_contract31("script", twin))) == ("script", twin)
                and _found31(_digest31(_contract31("zcode", twin))) == ("zcode", twin)
                and _digest31(_contract31("script", twin)) != _digest31(_contract31("script", name)))
    except Exception as exc:  # noqa: BLE001 - named with the scenario below
        print("   std02 %s: %s: %s" % (name, type(exc).__name__, exc))
        return False


_names31 = set(_names31())
_twinned31 = [name for name in sorted(_ALL31) if name.startswith("uia_param_") and name + _SUFFIX31 in _names31]
_broken31 = [name for name in _twinned31 if not _holds31(name)]
check("std02: %d param scenarios - the twin has its base's ops, pilot, goal, tab spec, app conf "
      "and dispatch on the precondition fixture, the base keeps the cube fixture, and each "
      "contract resolves to its full name" % len(_twinned31), not _broken31, "failing: %r" % (_broken31,))

# The shapes plate is the second suffixed fixture (the rows' models: a cube, a
# cylinder, a bridge, overhang steps, a second cube on extruder 3): the same rule
# with its own fixture, and its save-only baseline.
_SHAPES31 = (_ap31.SHAPES_FIXTURE, _ap31.SHAPES_FIXTURE_SHA256)
check("shapes: the plate on disk is the pinned bytes", _sha31(_SHAPES31) == _SHAPES31[1])
_twinned_shapes31 = [name for name in _twinned31 if name + _ap31.SHAPES_SUFFIX in _names31]
_broken_shapes31 = [name for name in _twinned_shapes31
                    if not _holds31(name, _ap31.SHAPES_SUFFIX, _SHAPES31)]
check("shapes: every twinned param scenario (%d of %d) runs on the plate with its base's ops "
      "(filament targets as on the cube), pilot, tab spec and dispatch, and its contract "
      "resolves to its own full name" % (len(_twinned_shapes31), len(_twinned31)),
      len(_twinned_shapes31) == len(_twinned31) and not _broken_shapes31,
      "failing: %r" % (_broken_shapes31,))
check("shapes: the plate's save-only baseline opens the plate, keeps the cube's PETG rows, "
      "and has no twin of its own",
      _np31.native_fixture(_ap31.SHAPES_SCENARIO) == _SHAPES31
      and _np31.pilot_module(_ap31.SHAPES_SCENARIO).CASE_ID == "param_shapes_save_only"
      and nsb.scenario_ops(_ap31.SHAPES_SCENARIO) == []
      and [op.get("target") for op in nsb.scenario_ops("uia_param_support_filament" + _ap31.SHAPES_SUFFIX)
           if op.get("op") == "rowcombo"] == ["PETG"]
      and _ap31.SHAPES_SCENARIO + _SUFFIX31 not in _names31
      and _ap31.SHAPES_SCENARIO + _ap31.SHAPES_SUFFIX not in _names31)

# Every other fixture suffix follows the same rule (the rows' own models on the
# precondition settings, added 2026-11-24): the bytes are the pin, each twinned
# param scenario holds on it, its baseline is registered with no ops and no twin.
for _sfx in [s for s in _ap31.FIXTURE_SUFFIXES if s not in (_SUFFIX31, _ap31.SHAPES_SUFFIX)]:
    _pair = _ap31.FIXTURE_SUFFIXES[_sfx]
    _tw = [name for name in _twinned31 if name + _sfx in _names31]
    _br = [name for name in _tw if not _holds31(name, _sfx, _pair)]
    _base, _case = _ap31.BASELINES[_sfx]
    check("fixture %s: the bytes on disk are the pin; every twinned param scenario (%d of %d) "
          "holds on it with its base's ops, pilot, tab spec and dispatch; its baseline is "
          "registered, has no ops and no twin" % (_sfx, len(_tw), len(_twinned31)),
          _sha31(_pair) == _pair[1] and len(_tw) == len(_twinned31) and not _br
          and _np31.pilot_module(_base).CASE_ID == _case and nsb.scenario_ops(_base) == []
          and _np31.native_fixture(_base) == _pair and _base + _sfx not in _names31
          and _base + _SUFFIX31 not in _names31,
          "failing: %r" % (_br[:6],))

# The settings are read without loading the meshes (VM run e3422b44: the app opened,
# sliced and saved the 3DBenchy fixture; the verifier refused it because its mesh member
# is 18 MB, over the 16 MB a member may have). The member rule itself does not move.
from harness.project_3mf import _archive as _archive31, _settings as _settings31  # noqa: E402
from harness.script_verify import _InvalidEvidence as _Invalid31  # noqa: E402
_boat31 = (_Path(root) / "fixtures/feishu_std_boat.3mf").read_bytes()
try:
    _archive31(_boat31, lambda: False)
    _boat_whole31 = "accepted"
except _Invalid31 as _exc31:
    _boat_whole31 = str(_exc31)
check("project_3mf: a project whose mesh member is over 16 MB (the 3DBenchy fixture) is still refused "
      "when read as a whole, and is read for its settings alone",
      _boat_whole31 == "project_zip_member" and _settings31(_boat31, lambda: False).get("layer_height") == "0.2",
      "whole: %r" % (_boat_whole31,))

_baseline31 = _BASELINE31
_controls31 = (_np31.native_fixture("uia_param_save_only") == _CUBE31
               and _np31.native_fixture(_baseline31) == _STD31
               and _np31.pilot_module("uia_param_save_only").CASE_ID == "param_save_only_control"
               and _np31.pilot_module(_baseline31).CASE_ID == "param_std_save_only"
               and nsb.scenario_ops("uia_param_save_only") == [] and nsb.scenario_ops(_baseline31) == []
               and "uia_param_save_only" + _SUFFIX31 not in _names31 and _baseline31 + _SUFFIX31 not in _names31)
check("std02: the two save-only controls are registered without ops on their own fixture and have no twin",
      _controls31)


def _refused31(name):
    lookups = (lambda: _tab31("script", name), lambda: _tab31("zcode", name), lambda: _np31.pilot_module(name))
    return all(_code31(lookup) is not None for lookup in lookups)


_outside31 = ["uia_hybrid_layer", "quality_a", "pilot_strength", "uia_param_bogus", "_std02"]
check("std02: a `_std02` name outside the param family, or of an unregistered base, is no scenario",
      all(_refused31(name + _SUFFIX31) for name in _outside31), "%r" % (_outside31,))

# The PETG target. The extruder popups paint "<n> <filament type>": Default / 1 PETG /
# 2 PLA / 3 PLA / 4 PLA / 5 PLA on the cube (census 67690ed4 / c814315c); every filament
# of the precondition fixture is PLA, so 'PETG' names no row there and row 1 reads "1 PLA".
_petg31 = [name for name in sorted(nsb.PARAM_OPS)
           if any(op.get("op") == "rowcombo" and op.get("target") == "PETG" for op in nsb.PARAM_OPS[name])]


def _swapped31(before, after):
    """True when `after` is `before` with the PETG rowcombo targets reading "1 PLA"."""
    return (len(before) == len(after)
            and all(a == b or (a.get("op") == "rowcombo" and a.get("target") == "PETG"
                               and dict(b, target="PETG") == a) for a, b in zip(before, after))
            and any(op.get("target") == "1 PLA" for op in after))


check("std02: in the twin of each of the %d scenarios that pick the PETG extruder (%s) that target "
      "reads '1 PLA' and nothing else changes; the base's ops are the table's own objects"
      % (len(_petg31), " ".join(name.replace("uia_param_", "") for name in _petg31)),
      _petg31 and all(nsb.scenario_ops(name) is nsb.PARAM_OPS[name]
                      and _swapped31(nsb.PARAM_OPS[name], nsb.scenario_ops(name + _SUFFIX31))
                      for name in _petg31), "%r" % (_petg31,))


def _popup31(labels):
    """OCR words of a popup: one line of tokens per label."""
    words = []
    for row, label in enumerate(labels):
        words += [(token, 12 * column, 24 * row, 30, 12) for column, token in enumerate(label.split(" "))]
    return words


_rows31 = lambda labels, target: [text for _x, _y, text in pp.popup_line_hits(_popup31(labels), target)]
_cube_popup31 = _rows31(["Default", "1 PETG", "2 PLA", "3 PLA", "4 PLA", "5 PLA"], "PETG")
_std_popup31 = _popup31(["Default", "1 PLA", "2 PLA", "3 PLA", "4 PLA", "5 PLA"])
check("std02: on the cube's popup 'PETG' is one row; on the precondition fixture's popup it is none",
      _cube_popup31 == ["1 PETG"] and _rows31(["Default", "1 PLA", "2 PLA", "3 PLA", "4 PLA", "5 PLA"], "PETG") == [])
check("std02: on the precondition fixture's popup '1 PLA' is row 1 alone, a preset name is no row, "
      "'PLA' is all five rows (the first one read would be clicked)",
      [text for _x, _y, text in pp.popup_line_hits(_std_popup31, "1 PLA")] == ["1 PLA"]
      and pp.popup_line_hits(_std_popup31, "Generic PLA") == []
      and [text for _x, _y, text in pp.popup_line_hits(_std_popup31, "PLA")]
      == ["1 PLA", "2 PLA", "3 PLA", "4 PLA", "5 PLA"])
check("std02: the rowcombo readback accepts a row that paints '1 PLA' for the target '1 PLA'",
      pcr._shows("1 PLA", "1 PLA"))

# 32. The layer schedule a case asserts was measured on the cube: it belongs to the
#     fixture (2026-11-24). make_verify asserts it on the cube only; on the precondition
#     fixture the layers are recorded until a run has measured them. analyze_gcode is
#     stubbed: what is decided here is what is done with its count.
_cube_raw31, _std_raw31 = ((_Path(root) / pair[0]).read_bytes() for pair in (_CUBE31, _STD31))


def _archive31(config):
    """A one-member project: the settings config alone is all the verifier reads."""
    buffer = _io31.BytesIO()
    with _zip31.ZipFile(buffer, "w") as archive:
        archive.writestr("Metadata/project_settings.config", config)
    return buffer.getvalue()


_cube_config31 = _json31.loads(_zip31.ZipFile(_io31.BytesIO(_cube_raw31)).read("Metadata/project_settings.config"))
_other_raw31 = _archive31(_json31.dumps(_cube_config31).encode())       # same settings, another archive
_edited_config31 = dict(_cube_config31, layer_height="0.3")
_edited_raw31 = _archive31(_json31.dumps(_edited_config31).encode())
_verify31 = pcl.make_verify("sim32_schedule", {}, schedule={"layer_count": 68, "last_z": "27.2"})
_layers31 = {"layer_count": 134, "first_z": "0.25", "last_z": "27.05", "sha256": "0" * 64}
_genuine_analyze31 = pcl.analyze_gcode
try:
    pcl.analyze_gcode = lambda raw, **options: dict(_layers31)
    _on_std31 = _verify31(_std_raw31, _std_raw31, b"gcode")
    _on_cube31 = _code31(_verify31, _cube_raw31, _cube_raw31, b"gcode")
    _on_other31 = _code31(_verify31, _other_raw31, _other_raw31, b"gcode")
    pcl.analyze_gcode = lambda raw, **options: dict(_layers31, layer_count=68, first_z="0.4", last_z="27.2")
    _cube_ok31 = _verify31(_cube_raw31, _cube_raw31, b"gcode")
finally:
    pcl.analyze_gcode = _genuine_analyze31
check("schedule: on the precondition fixture a make_verify verifier does not raise on 134 layers "
      "and records the measured count, first Z and last Z",
      _on_std31 == {"case_id": "sim32_schedule", "other_settings_preserved": True, "layer_count": 134,
                    "last_z": "27.05", "gcode_sha256": "0" * 64, "first_z": "0.25", "schedule_asserted": False},
      "got %r" % (_on_std31,))
check("schedule: on the cube the same verifier still raises on 134 layers",
      _on_cube31 == "param_layer_count", "got %r" % (_on_cube31,))
check("schedule: ... and passes on 68 layers with the result it always gave",
      _cube_ok31 == {"case_id": "sim32_schedule", "other_settings_preserved": True, "layer_count": 68,
                     "last_z": "27.2", "gcode_sha256": "0" * 64}, "got %r" % (_cube_ok31,))
check("schedule: a fixture nobody pinned is refused", _on_other31 == "param_fixture_unregistered",
      "got %r" % (_on_other31,))
# analyze_gcode refuses some exports of a plate (two object tools on the shapes plate:
# gcode_multiple_object_tools, fa706g3 70da5cd5). With nothing pinned the refusal is
# recorded; where something is asserted it still propagates.
def _refusing31(raw, **options):
    raise ValueError("gcode_multiple_object_tools")
try:
    pcl.analyze_gcode = _refusing31
    _refused_std31 = _verify31(_std_raw31, _std_raw31, b"gcode")
    _refused_cube31 = _code31(_verify31, _cube_raw31, _cube_raw31, b"gcode")
    _ironing31 = pcl.make_verify("sim32_ironing", {}, schedule={"layer_count": 68, "last_z": "27.2"},
                                 ironing={"speed_comment": "x", "min_moves": 1})
    _refused_iron31 = _code31(_ironing31, _std_raw31, _std_raw31, b"gcode")
finally:
    pcl.analyze_gcode = _genuine_analyze31
check("schedule: a layer analysis that refuses the export is recorded, not raised, on a fixture "
      "with no pin (values and preserved settings still judged)",
      _refused_std31.get("other_settings_preserved") is True
      and _refused_std31.get("schedule_error") == "gcode_multiple_object_tools"
      and "layer_count" not in _refused_std31, "got %r" % (_refused_std31,))
check("schedule: ... and still raised where something is asserted (the cube's pin, an ironing count)",
      _refused_cube31 == "gcode_multiple_object_tools"
      and _refused_iron31 == "gcode_multiple_object_tools",
      "got %r %r" % (_refused_cube31, _refused_iron31))

# 33. The save-only controls run the cases' path with no op and are judged by the same
#     rule with an empty change set; the G-code facts are recorded. The real fixture
#     bytes are project and fixture at once (every setting preserved by construction).
_gcode31 = (b";LAYER_CHANGE\n;TYPE:External perimeter\nG1 X10 Y10 E1 F1800\nG1 X20 Y10 E2\n"
            b"G0 X30 Y10 F9000\n;LAYER_CHANGE\n;TYPE:Sparse infill\nG1 X40 Y10 E3 F2400\n")
_control31 = _np31.pilot_module("uia_param_save_only").verify_business
_baseline_verify31 = _np31.pilot_module(_baseline31).verify_business
_saved31 = _control31(_cube_raw31, _cube_raw31, _gcode31)
check("save-only control: a project saved unchanged passes the existing preserved rule (empty change set) "
      "and records the layer changes, the feeds and an empty config diff",
      _saved31.get("other_settings_preserved") is True and _saved31.get("case_id") == "param_save_only_control"
      and _saved31.get("layer_change_lines") == 2
      and _saved31.get("config_changes") == {"count": 0, "keys": "", "sample": []}
      and _saved31.get("feature_speeds", {}).get("travel", {}).get("first") == "9000x1"
      and _saved31.get("feature_speeds", {}).get("Sparse infill", {}).get("other") == "2400x1"
      and "schedule_error" in _saved31, "got %r" % (_saved31,))
check("save-only control: a project whose config changed is refused by the existing rule",
      _code31(_control31, _edited_raw31, _cube_raw31, _gcode31) == "pilot_unrelated_setting_changed:layer_height",
      "got %r" % (_code31(_control31, _edited_raw31, _cube_raw31, _gcode31),))
_baseline_run31 = _baseline_verify31(_std_raw31, _std_raw31, _gcode31)
check("save-only baseline: the precondition fixture saved unchanged passes the same rule and records its facts",
      _baseline_run31.get("other_settings_preserved") is True and _baseline_run31.get("case_id") == "param_std_save_only"
      and _baseline_run31.get("layer_change_lines") == 2
      and _baseline_run31.get("config_changes") == {"count": 0, "keys": "", "sample": []},
      "got %r" % (_baseline_run31,))
# The result is the business check's detail, which run_verdict bounds to 4096 characters;
# the first real control (baa3168, 51 changed keys each with its values) overflowed it and
# was reported native_evidence_unavailable. A save that rewrote every migrated key and
# added the app's defaults still has to fit.
from harness import pilot_common as _pcm35  # noqa: E402
_migrated35 = dict(_cube_config31)
for _key35 in _pcm35._VECTOR_MIGRATIONS:
    if isinstance(_migrated35.get(_key35), str):
        _migrated35[_key35] = [_migrated35[_key35]]
_migrated35.update(_pcm35._ADDED_DEFAULTS)
_wide35 = b"".join(b";LAYER_CHANGE\n;TYPE:F%d\nG1 X10 Y10 E1 F1800\nG1 X20 Y10 E2\n" % (n,) for n in range(2))
_wide35 = b"".join(b";TYPE:Feature number %d\nG1 F1800\nG1 X10 Y%d E1\nG1 X20 Y%d E2\nG1 F2400\nG1 X30 Y%d E3\n" % (n, n, n, n)
                   for n in range(16)) + _wide35
_migrated_raw35 = _archive31(_json31.dumps(_migrated35).encode())
_big35 = _control31(_migrated_raw35, _cube_raw31, _wide35)
check("save-only control: a save that rewrote %d migrated keys and added %d defaults passes the rule, "
      "counts every change and keeps its result inside the 4096-character check detail"
      % (len(_pcm35._VECTOR_MIGRATIONS), len(_pcm35._ADDED_DEFAULTS)),
      _big35.get("other_settings_preserved") is True
      and _big35["config_changes"]["count"] == len(_pcm35._VECTOR_MIGRATIONS) + len(_pcm35._ADDED_DEFAULTS)
      and len(_json31.dumps(_big35, sort_keys=True)) <= 4096,
      "count %r len %r" % (_big35.get("config_changes", {}).get("count"), len(_json31.dumps(_big35, sort_keys=True))))

failed = [n for n, ok in results if not ok]
print("\n%d checks, %d failed" % (len(results), len(failed)))
sys.exit(1 if failed else 0)
