#!/usr/bin/env python3
# diag_m7_probe.py — runtime probe for the m7 main-flow op surface (does NOT
# guess: enumerates the real context menus and the real gizmo toolbar).
#   1. boot mixed fixture -> model arrives
#   2. select model -> real right-click on it -> enumerate object menu rows
#   3. real right-click on empty bed -> enumerate default menu rows
#   4. hover-scan the top gizmo toolbar -> list every slot tooltip
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import cv2  # noqa: E402

from harness import topbar_util, winutil  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness.anchors import PAINT_BAR_Y as BAR_Y, PAINT_PITCH as PITCH  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
from m4e_mixing_paint import client, find_model_centroid, find_slot  # noqa: E402

LOG = "[diag_m7]"
ART = HERE / "artifacts"


def dump_menu(label):
    menus = topbar_util.wait_menu_popup(SESSION_PID, timeout_s=4.0)
    if not menus:
        print(f"{LOG} {label}: NO menu popup")
        return []
    for rect, hwnd in [(m[:4], m[4]) for m in menus]:
        hmenu = topbar_util.menu_hmenu(hwnd)
        items = topbar_util.menu_items(hmenu)
        print(f"{LOG} {label}: menu hwnd=0x{hwnd:x} rect={rect} items={len(items)}")
        for i, text, st in items:
            print(f"{LOG}   [{i}] {text!r} state=0x{st:x}")
    return menus


SESSION_PID = 0


def main() -> int:
    global SESSION_PID
    ap = add_common_args(__import__("argparse").ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=args.model or MIXED_3MF)
    SESSION_PID = session.pid
    try:
        ok, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok} ({frac:.2%})")
        time.sleep(1.0)

        # --- 1. select model, then right-click ON it ---
        pos = find_model_centroid(session)
        print(f"{LOG} centroid: {pos}")
        if pos:
            sx, sy = client(session, *pos)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_right_click_screen(sx, sy)
            time.sleep(1.0)
            dump_menu("object-menu")
            topbar_util.close_menu_windows(session.pid)
            time.sleep(0.5)

        # --- 2. right-click on empty bed (viewport bottom-left area) ---
        rect = winutil.window_rect(session.hwnd)
        w = rect[2] - rect[0]
        ex, ey = client(session, 470, 500)
        winutil.user32.SetCursorPos(ex, ey)
        time.sleep(0.3)
        winutil.real_right_click_screen(ex, ey)
        time.sleep(1.0)
        dump_menu("default-menu")
        topbar_util.close_menu_windows(session.pid)
        time.sleep(0.5)

        # --- 3. gizmo toolbar tooltip scan (left band of the viewport) ---
        img = capture_bgr(session)
        x0 = 430 + 60
        slots = []
        for i in range(min((img.shape[1] - 60 - x0) // PITCH + 1, 40)):
            cx = x0 + i * PITCH
            from m4e_mixing_paint import hover_tooltip_text
            text = hover_tooltip_text(session, cx, BAR_Y, dwell_s=1.0)
            if text:
                print(f"{LOG} toolbar slot @x{cx}: {text!r}")
                slots.append((cx, text))
        cv2.imwrite(str(ART / "diag_m7_probe.png"), capture_bgr(session))
        print(f"{LOG} slots={len(slots)}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
