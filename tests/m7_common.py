#!/usr/bin/env python3
# m7_common.py — shared ops for the m7 main-flow cases (Feishu 测试用例 base
# WbIjb4vM0aZX7BsJxI9cWBWAnad, table tblLR8zYgwBuggDI: ORCA测试 GUI业务
# #7-#24 + 主流程-模板 O-xx/M-xx chains).
#
# Ops are composed from primitives the older milestones already proved on
# the guest rig:
#   - gizmo toolbar slots via in-canvas tooltip hover scans (m4e)
#   - ImGui field focus = real click + message keyboard (m6a)
#   - native popup menus need REAL input (m3b) — including the Plater
#     context menu, opened by winutil.real_right_click_screen
#   - topbar menus via topbar_util (File > New Project etc.)
#   - menu rows can also be located exactly via GetMenuItemRect and
#     real-clicked (context menus have no per-row HWND).
#
# Source map (SnapmakerOrca_dev, branch of 08-26 build):
#   O-01 open/O-02 close      launcher / session.close
#   O-03 printer preset       m5a/m3e (topbar preset combo)
#   O-04 filament merge       sidebar (m4d)                     [not re-done here]
#   O-05 new project          File menu > New Project (MainFrame.cpp:2548)
#   M-01 import               File > Import STL / launcher model arg
#   M-02 slice                m2 click_slice_start
#   M-03 arrange              toolbar "Arrange all objects" [A] (GLCanvas3D:7740)
#   M-04 auto orient          toolbar "Auto orient" [Q]         (GLCanvas3D:7718)
#   M-05/M-07 split           toolbar "Split to objects/parts"  (:7764/:7776)
#   M-08 variable layer hgt   toolbar "Variable layer height"   (:7786)
#   M-09/M-11/M-12 transform  Move/Rotate/Scale gizmo fields (m6a pattern)
#   M-13 place on face        Flatten gizmo
#   M-14 cut                  Cut gizmo
#   M-15 mesh boolean         MeshBoolean gizmo / object menu "Mesh boolean"
#   M-16 paint supports       FdmSupports gizmo (m4e paint primitive)
#   M-17 paint                MmSegmentation gizmo (m4e)
#   M-18 change filament      object menu > Change Filament (GUI_Factories:1782)
#   M-19 delete               object menu > Delete (GUI_Factories:528)
#   M-20 add primitive        bed menu > Add Primitive > shape (GUI_Factories:510)

import ctypes
import ctypes.wintypes
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # repo root (case lives in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import topbar_util, winutil  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness.anchors import (MATCH_THRESHOLD, VIEWPORT_X0,  # noqa: E402
                             has_colored_content, viewport_crop)
from m1_minimal_loop import capture_bgr  # noqa: E402

LOG = "[m7]"
ART = HERE / "artifacts"
WM_CHAR, WM_KEYDOWN, VK_RETURN = 0x0102, 0x0100, 0x0D
EMPTY_BED_FLOOR = 0.004  # m3b's measured empty-bed chromatic fraction

# Gizmo toolbar band (guest rig 09-08, maximized 1920x1032, dpi=96):
# icons span client y ~65-105 and x ~700-1700 (full-res strip crop,
# artifacts/topstrip.jpg). Selection-dependent gizmos sit right of the
# first separator (~x1050).
BAR_Y = 84
SCAN_X0 = 690
SCAN_X1_OFF = 120          # scan up to (width - SCAN_X1_OFF)
SLOT_PITCH = 22            # fine hover step; icon ~40px wide, so every
                           # icon is hit by at least one hover point

user32 = ctypes.WinDLL("user32")
MF_BYPOSITION = 0x400


def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)


def tooltip_text(session, cx, cy, dwell_s=1.4):
    """Park the cursor and OCR the in-canvas tooltip below it. Unlike the
    m4e version this returns even SHORT texts (Move/Rotate are 4-6 chars)
    and reports the raw read when the caller asks."""
    sx, sy = client(session, cx, cy)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    deadline = time.monotonic() + dwell_s
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        crop = img[cy + 14:cy + 96, max(0, cx - 120):cx + 140]
        if crop.size:
            words = mdu.ocr_words_img(crop, scale=3)
            text = " ".join(w for w, *_ in words)
            if len(text) >= 4:
                return text
        time.sleep(0.3)
    return ""


def scan_slots(session, x0=SCAN_X0, cy=BAR_Y, pred=None, dwell_s=1.1):
    """Hover-scan the gizmo toolbar row; return [(x, tooltip)] hits with
    duplicate texts deduped (consecutive). `pred` filters on lowercase."""
    ensure_maximized(session)
    img = capture_bgr(session)
    x1 = img.shape[1] - 120
    hits, prev = [], None
    x = x0
    while x < x1:
        text = tooltip_text(session, x, cy, dwell_s=dwell_s)
        if text and text != prev:
            print(f"{LOG} slot @x{x}: {text!r}")
            if pred is None or pred(text.lower()):
                hits.append((x, text))
        prev = text or prev
        x += SLOT_PITCH
    return hits


def find_slot(session, pred, cy=BAR_Y):
    """First toolbar slot whose tooltip satisfies pred — m4e contract."""
    hits = scan_slots(session, cy=cy, pred=pred)
    return (hits[0][0], hits[0][1]) if hits else (None, "")


# --- selection ---------------------------------------------------------------

def ensure_maximized(session) -> bool:
    """Re-assert SW_MAXIMIZE. The app spontaneously RESTORES (~1366x751)
    around the first user input after a job (m5_common lesson, re-measured
    09-08 after Arrange) — every calibrated band goes stale when that
    happens, so context menus / slot scans must re-check."""
    l, t, r, b = winutil.window_rect(session.hwnd)
    if (r - l) < 1900:
        winutil.user32.ShowWindow(session.hwnd, 3)  # SW_MAXIMIZE
        time.sleep(1.5)
        print(f"{LOG} re-maximized: {winutil.window_rect(session.hwnd)}")
        return True
    return False


def select_model(session, tries=4):
    ensure_maximized(session)
    """Click the model's chromatic centroid until the Rotate gizmo slot's
    tooltip stops demanding a selection (m4e pattern, own scan bands)."""
    rot_x, _ = find_slot(session, lambda t: "rotate" in t)
    if rot_x is None:
        print(f"{LOG} rotate slot not found — toolbar unreadable?")
        return False
    for _ in range(tries):
        pos = find_centroid(session)
        if not pos:
            time.sleep(1.0)
            continue
        sx, sy = client(session, *pos)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        tip = tooltip_text(session, rot_x, BAR_Y)
        print(f"{LOG} rotate tooltip after click: {tip!r}")
        if tip and "select" not in tip.lower():
            return True
    return False


def find_centroid(session):
    """Largest chromatic blob centroid in the viewport (m4e algorithm,
    viewport-wide band)."""
    import cv2
    import numpy as np
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = VIEWPORT_X0 + 10, 110, w - 10, h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > best_area:
            best, best_area = i, area
    if best is None or best_area < 400:
        return None
    cx, cy = centroids[best]
    return int(cx) + x0, int(cy) + y0


# --- context menu (Plater right-click) ---------------------------------------

def open_context_menu(session, where="model"):
    """Real right-click the model centroid ('model') or an empty-bed spot
    ('bed'); wait for the native popup; return its (hwnd, hmenu) or None.
    The Plater context menu is a #32768 popup whose modal loop ignores
    message-level input — opening AND row selection both need REAL input
    (same lesson as the topbar dropdown, m3b)."""
    ensure_maximized(session)
    if where == "model":
        pos = find_centroid(session)
        if not pos:
            print(f"{LOG} no model centroid for right-click")
            return None
    else:
        img = capture_bgr(session)
        pos = (VIEWPORT_X0 + 60, img.shape[0] - 160)  # empty bed, bottom-left
    sx, sy = client(session, *pos)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    winutil.real_right_click_screen(sx, sy)
    menus = topbar_util.wait_menu_popup(session.pid, timeout_s=4.0)
    if not menus:
        print(f"{LOG} {where} right-click: no popup")
        return None
    rect, hwnd = menus[0][:4], menus[0][4]
    return hwnd, topbar_util.menu_hmenu(hwnd)


def list_menu(hmenu):
    """[(index, label)] of a live HMENU (labels without accelerator tail)."""
    return [(i, lbl) for i, lbl, _st in topbar_util.menu_items(hmenu)]


def _menu_item_rect(menu_hwnd, hmenu, index):
    """Screen rect of a popup-menu row via GetMenuItemRect. NULL hWnd is
    documented-optional but FAILED on the guest (09-08: every call returned
    0 with the menu open) — the menu's own #32768 window works."""
    rect = ctypes.wintypes.RECT()
    for hwnd in (menu_hwnd, None):
        if hwnd and user32.GetMenuItemRect(hwnd, hmenu, index, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
        if not hwnd and user32.GetMenuItemRect(None, hmenu, index, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
    print(f"{LOG} GetMenuItemRect failed for index {index} "
          f"(err={ctypes.GetLastError()})")
    return None


def click_menu_row(session, hwnd, hmenu, row_substr, nested=False):
    """Real-click the row whose label contains row_substr. Returns the row
    index, or None. `nested` = row is a submenu handle: hover it so the
    submenu opens, and return (index, submenu_tuple) instead."""
    items = list_menu(hmenu)
    for i, lbl in items:
        if row_substr.lower() in lbl.lower():
            rect = _menu_item_rect(hwnd, hmenu, i)
            if rect:
                x = (rect[0] + rect[2]) // 2
                y = (rect[1] + rect[3]) // 2
            else:
                # fallback: menu window rect + SM_CYMENU row geometry
                # (m3b precedent: native-menu rows are only geometrically
                # addressable; separators above shift the row down a hair)
                wrect = ctypes.wintypes.RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(wrect)):
                    print(f"{LOG} no menu geometry at all")
                    return None
                row_h = user32.GetSystemMetrics(21) or 24  # SM_CYMENU
                seps = sum(1 for j, l in items[:i] if not l.strip())
                y = wrect[1] + 4 + i * row_h - seps * (row_h - 8) + row_h // 2
                x = wrect[0] + 40
                print(f"{LOG} fallback row click @({x},{y}) idx={i}")
            winutil.user32.SetCursorPos(x, y)
            time.sleep(0.5)
            if nested:
                sub = topbar_util.wait_submenu(session.pid, {hwnd},
                                               timeout_s=3.0)
                if not sub:
                    print(f"{LOG} submenu of {lbl!r} did not open")
                    return None
                srect, shwnd = sub[0], sub[1]
                return (i, (shwnd, topbar_util.menu_hmenu(shwnd)))
            winutil.real_click_screen(x, y)
            time.sleep(1.0)
            return i
    print(f"{LOG} row {row_substr!r} not in menu: {[l for _i, l in items]}")
    return None


def dismiss_menus(session):
    topbar_util.close_menu_windows(session.pid)
    time.sleep(0.4)


def context_click_row(session, where, row_substr, success_fn=None,
                      via=None, label=""):
    """One-shot context-menu op: open the {where} menu, optionally enter
    the `via` submenu, real-click `row_substr`, verify via success_fn. A
    missed row is a FAILURE (never fall through to the success check)."""
    menu = open_context_menu(session, where=where)
    if not menu:
        return False
    hwnd, hmenu = menu
    if via:
        got = click_menu_row(session, hwnd, hmenu, via, nested=True)
        if not got:
            dismiss_menus(session)
            return False
        _idx, (shwnd, shmenu) = got
        return _click_in_submenu(session, shwnd, shmenu, row_substr,
                                 success_fn, label)
    idx = click_menu_row(session, hwnd, hmenu, row_substr)
    if idx is None:
        dismiss_menus(session)
        return False
    time.sleep(1.5)
    if success_fn is not None:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if success_fn():
                return True
            time.sleep(1.0)
        print(f"{LOG} {label or row_substr}: success_fn never passed")
        return False
    return True


def _click_in_submenu(session, shwnd, shmenu, row_substr, success_fn, label):
    for i, lbl in list_menu(shmenu):
        if row_substr.lower() in lbl.lower():
            rect = _menu_item_rect(shwnd, shmenu, i)
            if rect:
                winutil.user32.SetCursorPos((rect[0] + rect[2]) // 2,
                                            (rect[1] + rect[3]) // 2)
                time.sleep(0.4)
                winutil.real_click_screen((rect[0] + rect[2]) // 2,
                                          (rect[1] + rect[3]) // 2)
                time.sleep(1.5)
                if success_fn is None:
                    return True
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if success_fn():
                        return True
                    time.sleep(1.0)
    print(f"{LOG} submenu row {row_substr!r} not found/click failed")
    dismiss_menus(session)
    return False


# --- gizmo field entry (m6a pattern) -----------------------------------------

def gizmo_row_boxes(session, row_label):
    """[(x, y, text)] of EVERY numeric field on the gizmo-window row whose
    label starts with row_label, left-to-right (X/Y/Z order).

    Multiple words may start with the label (toolbar tooltip 'Rotate [R]',
    window title 'Rotate', field row 'Rotate (relative)') — the first
    candidate with numeric boxes to its right wins. OCR brackets glue to
    the value ('[0.00') so the numeric pattern strips leading punctuation."""
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img, scale=3)

    def numerics_right(px, py):
        nums = []
        for w in words:
            t = w[0].lstrip("([")
            if re.fullmatch(r"-?\d+(?:[.,]\d{1,2})?", t)                     and abs(w[2] - py) < 14 and w[1] > px:
                nums.append((w[1] + w[3] // 2, w[2] + w[4] // 2, t))
        return sorted(nums, key=lambda n: n[0])

    best: list = []
    for w in words:
        if w[0].lower().startswith(row_label.lower()):
            boxes = numerics_right(w[1], w[2])
            if len(boxes) > len(best):
                best = boxes
    return best


def gizmo_field_box(session, row_label, viewport_origin=(0, 0)):
    """(x, y, current_text) of the first numeric field right of `row_label`
    inside the active gizmo window (ImGui, drawn in-canvas)."""
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img, scale=3)
    pos = next((w for w in words if w[0].lower().startswith(row_label.lower())),
               None)
    if not pos:
        return None, ""
    px, py = pos[1], pos[2]
    nums = sorted((w for w in words
                   if re.fullmatch(r"-?[\d]+(?:[.,]\d{1,2})?", w[0])
                   and abs(w[2] - py) < 14 and w[1] > px),
                  key=lambda w: w[1])
    if not nums:
        return None, ""
    n = nums[0]
    return (n[1] + n[3] // 2, n[2] + n[4] // 2), n[0]


def type_into_field(session, box, text, old_len=4):
    """Focus the field with a REAL click (ImGui hit test) then clear +
    type + commit via message keyboard through the deepest canvas child
    (m6a: chars must land on the canvas window, not the frame)."""
    fx, fy = client(session, *box)
    winutil.user32.SetCursorPos(fx, fy)
    time.sleep(0.2)
    winutil.real_click_screen(fx, fy)
    time.sleep(0.6)
    probe = winutil.client_to_screen(session.hwnd, 600, 400)
    hwnd = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
    for _ in range(old_len + 2):
        winutil._send_msg(hwnd, WM_CHAR, 0x08, 0)   # backspace
        time.sleep(0.04)
    for ch in text:
        winutil._send_msg(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(0.05)
    winutil._send_msg(hwnd, WM_KEYDOWN, VK_RETURN, 0)
    time.sleep(0.1)
    winutil._send_msg(hwnd, WM_CHAR, 0x0D, 0)
    time.sleep(1.2)


def words(session):
    """OCR words of the current frame: [(text, x, y, ...)] (mdu contract)."""
    return mdu.ocr_words_img(capture_bgr(session), scale=2)


def click_slot(session, x, cy=BAR_Y):
    sx, sy = client(session, x, cy)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    winutil.real_click_screen(sx, sy)
    time.sleep(1.2)
    # park away from the toolbar: the gizmo tooltip otherwise lingers over
    # the frame and OCRs before the window rows (m7e lesson)
    px, py = client(session, 960, 500)
    winutil.user32.SetCursorPos(px, py)
    time.sleep(1.0)


# --- model presence / export --------------------------------------------------

def model_colored_frac(session):
    return has_colored_content(capture_bgr(session))


def model_present(session, floor=EMPTY_BED_FLOOR + 0.002):
    return model_colored_frac(session) > floor


def blob_count(session, min_area=400):
    """Number of distinct chromatic blobs in the viewport (multi-model
    assertions: arrange separation)."""
    import cv2
    import numpy as np
    img = capture_bgr(session)
    h, w = img.shape[:2]
    band = img[110:h - 60, VIEWPORT_X0 + 10:w - 10].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    return sum(1 for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area)


def save_project_as(session, out_path: Path, timeout_s=60.0):
    """File > Save Project As via the m3g primitive (native save dialog)."""
    from m3g_export_3mf import save_project_as as _save
    return _save(session, out_path, timeout_s=timeout_s)


# --- native dialogs (#32770): import/error/message boxes ----------------------

def wait_dialog(pid, timeout_s=15.0, title_substr=""):
    """(hwnd, title, rect) of the pid's visible #32770 whose title contains
    title_substr (case-insensitive; empty = any)."""
    from harness import export_util
    return export_util.wait_toplevel(
        pid, lambda c, t, r: c == "#32770"
        and title_substr.lower() in (t or "").lower(), timeout_s)


def dialog_buttons(dlg_hwnd):
    """[(text, (cx, cy))] of a dialog's Button children (screen centers)."""
    import ctypes
    user32 = ctypes.WinDLL("user32")
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)
    buttons = []

    def cb(h, _lp):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value == "Button":
            txt = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(h, txt, 128)
            rc = ctypes.wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rc))
            buttons.append((txt.value, ((rc.left + rc.right) // 2,
                                        (rc.top + rc.bottom) // 2)))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(dlg_hwnd), WNDENUMPROC(cb), 0)
    return buttons


WM_COMMAND_MSG = 0x0111
STANDARD_IDS = {"ok": 1, "cancel": 2, "yes": 6, "no": 7, "dont": 7}


def click_dialog_button(dlg_hwnd, text_substr, fallback_first=True):
    """Activate the dialog button matching text_substr. Three tiers:
    (1) real button text -> message click; (2) owner-drawn buttons (wx
    BBL dialogs expose EMPTY GetWindowText — measured 09-08 on the Save
    prompt) -> OCR the dialog frame and real-click the label;
    (3) WM_COMMAND with the standard MSW dialog control id
    (IDOK=1/IDCANCEL=2/IDYES=6/IDNO=7). Returns the action taken."""
    buttons = dialog_buttons(dlg_hwnd)
    print(f"{LOG} dialog buttons: {[t for t, _p in buttons]}")
    for t, (x, y) in buttons:
        if t and text_substr.lower() in t.lower():
            winutil.msg_click_screen(x, y, dlg_hwnd)
            time.sleep(0.8)
            return f"clicked {t!r}"
    # owner-drawn tier: PrintWindow the dialog itself and OCR it for the
    # label (the guest python has no mss; winutil.capture_window covers any
    # hwnd, measured 09-08)
    # PrintWindow renders the CLIENT area — anchor OCR coords at the
    # client origin (GetWindowRect includes the non-client frame, which
    # missed every button by the border+title offset, measured 09-08)
    pt = ctypes.wintypes.POINT(0, 0)
    if user32.ClientToScreen(dlg_hwnd, ctypes.byref(pt)):
        try:
            import cv2
            import numpy as np
            cap = winutil.capture_window(dlg_hwnd)
            img = cv2.cvtColor(
                np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4),
                cv2.COLOR_BGRA2BGR)
            words = mdu.ocr_words_img(img, scale=3)
            print(f"{LOG} dialog ocr: {[w[0] for w in words]}")
            for w in words:
                if text_substr.lower() in w[0].lower():
                    sx = pt.x + w[1] + w[3] // 2
                    sy = pt.y + w[2] + w[4] // 2
                    winutil.user32.SetCursorPos(sx, sy)
                    time.sleep(0.2)
                    winutil.real_click_screen(sx, sy)
                    time.sleep(0.8)
                    return f"ocr-clicked {w[0]!r}"
        except Exception as exc:
            print(f"{LOG} ocr tier failed: {exc}")
    # standard-id tier
    for key, wid in STANDARD_IDS.items():
        if key in text_substr.lower():
            user32.SendMessageW(dlg_hwnd, WM_COMMAND_MSG, wid, 0)
            time.sleep(0.8)
            return f"WM_COMMAND({wid})"
    if fallback_first and buttons:
        t, (x, y) = buttons[0]
        winutil.msg_click_screen(x, y, dlg_hwnd)
        time.sleep(0.8)
        return f"clicked first (empty {t!r})"
    return None


def dismiss_dialog(session, timeout_s=15.0):
    """Close the current #32770 (OK/first button); returns its title."""
    dlg = wait_dialog(session.pid, timeout_s=timeout_s)
    if not dlg:
        return None
    print(f"{LOG} dialog: '{dlg[1]}' rect={dlg[2]}")
    click_dialog_button(dlg[3])
    time.sleep(1.0)
    return dlg[1]


def file_menu_dispatch(session, item_substr, expect_dialog=False,
                       timeout_s=12.0, via=None):
    """Open the topbar File menu, dispatch item_substr via WM_COMMAND
    (m3g's proven path — frame commands don't need real clicks). `via`
    enters a SUBMENU first ('Import' holds the STL/3MF rows — dispatching
    the submenu title itself is a no-op, measured 09-08). Returns
    (ok, dialog) where dialog is a #32770 that popped (imports/opens)."""
    menu = topbar_util.open_file_menu(session)
    if not menu:
        print(f"{LOG} file menu did not open")
        return False, None
    _rect, hwnd, hmenu = menu
    rows = list_menu(hmenu)
    print(f"{LOG} file menu: {[l for _i, l in rows]}")
    target_hmenu = hmenu
    if via:
        idx = topbar_util.find_item(hmenu, via)
        if idx is None:
            topbar_util.close_menu_windows(session.pid)
            return False, None
        # open the submenu popup so its rows are live (row geometry only
        # exists while the menu is shown), then match the row inside it
        got = click_menu_row(session, hwnd, hmenu, via, nested=True)
        if not got:
            topbar_util.close_menu_windows(session.pid)
            return False, None
        _idx, (_shwnd, shmenu_live) = got
        target_hmenu = shmenu_live
        rows = list_menu(shmenu_live)
        print(f"{LOG} {via} menu: {[l for _i, l in rows]}")
    idx = topbar_util.find_item(target_hmenu, item_substr)
    if idx is None:
        topbar_util.close_menu_windows(session.pid)
        return False, None
    topbar_util.activate_menu_item(session, target_hmenu, idx)
    dlg = wait_dialog(session.pid, timeout_s=timeout_s) if expect_dialog \
        else None
    topbar_util.close_menu_windows(session.pid)
    return True, dlg


def m7_verdict(results: dict) -> int:
    print("\n[m7] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    ok = all(str(v).startswith("PASS") for v in results.values())
    print("[m7] " + ("GREEN" if ok else "RED"))
    return 0 if ok else 1


# --- template-case helpers (Feishu 主流程-模板 O-xx/M-xx chains) -------------

def run_template_case(steps, default_model):
    """Boot once, run the chain, verdict, close — the common skeleton of
    the m7tNN template cases."""
    import argparse
    from m3_common import add_common_args, boot_session
    ap = add_common_args(argparse.ArgumentParser(), default_model=default_model)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        steps(session, results)
        return m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


def step_model_arrives(session, results, timeout_s=240, min_frac=None):
    """Model-arrival gate; min_frac overrides the fixture-calibrated
    threshold for small imports (Prusa.stl reads ~0.35% vs 0.6%)."""
    from m2_slice_chain import wait_model_loaded, MODEL_COLORED_THRESHOLD
    gate = min_frac if min_frac is not None else MODEL_COLORED_THRESHOLD
    deadline = time.monotonic() + timeout_s
    frac = model_colored_frac(session)
    ok = frac >= gate
    while not ok and time.monotonic() < deadline:
        time.sleep(2.0)
        frac = model_colored_frac(session)
        ok = frac >= gate
    print(f"{LOG} model arrives: {ok} ({frac:.2%}, gate {gate:.2%})")
    results["model arrives"] = "PASS" if ok else "FAIL"
    time.sleep(1.0)
    return ok


def step_delete_all(session, results):
    """Edit menu > Delete All (m3b's op; the M-19 整板清除 entry)."""
    from harness import topbar_util
    from m1_minimal_loop import capture_bgr
    from harness.anchors import has_colored_content
    deleted = topbar_util.real_click_submenu_row(
        session, "Edit", "Delete All",
        success_fn=lambda: has_colored_content(capture_bgr(session))
        < EMPTY_BED_FLOOR,
        label="delete-all")
    print(f"{LOG} delete-all: {deleted}")
    results["delete all clears plate"] = "PASS" if deleted else "FAIL"
    return deleted


def op_add_primitive(session, shape="cube"):
    """Bed menu > Add Primitive > shape; returns the plate changed."""
    before = model_colored_frac(session)
    ok = context_click_row(session, "bed", shape, via="Add Primitive",
                           success_fn=lambda: model_colored_frac(session)
                           > before + 0.002,
                           label=f"add-{shape}")
    time.sleep(1.0)
    return ok


def op_gizmo_field(session, slot_pred, row_label, index, value):
    """Select + activate gizmo + type value into row field #index.
    Returns (ok, observed_text)."""
    if not select_model(session):
        return False, ""
    x, tip = find_slot(session, slot_pred)
    if x is None:
        return False, ""
    click_slot(session, x)
    time.sleep(1.0)
    boxes = gizmo_row_boxes(session, row_label)
    idx = index if index >= 0 else len(boxes) + index
    if idx < 0 or idx >= len(boxes):
        return False, ""
    type_into_field(session, boxes[idx][:2], value,
                    old_len=len(boxes[idx][2]))
    boxes2 = gizmo_row_boxes(session, row_label)
    idx2 = index if index >= 0 else len(boxes2) + index
    text = boxes2[idx2][2] if 0 <= idx2 < len(boxes2) else ""
    return text.startswith(value), text


def op_slice(session, results, key="slice completes", export_to=None,
             timeout_s=600):
    """Click Slice, wait done, optionally export gcode to export_to."""
    from m2_slice_chain import click_slice_start, wait_slicing_done
    if not click_slice_start(session):
        results[key] = "FAIL (slice click rejected)"
        return False
    done, _score = wait_slicing_done(session, timeout_s=timeout_s)
    print(f"{LOG} {key}: {done}")
    results[key] = "PASS" if done else "FAIL"
    if done and export_to is not None:
        from harness import export_util
        ok = export_util.export_gcode(session, Path(export_to),
                                      timeout_s=45.0)
        results["gcode exported"] = "PASS" if ok else "FAIL"
        return ok
    return done
