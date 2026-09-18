#!/usr/bin/env python3
"""diag_m8f_popup2.py — round 2: resolve the REAL combo control under the
'Flow' value text (WindowFromPoint + parent), click its arrow with a real
click, and enumerate EVERY window owned by the app pid (raw EnumWindows,
no toplevel filtering) so a native ComboLBox cannot hide.

    C:\\Python311\\python.exe diag\\diag_m8f_popup2.py
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
from harness import winutil, export_util  # noqa: E402
from harness.shot_archive import _save  # noqa: E402

OUT = HERE / "artifacts" / "m8f_diag"
u = winutil.user32
EW_REALTIME = 3


def pid_windows(pid):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _l):
        wpid = ctypes.c_uint32()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            buf = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(hwnd, buf, 64)
            rc = wt.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(rc))
            out.append((int(hwnd) if hwnd else 0, buf.value,
                        (rc.left, rc.top, rc.right, rc.bottom),
                        bool(u.IsWindowVisible(hwnd))))
        return True
    u.EnumWindows(cb, 0)
    return out


def main() -> int:
    ap = __import__("argparse").ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=HERE / "fixtures" / "mixed_filament_test.3mf")
    try:
        reads = m8.nozzle_reads(session)
        rect = reads["flow_rect"]
        # resolve the actual control under the value-text center
        tx = (rect[0] + rect[2]) // 2
        ty = (rect[1] + rect[3]) // 2
        sx, sy = winutil.client_to_screen(session.hwnd, tx, ty)
        u.SetCursorPos(sx, sy)
        time.sleep(0.2)
        hwnd_at = u.WindowFromPoint(wt.POINT(sx, sy))
        # walk up to the combo parent if the point hit the value Static
        buf = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd_at, buf, 64)
        parent = u.GetParent(hwnd_at)
        pbuf = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(parent, pbuf, 64) if parent else None
        prc = wt.RECT()
        u.GetWindowRect(parent or hwnd_at, ctypes.byref(prc))
        print(f"[d] point hit class={buf.value!r} parent={pbuf.value!r} "
              f"rect=({prc.left},{prc.top},{prc.right},{prc.bottom})", flush=True)

        # real click near the combo's right edge (dropdown arrow)
        ax = (prc.right - 10) if prc.right > sx else sx + 60
        ay = (prc.top + prc.bottom) // 2
        u.SetCursorPos(ax, ay)
        time.sleep(0.3)
        winutil.real_click_screen(ax, ay)
        time.sleep(1.2)
        wins = pid_windows(session.pid)
        vis = [w for w in wins if w[3]]
        print(f"[d] visible pid windows after click: "
              f"{[(c, r) for _h, c, r, _v in vis]}", flush=True)
        for i, (h, c, r, _v) in enumerate(vis):
            if c not in ("tooltips_class32", "SysShadow"):
                _save(h, OUT / f"w{i}_{c.strip('#')}.png")
        now = m8.nozzle_reads(session).get("flow")
        print(f"[d] flow after edge click: {now!r}", flush=True)
        return 0
    finally:
        session.close()
        print("[d] app closed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
