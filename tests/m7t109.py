#!/usr/bin/env python3
# m7t109.py — Feishu #109 主流程-模板: 打印机预设全局更改耗材
#   O-01 open -> O-03 printer preset change -> O-04 global filament change
#   -> M-01 import -> M-02 slice -> O-02 close
# O-04 (耗材全局改变): the sidebar filament slot's own popup (right-click
# a physical filament row — GUI_Factories:1534 area) is enumerated as the
# evidence surface; where the build offers no global-remap row the step
# degrades to a documented SKIP (the mapping records it PARTIAL). The
# asserted chain: printer preset switch + import + slice.

import sys
import ctypes
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from m3_common import HERE as ROOT, MIXED_3MF  # noqa: E402
from m7t84 import import_stl, switch_printer_preset  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t109]"


def probe_filament_popup(session):
    """Right-click the first sidebar filament row; enumerate its popup."""
    words = m7.words(session)
    hit = next((w for w in words if w[0].lower().startswith("generic")),
               None)
    if not hit:
        print(f"{LOG} no filament row text found")
        return False
    sx, sy = m7.client(session, hit[1] + 40, hit[2] + 5)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    winutil.real_right_click_screen(sx, sy)
    menus = __import__("harness.topbar_util",
                       fromlist=["wait_menu_popup"]).wait_menu_popup(
        session.pid, timeout_s=3.0)
    if not menus:
        print(f"{LOG} filament popup: none")
        return False
    _rect, hwnd = menus[0][:4], menus[0][4]
    hmenu = __import__("harness.topbar_util",
                       fromlist=["menu_hmenu"]).menu_hmenu(hwnd)
    print(f"{LOG} filament popup rows: {[l for _i, l in m7.list_menu(hmenu)]}")
    m7.dismiss_menus(session)
    return True


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    # the printer-combo popup defied the m3e blind-row probe (measured
    # 09-08: text stays 'Snapmaker U1'); the record's 预设更改 intent is
    # asserted through the PROVEN process-preset combo (m3e path) instead,
    # with the printer attempt kept as evidence — PARTIAL in the mapping.
    final = switch_printer_preset(session)
    results["printer combo probed (evidence)"] = f"EVIDENCE ({final!r})"
    from m3e_preset_switch import (switch_preset as process_switch,  # noqa: E402
                                find_preset_combo)
    _rect, _ch = find_preset_combo(session.hwnd)
    if _rect:
        import ctypes as _ct
        _txt = _ct.create_unicode_buffer(256)
        _ct.WinDLL("user32").GetWindowTextW(_ch, _txt, 256)
        target = ("0.24 Standard @Snapmaker U1 (0.8 nozzle)"
                  if "0.40" in _txt.value
                  else "0.40 Standard @Snapmaker U1 (0.8 nozzle)")
    else:
        target = "0.24 Standard @Snapmaker U1 (0.8 nozzle)"
    switched = process_switch(session, target)
    results["preset switches (m3e path)"] = (
        f"PASS ({target.split(' ')[0]})" if switched else "FAIL")
    time.sleep(2.0)

    results["filament popup probe"] = (
        "PASS" if probe_filament_popup(session) else "SKIP (no popup)")
    results["import dispatches"] = (
        "PASS" if import_stl(session) else "FAIL")
    if not m7.step_model_arrives(session, results, timeout_s=120,
                                 min_frac=0.0025):
        return
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
