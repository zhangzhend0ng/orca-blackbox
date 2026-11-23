#!/usr/bin/env python3
# process_panel.py — generic driver for the RIGHT-SIDEBAR Process panel
# (settings sidebar), extracted from m4g_mixing_sublayer (which remains the
# Color-Mixing-specific consumer). Everything here is calibrated for the
# MAXIMIZED window (08-31 recalibration) and window-size-adaptive:
#   - the sidebar is TOP-anchored (Process title row ~y616, tab row ~y697
#     at any window height); the options viewport under the tab row
#     STRETCHES with the window — never assume a fixed band, read it from
#     the panel rect (view_band).
#   - the scroll offset is SHARED across pages: force the viewport back to
#     top when arriving from a deep-scrolled page (RESET_WHEEL_NOTCHES).
#   - option labels are PAINTED by OG_CustomCtrl (no label HWNDs): rows are
#     located positionally (group title rect + OCR), values via the row's
#     Edit/checkbox controls.
#   - committing an Edit keeps keyboard focus and blocks wheel/clicks:
#     neutralize_focus() after every real_edit_set.
#
# All clicks are REAL (SendInput) or message-level per the m4g strategies.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from harness.anchors import CHECKED_FRACTION, capture_bgr  # noqa: E402

user32 = ctypes.WinDLL("user32")
# 64-bit-safe prototype: CB_SELECTSTRING passes a string POINTER in lParam
user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_ulonglong, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_longlong

SB_W = 424
VIEW_Y0, VIEW_Y1 = 700, 800  # fallback options band; the real band is read
                             # from the viewport panel (view_band) — it
                             # stretches with the window (73px windowed,
                             # 313px maximized)
RESET_WHEEL_NOTCHES = 40  # tab switch: force the options viewport back to
                          # top. Recalibrated 08-31: the scroll offset is
                          # SHARED across pages, so arriving from a
                          # max-scrolled Multimaterial page left Quality
                          # mid-content and 15 notches (~400-600px) could
                          # not recover the top (measured: Layer height
                          # unreachable on the 0.4-restore visit).

# Group-title geometry, measured on the 2.4.0 guest build (census run
# c101c0f4): every options-group title is a 393x18 window at x 13; the unit
# labels ('mm/s', 'mm/s or %', 'mm'...) are titled windows too, 120x26 at
# x 203, and must stay out of the title set (see group_titles).
GROUP_TITLE_MIN_W = 300
GROUP_TITLE_MAX_X = 60
GROUP_TITLE_MAX_H = 30
WHEEL_STEP_PX = 60          # one wheel notch moves the options page 60px
                            # (two rows), measured down and up in c101c0f4
# An ungrouped label scan has no title to position by, so it must be able
# to cross a whole page (Quality: 102 rows = ~51 notches). It ends at the
# page end through the stall guard; the notch and time caps only bound a
# label that is not on the page at all (the 12/26 notches of r3 covered
# 24 rows from the start and never reached 'Detect overhang walls' 55 rows
# down: overhang_speeds, run f775cd31).
SCAN_NOTCHES = 160
SCAN_SECONDS = 240.0   # a step costs >= 2.5s with OCR: 90s never
                        # reached 110 notches (review V1); the page end,
                        # not this cap, ends a search for a missing label
# A combo's popup list opens straight below the control and is NOT kept off
# the taskbar: with the 'Print sequence' combo at the viewport bottom
# (y 961-987) its popup was y 993-1049 while the work area ends at 1032, and
# the click on 'By object' resolved to Shell_TrayWnd (by_object run
# 6640e4a9, census c101c0f4). Park the row this far above the work-area
# bottom before opening anything (7 rows at the popup's 28px pitch).
POPUP_ROOM = 220
# OCR x from which a word can be a combo's painted VALUE (client px): the
# value windows start at x 246 on the 2.4.0 page, labels end well left of it.
VALUE_X0 = 235


def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)


def frect(session):
    return winutil.window_rect(session.hwnd)


def to_local(session, r):
    """Screen rect -> CLIENT rect. The capture the OCR runs on is the client
    area, so these are the coordinates OCR words come back in. Subtracting
    the WINDOW rect instead (7px above the client origin on the maximized
    guest frame) cropped the OCR band 7px low (fa706g3 review D6)."""
    ox, oy = client_origin(session)
    return (r[0] - ox, r[1] - oy, r[2] - ox, r[3] - oy)


def kids(session):
    out = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        lx, ly = r[0] - frect(session)[0], r[1] - frect(session)[1]
        out.append((t, c, r, h, lx, ly))
    return out


def real_click(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.8)


def view_band(session):
    """Visible options viewport band (client y0, y1), read from the panel's
    own rect so it tracks the window height. Recalibrated 08-31: with the
    fixed 700..800 band the maximized run wheeled the LAST group ('Color
    Mixing') fully into view (title resting at ty1~970 at max scroll) and
    still rejected it — the title could never enter [702,776]."""
    vp = options_viewport(session)
    if not vp:
        return VIEW_Y0, VIEW_Y1
    x0, y0, x1, y1 = to_local(session, vp[0])
    return y0, y1


def ocr_band(session, y0=None, y1=None, psm=3):
    """OCR words of the sidebar options band, client coords. psm 6 helps
    when rows sit half-cut at the band edge (psm 3 drops them — measured
    09-02 on the Ironing group)."""
    if y0 is None or y1 is None:
        y0, y1 = view_band(session)
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img[y0:y1, 0:SB_W], scale=3, psm=psm)
    return [(w, x, y + y0, w_w, w_h) for w, x, y, w_w, w_h in words]


def process_row_y(session):
    """Local y of the 'Process' title Static — the sidebar's ANCHOR row.
    The panel layout shifts with what the boot loaded (the mixed-fixture
    boot puts it at ~614, an empty boot at ~462 — no Color Mixing section),
    so every Process-panel y band anchors here instead of absolute px."""
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Process" \
                and user32.IsWindowVisible(h) and lx < 100:
            return ly
    return None


def close_setup_wizard(session, attempts=4, log="[panel]"):
    """Close the first-run 'Setup Wizard' (#32770, HTML) that pops OVER the
    main frame and swallows every real click / WindowFromPoint in its area
    (measured 09-01; user-spotted in the evidence video)."""
    gone = 0
    for i in range(attempts):
        hit = None
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and "wizard" in txt.lower():
                hit = h
                break
        if not hit:
            gone += 1
            if gone >= 2:
                return True
            time.sleep(0.5)
            continue
        print(f"{log} closing wizard hwnd 0x{hit:x}")
        winutil.close_window(hit)
        time.sleep(1.2)
    return not any(cls == "#32770" and "wizard" in txt.lower()
                   for cls, txt, r, h in mixing_util.toplevel(session.pid))


def relocate_wizard(session, attempts=3, log="[panel]"):
    """The 'Setup Wizard' overlays the window centre and swallows clicks;
    WM_CLOSE on it may cancel the whole setup and EXIT the app (measured
    09-01). Instead of closing, MOVE it far off-screen: the app is
    untouched and the covered interactions keep working."""
    moved = 0
    for _ in range(attempts):
        hit = None
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and "wizard" in txt.lower():
                hit = h
                break
        if not hit:
            return True
        winutil.user32.SetWindowPos(hit, 0, -32000, -32000, 0, 0,
                                    0x0001 | 0x0002 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
        moved += 1
        time.sleep(0.6)
    if moved:
        print(f"{log} relocated wizard x{moved}")
    return True


def advanced_switch(session):
    """The 'Advanced' SwitchButton right of its label on the Process title
    row (empty-text wxBitmapToggleButton; icons sit further right)."""
    py = process_row_y(session)
    if py is None:
        return None
    label = None
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Advanced" \
                and user32.IsWindowVisible(h) and abs(ly - py) <= 20:
            label = (lx, ly, r)
            break
    if not label:
        return None
    cands = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Button" or t.strip() or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (16 <= w <= 56 and 10 <= hh <= 28):
            continue
        if abs(ly - py) <= 20 and label[0] + 20 <= lx <= label[0] + 130:
            cands.append((r, h))
    cands.sort(key=lambda rh: rh[0][0])
    return cands[0] if cands else None


def advanced_on(session):
    """Switch knob position from the frame capture: ON paints the knob at the
    RIGHT half of the switch (teal). Returns (on_frac_left_half, diff_hint)."""
    sw = advanced_switch(session)
    if not sw:
        return None
    r = to_local(session, sw[0])
    img = capture_bgr(session)
    sub = img[r[1] + 2:r[3] - 2, r[0] + 2:r[2] - 2].astype(int)
    if sub.size == 0:
        return None
    mid = sub.shape[1] // 2

    def chroma(part):
        spread = part.max(axis=2) - part.min(axis=2)
        return float((spread > 40).mean())
    return chroma(sub[:, :mid]), chroma(sub[:, mid:])


# The Advanced switch is the page's own control and EVERY click saves the
# mode as advanced or simple (ParamsPanel.cpp:555-569 save_mode) - the app
# has no 'already on' short cut. In develop mode the knob does not paint as
# ON, so the reading below says off and the click would work - and take the
# app out of develop mode: fa run 17d2db91 was seeded user_mode=develop and
# its conf read 'advanced' after the census. A scenario that runs the app in
# develop mode (native_script_baseline.SCENARIO_CONF) sets this False from
# the worker; ensure_advanced then leaves the switch alone.
ADVANCED_SWITCH = True


def ensure_advanced(session, want=True, timeout_s=30.0):
    """Flip the Advanced switch only when its state differs from `want`.
    Returns True when the knob reading agrees with `want` afterwards - or,
    untouched, when the switch must not be used (ADVANCED_SWITCH False)."""
    if not ADVANCED_SWITCH:
        return True
    st = advanced_on(session)
    if st is None:
        return False
    on_now = st[1] > st[0]
    if on_now == want:
        return True
    sw = advanced_switch(session)
    if not sw:
        return False
    real_click(sw[0])
    time.sleep(2.0)
    st2 = advanced_on(session)
    return st2 is not None and (st2[1] > st2[0]) == want


def tab_button(session, name):
    """The self-drawn process tab item: wxWindowNR child whose text is the
    tab name, ~22px tall, in the tab row band (~50-110px below the
    'Process' anchor row — layout-shift safe)."""
    py = process_row_y(session)
    if py is None:
        return None
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and t.strip() == name \
                and user32.IsWindowVisible(h) \
                and 14 <= r[3] - r[1] <= 30 and 30 <= r[2] - r[0] <= 130 \
                and py + 50 <= ly <= py + 110 and lx > 5:
            return r, h
    return None


TAB_STRATEGY = [0]  # remembered across calls: 0 real, 1 message, 2 down/up


def _click_tab_item(session, rect, strategy):
    if strategy == 0:
        real_click(rect)
        return
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    if strategy == 1:
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.15)
        winutil.msg_click_screen(cx, cy, session.hwnd)
        time.sleep(0.8)
        return
    # strategy 2: split down / dwell / up
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.2)
    sw = winutil.user32.GetSystemMetrics(0)
    sh = winutil.user32.GetSystemMetrics(1)
    absx, absy = int(cx * 65535 / sw), int(cy * 65535 / sh)
    ev = winutil._INPUT()
    ev.type = 0
    ev.value.dx, ev.value.dy = absx, absy
    ev.value.dwFlags = winutil.MOUSEEVENTF_MOVE | winutil.MOUSEEVENTF_LEFTDOWN \
        | winutil.MOUSEEVENTF_ABSOLUTE
    winutil.user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(winutil._INPUT))
    time.sleep(0.25)
    ev2 = winutil._INPUT()
    ev2.type = 0
    ev2.value.dx, ev2.value.dy = absx, absy
    ev2.value.dwFlags = winutil.MOUSEEVENTF_LEFTUP | winutil.MOUSEEVENTF_ABSOLUTE
    winutil.user32.SendInput(1, ctypes.byref(ev2),
                             ctypes.sizeof(winutil._INPUT))
    time.sleep(0.8)


def click_tab(session, name, expect_word, timeout_s=75.0):
    """Switch the process page by clicking the tab item, VERIFY via a
    page-unique OCR word at the top of the options viewport (Quality ->
    'height', Multimaterial -> 'tower'), and wait out the sizer settle.
    After a field edit the tab strip may ignore plain real clicks
    (measured 08-30), so strategies rotate: real click -> message-level
    click (m1's ButtonsListCtrl path) -> split down/up."""
    strategies = [TAB_STRATEGY[0]] + [s for s in (0, 1, 2) if s != TAB_STRATEGY[0]]
    deadline = time.monotonic() + timeout_s
    clicked = False
    n_poll = 0
    si = 0
    strategy = strategies[0]
    while time.monotonic() < deadline:
        hit = tab_button(session, name)
        if hit:
            strategy = strategies[min(si // 2, len(strategies) - 1)]
            _click_tab_item(session, hit[0], strategy)
            clicked = True
            time.sleep(1.5)
        else:
            print(f"[panel] click_tab({name}): tab item NOT FOUND")
        vp = options_viewport(session)
        if vp:
            wheel_viewport(session, vp, RESET_WHEEL_NOTCHES, delta=120)
        joined = " ".join(w.lower() for w, *_ in ocr_band(session))
        print(f"[panel] click_tab({name}) poll{n_poll} strat{strategy}: "
              f"{joined[:70]!r}")
        if expect_word in joined:
            TAB_STRATEGY[0] = strategy
            time.sleep(3.0)  # sizer/fixup_items_positions settle
            return clicked
        n_poll += 1
        si += 1
        time.sleep(0.5)
    return False


def options_viewport(session):
    """The Multimaterial/Quality page viewport: a wide 'panel' wxWindowNR
    filling the band under the tab row. Size-adaptive (recalibrated 08-31
    on the maximized window): the panel TOP is anchored just below the tab
    row (which itself sits ~50-110px below the 'Process' anchor — the
    empty-boot layout sits ~150px higher than the fixture boot), and its
    HEIGHT stretches with the window (73px at the 800-tall window, 313px
    maximized) — the old 50..120 height cap matched only the windowed era
    and made every wheel a silent no-op (measured via diag_m4g_max)."""
    py = process_row_y(session)
    if py is None:
        return None
    best = None
    cands = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "wxWindowNR" or t.strip() != "panel":
            continue
        if not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if w >= 300 and hh >= 40:
            cands.append((lx, ly, w, hh))
        if 380 <= w <= 440 and hh >= 50 and py + 70 <= ly <= py + 130:
            if best is None or hh > best[0][3] - best[0][1]:
                best = (r, h)
    if best is None:
        print(f"[panel] options_viewport None; panel candidates "
              f"(lx,ly,w,h): {cands[:10]}")
    return best


MOUSEEVENTF_WHEEL = 0x0800


def real_wheel(session, x_client, y_client, notches, delta=-120):
    """Real wheel input at a client point (SetCursorPos + SendInput wheel).
    Real input goes through the OS routing (focused window -> wx forwards
    to the window under the cursor), unlike SendMessage'd WM_MOUSEWHEEL."""
    sx, sy = client(session, x_client, y_client)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.15)
    for _ in range(abs(notches)):
        ev = winutil._INPUT()
        ev.type = 0
        ev.value.dx = 0
        ev.value.dy = 0
        ev.value.mouseData = delta & 0xFFFFFFFF
        ev.value.dwFlags = MOUSEEVENTF_WHEEL
        winutil.user32.SendInput(1, ctypes.byref(ev),
                                 ctypes.sizeof(winutil._INPUT))
        time.sleep(0.08)
    time.sleep(0.4)


def wheel_viewport(session, viewport, notches, delta=-120):
    r, h = viewport
    ox, oy = client_origin(session)   # real_wheel takes a client point
    cx = (r[0] + r[2]) // 2 - ox
    cy = (r[1] + r[3]) // 2 - oy
    real_wheel(session, cx, cy, notches, delta=delta)


def group_title(session, substr):
    """The options-group title whose text contains `substr`: (rect, hwnd).
    Its rect tracks the scroll offset exactly, so it is usable for
    positioning even when scrolled out of view. See group_titles() for
    what counts as a group title."""
    for t, r, h in group_titles(session):
        if substr.lower() in t.lower():
            return r, h
    return None


def scroll_group_into_view(session, substr, timeout_s=420.0):
    """Wheel the options viewport until the group title `substr` sits high
    enough in the VISIBLE band that its FIRST OPTION ROW is also fully
    visible (title bottom within [band_top+2, band_bottom-24], band from
    view_band()). 1-notch steps with position read from the title's own
    rect (a multi-notch wheel can jump whole groups between OCRs).
    Self-heals a wheel stuck on the Edit focus via neutralize_focus().
    Returns (rect, hwnd) or None."""
    deadline = time.monotonic() + timeout_s
    oy = client_origin(session)[1]   # client coordinates, like view_band()
    last_y = None
    stuck = 0
    missing = 0
    no_vp = 0
    while time.monotonic() < deadline:
        # group_title() now sees a title wherever it is scrolled to, so the
        # wheel below goes UP when the title sits above the band. Before,
        # a title above the Process row was invisible here and the loop
        # only wheeled down (feature_speeds, run af5292e5).
        hit = group_title(session, substr)
        vp = options_viewport(session)
        if not vp:
            # The only way out used to be the deadline: timeout_s of
            # nothing (fa706g3 review D7).
            no_vp += 1
            if no_vp >= 5:
                print(f"[panel] scroll_group({substr!r}): no options viewport "
                      f"-> giving up", flush=True)
                return None
            time.sleep(0.5)
            continue
        no_vp = 0
        if hit:
            missing = 0
            ty1 = hit[0][3] - oy
            y0, y1 = view_band(session)
            if y0 + 2 <= ty1 <= y1 - 24:
                return hit
            wheel_viewport(session, vp, 1,
                           delta=-120 if ty1 > y1 - 24 else 120)
            if last_y == ty1:
                stuck += 1
                if stuck == 3:
                    print(f"[panel] wheel stuck at ty1={ty1}")
                    focus_off_edit(session, why="scroll_group(%r)" % substr)
                elif stuck >= 6:
                    # The title cannot move any further: it is the FIRST
                    # group of a page sitting at the top (its title rests
                    # above the visible band, so the in-band test can never
                    # pass) or the last group at the bottom. Wheeling on only
                    # burned the deadline - twice per op, 840s, which is what
                    # made #270 first_speeds look wedged on every run
                    # (0b7886bc and every earlier attempt).
                    print(f"[panel] scroll_group({substr!r}): title does not move "
                          f"at ty1={ty1} -> accepting it", flush=True)
                    return hit
            else:
                stuck = 0
            last_y = ty1
        else:
            # Title rects exist even when scrolled out of view, so "not
            # found" means the page has no such group. It used to wheel until
            # the 420s deadline, which is what a run with a wrong op 'group'
            # looked like (#263 asked for 'Bridge', real title 'Bridging':
            # run eacfc6ff = one such loop + the scan).
            missing += 1
            if missing > 16:
                print(f"[panel] scroll_group({substr!r}): no such group title "
                      f"on this page after {missing * 4} notches -> giving up",
                      flush=True)
                return None
            wheel_viewport(session, vp, 4, delta=-120)
        time.sleep(0.12)
    return None


def group_titles(session):
    """Every options-group title on the current page as (text, rect, hwnd),
    top to bottom, at ANY scroll position - the rects track the scroll
    offset even when a title is scrolled out of view.

    What counts (census run c101c0f4, 2.4.0): a titled wxWindowNR at
    x ~13, 393 wide, 18 high. Three things made the old filter wrong:
    - the unit labels ('mm/s', 'mm/s or %', 'mm'...) are titled wxWindowNR
      windows as well, 120 wide at x 203. With a 100px width floor they
      counted as 'the next title', so group_span() shrank to the ~10px
      between a group's title and its first unit label and every row but
      the first was rejected as 'a neighbouring group' (queue18:
      accelerations op 2+, seam_wipe 'Wipe speed', overhang_bridge).
    - 'ly > py' dropped every title scrolled above the Process row. After
      an edit commit the page is rebuilt and lands anywhere; with the title
      above that line scroll_group_into_view saw 'no such title' and its
      missing-branch only wheels DOWN, away from it (feature_speeds op 3:
      68 notches, 'no such group title').
    - descendants of the options viewport are the page's own windows
      wherever they sit; the preset panel's titled windows (above the
      Process row) are not its descendants.
    The containers are all named 'panel' (the viewport included) and must
    not be treated as titles: on_title_line() would then match every row."""
    py = process_row_y(session)
    if py is None:
        return []
    vp = options_viewport(session)
    vph = vp[1] if vp else 0
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and t.strip() and t.strip() != "panel" \
                and user32.IsWindowVisible(h) \
                and (r[2] - r[0]) >= GROUP_TITLE_MIN_W and lx < GROUP_TITLE_MAX_X \
                and (r[3] - r[1]) <= GROUP_TITLE_MAX_H \
                and (ly > py or (vph and user32.IsChild(vph, h))):
            out.append((t.strip(), r, h))
    out.sort(key=lambda item: item[1][1])
    return out


def client_origin(session):
    """Screen (x, y) of the frame's CLIENT origin. OCR coordinates are
    client coordinates (the capture is the client area), while kids() and
    frect() are WINDOW-rect relative; on the maximized guest frame the two
    differ by the 7px invisible border (frame (-7,-7,1927,1039), client
    (0,0,1920,1032)). Anything that compares an OCR y with a window rect
    has to go through this (speed_limits run 1e944276: the title word's top
    was 726 in client coords, the title window 730-748 window-relative)."""
    return winutil.client_to_screen(session.hwnd, 0, 0)


def on_title_line(session, y, tol=3):
    """True when client y lies on a visible GROUP TITLE line. A title can be
    spelled exactly like the first row under it: 'Layer height' heads the
    Quality page and is also its first row's label. The OCR scan took the
    title for the row and found no Edit on it (speed_limits, run fc5b643c;
    before r3 the row's Edit 32px lower was still picked up by a wide
    tolerance). `y` is a client coordinate; so is the title rect here."""
    oy = client_origin(session)[1]
    for _t, r, _h in group_titles(session):
        if r[1] - oy - tol <= y <= r[3] - oy + tol:
            return True
    return False


def scroll_signature(session):
    """Ground truth for 'did the page move': the y of every group title.
    Window rects, no OCR - immune to the OCR jitter that made a y-only
    OCR signature report 'unchanged' for a moving page (see _StallGuard)."""
    return tuple((t, r[1]) for t, r, _h in group_titles(session))


def group_span(session, substr):
    """(y_top, y_bottom) CLIENT band that belongs to ONE options group: from
    just below its title to the next group's title. Lets a label search stay
    inside the group it asked for - 'Outer wall' and 'Travel' exist in three
    groups of the Speed page (2.4.0 screenshot, run f0e683fb) and a row label
    can be spelled exactly like its group title ('Overhang speed').
    None when there is no such title."""
    titles = group_titles(session)
    oy = client_origin(session)[1]
    for i, (t, r, _h) in enumerate(titles):
        if substr.lower() in t.lower():
            top = r[3] - oy
            bottom = titles[i + 1][1][1] - oy if i + 1 < len(titles) else top + 4000
            return (top, bottom)
    return None


def leftmost_on_line(words, i, tol=10):
    """True when words[i] is the first (left-most) word of its OCR line."""
    _w, x, y, _ww, _hh = words[i]
    for j, (_t, xj, yj, _wj, _hj) in enumerate(words):
        if j != i and abs(yj - y) < tol and xj < x - 8:
            return False
    return True


def popup_line_hits(words, target):
    """Popup rows whose LINE text contains `target` (case-insensitive), as
    [(cx, cy, line_text)] top to bottom. OCR yields one word per tuple, so a
    multi-word target ('By Object', 'Outer only') can never be found inside
    a single word - both the click and the after-check silently failed for
    every such target (runs 244ae35e, f0e683fb). Words are grouped into
    lines by y."""
    rows = {}
    for t, x, y, ww, hh in words:
        key = y
        for k in rows:
            if abs(k - y) <= 10:
                key = k
                break
        rows.setdefault(key, []).append((x, y, ww, hh, t))
    out = []
    for _k, parts in rows.items():
        parts.sort()
        text = " ".join(p[4] for p in parts)
        if target.lower() in text.lower():
            x0 = min(p[0] for p in parts)
            x1 = max(p[0] + p[2] for p in parts)
            yc = sum(p[1] + p[3] // 2 for p in parts) // len(parts)
            out.append(((x0 + x1) // 2, yc, text))
    out.sort(key=lambda hit: hit[1])
    return out


class _GUITHREADINFO(ctypes.Structure):
    """Declared by hand: ctypes.wintypes has no GUITHREADINFO on the guest's
    Python 3.11 (run 7834c486: AttributeError the first time the stall guard
    tried to reset the focus - the offline tests had stubbed the reset)."""
    _fields_ = [("cbSize", ctypes.wintypes.DWORD), ("flags", ctypes.wintypes.DWORD),
                ("hwndActive", ctypes.wintypes.HWND), ("hwndFocus", ctypes.wintypes.HWND),
                ("hwndCapture", ctypes.wintypes.HWND), ("hwndMenuOwner", ctypes.wintypes.HWND),
                ("hwndMoveSize", ctypes.wintypes.HWND), ("hwndCaret", ctypes.wintypes.HWND),
                ("rcCaret", ctypes.wintypes.RECT)]


def focus_info(session):
    """(hwnd, class) holding KEYBOARD focus in the app's GUI thread, or
    (None, None). GetFocus() only reports the caller's own thread."""
    tid = user32.GetWindowThreadProcessId(session.hwnd, None)
    gti = _GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(gti)
    if not tid or not user32.GetGUIThreadInfo(ctypes.c_uint(tid), ctypes.byref(gti)) or not gti.hwndFocus:
        return None, None
    return gti.hwndFocus, winutil.window_class(gti.hwndFocus)


def focus_off_edit(session, why=""):
    """Move keyboard focus off an option Edit/ComboBox back onto the options
    panel so the wheel scrolls it again (wx lets the focused child consume
    the wheel). neutralize_focus() goes first for continuity, but a Static
    cannot take focus, so if an Edit/ComboBox still holds it the panel gets
    the focus through an attached input queue. Focus before/after is logged
    as evidence."""
    before = focus_info(session)[1]
    neutralize_focus(session)
    after = focus_info(session)[1]
    if after in ("Edit", "ComboBox") or after is None:
        vp = options_viewport(session)
        if vp:
            import ctypes
            ours = ctypes.windll.kernel32.GetCurrentThreadId()
            theirs = user32.GetWindowThreadProcessId(session.hwnd, None)
            attached = user32.AttachThreadInput(ours, theirs, True) if theirs else False
            user32.SetFocus(ctypes.c_void_p(vp[1]))
            if attached:
                user32.AttachThreadInput(ours, theirs, False)
            time.sleep(0.3)
            after = focus_info(session)[1]
    print(f"[panel] focus reset ({why}): {before} -> {after}", flush=True)


class _StallGuard:
    """Detects a wheel that no longer moves the options panel and revives it.

    While keyboard focus sits in one of the panel's Edit/ComboBox children
    the panel ignores the wheel (runs 99a53a80 / f149c3da, 2026-11-23: the
    group had just been scrolled into view, then 12+26 blind notches changed
    nothing, so any label beyond the first screen after the group title
    could never be reached). scroll_group_into_view() always had this
    self-heal; the label scans did not. step(words) returns True when the
    caller should stop scanning in this direction: two focus resets later
    the band still did not move, i.e. the page end."""

    def __init__(self, session, what):
        self.session, self.what = session, what
        self.reset()

    def reset(self):
        self.last, self.stalls, self.revives = None, 0, 0

    def step(self, words):
        # Two signals: the group titles' window y (no OCR involved) and the
        # OCR words WITH their text. The signature used to be the set of OCR
        # word y values alone. One notch moves the page 60px = two rows, so
        # over uniform rows the band shows the same y layout step after step
        # while the page is moving - which read as 'unchanged', cost two
        # focus resets and then ended the scan as 'end of page' in the
        # middle of a group (queue18: seam_wipe, overhang_bridge and
        # feature_speeds each logged 9 unchanged wheels; census c101c0f4
        # then wheeled those rows with the focus on a checkbox Button and
        # the page moved on every notch).
        titles = scroll_signature(self.session)
        ocr = tuple(sorted((int(y) // 6, str(w).lower()) for w, _x, y, *_r in words))
        sig = (titles, ocr) if titles else (None, ocr)
        if sig != self.last:
            self.last, self.stalls = sig, 0
            return False
        self.stalls += 1
        if self.stalls % 3:
            return False
        if self.revives >= 2:
            # What sits under the real cursor: a child control that eats the
            # wheel looks exactly like the page end (review V4).
            try:
                pt = winutil.wt.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                under = winutil.window_class(winutil.window_from_screen_point(pt.x, pt.y))
            except Exception:  # diagnostic only
                under = "?"
            print(f"[panel] {self.what}: band unchanged after {self.stalls} "
                  f"wheels and {self.revives} focus resets -> end of page "
                  f"(cursor over {under})", flush=True)
            return True
        self.revives += 1
        focus_off_edit(self.session, why=self.what)
        return False


def neutralize_focus(session):
    """After real typing the keyboard focus sits in the option Edit; with
    that focus the real wheel no longer scrolls the options viewport and
    real clicks on the tab strip are ignored (measured 08-30). ESC + a
    harmless click on the 'Process' title Static returns focus to the
    panel."""
    mdu._send_keys([(0x1B, False), (0x1B, True)])
    time.sleep(0.3)
    py = process_row_y(session)
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Process" \
                and user32.IsWindowVisible(h) \
                and (py is None or abs(ly - py) <= 25):
            real_click(r)
            return True
    return False


def row_checkboxes(session, y_client, y_tol=12, x_lo=200, x_hi=420):
    # x_hi 330->420 (2026-11-23): long labels ('Slow down for curled
    # perimeters') push the row's checkbox past 330 - run b4dfede6 found the
    # row but zero boxes in the window; 420 stays left of the canvas.
    """Empty-text ~18px Buttons (option checkboxes) on an option row band;
    candidates that horizontally overlap a same-band Edit are spin/undo
    artifacts and dropped."""
    band = [k for k in kids(session)
            if k[1] == "Button" and not k[0].strip()
            and user32.IsWindowVisible(k[3])]
    # y_client is an OCR (client) coordinate: compare against the CLIENT
    # origin, not the window rect (7px apart on the maximized guest frame).
    oy = client_origin(session)[1]
    sq = [(r, h) for t, c, r, h, lx, ly in band
          if 12 <= r[2] - r[0] <= 26 and 12 <= r[3] - r[1] <= 26
          and abs((r[1] + r[3]) // 2 - oy - y_client) <= y_tol
          and x_lo <= lx <= x_hi]
    edits = [(r, h) for t, c, r, h, lx, ly in kids(session)
             if c == "Edit" and user32.IsWindowVisible(h)
             and abs((r[1] + r[3]) // 2 - oy - y_client) <= y_tol]
    out = []
    for r, h in sq:
        cx = (r[0] + r[2]) // 2
        if any(abs((er[0] + er[2]) // 2 - cx) < 60 for er, _eh in edits):
            continue
        out.append((r, h))
    out.sort(key=lambda rh: rh[0][0])
    return out


def checked_state(session, rect):
    """Teal fraction of the checkbox rect in the FRAME capture (the real
    render; PrintWindow washes the alpha bitmaps). Checked box paints the
    teal checkmark (#009688), unchecked is a plain gray/white box."""
    x0, y0, x1, y1 = to_local(session, rect)
    img = capture_bgr(session)
    sub = img[y0 + 2:y1 - 2, x0 + 2:x1 - 2].astype(int)
    if sub.size == 0:
        return 0.0
    spread = sub.max(axis=2) - sub.min(axis=2)
    return float((spread > 50).mean())


def top_dialog_set(session):
    return set(h for _c, _t, _r, h in mixing_util.toplevel(session.pid))


def find_conflict_dialog(session, known, timeout_s=8.0):
    """hwnd of a NEW small #32770 (RichMessageDialog) of the app, or None."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and h not in known \
                    and (r[3] - r[1]) < 300:
                return h
        time.sleep(0.25)
    return None


def dialog_body(pid, dlg):
    body = " ".join(t for t, c, r, h in mixing_util.children(dlg)
                    if t.strip() and c == "Static")
    if not body:
        from harness import ocr_util
        try:
            body = ocr_util.ocr_hwnd(dlg)
        except Exception:
            pass
    return body


def dismiss_conflict(session, dlg):
    """Click the dialog's OK (RichMessageDialog wxOK)."""
    hit = mixing_util.child_by_text(dlg, "OK")
    if not hit:
        return False
    r = hit[2]
    winutil.real_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(1.2)
    return True


def float_edits_in_view(session):
    """Visible Edit children inside the options viewport band with a float
    value, topmost first (the Quality page's 'Layer height' is the first
    option row; the label is painted, so disambiguation is positional)."""
    y0, y1 = view_band(session)
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Edit" or not user32.IsWindowVisible(h):
            continue
        if not (y0 <= ly <= y1 and 220 <= lx <= 340):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (50 <= w <= 140 and 12 <= hh <= 26):
            continue
        val = mdu.edit_value(h)
        try:
            float(val)
        except ValueError:
            continue
        out.append((r, h, val))
    out.sort(key=lambda x: x[0][1])
    return out


def wait_float_edit(session, timeout_s=180.0):
    """Topmost float Edit on the (Quality) page = the first option row
    ('Layer height'; the label is painted by OG_CustomCtrl). If nothing is
    found, periodically force the viewport back to top — the scroll offset
    persists across tab switches (RESET_WHEEL_NOTCHES note)."""
    deadline = time.monotonic() + timeout_s
    n = 0
    while time.monotonic() < deadline:
        eds = float_edits_in_view(session)
        if eds:
            return eds[0]
        n += 1
        if n % 3 == 0:
            vp = options_viewport(session)
            if vp:
                wheel_viewport(session, vp, RESET_WHEEL_NOTCHES, delta=120)
        time.sleep(1.0)
    return None


GUITHREADINFO = mdu.GUITHREADINFO


def focus_hwnd(hwnd):
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    user32.GetGUIThreadInfo(tid, ctypes.byref(info))
    return info.hwndFocus


def real_edit_set(session, rect, hwnd, text):
    """Real-click focus an Edit, Ctrl+A + Del, unicode-type `text`, Enter.
    Returns the live text (mdu.edit_value) or None when focus failed."""
    VK_CONTROL, VK_A, VK_DELETE, VK_RETURN = 0x11, 0x41, 0x2E, 0x0D
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    ok_focus = False
    for _ in range(4):
        winutil.force_set_foreground(session.hwnd)
        time.sleep(0.4)
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.15)
        winutil.real_click_screen(x, y)
        time.sleep(0.5)
        if focus_hwnd(hwnd) == hwnd:
            ok_focus = True
            break
    if not ok_focus:
        return None
    mdu._send_keys([(VK_CONTROL, False), (VK_A, False), (VK_A, True),
                    (VK_CONTROL, True)])
    time.sleep(0.15)
    mdu._send_keys([(VK_DELETE, False), (VK_DELETE, True)])
    time.sleep(0.2)
    mdu._send_chars(text)
    time.sleep(0.3)
    mdu._send_keys([(VK_RETURN, False), (VK_RETURN, True)])
    time.sleep(0.6)
    return mdu.edit_value(hwnd)


def scroll_to_word(session, substr, max_notches=160, notches_per_round=5):
    """Wheel the options viewport (real input) until `substr` OCRs inside
    it. Returns the word's client rect or None."""
    seen = 0
    last_join = ""
    while seen <= max_notches:
        words = ocr_band(session)
        for w, x, y, ww, hh in words:
            if substr.lower() in w.lower():
                if seen:
                    print(f"[panel] scrolled {seen} notches to reach {substr!r}")
                return (x, y, x + ww, y + hh)
        join = " ".join(w for w, *_ in words)
        if join != last_join:
            print(f"[panel] scroll@{seen}: {join[:90]!r}")
            last_join = join
        vp = options_viewport(session)
        if not vp:
            print(f"[panel] scroll: viewport lost at {seen}")
            return None
        wheel_viewport(session, vp, notches_per_round)
        seen += notches_per_round
    print(f"[panel] scroll: {substr!r} NOT reached in {seen} notches; "
          f"last={last_join[:90]!r}")
    return None


def find_process_preset_combo(session):
    """The print/process preset selector on the Process title row — the row
    just below the 'Process' anchor. Text varies by boot:
      - fixture boot: '0.40 Standard @Snapmaker U1 (0.8 nozzle)'
      - empty boot:   'Default Setting' (no preset embedded)
    Returns (rect, hwnd, text), or (None, None, None) with a sidebar
    diagnostic dump when nothing matches."""
    py = process_row_y(session)
    if py is None:
        return (None, None, None)
    fallback = None
    for t, c, r, h, lx, ly in kids(session):
        if not user32.IsWindowVisible(h) or not t.strip():
            continue
        if not (py + 10 <= ly <= py + 70) or not (10 <= lx <= 60):
            continue
        w = r[2] - r[0]
        if "@Snapmaker" in t and w >= 100:
            return (r, h, t.strip())
        if t.strip() == "Default Setting" and w >= 100:
            fallback = (r, h, t.strip())
    if fallback:
        return fallback
    probe = []
    for t, c, r, h, lx, ly in kids(session):
        if t.strip() and len(t.strip()) > 3 and user32.IsWindowVisible(h) \
                and lx < 440 and py <= ly <= py + 90:
            probe.append((t.strip()[:44], c, lx, ly))
        if len(probe) >= 20:
            break
    print(f"[panel] preset NOT found; sidebar texts near Process row: "
          f"{probe}")
    return (None, None, None)


def _norm_preset(s: str) -> str:
    """Normalise a preset label for matching: drop the layer-height 'mm'
    suffix and collapse whitespace. 2.4.0 labels read '0.24mm Standard @...'
    while callers pass '0.24 Standard' (measured 09-22)."""
    return " ".join(s.replace("mm", " ").split()).lower()


def switch_process_preset(session, target_substr, tries=6):
    """Switch the process preset to the popup row containing
    `target_substr`. The row popup is a self-drawn 'panel' top-level; rows
    are OCR-located first, probed at the measured 28px pitch as fallback;
    every click selects + closes the popup, so the loop reopens until the
    combo text confirms (m3e mechanics, text re-anchored)."""
    r, ch, txt = find_process_preset_combo(session)
    if not ch:
        return False
    if _norm_preset(target_substr) in _norm_preset(txt):
        return True
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for attempt in range(tries):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = None
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and not popup:
            time.sleep(0.2)
            for t, ptxt, pr, h in mixing_util.toplevel(session.pid):
                if t == "wxWindowNR" and ptxt == "panel":
                    popup = (pr, h)
        if not popup:
            print(f"[panel] preset popup did not open (attempt {attempt})")
            return False
        pr, ph = popup
        # diagnostic: ALL panel toplevels right now (wrong-panel risk)
        allp = [(r2, h2) for t2, pt2, r2, h2 in mixing_util.toplevel(session.pid)
                if t2 == "wxWindowNR" and pt2 == "panel"]
        print(f"[panel] panel toplevels: {allp}")
        clicked = False
        # OCR-locate the row inside the popup (its own pixels)
        w, hgt, bgra = winutil.capture_window(ph)
        import numpy as np
        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
        try:
            import cv2
            cv2.imwrite(str(HERE / "artifacts" / "m5a_popup.png"),
                        img[:, :, ::-1])
        except Exception:
            pass
        words = mdu.ocr_words_img(img, scale=3)
        print(f"[panel] preset popup {pr} ocr: "
              f"{' | '.join(t for t, *_ in words)[:160]!r}")
        # 2.4.0 preset labels carry the 'mm' layer-height suffix ('0.40mm
        # Standard @Snapmaker U1 (0.8 nozzle)') and OCR splits a row into
        # separate tokens — a single-word substring match for '0.40
        # Standard' therefore never hit and the blind 28px pitch walk
        # clicked the wrong rows (measured 09-22: m5a 'switched=False').
        # Group tokens into rows by y, normalise ('mm' -> space), match.
        norm = _norm_preset
        row_toks: dict = {}
        for tok in words:
            row_toks.setdefault(round(tok[2] / 8), []).append(tok)
        clicked = False
        for key in sorted(row_toks):
            row = sorted(row_toks[key], key=lambda v: v[1])
            if norm(target_substr) in norm(" ".join(v[0] for v in row)):
                anchor = row[0]
                sx = pr[0] + anchor[1] + anchor[3] // 2
                sy = pr[1] + anchor[2] + anchor[4] // 2
                winutil.msg_click_screen(sx, sy)  # popup: no root piercing
                clicked = True
                break
        if not clicked:
            py = pr[1] + 14 + attempt * 28
            winutil.msg_click_screen((pr[0] + pr[2]) // 2, py)
        time.sleep(0.8)
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(ch, buf, 256)
        if _norm_preset(target_substr) in _norm_preset(buf.value):
            return True
    return False


def set_option_float(session, label_substr, text, group_substr=None):
    """Locate the option row `label_substr` and type `text` into its Edit.
    Returns (ok, old_value, new_value). Neutralizes focus afterwards (a
    focused Edit blocks wheel/clicks)."""
    r, h, old = find_option_edit(session, label_substr, group_substr)
    if not h:
        return False, old, None
    new = real_edit_set(session, r, h, text)
    neutralize_focus(session)
    ok = bool(new and new.startswith(text))
    return ok, old, new


def find_option_row(session, label_substr, group_substr=None,
                    timeout_s=420.0, psm=3):
    """Locate an OPTION ROW by its painted label: scroll `group_substr`'s
    group into view, then OCR the visible band for `label_substr`.
    Returns (word_rect_client, y_row_center) or (None, None). Labels are
    PAINTED by OG_CustomCtrl (no HWNDs) — OCR is the only handle."""
    if group_substr:
        hit = scroll_group_into_view(session, group_substr, timeout_s)
        print(f"[panel] scroll_group({group_substr!r}) -> "
              f"{'hit' if hit else 'NOT FOUND'}")
        if not hit:
            return None, None
    if " " in label_substr.strip():
        # A multi-word label is never inside ONE OCR word (review D8). The
        # checkbox path already routed such labels to the phrase matcher;
        # through any other caller they scanned the whole page twice for
        # nothing ('Detect overhang', 'Slow down' - queue18 / queue19).
        from .param_case_lib import _find_phrase_row
        y = _find_phrase_row(session, label_substr, group_substr)
        return (((0, y, 0, y), y) if y is not None else (None, None))
    # 2026-11-22: deep groups need more than 6 single-notch wheels;
    # multi-notch steps reset to top (fa706g3 pathology).
    # 2026-11-23: an edit commit rebuilds the panel and the scroll lands
    # anywhere (run 983bab81) - scan down first, then back up.
    # 2026-11-23: stall guard + focus reset while scanning (_StallGuard), and
    # with a group requested the hit must lie inside that group's band.
    # 2026-11-23 r3c (census c101c0f4 + queue18): the span is re-read on every
    # step - it is in client coordinates and the page moves under it; frozen
    # at the start it rejected the group's own rows once they had scrolled
    # above the title's starting position. A label spelled like a group title
    # does not match the title line itself. A scan runs to the page end (the
    # stall guard) within SCAN_NOTCHES / SCAN_SECONDS per direction.
    stall = _StallGuard(session, "find_option_row(%r)" % label_substr)
    for direction in (-120, 120):
        stall.reset()
        started = time.monotonic()
        last_band = None
        for _ in range(SCAN_NOTCHES):
            if time.monotonic() - started > SCAN_SECONDS:
                print(f"[panel] find_option_row({label_substr!r}): "
                      f"{SCAN_SECONDS:.0f}s cap reached scanning "
                      f"{'down' if direction < 0 else 'up'}", flush=True)
                break
            span = group_span(session, group_substr) if group_substr else None
            words = ocr_band(session, psm=psm)
            band = " ".join(w for w, *_ in words)[:120]
            if band != last_band:
                print(f"[panel] find_option_row({label_substr!r}) band: {band!r}")
                last_band = band
            for w, x, y, ww, hh in words:
                if label_substr.lower() in w.lower():
                    if on_title_line(session, y):
                        continue  # the group title, not a row
                    if span and not (span[0] <= y < span[1]):
                        continue  # the same word in a neighbouring group
                    return (x, y, x + ww, y + hh), y + hh // 2
            vp = options_viewport(session)
            if vp:
                if stall.step(words):
                    break
                wheel_viewport(session, vp, 1, delta=direction)
            time.sleep(0.4)
    return None, None


def option_edit_at(session, y_row, y_tol=14, x_lo=220, x_hi=340):
    """The Edit control on the option row at client y `y_row` (the value
    column sits at x 220..340; m4g's float_edits_in_view calibration)."""
    oy = client_origin(session)[1]   # y_row is a client coordinate (review D5)
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Edit" or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (40 <= w <= 140 and 12 <= hh <= 26):
            continue
        if abs((r[1] + r[3]) // 2 - oy - y_row) <= y_tol                 and x_lo <= lx <= x_hi:
            out.append((r, h))
    out.sort(key=lambda rh: rh[0][0])
    return out[0] if out else None


def option_combo_at(session, y_row, y_tol=14):
    """The ComboBox control on the option row at client y `y_row`."""
    oy = client_origin(session)[1]   # y_row is a client coordinate (review D5)
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "ComboBox" or not user32.IsWindowVisible(h) or not t.strip():
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (80 <= w <= 180 and 16 <= hh <= 30):
            continue
        if abs((r[1] + r[3]) // 2 - oy - y_row) <= y_tol                 and 180 <= lx <= 380:
            out.append((r, h, t.strip()))
    out.sort(key=lambda rh: rh[0][0])
    return out[0] if out else None


def find_option_edit(session, label_substr, group_substr=None):
    """(rect, hwnd, current_text) of the Edit on the option row labeled
    `label_substr`, or (None, None, None)."""
    word, y_row = find_option_row(session, label_substr, group_substr)
    if not word:
        return None, None, None
    hit = option_edit_at(session, y_row)
    if not hit:
        return None, None, None
    r, h = hit
    return r, h, mdu.edit_value(h)


def set_option_combo(session, current_value, target):
    """Switch an options-panel combo currently showing `current_value` to
    `target` via keyboard cycling (cycle_combo_to)."""
    r, h, _cur = find_option_combo(session, current_value)
    if not h:
        return False
    return cycle_combo_to(session, r, h, target)


def find_option_combo(session, current_value, psm=3):
    """Locate an options-panel combo by its PAINTED value text (the value is
    painted by OG_CustomCtrl like the label; the control exposes no window
    text). OCR finds the word, WindowFromPoint resolves the real hwnd.
    Returns (rect, hwnd, text)."""
    word, y_row = find_option_row(session, current_value, psm=psm)
    if not word:
        return (None, None, None)
    # OCR coordinates are client coordinates: add the CLIENT origin, not the
    # window rect (7px apart on the maximized frame; adding the window rect
    # put the point 7px left of a value that starts at its window's edge,
    # and WindowFromPoint returned the row container instead - census
    # 67690ed4: Support Type/Style and Skirt 'Disabled' opened no popup).
    ox, oy = client_origin(session)
    sx, sy = ox + (word[0] + word[2]) // 2, oy + y_row
    return value_control_at(session, sx, sy, current_value)


def set_combo_native(session, word_text, target_prefix, log="[panel]"):
    """Select an options-panel combo option by NATIVE CB_ messages: locate
    the combo GEOMETRICALLY (the smallest control whose rect contains the
    painted value word), CB_FINDSTRING the option, CB_SETCURSEL it, then
    notify the parent with CBN_SELCHANGE so wx records the change."""
    word, y_row = find_option_row(session, word_text)
    if not word:
        print(f"{log} set_combo_native: word {word_text!r} not found")
        return False
    f = frect(session)
    wxp, wyp = f[0] + (word[0] + word[2]) // 2, f[1] + y_row
    best = None
    for t, c, r, h, lx, ly in kids(session):
        if not user32.IsWindowVisible(h):
            continue
        if r[0] <= wxp < r[2] and r[1] <= wyp < r[3]:
            area = (r[2] - r[0]) * (r[3] - r[1])
            if best is None or area < best[0]:
                best = (area, r, h, c, t)
    if not best:
        print(f"{log} set_combo_native: no control at the word")
        return False
    ch = best[2]
    buf = ctypes.create_unicode_buffer(target_prefix)
    lparam = ctypes.cast(buf, ctypes.c_void_p)
    idx = user32.SendMessageW(ch, 0x014C, 0xFFFFFFFF, lparam)  # CB_FINDSTRING
    print(f"{log} combo hwnd=0x{ch:x} class={best[3]} find={idx}")
    if idx < 0:
        return False
    user32.SendMessageW(ch, 0x014E, idx, None)                 # CB_SETCURSEL
    time.sleep(0.4)
    parent = user32.GetParent(ch)
    cid = user32.GetDlgCtrlID(ch)
    if parent and cid:
        user32.SendMessageW(parent, 0x0111,
                            ((cid & 0xFFFF) << 16) | 1, ch)    # CBN_SELCHANGE
    time.sleep(0.8)
    text = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, text, 256)
    ok = target_prefix.lower() in text.value.lower()
    print(f"{log} combo text after select: {text.value!r} ok={ok}")
    return ok


def cycle_combo_to(session, rect, hwnd, target_word, max_steps=4):
    """Switch an options-panel combo to the option whose text contains
    `target_word`. The combo has real window text but the popup is NOT a
    dialog 'panel' — so: 1) CB_SELECTSTRING + CBN_SELCHANGE notification
    (native, deterministic); 2) fallback: keyboard DOWN/ENTER cycling with
    OCR verification of the painted value."""
    WM_COMMAND = 0x0111
    CB_SELECTSTRING = 0x014D
    CBN_SELCHANGE = 1

    def combo_text():
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def notify_parent():
        parent = user32.GetParent(hwnd)
        cid = user32.GetDlgCtrlID(hwnd)
        if parent and cid:
            user32.SendMessageW(parent, WM_COMMAND,
                                ((cid & 0xFFFF) << 16) | CBN_SELCHANGE, hwnd)

    def try_selectstring():
        buf = ctypes.create_unicode_buffer(target_word)
        lparam = ctypes.cast(buf, ctypes.c_void_p).value or 0
        user32.SendMessageW(hwnd, CB_SELECTSTRING, 0xFFFFFFFF, lparam)
        time.sleep(0.4)
        ok = target_word.lower() in combo_text().lower()
        if ok:
            notify_parent()
            time.sleep(0.4)
        print(f"[panel] cycle CB_SELECTSTRING -> text={combo_text()!r} "
              f"ok={ok}")
        return ok

    def committed():
        for w, *_ in ocr_band(session):
            if target_word.lower() in w.lower():
                return True
        return False

    def focus():
        # clicks route by position, but the keyboard only reaches the app
        # when it holds focus (it is demoted/NOACTIVATE). A click on the
        # combo OPENS the dropdown, so the focused hwnd becomes the combo's
        # list — accept ANY focus inside the app thread (measured 09-01)
        for _ in range(4):
            relocate_wizard(session)
            winutil.force_set_foreground(session.hwnd)
            cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.15)
            winutil.real_click_screen(cx, cy)
            time.sleep(0.6)
            fh = focus_hwnd(session.hwnd)
            if fh:
                return True
            time.sleep(0.4)
        return False

    print(f"[panel] cycle combo start: text={combo_text()!r} "
          f"target={target_word!r}")
    if try_selectstring() and committed():
        return True
    VK_DOWN, VK_UP, VK_RETURN = 0x28, 0x26, 0x0D
    for vk in (VK_DOWN, VK_UP):
        for _step in range(max_steps):
            if not focus():
                print("[panel] cycle: combo focus FAILED")
                continue
            mdu._send_keys([(vk, False), (vk, True)])
            time.sleep(0.3)
            mdu._send_keys([(VK_RETURN, False), (VK_RETURN, True)])
            time.sleep(0.8)
            print(f"[panel] cycle vk={vk:#x} step={_step}: "
                  f"text={combo_text()!r} ocr_committed={committed()}")
            if committed():
                return True
        mdu._send_keys([(0x1B, False), (0x1B, True)])
        time.sleep(0.3)
    return False


def find_option_checkbox(session, label_substr, group_substr=None):
    """[(rect, hwnd)] checkbox candidates on the option row labeled
    `label_substr` (m4g's find_subdivide_row, generalized). A label with a
    space in it is matched as a PHRASE: find_option_row looks inside ONE
    OCR word, so 'Detect overhang' / 'Slow down' could never match
    (overhang_speeds scanned the whole page twice in each of queue18 and
    queue19: f775cd31, 90881c68)."""
    if " " in label_substr.strip():
        from .param_case_lib import _find_phrase_row
        y_row = _find_phrase_row(session, label_substr, group_substr)
        if y_row is None:
            return []
    else:
        word, y_row = find_option_row(session, label_substr, group_substr)
        if not word:
            return []
    cands = row_checkboxes(session, y_row, y_tol=14)
    if not cands:
        # A label that wraps to two lines ('Slow down for curled /
        # perimeters'): the box is centred on the ROW, about 15px off the
        # matched line's centre (overhang_curl c8225950 found the label and
        # nothing within 14px). Only that narrow band counts, so the next
        # row's box (30px or more away) still cannot.
        around = (row_checkboxes(session, y_row + 15, y_tol=8)
                  + row_checkboxes(session, y_row - 15, y_tol=8))
        if len(around) == 1:
            cands = around
    return cands


def find_option_row_seq(session, seq, group_substr=None,
                        timeout_s=420.0, psm=3):
    """find_option_row for a consecutive OCR word SEQUENCE: single-word
    matching is ambiguous when the value starts with a common token
    ('No ironing' and 'Nozzle' both match 'no' — measured 09-02).

    Scans like find_option_row - down to the page end, then back up - inside
    `group_substr`'s band, and the word run must start in the VALUE column.
    Until 2026-11-23 it looked at the start view and 5 notches down, then
    walked back: a value more than ~10 rows below its group title was
    unreachable (fa706g3 review D1), and the first word run anywhere in the
    band counted, label column included (D3).
    Returns (rect_of_word_run_client, run_center_y) or (None, None)."""
    if group_substr:
        hit = scroll_group_into_view(session, group_substr, timeout_s)
        print(f"[panel] scroll_group({group_substr!r}) -> "
              f"{'hit' if hit else 'NOT FOUND'}")
        if not hit:
            return None, None
    seq_l = [s.lower() for s in seq]
    n = len(seq_l)
    stall = _StallGuard(session, "find_option_row_seq%r" % (seq,))
    for direction in (-120, 120):
        stall.reset()
        started = time.monotonic()
        last_band = None
        for _ in range(SCAN_NOTCHES):
            if time.monotonic() - started > SCAN_SECONDS:
                print(f"[panel] row_seq{seq!r}: {SCAN_SECONDS:.0f}s cap reached", flush=True)
                break
            span = group_span(session, group_substr) if group_substr else None
            words = ocr_band(session, psm=psm)
            band = " ".join(w for w, *_ in words)[:110]
            if band != last_band:
                print(f"[panel] row_seq{seq!r} band: {band!r}")
                last_band = band
            for i in range(len(words) - n + 1):
                got = [w.lower() for w, *_ in words[i:i + n]]
                if got != seq_l:
                    continue
                x0, y0 = words[i][1], words[i][2]
                x1 = words[i + n - 1][1] + words[i + n - 1][3]
                y1 = words[i + n - 1][2] + words[i + n - 1][4]
                yc = (y0 + y1) // 2
                if x0 < VALUE_X0 or on_title_line(session, yc):
                    continue  # the label column, or a group title
                if span and not (span[0] <= y0 < span[1]):
                    continue  # the same value in a neighbouring group
                print(f"[panel] row_seq{seq!r} found at y={yc} x={x0}", flush=True)
                return (x0, y0, x1, y1), yc
            vp = options_viewport(session)
            if vp:
                if stall.step(words):
                    break
                wheel_viewport(session, vp, 1, delta=direction)
            time.sleep(0.4)
    return None, None


def find_option_combo_seq(session, seq, group_substr=None, psm=3):
    """find_option_combo keyed by a word SEQUENCE (see find_option_row_seq):
    resolve the combo control under the matched value run via
    WindowFromPoint. Returns (rect, hwnd, text)."""
    word, y_row = find_option_row_seq(session, seq, group_substr, psm=psm)
    if not word:
        return (None, None, None)
    ox, oy = client_origin(session)   # client coordinates, see find_option_combo
    sx, sy = ox + (word[0] + word[2]) // 2, oy + y_row
    return value_control_at(session, sx, sy, seq)


def value_control_at(session, x, y, value):
    """(rect, hwnd, text) of the control that paints a combo VALUE at screen
    (x, y), or (None, None, None) when there is none or it is disabled.

    Found by enumeration - the smallest visible child window that contains
    the point, carries text and is at most 320x64 - and the disabled verdict
    comes from IsWindowEnabled on that control. WindowFromPoint was used
    instead: it skips disabled windows and returns whatever lies behind
    (the 393x270 row container under 'Tree' while support is off, census
    c814315c), so "disabled" had to be guessed from the size of the answer -
    and on fa706g3 the point over an ENABLED 'Tree (auto)' resolved to a
    254x39 window and the combo was refused (fa run 744a5451)."""
    best = None
    for t, c, r, h, lx, ly in kids(session):
        if not t.strip() or not user32.IsWindowVisible(h):
            continue
        if not (r[0] <= x < r[2] and r[1] <= y < r[3]):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if w > 320 or hh > 64:
            continue
        if best is None or w * hh < (best[0][2] - best[0][0]) * (best[0][3] - best[0][1]):
            best = (r, h, t.strip())
    if best is None:
        print(f"[panel] value {value!r}: no control with text under ({x}, {y}) "
              f"- not a clickable combo", flush=True)
        return (None, None, None)
    rc, hwnd, text = best
    if not user32.IsWindowEnabled(hwnd):
        print(f"[panel] value {value!r}: control {rc} text {text!r} is DISABLED "
              f"(depends on another setting) - not a clickable combo", flush=True)
        return (None, None, None)
    return (rc, hwnd, text)


def work_area():
    """(left, top, right, bottom) of the primary monitor's work area - the
    screen minus the taskbar: 1920x1032 on the guest, while the maximized
    frame reports y up to 1039 and the options viewport reaches 1038
    (census c101c0f4). None when the query fails."""
    import ctypes.wintypes as wt
    rc = wt.RECT()
    if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0):  # SPI_GETWORKAREA
        return None
    return (rc.left, rc.top, rc.right, rc.bottom)


def park_for_popup(session, rect):
    """Wheel the options page DOWN until the control at screen `rect` has
    POPUP_ROOM px of work area below it. Returns the notch count (0 = the
    page did not move). The page moves WHEEL_STEP_PX per notch, so the
    caller has to locate its row again whenever this returns > 0."""
    work = work_area()
    vp = options_viewport(session)
    if not work or not vp:
        return 0
    short = POPUP_ROOM - (work[3] - rect[3])
    if short <= 0:
        return 0
    # Exactly enough notches, no spare one: a spare pushed rows that sat at
    # the very bottom (bottom 1009/1030) 300px up, i.e. above the viewport
    # top, where OCR no longer saw the label (brim 5a73aee3, filament_features
    # f27ba25c: 'param_combo_row_after_park' / a hunt for a row that was gone).
    notches = min(8, -(-short // WHEEL_STEP_PX))
    wheel_viewport(session, vp, notches, delta=-120)
    print(f"[panel] popup parking: row bottom {rect[3]} had "
          f"{work[3] - rect[3]}px of {POPUP_ROOM}px above the work-area "
          f"bottom {work[3]} -> {notches} notches", flush=True)
    return notches


def popup_hit_clickable(popup_hwnd, x, y):
    """True when a click at screen (x, y) would land INSIDE the popup. A
    popup row can sit under the taskbar: WindowFromPoint then names another
    window - Shell_TrayWnd for 'By object' (census c101c0f4)."""
    hwnd = winutil.window_from_screen_point(x, y)
    return bool(hwnd) and (hwnd == popup_hwnd
                           or bool(user32.IsChild(popup_hwnd, hwnd)))


def close_popup(session, popup_hwnd, combo_point):
    """Dismiss an open options popup; True once its window is gone or
    hidden. ESC first, then - if it is still there - a click on its own
    combo, which toggles it (a click anywhere else closes it too, but might
    toggle something on the way). Measured in census e80c899c: after ESC
    the next click on the combo opened nothing, i.e. the popup was still up
    and that outside click only closed it."""
    mdu._send_keys([(0x1B, False), (0x1B, True)])
    time.sleep(0.6)
    if popup_hwnd and user32.IsWindowVisible(popup_hwnd):
        winutil.msg_click_screen(combo_point[0], combo_point[1], session.hwnd)
        time.sleep(0.6)
    return not (popup_hwnd and user32.IsWindowVisible(popup_hwnd))


def set_combo_by_popup(session, locate, target_substr, log="[panel]",
                       verify_seq=None, group_substr=None, psm=3):
    """m5d's Support-Type mechanic, generalized: open the options-panel
    combo whose painted value matches `locate` (a word substring, or a word
    SEQUENCE tuple for ambiguous tokens), then click the popup row whose
    text contains `target_substr` (OCR-located first, blind 28px-pitch row
    fallback with re-open). Returns (ok, target_confirmed) where
    target_confirmed is True once `target_substr` is the painted value.

    verify_seq + group_substr: MEASURED 09-02 — a combo commit REBUILDS the
    page and the scroll lands elsewhere, so the painted-value OCR verify
    can hunt forever with the row off-band. When given, re-scroll
    `group_substr` into view, re-resolve the combo by the NEW value's word
    SEQUENCE `verify_seq`, and check the combo's REAL window text (the
    control exposes it even though the popup painting is OCR-hostile)."""
    import numpy as np
    from harness import export_util
    relocate_wizard(session)
    if group_substr and not isinstance(locate, (tuple, list)):
        # 2026-11-22: the string-locate path ignored group_substr; pre-scroll
        # the group into view so deep rows (Ironing type row, run 9b9048c4)
        # are on-band before the painted-value search. Best effort.
        try:
            scroll_group_into_view(session, group_substr)
        except Exception as exc:
            print(f"{log} group pre-scroll failed: {type(exc).__name__}")
    def _locate():
        if isinstance(locate, (tuple, list)):
            return find_option_combo_seq(session, locate, group_substr,
                                         psm=psm)
        return find_option_combo(session, locate, psm=psm)

    def _open():
        """Click the combo; its popup's (rect, hwnd) or None. A control
        whose popup was just dismissed can swallow the first click (census
        e80c899c), so the click is repeated once."""
        for attempt in range(2):
            winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2,
                                     session.hwnd)
            for _ in range(12 if attempt == 0 else 20):
                popup = export_util.wait_popup(session.pid, timeout_s=0.5)
                if popup:
                    return popup[2], popup[3]
            time.sleep(0.6)
        return None

    def _words(ph):
        time.sleep(0.8)  # self-drawn rows lag the popup creation
        words = []
        for _attempt in range(3):
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3, psm=6)   # list-like popup: see pick_combo_at_label
            if words:
                break
            time.sleep(0.6)
        return words

    r, h, cur = _locate()
    if h and park_for_popup(session, r):
        r, h, cur = _locate()  # the row moved up with the page
    print(f"{log} set_combo_by_popup({locate!r} -> {target_substr!r}): "
          f"combo text={cur!r}")
    if not h:
        return False, False
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    opened = _open()
    print(f"{log} popup: {opened}")
    if opened:
        pr, ph = opened
        words = _words(ph)
        print(f"{log} popup rows: "
              f"{' | '.join(t for t, *_ in words)[:140]!r}")
        hits = popup_line_hits(words, target_substr)
        if hits and not popup_hit_clickable(
                ph, pr[0] + hits[0][0], pr[1] + hits[0][1]):
            # The row is there but not on screen (under the taskbar). Close
            # the popup, move the page, open it again - once.
            print(f"{log} popup row {target_substr!r} is off-screen "
                  f"(popup {pr}, work area {work_area()}) -> parking the "
                  f"row and reopening", flush=True)
            close_popup(session, ph, (cx, cy))
            vp = options_viewport(session)
            if vp:
                wheel_viewport(session, vp, 3, delta=-120)
            # Everything derived from the old combo is stale from here on
            # (fa706g3 static review, 2026-11-23): cx/cy would sit 180px
            # below the row again - the blind fallback reopens "the combo"
            # at that point, i.e. whatever control sits there now - and a
            # failed re-locate or reopen left the CLOSED popup's rect/hwnd
            # in pr/ph for the click loop to work on.
            opened = None
            if h:
                cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                opened = _open()
            print(f"{log} popup after parking: {opened} (combo located: {bool(h)})")
            if opened:
                pr, ph = opened
                words = _words(ph)
                print(f"{log} popup rows: "
                      f"{' | '.join(t for t, *_ in words)[:140]!r}")
                hits = popup_line_hits(words, target_substr)
            else:
                hits = []
        popup_open = bool(opened)
        clicked = False
        for cx_, cy_, _line in hits:
            x, y = pr[0] + cx_, pr[1] + cy_
            if popup_hit_clickable(ph, x, y):
                winutil.msg_click_screen(x, y)
                clicked = True
            else:
                print(f"{log} popup row at ({x}, {y}) is still not "
                      f"clickable - leaving it unclicked", flush=True)
            break
        if not clicked and not hits and popup_open:
            # blind fallback: 28px row pitch; verify by re-locating the
            # combo by its new value after each click, reopen when missed
            for row in range(5):
                x, y = (pr[0] + pr[2]) // 2, pr[1] + 14 + row * 28
                if not popup_hit_clickable(ph, x, y):
                    continue
                winutil.msg_click_screen(x, y)
                time.sleep(1.0)
                if find_option_combo(session, target_substr)[1]:
                    clicked = True
                    print(f"{log} blind row {row} hit {target_substr!r}")
                    break
                winutil.msg_click_screen(cx, cy, session.hwnd)
                time.sleep(1.0)
                popup2 = None
                for _ in range(10):
                    popup2 = export_util.wait_popup(session.pid,
                                                    timeout_s=0.5)
                    if popup2:
                        break
                    time.sleep(0.2)
                if not popup2:
                    break
                pr, ph = popup2[2], popup2[3]   # a reopened popup can be a new window
        time.sleep(1.5)
    # Verification, cheapest and most exact first. The combo is a real
    # ComboBox and its window text is the committed value: reading it is
    # free and settles the question both ways (run 6640e4a9 scanned whole
    # pages for the painted value - 38 notches - to learn that nothing had
    # changed). Without window text (the control was rebuilt, or never had
    # any) a combo is located by the TARGET value with the word-sequence
    # logic that found the combo in the first place. An earlier version
    # accepted any line on the band that merely contained the words - a
    # label would have done (fa706g3 review).
    buf = ctypes.create_unicode_buffer(256)
    if h and user32.IsWindow(h):
        user32.GetWindowTextW(h, buf, 256)
    ok = bool(buf.value) and target_substr.lower() in buf.value.lower()
    if buf.value:
        print(f"{log} combo window text now {buf.value!r} -> {ok}")
    if not ok and not buf.value:
        if " " in target_substr.strip():
            ok = find_option_combo_seq(session, tuple(target_substr.lower().split()),
                                       group_substr, psm=psm)[1] is not None
        else:
            ok = find_option_combo(session, target_substr, psm=psm)[1] is not None
    if not ok and verify_seq:
        if group_substr:
            scroll_group_into_view(session, group_substr)
        _r2, _h2, txt2 = find_option_combo_seq(session, verify_seq,
                                               psm=psm)
        ok = bool(_h2 and target_substr.lower() in (txt2 or "").lower())
        print(f"{log} verify by combo text: {txt2!r} ok={ok}")
    else:
        print(f"{log} combo now paints target: {ok}")
    return h is not None, ok


def set_option_checkbox(session, label_substr, want_checked,
                        group_substr=None, tries=4):
    """Toggle the checkbox on the option row `label_substr` until the frame
    state reads `want_checked` (checked ~0.21 teal fraction, unchecked
    ~0.00-0.06; measured 08-31). Returns (state, rect) or (None, None)."""
    cands = find_option_checkbox(session, label_substr, group_substr)
    for attempt in range(tries):
        if not cands:
            cands = find_option_checkbox(session, label_substr, group_substr)
            if not cands:
                return None, None
        for rect, h in cands[:3]:
            before = checked_state(session, rect)
            if attempt < 2:
                real_click(rect)
            else:
                cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
                winutil.user32.SetCursorPos(cx, cy)
                time.sleep(0.15)
                winutil.msg_click_screen(cx, cy, session.hwnd)
                time.sleep(1.0)
            time.sleep(0.8)
            after = checked_state(session, rect)
            print(f"[panel] checkbox {label_substr!r} att{attempt}: "
                  f"{before:.2f} -> {after:.2f}")
            now_on = after > CHECKED_FRACTION
            if now_on == want_checked:
                return now_on, rect
        time.sleep(0.8)
    return None, None
