#!/usr/bin/env python3
# diag_m6_move2.py — P1-5 full-chain diag: drive the Move window's Position X
# ImGui field via message keyboard, verify the model moves AND the 3mf
# transform follows. Chain: boot -> select -> Move gizmo on -> OCR the
# Position row -> click the X value box -> backspace-clear + type '60' +
# Enter -> OCR new value + centroid moved -> Save Project as -> parse
# <item transform> translation X.
# Artifacts: artifacts/diag_m6b_*.png + artifacts/diag_m6b_out.3mf

import re
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent.parent  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
from m4e_mixing_paint import (BAR_Y, client, find_slot, find_model_centroid,  # noqa: E402
                              select_model, viewport_img)
from m3g_export_3mf import save_project_as  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import winutil  # noqa: E402

LOG = "[diag-m6b]"
ART = HERE / "artifacts"
WM_CHAR, WM_KEYDOWN = 0x0102, 0x0100
VK_RETURN = 0x0D


def save(session, tag):
    p = ART / f"diag_m6b_{tag}.png"
    cv2.imwrite(str(p), viewport_img(session))
    print(f"{LOG} shot -> {p.name}")


def position_row(session):
    """OCR the canvas for the Position row: returns (x_value_box_center,
    current_text) of the FIRST numeric field right of the 'Position' label,
    or (None, ''). Adaptive to any window size (no hardcoded coords)."""
    img = viewport_img(session)
    words = mdu.ocr_words_img(img, scale=3)  # (text, x, y, w, h)
    pos = next((w for w in words if w[0].lower() == "position"), None)
    if not pos:
        return None, ""
    px, py = pos[1], pos[2]
    nums = [w for w in words
            if re.fullmatch(r"[\d]+[.,]\d{1,2}", w[0])
            and abs(w[2] - py) < 14 and w[1] > px]
    nums.sort(key=lambda w: w[1])
    if not nums:
        return None, ""
    n = nums[0]
    return (n[1] + n[3] // 2, n[2] + n[4] // 2), n[0]


def type_into_canvas(session, text, enter=True):
    """Message-keyboard into the GL canvas (ImGui InputDouble)."""
    hwnd = winutil.deepest_child_at(session.hwnd,
                                    *winutil.client_to_screen(session.hwnd, 600, 400))
    hwnd = hwnd or session.hwnd
    for ch in text:
        winutil._send_msg(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(0.05)
    if enter:
        winutil._send_msg(hwnd, WM_KEYDOWN, VK_RETURN, 0)
        time.sleep(0.1)
        winutil._send_msg(hwnd, WM_CHAR, 0x0D, 0)


def parse_transform():
    import zipfile
    p = ART / "diag_m6b_out.3mf"
    with zipfile.ZipFile(p) as z:
        data = z.read("3D/3dmodel.model").decode("utf-8", errors="replace")
    m = re.search(r'transform="([^"]+)"', data)
    return [float(v) for v in m.group(1).split()] if m else None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    out3mf = ART / "diag_m6b_out.3mf"
    session = boot_session(args, model=args.model)
    try:
        ok, _ = wait_model_loaded(session, timeout_s=240)
        if not ok:
            print(f"{LOG} model not loaded")
            return 1
        time.sleep(2.0)
        cx0, cy0 = find_model_centroid(session)
        print(f"{LOG} centroid before: ({cx0},{cy0})")

        if not select_model(session):
            return 2
        move_x, _ = find_slot(session, lambda t: "move" in t)
        if move_x is None:
            return 3
        sx, sy = client(session, move_x, BAR_Y)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        winutil.real_click_screen(sx, sy)
        time.sleep(2.5)
        save(session, "01_move_active")

        box, cur = position_row(session)
        print(f"{LOG} Position X field: box={box} current={cur!r}")
        if box is None:
            return 4

        # focus the X field (real click — ImGui hit test needs real input)
        fx, fy = client(session, *box)
        winutil.user32.SetCursorPos(fx, fy)
        time.sleep(0.2)
        winutil.real_click_screen(fx, fy)
        time.sleep(0.6)
        save(session, "02_field_focused")

        # clear (backspaces) + type 60 + Enter — message keyboard
        for _ in range(len(cur) + 2):
            winutil._send_msg(session.hwnd, WM_CHAR, 0x08, 0)
            time.sleep(0.04)
        type_into_canvas(session, "60")
        time.sleep(1.5)
        save(session, "03_after_type")

        box2, cur2 = position_row(session)
        print(f"{LOG} Position X after: {cur2!r}")
        cx1, cy1 = find_model_centroid(session)
        print(f"{LOG} centroid after: ({cx1},{cy1})")

        if out3mf.exists():
            out3mf.unlink()
        ok_save = save_project_as(session, out3mf)
        print(f"{LOG} saved 3mf: {ok_save}")
        if ok_save:
            t = parse_transform()
            print(f"{LOG} transform: {t}")
        save(session, "04_final")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
