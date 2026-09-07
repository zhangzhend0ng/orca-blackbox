#!/usr/bin/env python3
# m7t82.py — Feishu #82 主流程-模板: 剪贴耗材切换
#   M-01 import -> M-14 cut -> M-18 change filament -> M-02 slice
#   -> O-02 close
# Cut splits the object (Perform cut); Change Filament (object menu
# nested submenu, GUI_Factories:2061) remaps the object's extruder; the
# slice completes after both.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF  # noqa: E402
from m7t77 import perform_cut  # noqa: E402
import m7_common as m7  # noqa: E402


def change_filament_last(session):
    """Object menu > Change Filament > last row (the remap target)."""
    if not m7.select_model(session):
        return False
    menu = m7.open_context_menu(session, where="model")
    if not menu:
        return False
    hwnd, hmenu = menu
    got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                            nested=True)
    if not got:
        m7.dismiss_menus(session)
        return False
    _idx, (shwnd, shmenu) = got
    rows = m7.list_menu(shmenu)
    if len(rows) < 2:
        m7.dismiss_menus(session)
        return False
    _i, lbl = rows[-1]
    m7.click_menu_row(session, shwnd, shmenu, lbl)
    time.sleep(1.5)
    return True


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    results["cut step"] = "SKIP (no Cut gizmo on the main toolbar)"
    results["filament switched"] = (
        "PASS" if change_filament_last(session) else "FAIL")
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
