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
#     (VM run 210446b4: 'Overhang speed', five boxes at a 27px pitch, the
#     label centred on the block). Field i is the i-th Edit from the top.
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
finally:
    if _fake_before is None:
        sys.modules.pop("win32gui", None)
    else:
        sys.modules["win32gui"] = _fake_before

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

# 22. A modal the app opens after a checkbox is found and answered. Spiral
#     vase (VM run 49723134): the Yes/No box stayed open - wait_popup only
#     knows the combo popup - and the next guard raised
#     main_window_modal_blocked.
from harness import export_util as _eu22, mixing_util as _mu22, winutil as _wu22  # noqa: E402
import harness.param_case_lib as _pcl22  # noqa: E402

if hasattr(_pcl22, "settle_dialog"):
    _clicks22, _posted22 = [], []
    _modal22 = {"open": False, "command_closes": False}   # main window 4 disabled = a modal

    class _U22:
        """stands in for user32: PostMessageW is recorded, not called"""

        @staticmethod
        def PostMessageW(h, msg, w, _l):
            _posted22.append((h, msg, w))
            if msg == 0x0111 and _modal22["command_closes"]:
                _modal22["open"] = False       # the box answered: the modal is gone

        @staticmethod
        def IsWindowEnabled(h):
            return not (h == 4 and _modal22["open"])

    _saved22 = (_mu22.toplevel, pp.dialog_body, _mu22.children, _eu22.wait_popup,
                _wu22.real_click_screen, _wu22.user32)
    try:
        _wu22.user32 = _U22
        _wu22.real_click_screen = lambda x, y: _clicks22.append((x, y))
        ui22 = types.SimpleNamespace(app=types.SimpleNamespace(pid=3, hwnd=4), pause=lambda s: None)
        # NOT #32770: the box is found by its effect on the main window
        _mu22.toplevel = lambda pid: [("wxWindowNR", "Orca", (800, 400, 1120, 560), 99)]
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
        _modal22["open"] = True
        pp.dialog_body = lambda pid, dlg: SPIRAL
        _mu22.children = lambda dlg: [("...", "Static", (1, 1, 2, 2), 5),
                                      ("&Yes", "Button", (100, 200, 160, 222), 11),
                                      ("&No", "Button", (180, 200, 240, 222), 12)]
        r = _pcl22.settle_dialog(ui22, set(), "Yes")
        check("settle_dialog: the spiral box is answered Yes - the Yes button is clicked, not closed",
              r[0] == 99 and _clicks22 == [(130, 211)] and not _posted22,
              "%r %r" % (_clicks22, _posted22))
        _clicks22.clear()
        _mu22.children = lambda dlg: [("...", "Static", (1, 1, 2, 2), 5),
                                      ("\u662f(&Y)", "Button", (100, 200, 160, 222), 11),
                                      ("\u5426(&N)", "Button", (180, 200, 240, 222), 12)]
        _pcl22.settle_dialog(ui22, set(), "Yes")
        check("settle_dialog: a box labelled in the Windows language - Yes is the first of two",
              _clicks22 == [(130, 211)], "%r" % (_clicks22,))
        _clicks22.clear()
        _mu22.children = lambda dlg: [("&No", "Button", (100, 200, 160, 222), 11),
                                      ("&Yes", "Button", (180, 200, 240, 222), 12)]
        _pcl22.settle_dialog(ui22, set(), "Yes")
        check("settle_dialog: ... unless the first button says No",
              _clicks22 == [(210, 211)], "%r" % (_clicks22,))
        _clicks22.clear()
        _mu22.children = lambda dlg: [("&Yes", "Button", (100, 200, 160, 222), 11),
                                      ("&No", "Button", (180, 200, 240, 222), 12)]
        _pcl22.settle_dialog(ui22, set())          # no answer named
        check("settle_dialog: an unnamed dialog is closed, never answered",
              _posted22 == [(99, 0x0010, 0)] and not _clicks22, "%r %r" % (_clicks22, _posted22))
        _posted22.clear()
        _mu22.children = lambda dlg: [("OK", "Button", (100, 200, 160, 222), 11)]
        _pcl22.settle_dialog(ui22, set(), "Yes")
        check("settle_dialog: a one-button box is closed even when an answer is named "
              "(the command is tried first and does not close it)",
              _posted22 == [(99, 0x0111, 6), (99, 0x0010, 0)] and not _clicks22,
              "%r %r" % (_clicks22, _posted22))
        _posted22.clear()
        # VM run eab35b9a: Windows 11 message boxes draw their buttons in a
        # DirectUI child - no Button window; the box was closed = No.
        _mu22.children = lambda dlg: [("...", "Static", (1, 1, 2, 2), 5)]
        _modal22["command_closes"] = True
        _wc22 = _wu22.window_class
        _wu22.window_class = lambda h: "#32770"
        try:
            _pcl22.settle_dialog(ui22, set(), "Yes")
        finally:
            _wu22.window_class = _wc22
        check("settle_dialog: a box without Button windows is answered by WM_COMMAND IDYES "
              "(VM run eab35b9a)",
              _posted22 == [(99, 0x0111, 6)] and not _clicks22 and not _modal22["open"],
              "%r %r" % (_clicks22, _posted22))
        _posted22.clear()
        _modal22.update(open=True, command_closes=False)
        _pcl22.settle_dialog(ui22, set(), "No")
        check("settle_dialog: a command that does not close the box -> closed as before",
              _posted22 == [(99, 0x0111, 7), (99, 0x0010, 0)] and not _clicks22,
              "%r %r" % (_clicks22, _posted22))
    finally:
        (_mu22.toplevel, pp.dialog_body, _mu22.children, _eu22.wait_popup,
         _wu22.real_click_screen, _wu22.user32) = _saved22
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

failed = [n for n, ok in results if not ok]
print("\n%d checks, %d failed" % (len(results), len(failed)))
sys.exit(1 if failed else 0)
