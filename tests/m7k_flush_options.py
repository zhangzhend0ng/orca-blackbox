#!/usr/bin/env python3
# m7k_flush_options.py — Feishu #24 (GUI业务, P0, PARTIAL):
#   【正向】擦除塔材料切换后G-Code正确
#
# Scope note: the record's wipe-tower-material gcode semantics need a
# printer profile with a wipe tower and network/multi-material context;
# the black-box-reachable surface of the same feature is the object
# context menu's 'Flush Options' submenu (GUI_Factories
# append_menu_items_flush_options) — per-filament flush toggles with
# CHECKABLE state. This case asserts the toggle actually flips (menu
# state flag before/after); the gcode-level wipe-tower assertion stays
# manual (recorded in the mapping).
#
# Black-box path: boot mixed fixture (4 filaments) -> select -> right-click
# > Flush Options (rows + state enumerated) -> toggle the first checkable
# row -> reopen -> the row's state flag must differ.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import topbar_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7k]"
MF_BYPOSITION = 0x400


def open_flush_submenu(session):
    """(hwnd, hmenu, shwnd, shmenu) of the model menu's Flush Options."""
    menu = m7.open_context_menu(session, where="model")
    if not menu:
        return None
    hwnd, hmenu = menu
    got = m7.click_menu_row(session, hwnd, hmenu, "flush options",
                            nested=True)
    if not got:
        m7.dismiss_menus(session)
        return None
    _idx, (shwnd, shmenu) = got
    return hwnd, hmenu, shwnd, shmenu


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.5)

        if not m7.select_model(session):
            results["model selected"] = "FAIL"
            return m7.m7_verdict(results)
        results["model selected"] = "PASS"

        opened = open_flush_submenu(session)
        results["Flush Options submenu opens"] = "PASS" if opened else "FAIL"
        if not opened:
            return m7.m7_verdict(results)
        _hwnd, _hmenu, shwnd, shmenu = opened
        rows = m7.list_menu(shmenu)
        print(f"{LOG} flush rows: {rows}")
        target = next(((i, l) for i, l in rows if l.strip()), None)
        results["flush options listed"] = (
            f"PASS ({len(rows)} rows)" if target else "FAIL (empty)")
        if not target:
            m7.dismiss_menus(session)
            return m7.m7_verdict(results)
        idx, lbl = target
        st_before = ctypes.WinDLL("user32").GetMenuState(shmenu, idx,
                                                         MF_BYPOSITION)

        rect = m7._menu_item_rect(shwnd, shmenu, idx)
        if not rect:
            results["flush toggle flips state"] = "FAIL (no row rect)"
            m7.dismiss_menus(session)
            return m7.m7_verdict(results)
        sx, sy = m7.client(session, (rect[0] + rect[2]) // 2,
                           (rect[1] + rect[3]) // 2)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        winutil.real_click_screen(sx, sy)
        time.sleep(2.0)
        m7.dismiss_menus(session)
        time.sleep(1.0)

        reopened = open_flush_submenu(session)
        if not reopened:
            results["flush toggle flips state"] = "FAIL (reopen failed)"
            return m7.m7_verdict(results)
        _h2, _hm2, shwnd2, shmenu2 = reopened
        st_after = ctypes.WinDLL("user32").GetMenuState(shmenu2, idx,
                                                        MF_BYPOSITION)
        print(f"{LOG} flush state {lbl!r}: 0x{st_before:x} -> 0x{st_after:x}")
        results["flush toggle flips state"] = (
            "PASS" if st_before != st_after else "FAIL (state unchanged)")
        m7.dismiss_menus(session)
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
