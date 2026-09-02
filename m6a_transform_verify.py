#!/usr/bin/env python3
# m6a_transform_verify.py — P1-5 (absorbed from white-box ab3b34adf5:459):
# an object transform driven through the Move gizmo window's Position X
# field lands in the exported 3mf's <build><item transform> with EXACT
# precision — the "instance matrix is blackbox-untestable" C-tier claim
# only holds for RUNTIME reads; the exported 3mf carries it as plaintext.
#
# White-box refs:
#   - wx_gui_business_tests.cpp:459 — transform reflects in instance matrix
#     (white-box reads the matrix live; we assert the same value via the
#     exported artifact instead).
#   - Gizmos/GizmoObjectManipulation.cpp:800 do_render_move_window — the
#     Position/Size/Rotation fields are ImGui BBLInputDouble boxes drawn
#     INSIDE the GL canvas (no child HWNDs): focus needs a real click,
#     text entry goes through wxEVT_CHAR (message keyboard works).
#   - Format/3mf.cpp TRANSFORM_ATTR — <item transform="r..r tx ty tz">,
#     translation = last 3 components of the build item.
#
# Black-box path: boot mixed fixture -> select model -> activate the Move
# gizmo (tooltip scan) -> OCR the Position row, click the X value box ->
# backspace-clear + type '60' + Enter -> assert the OCR'd value flips to
# 60.00, the model centroid moves -> Save Project as -> unzip and assert
# the build-item translation X == 60.0 with Y/Z unchanged (136/13.5).
# Undo/redo of a transform stays white-box (:505) — out of scope here.
#
# Guest-verified chain of custody: diag_m6_move.py + diag_m6_move2.py
# (2026-09-02, win11-test maximized, dev exe).

import re
import sys
import time
import zipfile
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402
from m3g_export_3mf import save_project_as  # noqa: E402
from m4e_mixing_paint import (BAR_Y, client, find_model_centroid,  # noqa: E402
                              find_slot, select_model, viewport_img)
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import winutil  # noqa: E402

LOG = "[m6a]"
ART = HERE / "artifacts"
WM_CHAR, WM_KEYDOWN = 0x0102, 0x0100
VK_RETURN = 0x0D
TARGET_X = "60"          # typed into Position X
EXPECT_Y, EXPECT_Z = 136.0, 13.5  # fixture's untouched components


def position_row(session):
    """(x_value_box_center, current_text) of the first numeric field right
    of the 'Position' label — adaptive, no hardcoded coordinates."""
    img = viewport_img(session)
    words = mdu.ocr_words_img(img, scale=3)
    pos = next((w for w in words if w[0].lower() == "position"), None)
    if not pos:
        return None, ""
    px, py = pos[1], pos[2]
    nums = sorted((w for w in words
                   if re.fullmatch(r"[\d]+(?:[.,]\d{1,2})?", w[0])
                   and abs(w[2] - py) < 14 and w[1] > px),
                  key=lambda w: w[1])
    if not nums:
        return None, ""
    n = nums[0]
    return (n[1] + n[3] // 2, n[2] + n[4] // 2), n[0]


def type_chars(session, text, enter=True):
    """Message keyboard into the GL CANVAS child (ImGui InputDouble via
    wxEVT_CHAR). Sending to the main frame does NOT reach ImGui — the
    chars must land on the canvas window under the viewport (diag_m6b
    lesson: main-hwnd delivery left the field uncommitted)."""
    probe = winutil.client_to_screen(session.hwnd, 600, 400)
    hwnd = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
    for ch in text:
        winutil._send_msg(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(0.05)
    if enter:
        winutil._send_msg(hwnd, WM_KEYDOWN, VK_RETURN, 0)
        time.sleep(0.1)
        winutil._send_msg(hwnd, WM_CHAR, 0x0D, 0)


def build_item_translation(path_3mf: Path):
    """Last 3 components of the <build><item transform> (the INSTANCE
    translation — the mesh-level transforms inside Objects/*.model are
    not the assertion target). None when absent."""
    with zipfile.ZipFile(path_3mf) as z:
        data = z.read("3D/3dmodel.model").decode("utf-8", errors="replace")
    m = re.search(r"<item[^>]*\stransform=\"([^\"]+)\"", data)
    if not m:
        return None
    vals = [float(v) for v in m.group(1).split()]
    return vals[9:12] if len(vals) == 12 else None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out3mf = ART / "m6a_out.3mf"
    if out3mf.exists():
        out3mf.unlink()

    session = boot_session(args, model=args.model)
    try:
        ok, _ = wait_model_loaded(session, timeout_s=240)
        results["project loads"] = "PASS" if ok else "FAIL"
        if not ok:
            return verdict(results)
        time.sleep(2.0)
        before = find_model_centroid(session)

        selected = select_model(session)
        results["model selected"] = "PASS" if selected else "FAIL"
        if not selected:
            return verdict(results)

        move_x, tip = find_slot(session, lambda t: "move" in t)
        results["Move gizmo found"] = "PASS" if move_x else "FAIL"
        if move_x is None:
            return verdict(results)
        sx, sy = client(session, move_x, BAR_Y)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        winutil.real_click_screen(sx, sy)
        time.sleep(2.5)

        box, cur = position_row(session)
        results["Position X field located"] = (
            f"PASS (was {cur})" if box else "FAIL")
        if box is None:
            return verdict(results)

        # focus the X field: ImGui hit test needs a REAL click
        fx, fy = client(session, *box)
        winutil.user32.SetCursorPos(fx, fy)
        time.sleep(0.2)
        winutil.real_click_screen(fx, fy)
        time.sleep(0.6)

        # clear + type + commit (message keyboard through the CANVAS child)
        probe = winutil.client_to_screen(session.hwnd, 600, 400)
        canvas_hwnd = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
        for _ in range(len(cur) + 2):
            winutil._send_msg(canvas_hwnd, WM_CHAR, 0x08, 0)
            time.sleep(0.04)
        type_chars(session, TARGET_X)
        time.sleep(1.5)

        _box2, cur2 = position_row(session)
        results["field commits typed value"] = (
            "PASS (now %s)" % cur2 if cur2.startswith(TARGET_X) else
            f"FAIL (now {cur2!r})")

        after = find_model_centroid(session)
        moved = bool(before and after and
                     (abs(after[0] - before[0]) > 40 or
                      abs(after[1] - before[1]) > 40))
        results["model centroid moves"] = "PASS" if moved else "FAIL"

        ok_save = save_project_as(session, out3mf)
        results["3mf exported"] = "PASS" if ok_save else "FAIL"
        if not ok_save:
            return verdict(results)

        t = build_item_translation(out3mf)
        if t is None:
            results["transform X == 60.0"] = "FAIL (no build item)"
            results["transform Y/Z unchanged"] = "FAIL (no build item)"
        else:
            results["transform X == 60.0"] = (
                "PASS (%.1f)" % t[0] if abs(t[0] - float(TARGET_X)) < 0.01
                else f"FAIL ({t[0]})")
            results["transform Y/Z unchanged"] = (
                "PASS (%.1f/%.1f)" % (t[1], t[2])
                if abs(t[1] - EXPECT_Y) < 0.01 and abs(t[2] - EXPECT_Z) < 0.01
                else f"FAIL ({t[1]}/{t[2]})")

        cv2.imwrite(str(ART / "m6a_final.png"), viewport_img(session))
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
