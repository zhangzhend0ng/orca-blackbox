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
         "set_option_checkbox": ["session", "label_substr", "want_checked"]},
}
for module, funcs in API.items():
    for fname, params in funcs.items():
        fn = getattr(module, fname, None)
        got = list(inspect.signature(fn).parameters)[:len(params)] if callable(fn) else None
        check("%s.%s exists, params %s" % (module.__name__.split(".")[-1], fname, params),
              got == params, "got %r" % (got,))


# (check() is defined at the top, before the API-surface block)


# ---------------------------------------------------------------- fake page
class Page:
    def __init__(self, rows, spans, dead=False, revive_works=True):
        self.rows = rows            # [(text, page_y)]
        self.spans = spans          # group -> (y_top, y_bottom) page coords
        self.offset = 0
        self.dead = dead
        self.revive_works = revive_works
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

    def wheel(self, _session, _vp, notches, delta=-120):
        self.wheels += 1
        if self.dead:
            return
        step = ROW_H * notches * (-1 if delta < 0 else 1)
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

failed = [n for n, ok in results if not ok]
print("\n%d checks, %d failed" % (len(results), len(failed)))
sys.exit(1 if failed else 0)
