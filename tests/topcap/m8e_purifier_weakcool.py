#!/usr/bin/env python3
# m8e_purifier_weakcool.py — 飞书基线用例 #114/#129 (顶盖1.4.0 弱冷 gcode, P0)。
# feishu: baseline#114 baseline#129
#
# 源码事实: 弱冷分支 -> SET_PURIFIER_MODE MODE=3 DESIRE_TEMP=0
# FAN_SPEED=0.6 DELAY_OFF=600 (无 ALARM_TEMP) — 值以生效机器模板为准。
# 2026-09-21 实测: app 发行包自带模板 (2.3.6 与 2.4.0 相同) 的弱冷分支写
# 600, 而仓库 vendor 的 resources/ 副本 (20260128) 仍写 180; preset 种子
# 取自 app 的 resources\profiles, 故 gcode 实际出 600 —— 基线与断言均按
# 600 (人工判定)。模板按
# filament_is_high_temperature[0]/temperature_vitrification[0]
# 单耗材分支。弱冷条件 = 低温耗材且 vitrification > 50
# (Generic PETG @U1 vitr=70)。
#
# 黑盒路径 (mixed 夹具): 清场 -> cube (默认槽1 = Generic PETG) ->
# slice+export -> 断言 MODE=3 + DESIRE_TEMP=0 + 无 ALARM_TEMP +
# DELAY_OFF=600。cube 若不在 PETG 槽 (读 gcode filament used 校验),
# Change Filament -> 槽1 后重切。

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8e]"
ART = HERE / "artifacts"


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

        if not m7.step_delete_all(session, results):
            return m7.m7_verdict(results)
        if not m7.op_add_primitive(session, "cube"):
            results["cube added"] = "FAIL"
            return m7.m7_verdict(results)
        results["cube added"] = "PASS"
        time.sleep(1.0)

        g = ART / "m8e_petg.gcode"
        g.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
        if not m7.op_slice(session, results, key="PETG slice",
                           export_to=g):
            return m7.m7_verdict(results)
        data = g.read_bytes()
        used = m8.used_filaments(data)
        p = m8.purifier_params(data)
        print(f"{LOG} used={used} params={p}")

        if used and used[0] != 1:
            # cube landed on a PLA slot — move it to PETG slot 1, re-slice
            print(f"{LOG} cube on slot {used[0]}, moving to slot 1 (PETG)")
            if not m7.select_model(session):
                results["cube selected"] = "FAIL"
                return m7.m7_verdict(results)
            menu = m7.open_context_menu(session, where="model")
            if menu:
                hwnd, hmenu = menu
                got = m7.click_menu_row(session, hwnd, hmenu,
                                        "change filament", nested=True)
                if got:
                    _i, (shwnd, shmenu) = got
                    rows = m7.list_menu(shmenu)
                    print(f"{LOG} filament rows: {[l for _i, l in rows]}")
                    m7.click_menu_row(session, shwnd, shmenu, "PETG")
                    time.sleep(1.5)
                m7.dismiss_menus(session)
            g = ART / "m8e_petg2.gcode"
            g.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
            if not m7.op_slice(session, results, key="PETG slice (retry)",
                               export_to=g):
                return m7.m7_verdict(results)
            data = g.read_bytes()
            used = m8.used_filaments(data)
            p = m8.purifier_params(data)
            print(f"{LOG} retry used={used} params={p}")

        results["PETG slot used"] = (
            "PASS" if used and used[0] == 1 else f"FAIL (used={used})")
        results["#114/#129 weak MODE=3"] = (
            "PASS" if p and p["MODE"] == "3" else f"FAIL ({p})")
        results["#114 DESIRE_TEMP=0"] = (
            "PASS" if p and p["DESIRE_TEMP"] == "0" else f"FAIL ({p})")
        results["#114/#129 no ALARM_TEMP"] = (
            "PASS" if p and p["ALARM_TEMP"] is None else f"FAIL ({p})")
        results["#129 DELAY_OFF=600 (app template)"] = (
            "PASS" if p and p["DELAY_OFF"] == "600" else f"FAIL ({p})")
        results["#129 params complete"] = (
            "PASS" if p and p["FAN_SPEED"] is not None else f"FAIL ({p})")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
