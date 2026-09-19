#!/usr/bin/env python3
# m8d_purifier_gcode.py — 飞书基线用例 #113/#122/#126/#127/#128 (顶盖1.4.0
# 净化器保温/强冷 gcode, P0)。
#
# 源码事实: U1 机器模板 machine_start_gcode 按 chamber_cooling_mode 分支
# 写 SET_PURIFIER_MODE — 强冷 MODE=1 DESIRE_TEMP=42 ALARM_TEMP=45
# DELAY_OFF=0；保温 MODE=3 DESIRE_TEMP=45 (无 ALARM_TEMP) DELAY_OFF=600；
# 弱冷 MODE=3 DESIRE_TEMP=0。GCode.cpp:2722 推导: 低温耗材
# temperature_vitrification<=50 -> 强冷；>50 或 filament_is_high_temperature
# -> 不降级 (默认保温)。
#
# 黑盒路径 (mixed 夹具): 清场 -> cube -> Change Filament -> PLA Silk 槽
# (vitr=45 -> 强冷) -> slice+export A: MODE=1 + ALARM_TEMP=45
# (#122 前态) -> 槽2 combo -> Generic ABS (high_temp=1) -> slice+export B:
# MODE=3 DESIRE_TEMP=45 无 ALARM (#113/#122 后态/#126/#128)
# -> 槽2 -> Generic PC -> slice+export C: 同保温分支 (#127)。

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8d]"
ART = HERE / "artifacts"


def add_cube_on_pla_slot(session, results):
    if not m7.step_delete_all(session, results):
        return False
    if not m7.op_add_primitive(session, "cube"):
        results["cube added"] = "FAIL"
        return False
    results["cube added"] = "PASS"
    time.sleep(0.8)
    if not m7.select_model(session):
        results["cube selected"] = "FAIL"
        return False
    menu = m7.open_context_menu(session, where="model")
    if not menu:
        results["context menu"] = "FAIL"
        return False
    hwnd, hmenu = menu
    got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                            nested=True)
    if not got:
        m7.dismiss_menus(session)
        results["change filament"] = "FAIL"
        return False
    _i, (shwnd, shmenu) = got
    rows = m7.list_menu(shmenu)
    print(f"{LOG} filament rows: {[l for _i, l in rows]}")
    hit = m7.send_menu_command(session, shmenu, "Silk", confirm_ok=True)  # slot 2 (PLA)
    m7.dismiss_menus(session)
    return bool(hit)


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        ensure_gl_ready(session)

        if not add_cube_on_pla_slot(session, results):
            return m7.m7_verdict(results)

        g_a = ART / "m8d_pla.gcode"
        g_a.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
        if not m7.op_slice(session, results, key="PLA slice (strong pre)",
                           export_to=g_a):
            return m7.m7_verdict(results)
        pa = m8.purifier_params(g_a.read_bytes())
        used = m8.used_filaments(g_a.read_bytes())
        print(f"{LOG} A params={pa} used={used}")
        if pa and pa["DESIRE_TEMP"] == "0":
            # cube stayed on the PETG slot: redo the remap, re-slice
            print(f"{LOG} weak params -> remap retry")
            if m7.select_model(session):
                menu = m7.open_context_menu(session, where="model")
                if menu:
                    hwnd, hmenu = menu
                    got = m7.click_menu_row(session, hwnd, hmenu,
                                            "change filament", nested=True)
                    if got:
                        _i, (shwnd, shmenu) = got
                        m7.click_menu_row(session, shwnd, shmenu, "Silk")
                        time.sleep(1.5)
                    m7.dismiss_menus(session)
            g_a.unlink(missing_ok=True)
            if m7.op_slice(session, results, key="PLA slice (remap retry)",
                           export_to=g_a):
                pa = m8.purifier_params(g_a.read_bytes())
                used = m8.used_filaments(g_a.read_bytes())
                print(f"{LOG} A2 params={pa} used={used}")
        results["#122 pre: PLA strong MODE=1"] = (
            "PASS" if pa and pa["MODE"] == "1" and pa["ALARM_TEMP"] == "45"
            else f"FAIL ({pa})")

        # --- switch slot 2 preset to ABS -> keep-warm ---------------------
        final = m8.switch_filament_preset(session, slot=2,
                                          target_substr="ABS")
        results["slot2 -> Generic ABS"] = (
            "PASS" if "ABS" in final else f"FAIL ({final!r})")
        if "ABS" not in final:
            return m7.m7_verdict(results)
        time.sleep(2.0)

        g_b = ART / "m8d_abs.gcode"
        g_b.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
        if not m7.op_slice(session, results, key="ABS slice (keep-warm)",
                           export_to=g_b):
            return m7.m7_verdict(results)
        pb = m8.purifier_params(g_b.read_bytes())
        print(f"{LOG} B params={pb}")
        results["#113/#122 MODE flips 1->3"] = (
            "PASS" if (pa and pb and pa["MODE"] == "1" and pb["MODE"] == "3")
            else f"FAIL (A={pa and pa['MODE']}, B={pb and pb['MODE']})")
        results["#113 keep-warm DESIRE_TEMP=45"] = (
            "PASS" if pb and pb["DESIRE_TEMP"] == "45" else f"FAIL ({pb})")
        results["#113 no ALARM_TEMP"] = (
            "PASS" if pb and pb["ALARM_TEMP"] is None else f"FAIL ({pb})")
        results["#128 params complete"] = (
            "PASS" if pb and all(pb.get(k) is not None for k in
                                 ("MODE", "DESIRE_TEMP", "FAN_SPEED",
                                  "DELAY_OFF")) else f"FAIL ({pb})")

        # --- #127: PC also classifies keep-warm ----------------------------
        final_pc = m8.switch_filament_preset(session, slot=2,
                                             target_substr="ABS-GF")
        results["slot2 -> Generic PC"] = (
            "PASS" if "PC" in final_pc and "ABS" not in final_pc
            else f"FAIL ({final_pc!r})")
        if "PC" in final_pc:
            time.sleep(2.0)
            g_c = ART / "m8d_pc.gcode"
            g_c.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
            if m7.op_slice(session, results, key="PC slice (keep-warm)",
                           export_to=g_c):
                pc = m8.purifier_params(g_c.read_bytes())
                print(f"{LOG} C params={pc}")
                results["#127 PC keep-warm"] = (
                    "PASS" if pc and pc["MODE"] == "3"
                    and pc["DESIRE_TEMP"] == "45" else f"FAIL ({pc})")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
