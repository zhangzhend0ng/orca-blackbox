#!/usr/bin/env python3
"""diag_m8f_popup3.py — round 3: enumerate CHILD windows around the nozzle
Flow area (the value text may overlay a native wxComboBox); if a real
ComboBox control exists, drive it with CB_SHOWDROPDOWN / keyboard instead
of click coordinates.

    C:\\Python311\\python.exe diag\\diag_m8f_popup3.py
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import add_common_args, boot_session  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import winutil  # noqa: E402

OUT = HERE / "artifacts" / "m8f_diag"
u = winutil.user32


def child_windows(hwnd):
    out = []
    h = 0
    while True:
        h = u.FindWindowExW(hwnd, h, None, None)
        if not h:
            break
        rc = wt.RECT()
        u.GetWindowRect(h, ctypes.byref(rc))
        buf = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, buf, 64)
        out.append((h, buf.value, (rc.left, rc.top, rc.right, rc.bottom)))
    return out


def main() -> int:
    ap = __import__("argparse").ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=HERE / "fixtures" / "mixed_filament_test.3mf")
    try:
        reads = m8.nozzle_reads(session)
        fr = reads["flow_rect"]  # client coords of the Flow value text
        sx0, sy0 = winutil.client_to_screen(session.hwnd, 0, 0)
        kids = child_windows(session.hwnd)
        near = [k for k in kids
                if k[2][0] < sx0 + fr[2] + 30 and k[2][2] > sx0 + fr[0] - 30
                and k[2][1] < sy0 + fr[3] + 30 and k[2][3] > sy0 + fr[1] - 30]
        print(f"[d] children near Flow: "
              f"{[(c, r) for _h, c, r in near]}", flush=True)
        combo = next((k for k in near if "comb" in k[1].lower()), None)
        if not combo:
            # widen: any descendant of the child owning the point
            tx, ty = winutil.client_to_screen(
                session.hwnd, (fr[0] + fr[2]) // 2, (fr[1] + fr[3]) // 2)
            hit = u.WindowFromPoint(wt.POINT(tx, ty))
            cb = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(hit, cb, 64)
            print(f"[d] WindowFromPoint now class={cb.value!r}", flush=True)
            return 1
        h, cls, rect = combo
        print(f"[d] combo hwnd=0x{h:x} class={cls!r} rect={rect}", flush=True)
        CB_SHOWDROPDOWN = 0x014F
        u.SendMessageW(h, CB_SHOWDROPDOWN, 1, 0)
        time.sleep(1.0)
        CB_GETDROPPEDSTATE = 0x0157
        state = u.SendMessageW(h, CB_GETDROPPEDSTATE, 0, 0)
        print(f"[d] dropped state={state}", flush=True)
        # native listbox of the combo
        lb = winutil.user32.GetWindow(h, 5)  # GW_CHILD? try FindWindowEx
        listbox = u.FindWindowExW(h, 0, "ComboLBox", None)
        print(f"[d] ComboLBox hwnd=0x{listbox:x}" if listbox else
              "[d] no ComboLBox child", flush=True)
        time.sleep(0.5)
        from harness import export_util
        from harness.shot_archive import _save
        import winutil as _w
        cap = _w.capture_window(h)
        import cv2, numpy as np
        img = np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4)
        cv2.imwrite(str(OUT / "combo_after_show.png"), img[:, :, :3])
        # keyboard select: focus + down + return
        u.SetFocus(h)
        time.sleep(0.2)
        u.SendMessageW(h, 0x0100, 0x28, 0)  # WM_KEYDOWN DOWN
        time.sleep(0.3)
        u.SendMessageW(h, 0x0100, 0x0D, 0)  # WM_KEYDOWN RETURN
        time.sleep(1.0)
        print(f"[d] flow after DOWN+ENTER: {m8.nozzle_reads(session).get('flow')!r}",
              flush=True)
        return 0
    finally:
        session.close()
        print("[d] app closed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
