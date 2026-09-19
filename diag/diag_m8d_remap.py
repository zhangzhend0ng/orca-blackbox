#!/usr/bin/env python3
"""diag_m8d_remap.py — the Change Filament submenu real-click silently
does nothing on the 09-16 build (gcode proves the object stays on PETG).
Test the WM_COMMAND route instead: GetMenuItemID on the native submenu,
then SendMessageW(frame, WM_COMMAND, id) — no coordinates involved.

Verdict = the exported gcode's first filament_settings_id.

    C:\\Python311\\python.exe diag\\diag_m8d_remap.py
"""
import ctypes
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import winutil  # noqa: E402

u = winutil.user32
WM_COMMAND = 0x0111


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, _f = m8.wait_arrival(session)
        print(f"[d] arrival={ok}", flush=True)
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        if not m7.step_delete_all(session, {}):
            print("[d] delete-all failed", flush=True)
            return 1
        if not m7.op_add_primitive(session, "cube"):
            print("[d] add cube failed", flush=True)
            return 1
        time.sleep(0.8)
        if not m7.select_model(session):
            print("[d] select failed", flush=True)
        menu = m7.open_context_menu(session, where="model")
        if not menu:
            print("[d] no context menu", flush=True)
            return 1
        hwnd, hmenu = menu
        got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                                nested=True)
        if not got:
            m7.dismiss_menus(session)
            print("[d] no change-filament submenu", flush=True)
            return 1
        _i, (shwnd, shmenu) = got
        rows = m7.list_menu(shmenu)
        target = None
        for idx, lbl in rows:
            if "Silk" in lbl:
                target = idx
                break
        if target is None:
            print(f"[d] no Silk row in {rows}", flush=True)
            return 1
        item_id = u.GetMenuItemID(shmenu, target)
        print(f"[d] Silk row idx={target} item_id={item_id}", flush=True)
        m7.dismiss_menus(session)
        # post the menu command straight to the frame
        u.SendMessageW(session.hwnd, WM_COMMAND, item_id, 0)
        time.sleep(2.5)
        # verify: slice and read the gcode's first filament id
        g = HERE / "artifacts" / "m8d_remap_diag.gcode"
        g.unlink(missing_ok=True)
        results = {}
        if not m7.op_slice(session, results, key="diag slice",
                           export_to=g):
            print("[d] slice failed", flush=True)
            return 1
        head = g.read_text(encoding="utf-8", errors="replace")[:20000]
        m = re.search(r"; filament_settings_id = ([^\r\n]+)", head)
        first = m.group(1).split(";")[0].strip() if m else "(?)"
        print(f"[d] first filament: {first!r}", flush=True)
        print("[d] REMAP-OK" if "Silk" in first else "[d] REMAP-STILL-PETG",
              flush=True)
        return 0
    finally:
        session.close()
        print("[d] app closed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
