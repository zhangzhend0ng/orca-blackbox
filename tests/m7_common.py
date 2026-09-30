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
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

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


def select_model(session, tries=3):
    """Click the model until the Rotate slot's tooltip stops demanding a selection.

    Tries the largest chromatic blobs IN TURN (see find_centroids): the fixture
    carries two objects (a striped colour-mixing box + a cube) and an open gizmo
    adds a panel-sized blob, so trusting a single "largest blob" selects the wrong
    thing. Each candidate is clicked slightly BELOW its centroid, because the
    object's name label ('Untitled') is painted just above it and swallows a
    centre click (measured 09-21: after a Move the centroid jumped to (943,371)
    — the other object's label row — and Rotate never left 'Please select ...').
    """
    ensure_maximized(session)
    rot_x, _ = find_slot(session, lambda t: "rotate" in t)
    if rot_x is None:
        print(f"{LOG} rotate slot not found — toolbar unreadable?")
        return False
    for _attempt in range(tries):
        cands = model_candidates(session)
        print(f"{LOG} select candidates: {cands}")
        for cx, cy in cands:
            sx, sy = client(session, cx, cy + 22)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.2)
            tip = tooltip_text(session, rot_x, BAR_Y)
            print(f"{LOG} rotate tooltip after click @({cx},{cy + 22}): {tip!r}")
            if tip and "select" not in tip.lower():
                return True
        time.sleep(1.0)
    return False


def find_centroids(session, limit=5, min_area=400, kernel=5):
    """Centroids of the largest chromatic blobs, LARGEST FIRST.

    A single "largest blob" is not enough: the mixed_filament_test fixture ships
    two objects (a striped colour-mixing box + a cube), and an open gizmo adds its
    own panel-sized blob — so after a Move the biggest blob may be the other
    object or the panel, and clicking it selects nothing (measured 09-21: centroid
    jumped from the cube at (1172,514) to (943,371), where the object's 'Untitled'
    label sits, and Rotate stayed at 'Please select at least one object').
    `kernel` widens the morphological close so fragmented renders merge (the
    coarse pass is what blob_count uses)."""
    import cv2
    import numpy as np
    img = capture_bgr(session)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = VIEWPORT_X0 + 10, 110, w - 10, h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            np.ones((kernel, kernel), np.uint8))
    n, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    out = []
    for i in order[:limit]:
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            break
        cx, cy = centroids[i]
        out.append((int(cx) + x0, int(cy) + y0))
    return out


def model_candidates(session, limit=6):
    """Click points for 'the model', largest-first, merged from the fine and
    coarse blob masks.

    One mask is not enough on 2.4.0: after an arrange the colour-mixing box
    and the (grey) printed cube read very differently, and the largest
    fine-mask blob can be the object's NAME LABEL — right-clicking the label
    opens NO menu at all, while the model a few px below opens the object
    menu (measured 09-23, g17: @(943,401) nothing vs @(1172,514) the menu).
    """
    out: list = []
    for cx, cy in find_centroids(session, limit=4) + \
            find_centroids(session, limit=limit, min_area=150, kernel=9):
        if all(abs(cx - ox) > 25 or abs(cy - oy) > 25 for ox, oy in out):
            out.append((cx, cy))
    return out[:limit]


def find_centroid(session):
    """Largest chromatic blob centroid (kept for callers that want just one)."""
    cands = find_centroids(session, limit=1)
    return cands[0] if cands else None


# --- context menu (Plater right-click) ---------------------------------------

def open_context_menu(session, where="model"):
    """Real right-click the model ('model') or an empty-bed spot ('bed');
    wait for the native popup whose rect CONTAINS the click point; return
    its (hwnd, hmenu) or None.

    Two failure modes measured on V2.3.6 (09-22, g6):
      * a STALE topbar/dropdown #32768 lingers after WM_CANCELMODE (and
        real ESC x2 does NOT close it on this build either) — a bare
        wait_menu_popup returned the stale window, whose items were dead
        by enumeration time (m7t73's 'menu: []');
      * the model centroid can sit on the 'Untitled' LABEL painted above
        the object — right-clicking the label opens NOTHING (m7t75's
        'no popup'). So walk the centroid candidates like select_model
        does, and accept only a menu that contains the click point."""
    ensure_maximized(session)
    if where == "model":
        candidates = [(cx, cy + 22) for cx, cy in model_candidates(session)]
        print(f"{LOG} model right-click candidates: {candidates}")
    else:
        # several empty-bed spots: after a dropdown/delete-all the first
        # right-click can be swallowed by leftovers (measured 09-23: m8b's
        # bed right-click after Delete All opened nothing at the first spot)
        img = capture_bgr(session)
        candidates = [(VIEWPORT_X0 + 60, img.shape[0] - 160),
                      (VIEWPORT_X0 + 140, img.shape[0] - 260),
                      (VIEWPORT_X0 + 80, img.shape[0] - 360)]
    for cx, cy in candidates:
        sx, sy = client(session, cx, cy)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        if where == "bed":
            # give the canvas focus first: after a topbar-dropdown flow the
            # FIRST right-click is consumed re-activating the plater and no
            # menu appears (measured 09-23: m8b's post-Delete-All bed click)
            winutil.real_click_screen(sx, sy)
            time.sleep(0.5)
        for _try in range(2):
            winutil.real_right_click_screen(sx, sy)
            deadline = time.monotonic() + 4.0
            seen: set = set()
            while time.monotonic() < deadline:
                for rect, hwnd in [(m[:4], m[4]) for m in
                                   topbar_util._enum_menu_windows(
                                       session.pid)]:
                    seen.add(rect)
                    l, t, r, b = rect
                    if l - 30 <= sx <= r + 30 and t - 30 <= sy <= b + 30:
                        return hwnd, topbar_util.menu_hmenu(hwnd)
                time.sleep(0.25)
            print(f"{LOG} {where} right-click @({cx},{cy}) try{_try + 1}: "
                  f"no menu (menu windows seen: {sorted(seen)})")
            time.sleep(0.6)
    return None


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


def dismiss_transfer_dialog(session):
    """Answer the app's 'Transfer or discard changes' prompt with DISCARD.

    Switching away from a preset whose values were modified (a flow switch
    modifies the current process/filament preset) raises this #32770: buttons
    are plain wxWindowNR children labelled 'Transfer' / 'Discard' / 'Save'
    (measured 09-23, g29; the label-only children are invisible to
    dialog_buttons(), which filters class 'Button'). The tester's manual
    choice is Discard, which keeps the state clean for the next selection.
    Returns True when a prompt was answered."""
    dlg = wait_dialog(session.pid, timeout_s=3.0, title_substr="")
    if not dlg:
        return False
    from harness import export_util
    for t, r, ch in export_util._children_texts(dlg[3]):
        if "discard" in t.strip().lower():
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.msg_click_screen(cx, cy, dlg[3])
            time.sleep(1.0)
            print(f"{LOG} transfer prompt -> Discard clicked")
            return True
    print(f"{LOG} transfer prompt raised but Discard not found; children: "
          f"{[t for t, _r, _c in export_util._children_texts(dlg[3])][:8]}")
    return False


def dismiss_menus(session):
    topbar_util.close_menu_windows(session.pid)
    time.sleep(0.4)
    # V2.3.6: WM_CANCELMODE leaves expanded-submenu menus open (17.10) and
    # real ESC x2 does not close them either (g6 s1). A fresh real
    # right-click dismisses any open menu; CANCELMODE then closes the
    # fresh one (it has no expanded submenu).
    if topbar_util._enum_menu_windows(session.pid):
        img = capture_bgr(session)
        sx, sy = client(session, VIEWPORT_X0 + 60, img.shape[0] - 160)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_right_click_screen(sx, sy)
        time.sleep(1.0)
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
                dismiss_menus(session)
                return True
            time.sleep(1.0)
        print(f"{LOG} {label or row_substr}: success_fn never passed")
        dismiss_menus(session)
        return False
    dismiss_menus(session)
    return True


def _click_in_submenu(session, shwnd, shmenu, row_substr, success_fn, label):
    # Reuse click_menu_row: it falls back to geometric row geometry when
    # GetMenuItemRect fails, which this function used to lack — on 2.4.0 the
    # submenu rows then silently never got clicked (measured 09-22: m7t89's
    # 'submenu row cube not found/click failed' while m7i's direct
    # click_menu_row call on the SAME submenu worked and added the cube).
    idx = click_menu_row(session, shwnd, shmenu, row_substr)
    if idx is None:
        print(f"{LOG} submenu row {row_substr!r} not found")
        dismiss_menus(session)
        return False
    time.sleep(1.5)
    if success_fn is None:
        dismiss_menus(session)
        return True
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if success_fn():
            dismiss_menus(session)
            return True
        time.sleep(1.0)
    print(f"{LOG} {label or row_substr}: success_fn never passed")
    dismiss_menus(session)
    return False


# --- gizmo field entry (m6a pattern) -----------------------------------------

def gizmo_row_boxes(session, row_label, scale=3):
    """[(x, y, text)] of EVERY numeric field on the gizmo-window row whose
    label starts with row_label, left-to-right (X/Y/Z order).

    Multiple words may start with the label (toolbar tooltip 'Rotate [R]',
    window title 'Rotate', field row 'Rotate (relative)') — the first
    candidate with numeric boxes to its right wins. OCR brackets glue to
    the value ('[0.00') so the numeric pattern strips leading punctuation."""
    return gizmo_row_boxes_img(capture_bgr(session), row_label, scale=scale)


def gizmo_row_boxes_img(img, row_label, scale=3):
    """[(x, y, text)] of every numeric field right of words STARTING WITH
    row_label: rows top-to-bottom, columns left-to-right, with '' cells
    where OCR missed a value.

    Column x positions are clustered ACROSS ALL matching rows — OCR drops
    cells at random, so a row's LAST cell is not reliably Z (measured
    09-22: it is often the Y cell). A column seen in the sibling row
    anchors the missing one. Row y is the row's numeric-word mean: label
    words sit above the field text and clicking the label y misses the
    field (g5 round 2)."""
    words = mdu.ocr_words_img(img, scale=scale)

    def clean_token(t0):
        return clean_number_token(t0)

    def numerics_right(px, py):
        nums = []
        for w in words:
            t = clean_token(w[0])
            if t is not None and abs(w[2] - py) < 14 and w[1] > px:
                nums.append((w[1] + w[3] // 2, w[2] + w[4] // 2, t))
        return sorted(nums, key=lambda n: n[0])

    rows: list = []
    label_ys: list = []
    for w in words:
        if not w[0].lower().startswith(row_label.lower()):
            continue
        if w[2] <= 120:      # toolbar tooltips reuse gizmo names ('Rotate [R]')
            continue
        label_ys.append(w[2])
        nums = numerics_right(w[1], w[2])
        if nums:
            rows.append((sum(n[1] for n in nums) / len(nums), nums))
    if not rows:
        return []
    # cluster column x across ALL rows
    cols: list = []
    for x in sorted(n[0] for _, nums in rows for n in nums):
        if cols and x - cols[-1] <= 14:
            cols[-1] = (cols[-1] + x) / 2
        else:
            cols.append(float(x))
    # OCR can drop a WHOLE column in every row (measured 09-23, g20: the
    # Rotate panel's Z column vanished from both rows). Without
    # extrapolation the cell list is short, index -1 then addresses the Y
    # column while a readback at another OCR scale resolves to Z — typed
    # text and readback disagree forever. Extrapolate with the modal pitch.
    if cols:
        gaps = [b - a for a, b in zip(cols, cols[1:])]
        step = sorted(gaps)[len(gaps) // 2] if gaps else 63.0
        while len(cols) < 3:
            cols.append(cols[-1] + step)
    # same for a missing ROW: the Rotate panel has two label rows
    # ('(relative)'/'(absolute)'); if only one row of numbers was read and
    # two labels are present, synthesise the other row at the row pitch.
    if len(rows) == 1 and len(label_ys) >= 2:
        ry = rows[0][0]
        other = min(label_ys, key=lambda y: abs(y - ry))
        if abs(other - ry) > 6:
            rows.append((ry + (27.0 if other > ry else -27.0), []))
    out: list = []
    seen_y: set = set()
    for ry, nums in sorted(rows, key=lambda r: r[0]):
        if any(abs(ry - y) <= 6 for y in seen_y):
            continue
        seen_y.add(ry)
        for cx in cols:
            if not nums:
                out.append((int(cx), int(ry), ""))
                continue
            hit = min(nums, key=lambda n: abs(n[0] - cx))
            out.append((int(cx), int(ry),
                        hit[2] if abs(hit[0] - cx) <= 14 else ""))
    return out


# Fixed manipulation-panel geometry on the maximized rig (1920x1032, dpi 96).
# Measured repeatedly 09-08..09-23 (g2/g3/g5c/g13): every gizmo panel draws
# its numeric fields on the same three columns, 63px apart, on one or two
# rows 27px apart. Used ONLY as a fallback when the OCR grid comes back empty
# for a panel that is open (measured 09-23: m7t74's rotate panel read back
# '' for all five recipes while being visibly open).
def gizmo_field_box(session, row_label, viewport_origin=(0, 0)):
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


def _type_chars_verified(session, hwnd, box, text):
    """Send `text` char by char, re-sending a char until the field shows the
    expected prefix.

    WM_CHARs are dropped at random on this build (measured 09-23: '45'
    arrived as '4', '120' as '1', and some attempts lost everything), so a
    plain multi-char send can commit a WRONG value — '1' in the scale field
    means a 1% model. Reading the field after every char makes each char
    independently confirmed before moving on."""
    for i, ch in enumerate(text):
        want = text[:i + 1]
        for _try in range(4):
            winutil._send_msg(hwnd, WM_CHAR, ord(ch), 0)
            time.sleep(0.25)
            got = crop_read_cell(capture_bgr(session), box[0], box[1])
            if got and got.split(".")[0].startswith(want):
                break
            print(f"{LOG} char {ch!r} not landed yet (field reads {got!r})")
        else:
            return False
    return True


def type_into_field(session, box, text, old_len=4, wake=False, recipe=0):
    """Focus the field with a REAL click, type + commit via message keyboard
    through the deepest canvas child (m6a: chars must land on the canvas
    window, not the frame).

    Single click, not double: a double click as the panel's first
    interaction never entered text (g3: focus ring, value stayed 0.00),
    while a single click + digits + Enter committed (g4 t1: abs Z -> 45.00
    persisted across panel reopen; g5: Move X -> 60.00 pixel-verified).
    The click still occasionally fails to activate the widget on V2.3.6
    (the value just stays — g3/g5/g5c sessions), so op_gizmo_field retries
    across `recipe`/`wake` combinations:
      recipe 0: plain single click
      recipe 1: single click + clear the field first (backspaces)
      recipe 2: double click
      recipe 3: double click + clear
    `wake` prepends a bare click 1s before the real attempt."""
    fx, fy = client(session, *box)
    winutil.user32.SetCursorPos(fx, fy)
    time.sleep(0.2)
    if wake:
        winutil.real_click_screen(fx, fy)
        time.sleep(1.0)
    clicks = 2 if recipe in (2, 3) else 1
    for i in range(clicks):
        if i:
            time.sleep(0.08)
        winutil.real_click_screen(fx, fy)
    time.sleep(0.7)
    probe = winutil.client_to_screen(session.hwnd, 600, 400)
    hwnd = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
    if recipe in (1, 3, 4):
        for _ in range(max(old_len, 4) + 2):
            winutil._send_msg(hwnd, WM_CHAR, 0x08, 0)   # backspace
            time.sleep(0.04)
    if recipe == 4:
        if not _type_chars_verified(session, hwnd, box, text):
            print(f"{LOG} per-char typing did not converge — not committing")
            return
    else:
        for ch in text:
            winutil._send_msg(hwnd, WM_CHAR, ord(ch), 0)
            time.sleep(0.15)
    # A dropped character must NOT be committed: '45' arriving as '4' sets a
    # 4deg rotation, and '120' arriving as '1' scales the model to 1% — which
    # then breaks every later step of the case (measured 09-23: m7t74's model
    # vanished after the scale step committed 1.00). Verify the field content
    # first; on a partial read, leave the field uncommitted so the caller's
    # retry ladder can try again.
    got = crop_read_cell(capture_bgr(session), box[0], box[1])
    if got and not got.startswith(text):
        print(f"{LOG} typed {text!r} but the field reads {got!r} — "
              f"NOT committing (retry will re-type)")
        return
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


def model_blob_count(session, min_area=1500, aspect=(0.3, 3.0)):
    """Number of OBJECT-shaped chromatic blobs — the reliable object count.

    Plain blob_count() is not usable for object counting on 2.4.0: the
    object NAME LABEL (a ~71x9 chromatic strip) and the bottom-right plate
    widgets (~375x60 / 375x25 strips) also read as blobs >= 400 px, so a
    "one object left" assertion (blob_count < 2) can never hold (measured
    09-23, g18/g19: after a correct Delete the count stayed 3). Object
    renders are block-shaped, so keep blobs with area >= min_area and a
    bbox aspect ratio inside `aspect`."""
    import cv2
    import numpy as np
    img = capture_bgr(session)
    h, w = img.shape[:2]
    band = img[110:h - 60, VIEWPORT_X0 + 10:w - 10].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    keep = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area:
            continue
        bw = max(int(stats[i, cv2.CC_STAT_WIDTH]), 1)
        bh = max(int(stats[i, cv2.CC_STAT_HEIGHT]), 1)
        if aspect[0] <= bw / bh <= aspect[1]:
            keep.append((int(a), (int(stats[i, cv2.CC_STAT_LEFT]) + VIEWPORT_X0
                                  + 10,
                                  int(stats[i, cv2.CC_STAT_TOP]) + 110, bw, bh)))
    print(f"{LOG} object-shaped blobs: {keep}")
    return len(keep)


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


def add_primitive_via_toolbar(session, shape="cube"):
    """Fallback path for adding a primitive: the toolbar's 'Add' slot opens
    the same shape list.

    The bed right-click menu is dead after some flows (measured 09-23: after
    Edit > Delete All the bed right-click opens NOTHING at three points × two
    tries, which blocked m8b's cube step) — the toolbar slot is an
    independent entry point."""
    ensure_maximized(session)
    x, tip = find_slot(session, lambda t: t.strip().lower().startswith("add"))
    if x is None:
        print(f"{LOG} toolbar Add slot not found (tip={tip!r})")
        return False
    before = model_colored_frac(session)
    click_slot(session, x)
    deadline = time.monotonic() + 4.0
    menu = None
    while time.monotonic() < deadline:
        ms = topbar_util._enum_menu_windows(session.pid)
        if ms:
            menu = (ms[0][4], topbar_util.menu_hmenu(ms[0][4]))
            break
        time.sleep(0.25)
    if not menu:
        print(f"{LOG} toolbar Add slot opened no menu")
        return False
    hwnd, hmenu = menu
    rows = [l for _i, l in list_menu(hmenu)]
    print(f"{LOG} toolbar Add menu rows: {rows}")
    # the toolbar menu is open: click the shape row inside it, descending a
    # submenu when the row is nested
    for candidate in (shape, "primitive", "part"):
        hit = click_menu_row(session, hwnd, hmenu, candidate, nested=True)
        if hit and isinstance(hit, tuple):
            _i, (shwnd, shmenu) = hit
            if click_menu_row(session, shwnd, shmenu, shape):
                time.sleep(2.5)
                grew = model_colored_frac(session) > before + 0.001
                print(f"{LOG} toolbar add-{shape}: {grew}")
                dismiss_menus(session)
                return grew
        elif hit:
            time.sleep(2.5)
            grew = model_colored_frac(session) > before + 0.001
            print(f"{LOG} toolbar add-{shape}: {grew}")
            dismiss_menus(session)
            return grew
    dismiss_menus(session)
    return False


def op_add_primitive(session, shape="cube"):
    """Bed menu > Add Primitive > shape; returns the plate changed.

    The gate is RELATIVE to the empty-bed reading: a fresh cube on the
    default plate measures ~0.24% chromatic on 2.4.0 with the empty bed at
    ~0.06%, so a fixed +0.2pp margin sat right on the measured delta and
    flipped the verdict (measured 09-22: m7i/m7t73/m7t89/m8b 'model
    created' FAIL at 0.242%). +0.1pp is still ~2x the empty-bed reading."""
    before = model_colored_frac(session)
    ok = context_click_row(session, "bed", shape, via="Add Primitive",
                           success_fn=lambda: model_colored_frac(session)
                           > before + 0.001,
                           label=f"add-{shape}")
    if not ok:
        print(f"{LOG} bed menu route failed — trying the toolbar Add slot")
        ok = add_primitive_via_toolbar(session, shape)
    time.sleep(1.0)
    return ok


def clean_number_token(t0):
    """The number inside an OCR token, or None.

    Field values come back with decorations glued on — the Rotate panel's Z
    column reads '|0.00' (the field's caret/border glyph fused to the
    digits). Stripping only '([' dropped the whole cell as "not a number"
    (measured 09-23, g22)."""
    t = re.sub(r"^[|\[\](){}<>:;,'\"\s]+", "", t0)
    t = re.sub(r"[|\[\](){}<>:;,'\"\s°%]+$", "", t)
    return t if re.fullmatch(r"-?\d+(?:[.,]\d{1,2})?", t) else None


def crop_read_cell(img, cx, cy, half_w=34, half_h=13):
    """OCR a single gizmo cell from its own crop.

    The full-frame OCR at scale 3 upscales to ~5760x3096 and Tesseract drops
    small cells there — the Rotate Z column then reads '' at every scale
    while the SAME pixels crop cleanly ('0.00', measured 09-23, g22)."""
    crop = img[max(0, cy - half_h):cy + half_h, max(0, cx - half_w):cx + half_w]
    if crop.size == 0:
        return ""
    for scale in (4, 3, 6):
        for psm in (7, 6, 8):
            for w in mdu.ocr_words_img(crop, scale=scale, psm=psm):
                t = clean_number_token(w[0])
                if t is not None:
                    return t
    return ""


def read_gizmo_field(session, row_label, index, expect=None, timeout_s=12.0,
                     interval_s=1.0, scales=(3, 4, 2)):
    """Poll the gizmo row until field #index reads `expect`.

    The value comes from the FULL-row OCR at the CLUSTERED column — never
    'the last cell' (OCR drops columns at random, measured 09-22) and never
    a tiny cell crop (tesseract misreads/empties 68x28 crops of the focused
    field, g5/g5d). OCR is scale-dependent for the focused-field styling,
    so several scales are tried per frame.
    Returns (boxes, text)."""
    deadline = time.time() + timeout_s
    fallback = ([], "")
    while True:
        img = capture_bgr(session)
        for s in scales:
            boxes = gizmo_row_boxes_img(img, row_label, scale=s)
            idx = index if index >= 0 else len(boxes) + index
            text = boxes[idx][2] if 0 <= idx < len(boxes) else ""
            if boxes and (expect is None or text.startswith(expect)):
                return boxes, text
            if boxes and not fallback[0]:
                fallback = (boxes, text)
        if fallback[0]:
            bx = fallback[0]
            idx = index if index >= 0 else len(bx) + index
            if 0 <= idx < len(bx):
                t2 = crop_read_cell(img, bx[idx][0], bx[idx][1])
                if t2 and (expect is None or t2.startswith(expect)):
                    return bx, t2
                if t2 and not fallback[1]:
                    fallback = (bx, t2)
        if time.time() >= deadline:
            return fallback
        time.sleep(interval_s)


def op_gizmo_field(session, slot_pred, row_label, index, value,
                   fallback_dx=0):
    """Select + activate gizmo + type value into row field #index (index<0 =
    last row's last column, i.e. Rotate absolute Z). Returns (ok, text).

    Three robustness measures, all measured on this rig:
      * the toolbar toggle can be EATEN while the app re-renders the previous
        gizmo (09-23: m7t74's Rotate slot click after the Move step left the
        panel closed) — the keyboard shortcut re-toggles it;
      * the OCR grid can collapse to fewer columns than the panel has, so the
        cell list is built with column/row extrapolation (see
        gizmo_row_boxes_img) and index -1 stays the real Z column;
      * typing + readback is retried across recipes (plain single / clear /
        wake / double / double+clear); a cell is only typed into while the
        panel is open — an empty grid types NOTHING (never a blind click).
    The Scale slot shows NO tooltip while a model is selected and the
    rotate-tooltip smear breaks hover scans (g5), so `fallback_dx` clicks
    the slot at the fixed geometry Rotate+44 (1108+44)."""
    if not select_model(session):
        return False, ""
    if fallback_dx:
        x = 1108 + fallback_dx
        print(f"{LOG} {row_label} slot via fixed geometry: {x}")
    else:
        x, tip = find_slot(session, slot_pred)
    if x is None:
        return False, ""
    click_slot(session, x)
    time.sleep(1.0)
    if not gizmo_row_boxes(session, row_label):
        # The toolbar toggle can be eaten while the app is still re-rendering
        # the previous gizmo (measured 09-23: m7t74's Rotate slot click right
        # after the Move step left the panel closed — five recipes then read
        # an empty grid). The keyboard shortcut is a second, independent
        # channel (g21: 'R' toggles the rotate panel).
        print(f"{LOG} {row_label}: panel not open after the slot click")
        toggle_gizmo_key(session, row_label)
    text = ""
    for attempt, (recipe, wake) in enumerate(
            [(0, False), (1, False), (0, True), (2, False), (3, False),
             (4, False)],
            start=1):
        boxes = gizmo_row_boxes(session, row_label)
        if attempt == 1:
            print(f"{LOG} {row_label}: grid attempt1 = {boxes}")
        if not boxes:
            print(f"{LOG} {row_label}: panel closed — nothing to type into")
            break
        idx = index if index >= 0 else len(boxes) + index
        if not (0 <= idx < len(boxes)):
            break
        type_into_field(session, boxes[idx][:2], value,
                        old_len=max(len(boxes[idx][2]), 4),
                        wake=wake, recipe=recipe)
        _boxes2, text = read_gizmo_field(session, row_label, index,
                                         expect=value, timeout_s=6.0)
        print(f"{LOG} {row_label} attempt{attempt} recipe={recipe} "
              f"wake={wake}: {text!r}")
        if text.startswith(value):
            break
    # Toggle the gizmo back OFF — only when the panel is really open (a
    # redundant toggle would re-open it and the panel blob then wins
    # find_centroid's "largest blob" vote, so the next select_model clicks
    # the panel instead of the model, measured 09-21).
    if gizmo_row_boxes(session, row_label):
        click_slot(session, x)
        time.sleep(0.8)
        if gizmo_row_boxes(session, row_label):
            toggle_gizmo_key(session, row_label)
    return text.startswith(value), text


def click_slice_again(session):
    """Re-slice when the button already sits in its DONE rendering.

    After a completed slice the button shows the done template, so
    click_slice_start's IDLE template can never match ("click didn't take
    (still 1.000)", measured 09-23 twice: m8f's second slice in one session
    and the g23 determinism probe). Clicking the DONE template re-slices."""
    import cv2
    from m2_slice_chain import RESOURCE, wait_for
    score, sx, sy = wait_for(session, RESOURCE / "slice_button_done.png",
                             timeout_s=8.0)
    if score < 0.85:
        print(f"{LOG} done-template not found ({score:.3f})")
        return False
    winutil.msg_click_screen(sx, sy, session.hwnd)
    time.sleep(1.0)
    return True


def wait_slice_button_ready(session, timeout_s=120):
    """Poll until the Slice button is in its IDLE or DONE rendering.

    A parameter change (e.g. the Nozzle Flow switch) makes the app auto-slice;
    while that render is busy NEITHER the idle nor the done template matches,
    so both click paths fail with 'slice click rejected' (measured 09-24 on
    m8f/m8g right after Flow -> High Flow). Returns the template name that
    matched, or '' on timeout."""
    from harness.anchors import match
    from m2_slice_chain import RESOURCE
    # match() takes a template NAME or PATH (it loads the image itself) —
    # passing a cv2 array raises TypeError (measured 09-24)
    tpl_idle = str(RESOURCE / "slice_plate_button.png")
    tpl_done = str(RESOURCE / "slice_button_done.png")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        s_idle, _, _, _, _ = match(img, tpl_idle)
        if s_idle >= 0.85:
            return "idle"
        s_done, _, _, _, _ = match(img, tpl_done)
        if s_done >= 0.85:
            return "done"
        time.sleep(1.5)
    return ""


def op_slice(session, results, key="slice completes", export_to=None,
             timeout_s=600):
    """Click Slice, wait done, optionally export gcode to export_to."""
    from m2_slice_chain import click_slice_start, wait_slicing_done
    state = wait_slice_button_ready(session)
    print(f"{LOG} {key}: slice button state={state!r}")
    if state == "done":
        # already sliced (auto-slice after a parameter change): re-slice
        if not click_slice_again(session):
            results[key] = "FAIL (done-button click rejected)"
            return False
    elif not click_slice_start(session):
        # The message click can be rejected while the button still renders
        # idle — right after a Nozzle Flow change the plater needs genuine
        # input, the same lesson as the Plaster context menu / export button
        # (measured 09-24: m8f/m8g's post-flow-switch slice). Try a REAL click
        # on the matched button before falling back to the done rendering.
        from harness.anchors import match
        from m2_slice_chain import RESOURCE
        started = False
        img = capture_bgr(session)
        score, bx, by, bw, bh = match(
            img, str(RESOURCE / "slice_plate_button.png"))
        if score >= 0.85:
            sx, sy = client(session, bx + bw // 2, by + bh // 2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
            print(f"{LOG} {key}: real click on the slice button @({sx},{sy})")
            time.sleep(2.5)
            after, *_ = match(capture_bgr(session),
                              str(RESOURCE / "slice_plate_button.png"))
            started = after < 0.7
            print(f"{LOG} {key}: after real click idle-score={after:.3f} "
                  f"started={started}")
        if not started:
            print(f"{LOG} {key}: idle slice button not clickable — trying the "
                  f"done rendering")
            if not click_slice_again(session):
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
