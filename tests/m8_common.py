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
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

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
    """[(slot_no, combo(text,rect,hwnd), picker_rect)] parsed from the
    sidebar child tree. The grid rows live at y 400-520 on the maximized
    rig; chips are the numbered text children."""
    chips, texts, pickers = [], [], []
    for text, rect, ch in export_util._children_texts(session.hwnd):
        if not (395 <= rect[1] <= 540 and rect[0] < 425):
            continue
        if text.strip().isdigit() and rect[2] - rect[0] < 26:
            chips.append((int(text.strip()), rect))
        elif text.strip() and ('(' in text or '@' in text
                                or 'Filament' in text):
            texts.append((text.strip(), rect, ch))
        elif 12 <= rect[2] - rect[0] <= 30 and 16 <= rect[3] - rect[1] <= 30:
            pickers.append(rect)
    out = []
    for no, chip_rect in sorted(chips):
        cy = (chip_rect[1] + chip_rect[3]) / 2
        combo = None
        for text, rect, ch in texts:
            ry = (rect[1] + rect[3]) / 2
            if abs(ry - cy) < 12 and rect[0] > chip_rect[2] - 6:
                if combo is None or rect[0] < combo[1][0]:
                    combo = (text, rect, ch)
        picker = None
        for rect in pickers:
            ry = (rect[1] + rect[3]) / 2
            if abs(ry - cy) < 12 and rect[0] > chip_rect[2] - 6:
                if picker is None or rect[0] < picker[0]:
                    picker = rect
        out.append({"slot": no, "combo": combo, "picker": picker})
    return out


def combo_text(ch):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, buf, 256)
    return buf.value


def switch_filament_preset(session, slot, target_substr, tries=10):
    """Row-probe the slot's preset combo until the text flips to target.
    Returns the final text ('' on failure)."""
    slots = filament_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["combo"]:
        print(f"{LOG} slot {slot} combo not found")
        return ""
    text, rect, ch = hit["combo"]
    if target_substr in combo_text(ch):
        return combo_text(ch)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    for attempt in range(tries):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            time.sleep(0.5)
            continue
        pr = popup[2]
        px = (pr[0] + pr[2]) // 2
        py = pr[1] + 14 + attempt * 28
        winutil.msg_click_screen(px, py)
        time.sleep(0.9)
        now = combo_text(ch)
        print(f"{LOG} slot{slot} popup row {attempt}: {now!r}")
        if target_substr in now:
            time.sleep(1.0)
            return now
    return combo_text(ch)


def click_color_picker(session, slot, timeout_s=6.0, dialog_cls="#32770"):
    """Click the slot's color picker button; return the dialog tuple or
    None. The official FilamentColorDialog is a wx Dialog -> #32770; pass
    dialog_cls=None to fall back to the SidePopup wxWindowNR shape."""
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
    # dialog, measured 09-17 suite)
    sx, sy = winutil.client_to_screen(session.hwnd, px, py)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    # Measured 09-18 (diag_m8b_toplevels): the picker first opens a NATIVE
    # context menu (#32768: Edit / Delete / Merge with) — the color dialog
    # only appears after clicking its FIRST row ("Edit"). A plain wait for
    # #32770 therefore always timed out.
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
    if dialog_cls:
        dlg = export_util.wait_toplevel(
            session.pid, lambda c, t, r: c == dialog_cls,
            timeout_s=timeout_s)
    else:
        dlg = export_util.wait_popup(session.pid, timeout_s=timeout_s)
    time.sleep(1.0)
    return dlg


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
    """{diameter, flow, flow_rect} from the sidebar nozzle section (the
    diameter/flow combo VALUES are text children at y 280-320)."""
    diameter = flow = None
    flow_rect = None
    for text, rect, ch in export_util._children_texts(session.hwnd):
        if not (275 <= rect[1] <= 325 and rect[0] < 425):
            continue
        if text.strip() == "Diameter" or text.strip() == "Flow":
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
        # 09-18 popup3 diag: no native ComboBox child exists here (all
        # wxWindowNR), and neither the arrow msg_click nor a real_click
        # opened the dropdown. The filament preset combo opens on a CENTER
        # msg_click (switch_filament_preset) — try that shape first, fall
        # back to the arrow edge on odd attempts. The last surface
        # difference vs that combo is the demoted window: pull the app to
        # foreground before clicking.
        try:
            winutil.user32.SetForegroundWindow(session.hwnd)
            time.sleep(0.4)
        except Exception:  # noqa: BLE001
            pass
        if attempt % 2 == 0:
            winutil.msg_click_screen((rect[0] + rect[2]) // 2,
                                     (rect[1] + rect[3]) // 2, session.hwnd)
        else:
            sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            # the click may still have focused the combo — wx combos flip to
            # the first item matching a typed letter ('H'igh Flow)
            winutil.user32.SendMessageW(session.hwnd, 0x0102, ord("H"), 0)
            time.sleep(0.8)
            now = nozzle_reads(session).get("flow") or ""
            print(f"{LOG} flow key 'H': {now!r}")
            if target_substr in now:
                time.sleep(1.0)
                return now
            continue
        pr = popup[2]
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
