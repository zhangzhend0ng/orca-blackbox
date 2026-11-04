#!/usr/bin/env python3
# m8_common.py — shared ops for the m8 batch (飞书「基线用例」base
# EDUAbYWcbaL2HOsgFM1cXmBpn5f, table tblvh0eGrID9JQ02: Fit view #16-#19,
# official color dialog #44-#48/#55-#59, temperature-mixing gate #111/#112,
# purifier gcode #113/#114/#122/#126-#129, high-flow nozzle #133/#135/#136).
#
# Ops are composed from the primitives the older milestones proved:
#   - filament slots are a 2-column grid of [chip][combo][picker] triples
#     (measured 09-17 on the mixed fixture: slot1 combo [38,410,178,440],
#     picker [183,413,199,436], slot2 combo [236,410,388,440])
#   - preset combos are SELF-DRAWN: popup rows probed at the m3e 28px pitch
#     with GetWindowText readback (m3e.switch_preset contract)
#   - the color picker is a 20 DIP bitmap button (clr_picker) next to each
#     combo; ChangeExtruderColor opens the OFFICIAL FilamentColorDialog only
#     for Snapmaker-named presets (PresetComboBoxes.cpp:1067) and falls back
#     to the legacy wx colour dialog otherwise
#   - the Fit camera button is the ImGui FitCameraButtonWindow (GLCanvas3D
#     :7050, tooltip "Fit in all view"); ZoomToFit() (:2824): selection ->
#     zoom_to_selection, assemble canvas -> zoom_to_volumes, else
#     zoom_to_bed. On the maximized rig it sits at client
#     (VIEWPORT_X0+152, height-44) — measured by diag_m8_probe (09-17,
#     blob area 39k -> 424k on click)
#   - purifier gcode comes from the U1 machine start template:
#     SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=45 ... DELAY_OFF=600 (keep-warm),
#     MODE=1 DESIRE_TEMP=42 ALARM_TEMP=45 DELAY_OFF=0 (strong), MODE=3
#     DESIRE_TEMP=0 ... DELAY_OFF=600 (weak) — mode derived in
#     GCode.cpp:2722 from temperature_vitrification (<=50 strong, <=70
#     weak, high-temp filaments skip -> keep-warm)

import ctypes
import ctypes.wintypes as wt
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from harness.anchors import capture_bgr  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m8]"
ART = HERE / "artifacts"
user32 = ctypes.WinDLL("user32")

# Fit button client offset on the maximized rig (diag_m8_probe 09-17)
FIT_X_OFF = 152
FIT_Y_FROM_BOTTOM = 44

# purifier start-gcode line, asserted param sets per cooling class
PURIFIER_RE = re.compile(rb"SET_PURIFIER_MODE[^\r\n]*")


def fit_click(session):
    """Click the Fit camera button (bottom-left of the canvas)."""
    img = capture_bgr(session)
    h = img.shape[0]
    sx, sy = m7.client(session, m7.VIEWPORT_X0 + FIT_X_OFF,
                       h - FIT_Y_FROM_BOTTOM)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    winutil.msg_click_screen(sx, sy, session.hwnd)
    time.sleep(1.5)


def blob_stats(img):
    """Largest chromatic blob in the viewport: area / bbox / centroid."""
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    x0, y0, x1, y1 = m7.VIEWPORT_X0 + 10, 110, w - 10, h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _lbl, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > best_area:
            best, best_area = i, a
    if best is None:
        return None
    i = best
    return {
        "area": int(best_area),
        "bbox": [int(stats[i, cv2.CC_STAT_LEFT]) + x0,
                 int(stats[i, cv2.CC_STAT_TOP]) + y0,
                 int(stats[i, cv2.CC_STAT_WIDTH]),
                 int(stats[i, cv2.CC_STAT_HEIGHT])],
        "centroid": [int(cents[i][0]) + x0, int(cents[i][1]) + y0],
    }


def viewport_diff(img_a, img_b):
    """Fraction of pixels that changed meaningfully between two frames."""
    import numpy as np
    return float((abs(img_b.astype(int) - img_a.astype(int))
                  .sum(axis=2) > 40).mean())


# --- filament slot grid -------------------------------------------------------

def filament_slots(session):
    """[{slot, combo(text,rect,hwnd), picker_rect, swatch_rect}] from the
    sidebar child tree.

    STRUCTURAL, not band-based: the numbered chips are found by their text
    ('1'..'5', a small button), and each row's combo / legacy picker is matched
    by sharing the chip's row (same centre y, to the right of the chip). The
    previous version scoped rows with the 'Filaments' label + a fixed y band and
    an x<425 filter calibrated on the 1200x800 window — under the MAXIMIZED
    layout (1920x1080) that band matched only ONE row (measured 09-28: slots ==
    [(5, ...)]), so every slot lookup failed.

    It also computed `picker` OUTSIDE the per-chip loop, so every slot was
    handed the LAST row's rectangle — that is why clicking slot 2's colour
    control opened the wrong thing (leading, via the legacy Edit menu, to the
    native colour picker instead of the official library).

    `swatch` is the numbered chip itself: its background is the filament colour
    and, for Snapmaker presets, clicking it opens the OFFICIAL colour library
    (probe 09-28: chip '2' -> popup carrying 'Official Filaments' / 'sku
    34205'). `picker` is the 16x25 button to its right, whose click opens the
    legacy Edit/Delete/Merge #32768 menu.
    """
    rows = list(export_util._children_texts(session.hwnd))
    chips, texts, smalls = [], [], []
    for text, rect, ch in rows:
        if rect[0] > 520 or rect[2] <= rect[0]:     # sidebar only, sane rect
            continue
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        t = text.strip()
        if t.isdigit() and len(t) <= 2 and w <= 30 and h <= 32:
            chips.append((int(t), rect))
        elif 12 <= w <= 30 and 16 <= h <= 30:
            smalls.append(rect)
        elif t and w >= 60:
            texts.append((t, rect, ch))
    out = []
    for no, chip_rect in sorted(chips):
        cy = (chip_rect[1] + chip_rect[3]) / 2
        combo = None
        for text, rect, ch in texts:
            ry = (rect[1] + rect[3]) / 2
            if abs(ry - cy) < 12 and chip_rect[2] <= rect[0] <= chip_rect[2] + 20:
                if combo is None or rect[0] < combo[1][0]:
                    combo = (text, rect, ch)
        picker = None
        for rect in smalls:
            ry = (rect[1] + rect[3]) / 2
            if abs(ry - cy) < 12 and rect[0] > chip_rect[2] - 6:
                if picker is None or rect[0] < picker[0]:
                    picker = rect
        out.append({"slot": no, "combo": combo, "picker": picker,
                    "swatch": chip_rect})
    return out



def wait_slots(session, timeout_s=25.0):
    """filament_slots() once the sidebar actually exposes the slot rows.

    The sidebar is populated ASYNCHRONOUSLY: reading the child tree right after
    the GL canvas reports ready returns no slot rows at all, which surfaced as
    "slot 2 combo not found" and killed the whole case in its first step
    (measured 09-28 — the early system-preset re-apply). Poll instead of
    assuming the layout exists."""
    deadline = time.monotonic() + timeout_s
    slots = filament_slots(session)
    while time.monotonic() < deadline:
        if any(s.get("combo") for s in slots):
            return slots
        time.sleep(0.5)
        slots = filament_slots(session)
    print(f"{LOG} wait_slots: no slot combo appeared within {timeout_s:.0f}s "
          f"({[{k: (v is not None) for k, v in s.items() if k != 'slot'} for s in slots]})")
    return slots


def combo_text(ch):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, buf, 256)
    return buf.value


def _ocr_click_line(session, popup_rect, target_substr, popup_hwnd=None) -> bool:
    """OCR the POPUP window and click the line matching target_substr.

    The popup is a separate top-level window: the main-window capture does not
    contain it (a first cut OCR'd the panel underneath and read 'Advanced',
    'Multimaterial' — measured 09-21), so capture the popup itself.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from harness import mix_dialog_util as mdu  # noqa: PLC0415
    if popup_hwnd:
        try:
            w, h, buf = winutil.capture_window(popup_hwnd)
            img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(h, w, 4),
                               cv2.COLOR_BGRA2BGR)
        except Exception as exc:  # noqa: BLE001
            # PrintWindow times out while the app is busy (WinError 1460,
            # measured 09-23 across a whole filament-switch loop) — fall back
            # to a SCREEN grab cropped to the popup rect: the popup is a
            # top-level window, so the desktop shows it.
            print(f"{LOG} popup PrintWindow failed ({exc}) — screen crop")
            img = capture_bgr(session)
            x0, y0, x1, y1 = [int(v) for v in popup_rect]
            img = img[max(0, y0):y1, max(0, x0):x1]
        ox, oy = popup_rect[0], popup_rect[1]
    else:
        img = capture_bgr(session)
        ox = oy = 0
    if img.size == 0:
        return False
    try:
        words = mdu.ocr_words_img(img, scale=3, psm=6)
    except Exception as exc:  # noqa: BLE001
        # tesseract can fail to allocate while the app holds most of the
        # guest's RAM (pix_malloc fail, measured 09-23) — degrade to "row not
        # read this step" so the scroll loop retries instead of crashing
        print(f"{LOG} popup OCR failed ({exc}) — retrying")
        return False
    tokens = [t.lower() for t in re.split(r"\s+", target_substr) if t]
    lines: dict[int, list] = {}
    for wd in words:
        lines.setdefault(round(wd[2] / 8), []).append(wd)
    for key in sorted(lines):
        row = sorted(lines[key], key=lambda wd: wd[1])
        line_text = " ".join(wd[0] for wd in row).lower()
        if tokens and all(t in line_text for t in tokens):
            cx = ox + row[0][1] + row[0][3] // 2
            cy = oy + row[0][2] + row[0][4] // 2
            print(f"{LOG} popup OCR row {line_text!r} -> click ({cx},{cy})")
            winutil.msg_click_screen(cx, cy)   # popup is top-level: no root
            return True
    return False


def _real_wheel(x, y, notches):
    """Real (input-queue) wheel scroll at a screen point.

    Self-contained on purpose: some app popups ignore message-level
    WM_MOUSEWHEEL — the filament preset list never moved on 2.4.0, so an
    alphabetically earlier target ('Snapmaker PLA Rainbow' above the current
    selection) stayed unreachable (measured 09-28: 11 attempts OCR'd the same
    lower window). Inlined via ctypes so no harness-side change has to be
    shipped alongside the case."""
    import ctypes  # noqa: PLC0415
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    u.mouse_event(0x0800, 0, 0, 120 * int(notches), 0)


def click_popup_row(session, popup_rect, target_substr, popup_hwnd=None,
                    scrolls=14, notch=3) -> bool:
    """Find the target row in the popup (OCR of the POPUP window), scrolling.

    Rows are SELF-DRAWN (child enumeration yields nothing) and the popup shows
    only ~13 rows, so a click-walk at the historical 28px pitch stalls once it
    passes the visible area (measured 09-21 — it parked on 'Bambu PAHT-CF'
    while 'Generic ABS' stayed below the fold). The popup opens AT the current
    selection, so scroll to the top first, then walk down, re-OCR-ing each step.
    Wheel goes through WM_MOUSEWHEEL (message-level: no focus needed).
    """
    if popup_hwnd is None:
        return _ocr_click_line(session, popup_rect, target_substr)
    x = (popup_rect[0] + popup_rect[2]) // 2
    y = (popup_rect[1] + popup_rect[3]) // 2
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)

    def wheel(notches: int) -> None:
        wparam = (((-120 * notches) & 0xFFFF) << 16)   # negative delta = down
        winutil._send_msg(popup_hwnd, 0x020A, wparam, lparam)

    wheel(-scrolls * 2)          # first: back to the top of the list
    time.sleep(0.7)
    for _step in range(scrolls * 2 + 1):
        if _ocr_click_line(session, popup_rect, target_substr, popup_hwnd):
            return True
        wheel(notch)
        time.sleep(0.5)
    # Second pass with REAL wheel input: on 2.4.0 the preset popup ignored
    # message-level WM_MOUSEWHEEL (the OCR window never moved, so a target
    # ABOVE the opening position was unreachable — measured 09-28).
    print(f"{LOG} popup: message-level wheel found nothing — retrying with real input")
    _real_wheel(x, y, -scrolls)
    time.sleep(0.7)
    for _step in range(scrolls + 1):
        if _ocr_click_line(session, popup_rect, target_substr, popup_hwnd):
            return True
        _real_wheel(x, y, max(1, notch // 2))
        time.sleep(0.45)
    return False


def switch_filament_preset(session, slot, target_substr, tries=30, force=False):
    """Row-probe the slot's preset combo until the text flips to target.
    Returns the final text ('' on failure).

    force=True re-applies the preset even when the combo text ALREADY contains
    target_substr. That early return is a trap for project-carried settings: the
    project embeds its own filament_* values (mixed_filament_test.3mf carries 50
    of them), so slot 2 reads 'Snapmaker PLA Silk @U1 0.8 nozzle*' — the preset
    NAME with Orca's profile-modified marker. Returning on the name match leaves
    the PROJECT's values (and the asterisk) in place, while the case is supposed
    to run on the SYSTEM preset (user instruction, 09-24).

    tries=30: the filament popup lists every installed preset (aliases, Bambu,
    Generic, …) and the target can sit well past row 10 — with tries=10 the walk
    stopped early and returned the last row it happened to select (measured
    09-21: 'Bambu ASA-CF' instead of 'Generic ABS'). Each attempt re-opens the
    popup and clicks one row deeper, so the walk is O(rows), not a search.
    """
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["combo"]:
        print(f"{LOG} slot {slot} combo not found")
        return ""
    text, rect, ch = hit["combo"]
    if not force and target_substr in combo_text(ch):
        return combo_text(ch)
    # Budget guard: each attempt opens the popup (4s wait) and may scroll it 24
    # notches, so `tries=30` can run tens of minutes when the target row is not
    # in the list at all — a case that should FAIL loudly instead hung with the
    # screen frozen (measured 09-24: the force=True re-apply, which cannot use
    # the name-match short-circuit, sat >15min). The re-apply case also only
    # needs a short walk: the preset is already the one displayed on the combo.
    deadline = time.monotonic() + (90.0 if force else 240.0)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    for attempt in range(tries):
        if time.monotonic() > deadline:
            print(f"{LOG} slot{slot} preset-switch budget exhausted after "
                  f"{attempt} attempt(s) — reporting the current text")
            break
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            time.sleep(0.5)
            continue
        pr = popup[2]
        if click_popup_row(session, pr, target_substr, popup_hwnd=popup[3],
                           scrolls=24, notch=4):
            time.sleep(0.9)
            now = combo_text(ch)
            print(f"{LOG} slot{slot} OCR row -> {now!r}")
            if target_substr in now:
                return now
            continue
        # NO blind pitch-walk fallback: clicking rows that OCR did not match
        # mis-selects an arbitrary preset (measured 09-23: the walk landed on
        # 'eSUN PLA+' while looking for '- HF-TEST'), which then poisons every
        # later step. Report the current text instead and let the caller fail
        # loudly.
        # diagnostic: the popup's own text, so a failed match shows what the
        # list actually offered (OCR is the only reader — the rows are
        # self-drawn and expose no child text)
        try:
            from harness import mix_dialog_util as _mdu
            import cv2 as _cv2
            import numpy as _np
            pw, ph, pbuf = winutil.capture_window(popup[3])
            pimg = _cv2.cvtColor(_np.frombuffer(pbuf, _np.uint8).reshape(ph, pw, 4),
                                 _cv2.COLOR_BGRA2BGR)
            words = [w for w, *_ in _mdu.ocr_words_img(pimg, scale=2)]
            print(f"{LOG} slot{slot} popup OCR ({len(words)} words): "
                  f"{' '.join(words)[:280]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"{LOG} slot{slot} popup OCR unavailable: {exc}")
        print(f"{LOG} slot{slot} target {target_substr!r} not found by OCR "
              f"(attempt {attempt + 1}/{tries})")
        time.sleep(0.6)
    return combo_text(ch)


def confirm_flow_dialog(session):
    """Answer the prompt raised by a High-Flow switch (the doc's
    '确认切片分配喷嘴' popup) before slicing.

    Measured 09-24: right after Flow -> High Flow the Slice click is rejected
    ('slice click rejected') until the prompt is answered. Prefer a button
    mentioning the high-flow nozzle, then OK/Confirm, then the first button.
    Returns the action taken (or '' when no prompt appeared)."""
    dlg = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32770", timeout_s=3.0)
    if not dlg:
        return ""
    print(f"{LOG} flow prompt: {dlg[1]!r} rect={dlg[2]}")
    kids = export_util._children_texts(dlg[3])
    print(f"{LOG} flow prompt texts: {[t.strip() for t, _r, _c in kids if t.strip()][:10]}")
    for want in ("high", "高流量", "ok", "yes", "confirm", "确定"):
        # NOTE: this used to call a non-existent click_dialog_button(); the path
        # was never exercised (m8f/m8g only ever meet the high-flow prompt), so a
        # different dialog shape — measured 09-29: an app error box raised while
        # switching flow with an edited process parameter — crashed with
        # NameError. Match and click the button here, with a REAL click: a modal
        # dialog swallows message-level clicks (#123 lesson).
        hit = next(((t.strip(), r) for t, r, _h in kids
                    if want in t.strip().lower()), None)
        if hit:
            t, r = hit
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            winutil.real_click_screen(cx, cy)
            print(f"{LOG} flow prompt -> {t!r}")
            time.sleep(1.0)
            return t
    if kids:
        t, r, _c = [k for k in kids if k[0].strip()] or kids
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.real_click_screen(cx, cy)
        print(f"{LOG} flow prompt -> first child {t!r}")
        time.sleep(1.0)
        return f"first {t!r}"
    return ""


OFFICIAL_MARKER = "official filaments"


def official_color_popup(session, timeout_s=8.0):
    """The OFFICIAL colour library (#32770, empty title, children carrying
    'Official Filaments' + the current colour's name and SKU), or None.

    Measured 09-24/28 with diag_m8b_swatch_probe (8 controls in slot 2's row
    clicked one by one): the popup comes from the slot's NUMBERED COLOUR CHIP
    (child 'Button' with text '2', whose background is the filament colour) for
    a Snapmaker-named preset, while the 16x25 button to its right opens the
    Edit/Delete/Merge #32768 menu — the legacy chain that ends at the NATIVE
    Windows picker. The chip path was never taken by the old code because
    filament_slots() picked its 'picker' by size (leftmost 12-30px child)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, title, rect, hwnd in _visible_toplevels(session.pid):
            if cls != "#32770":
                continue
            texts = [t.strip().lower() for t, _r, _h
                     in export_util._children_texts(hwnd) if t.strip()]
            if any(OFFICIAL_MARKER in t for t in texts):
                return cls, title, rect, hwnd
        time.sleep(0.3)
    return None


def popup_colour_texts(popup):
    """(name, sku) of the official popup's current colour, or (None, None)."""
    names, skus = [], []
    for t, _r, _h in export_util._children_texts(popup[3]):
        t = t.strip()
        if not t:
            continue
        if t.lower().startswith("sku"):
            skus.append(t)
        elif OFFICIAL_MARKER not in t.lower() and t.lower() not in (
                "panel", "cancel", "ok", "+ other colors", "official filaments"):
            names.append(t)
    return (names[0] if names else None), (skus[0] if skus else None)


def slot_swatch_rgb(session, slot):
    """Mean BGR of the slot's colour chip (its background IS the filament
    colour) — the swatch surface the baseline rows talk about."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit.get("swatch"):
        return None
    x0, y0, x1, y1 = hit["swatch"]
    crop = _screen_crop(x0 + 4, y0 + 4, x1 - 4, y1 - 4)
    if crop is None or crop.size == 0:
        return None
    # cv2 BGR order; the chip is a flat colour, so the mean is stable
    return [int(v) for v in crop.reshape(-1, 3).mean(axis=0)]


def _screen_crop(x0, y0, x1, y1):
    """Crop the desktop grab; the chip rects come from GetWindowRect (screen
    coordinates), so they apply directly here (the earlier stills mixed client
    and screen coordinates and cropped the wrong region, measured 09-24)."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    sw, sh, buf = winutil.screen_grab()
    img = np.frombuffer(buf, np.uint8).reshape(sh, sw, 4)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img[max(0, y0):y1, max(0, x0):x1]


def click_official_color_popup(session, slot, timeout_s=8.0):
    """Click the slot's colour chip and return the official popup (or None)."""
    slots = wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit.get("swatch"):
        print(f"{LOG} slot {slot} colour chip not found")
        return None
    x0, y0, x1, y1 = hit["swatch"]
    sx, sy = winutil.client_to_screen(session.hwnd,
                                      (x0 + x1) // 2, (y0 + y1) // 2)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    popup = official_color_popup(session, timeout_s=timeout_s)
    print(f"{LOG} slot{slot} chip click at ({sx},{sy}) -> "
          f"{'official colour popup' if popup else 'nothing'}")
    return popup


def click_color_picker(session, slot, timeout_s=6.0, dialog_cls="#32770"):
    """Click the slot's colour control; return the OFFICIAL colour popup tuple
    or, when the slot holds a non-Snapmaker filament (which falls back to the
    legacy picker), the native 'Color' dialog.

    Preferred path (measured 09-28): the slot's NUMBERED COLOUR CHIP opens the
    official library directly for Snapmaker presets. Only when no official
    popup appears does the legacy chain run: picker (REAL click) -> native
    #32768 menu (Edit/Delete/Merge with) -> its first row 'Edit' -> 'Material
    settings' dialog -> its 'colourpicker' child (MESSAGE click: a real click
    there is swallowed, g7b) -> native 'Color' #32770."""
    popup = click_official_color_popup(session, slot, timeout_s=timeout_s)
    if popup:
        return popup
    # A non-official filament (非官方耗材, baseline #44's 纯色 case) falls back
    # to the LEGACY picker and the chip click already opened it — take that one
    # instead of running the menu chain again and stacking a second dialog
    # (measured 09-28: slot 1 'Generic PETG' -> 'Please choose the filament
    # color' with '&Basic colors:').
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        native_dlg = export_util.wait_toplevel(
            session.pid, lambda c, t, r: c == "#32770", timeout_s=0.5)
        if native_dlg:
            texts = [x.strip().lower() for x, _r, _h
                     in export_util._children_texts(native_dlg[3])]
            if any("basic colors" in x for x in texts):
                print(f"{LOG} slot{slot}: legacy picker opened by the chip "
                      f"(title={native_dlg[1]!r})")
                return native_dlg
            break
        time.sleep(0.3)
    slots = filament_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["picker"]:
        print(f"{LOG} slot {slot} picker not found")
        return None
    rect = hit["picker"]
    px = (rect[0] + rect[2]) // 2
    py = (rect[1] + rect[3]) // 2
    # REAL click: the clr_picker is a wxBitmapButton whose wx handler
    # needs a real input event (message-level clicks never opened the
    # menu, measured 09-17 suite)
    sx, sy = winutil.client_to_screen(session.hwnd, px, py)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    menu = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32768", timeout_s=3.0)
    if menu:
        mr = menu[2]
        my = mr[1] + max((mr[3] - mr[1]) // 6, 8)   # first row of three
        mx = (mr[0] + mr[2]) // 2
        winutil.user32.SetCursorPos(mx, my)
        time.sleep(0.2)
        winutil.real_click_screen(mx, my)
        time.sleep(0.5)
    # 'Material settings' (contains the colourpicker child)
    dlg = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32770", timeout_s=timeout_s)
    if dlg:
        cp = next((ch for t, r, ch
                   in export_util._children_texts(dlg[3])
                   if t.strip() == "colourpicker"), None)
        if cp:
            rc = wt.RECT()
            user32.GetWindowRect(cp, ctypes.byref(rc))
            winutil.msg_click_screen((rc.left + rc.right) // 2,
                                     (rc.top + rc.bottom) // 2, cp)
            time.sleep(1.5)
            # the official color dialog opens as a SECOND #32770 ('Color')
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                for cls, title, rect2, hwnd in _visible_toplevels(
                        session.pid):
                    if cls == "#32770" and "color" in title.lower():
                        time.sleep(1.0)
                        return cls, title, rect2, hwnd
                time.sleep(0.3)
    if dialog_cls:
        dlg = export_util.wait_toplevel(
            session.pid, lambda c, t, r: c == dialog_cls,
            timeout_s=timeout_s)
    else:
        dlg = export_util.wait_popup(session.pid, timeout_s=timeout_s)
    time.sleep(1.0)
    return dlg


def _visible_toplevels(pid):
    """[(cls, title, rect, hwnd)] of the pid's visible top-level windows."""
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(96)
        user32.GetWindowTextW(hwnd, txt, 96)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value,
                    (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def close_dialog_by_button(dlg, substr):
    """Click the dialog child button whose text contains substr."""
    kids = export_util._children_texts(dlg[3])
    for t, r, _h in kids:
        if substr.lower() in t.lower():
            winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            time.sleep(1.2)
            return True
    return False


# --- nozzle band --------------------------------------------------------------

def nozzle_reads(session):
    """{diameter, flow, flow_rect} from the sidebar nozzle section.

    Values are located RELATIVE to the 'Diameter'/'Flow' labels instead of the
    original rig's absolute band (screen y 275-325): on this rig the section sits
    elsewhere, so the band returned the diameter by luck and never saw the flow
    value (measured 09-21: flow=None while the panel showed 'Standard').
    On 2.4.0 the nozzle section appears TWICE in the child tree: a collapsed
    template instance (y~248-280, 20px slivers at x5-25) and the live one
    (y~283-315). Anchor on the LIVE labels (label rows below y=250) and only
    accept value rects wide enough to be the live widgets (measured 09-22, g11).
    """
    rows = list(export_util._children_texts(session.hwnd))
    labels = [r for t, r, _c in rows if t.strip() in ("Diameter", "Flow")
              and r[0] < 425 and r[1] > 250]
    if labels:
        lo, hi = min(r[1] for r in labels) - 12, max(r[3] for r in labels) + 12
    else:
        lo, hi = 275, 325
    diameter = flow = None
    flow_rect = None
    for text, rect, ch in rows:
        if not (lo <= rect[1] <= hi and rect[0] < 425):
            continue
        if text.strip() == "Diameter" or text.strip() == "Flow":
            continue
        if rect[2] - rect[0] < 40:      # degenerate template instance
            continue
        if text.strip().endswith("mm"):
            diameter = text.strip().replace(" ", "")
        elif text.strip() in ("Standard", "High Flow"):
            flow = text.strip()
            flow_rect = rect
    return {"diameter": diameter, "flow": flow, "flow_rect": flow_rect}


def switch_flow_combo(session, target_substr, tries=4):
    """Row-probe the nozzle Flow combo ('Standard'/'High Flow')."""
    reads = nozzle_reads(session)
    rect = reads.get("flow_rect")
    if not rect:
        print(f"{LOG} flow combo not found")
        return ""
    # click near the combo's dropdown arrow (the value text child is a
    # Static overlay; a center click can land on it and be swallowed)
    cx = rect[2] - 12
    cy = (rect[1] + rect[3]) // 2
    for attempt in range(tries):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            print(f"{LOG} flow attempt {attempt + 1}: popup did not open")
            time.sleep(0.6)
            continue
        pr = popup[2]
        # OCR the popup and click the ROW whose text contains the target —
        # the blind pitch walk missed whenever the popup failed to reopen on
        # the 2nd attempt, so the switch never happened (measured 09-24: the
        # options list DID contain 'High Flow' all along, g33).
        if click_popup_row(session, pr, target_substr, popup_hwnd=popup[3]):
            time.sleep(0.9)
            now = nozzle_reads(session).get("flow") or ""
            print(f"{LOG} flow OCR row -> {now!r}")
            if target_substr in now:
                time.sleep(0.8)
                return now
            continue
        px = (pr[0] + pr[2]) // 2
        py = pr[1] + 14 + attempt * 28
        winutil.msg_click_screen(px, py)
        time.sleep(0.9)
        now = nozzle_reads(session).get("flow") or ""
        print(f"{LOG} flow row {attempt}: {now!r}")
        if target_substr in now:
            time.sleep(1.0)
            return now
    return nozzle_reads(session).get("flow") or ""


def wait_arrival(session, timeout_s=300, min_frac=0.0025):
    """Wait for fixture-model arrival while CONTINUOUSLY sweeping blocker
    dialogs. The boot sweep (launcher, 25s budget) can miss load-phase
    dialogs: 'Customized Preset' re-pops per preset group and 'Loading...'
    lingers — any of them blocks arrival forever (measured 09-17 suite:
    m8d/m8c arrival FAIL with the dialog dismissed only once). Gate is
    0.25% (m7i small-cube gate): the mixed fixture reads only ~0.8%
    chromatic on the new build, jittering around the old 0.6% gate."""
    from m7_common import model_colored_frac
    from harness import launcher
    deadline = time.monotonic() + timeout_s
    frac = model_colored_frac(session)
    ok = frac >= min_frac
    while not ok and time.monotonic() < deadline:
        launcher.sweep_boot_blockers(session.pid, session.hwnd, budget_s=3.0)
        time.sleep(2.0)
        frac = model_colored_frac(session)
        ok = frac >= min_frac
    print(f"{LOG} arrival: {ok} ({frac:.2%}, gate {min_frac:.2%})")
    return ok, frac


# --- purifier gcode asserts ---------------------------------------------------

def purifier_params(gcode_bytes):
    """Parse the first SET_PURIFIER_MODE line into a dict (None if absent)."""
    m = PURIFIER_RE.search(gcode_bytes)
    if not m:
        return None
    line = m.group(0)
    out = {}
    for key in (b"MODE", b"DESIRE_TEMP", b"ALARM_TEMP", b"FAN_SPEED",
                b"DELAY_OFF"):
        km = re.search(key + rb"=([-\w.]+)", line)
        out[key.decode()] = km.group(1).decode() if km else None
    return out


def used_filaments(gcode_bytes):
    """[i+1 for slots with nonzero 'filament used [g]' weight]. The comment
    reads `; filament used [g] = 10.24, 0.00, ...` (measured 09-17)."""
    m = re.search(rb"; filament used \[g\] ?= ?([\d., ]+)", gcode_bytes)
    if not m:
        return []
    vals = [float(v) for v in re.split(rb"[, ]+", m.group(1).strip()) if v]
    return [i + 1 for i, v in enumerate(vals) if v > 0]
