#!/usr/bin/env python3
# m8d_purifier_gcode.py — 飞书基线用例 #113/#122/#126/#127/#128 (顶盖1.4.0
# 净化器保温/强冷 gcode, P0)。
#
# 源码事实: U1 机器模板 machine_start_gcode 按 chamber_cooling_mode 分支
# 写 SET_PURIFIER_MODE — 强冷 MODE=1 DESIRE_TEMP=42 ALARM_TEMP=45
# DELAY_OFF=0；保温 MODE=3 DESIRE_TEMP=45 (无 ALARM_TEMP)；弱冷 MODE=3
# DESIRE_TEMP=0。GCode.cpp:2722 推导: 低温耗材
# temperature_vitrification<=50 -> 强冷；>50 或 filament_is_high_temperature
# -> 不降级 (默认保温)。断言以 gcode 内 machine_start_gcode 回显为准
# (staged 模板与源码树版本不同, PITFALLS/BLACKBOX_CASES 09-17 基建事实2)。
#
# 09-19 重编（产品行为变更适配）: 09-16 build 的 Change Filament =
# 耗材槽合并（Plater.cpp:8404），对象级换槽不再可用；且 #122 步骤原文
# 就是"在耗材列中将 PLA 槽位的耗材直接修改/替换为 ABS"——黑盒等价原语 =
# 槽位预设切换 m8.switch_filament_preset（逐次实测 PASS）。
# 编排（cube 默认落槽1）:
#   A  槽1 -> 'Silk' (PLA vitr45)   -> export: MODE=1 + ALARM_TEMP=45
#      (#122 前态"已切片验证强冷" + #126 强冷侧证据)
#   B  槽1 -> 'ABS' (高温)          -> export: MODE=3 + DESIRE_TEMP=45
#      无 ALARM (#113/#122 后态/#126/#128)
#   C  槽1 -> 'PC' (无 PCTG)        -> export: 同保温分支 (#127)
#      staged 下拉无 PC 行时以 ABS-GF 替代并如实标注

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


def slice_and_params(session, results, key, path):
    g = ART / path
    g.unlink(missing_ok=True)
    if not m7.op_slice(session, results, key=key, export_to=g):
        return None
    data = g.read_bytes()
    used = m8.used_filaments(data)
    p = m8.purifier_params(data)
    print(f"{LOG} {key}: used={used} params={p}")
    return used, p


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
        # the Add-Primitive bed menu flakes under the demoted window;
        # op_add_primitive verifies the chromatic delta, retry is safe
        if not m7.op_add_primitive(session, "cube"):
            print(f"{LOG} cube add retry (bed-menu flake)")
            time.sleep(1.5)
            if not m7.op_add_primitive(session, "cube"):
                results["cube added"] = "FAIL"
                return m7.m7_verdict(results)
        results["cube added"] = "PASS"
        time.sleep(1.0)

        # --- A: PLA -> strong cool ----------------------------------------
        final = m8.switch_filament_preset(session, slot=1,
                                          target_substr="Silk")
        print(f"{LOG} slot1 -> {final!r}")
        results["slot1 -> PLA Silk"] = (
            "PASS" if "Silk" in final else f"FAIL ({final!r})")
        if "Silk" not in final:
            return m7.m7_verdict(results)
        time.sleep(1.5)
        out = slice_and_params(session, results, "A slice (PLA)",
                               "m8d_pla.gcode")
        if not out:
            return m7.m7_verdict(results)
        used, pa = out
        results["A job on slot1"] = (
            "PASS" if used == [1] else f"FAIL (used={used})")
        results["#122 pre: PLA strong MODE=1"] = (
            "PASS" if pa and pa["MODE"] == "1" and pa["ALARM_TEMP"] == "45"
            else f"FAIL ({pa})")
        # the staged strong-cool branch writes NO DELAY_OFF (template echo
        # in the gcode header) — require the other four params only
        results["#126 strong-side params written"] = (
            "PASS" if pa and pa["MODE"] == "1" and pa["DESIRE_TEMP"]
            is not None and pa["ALARM_TEMP"] is not None
            and pa["FAN_SPEED"] is not None else f"FAIL ({pa})")

        # --- B: ABS -> keep-warm -------------------------------------------
        # chamber_cooling_mode derivation (libslic3r/GCode.cpp:2726): the
        # loop SKIPS filament_is_high_temperature presets, so an all-
        # high-temp job keeps mode 0 = keep-warm. 'Bambu ABS' is high=0
        # vitr in (50,70] -> weak; 'Generic ABS' is high=1 -> keep-warm.
        final_b = m8.switch_filament_preset(session, slot=1,
                                            target_substr="Generic ABS",
                                            seek="Generic ABS")
        print(f"{LOG} slot1 -> {final_b!r}")
        results["slot1 -> ABS"] = (
            "PASS" if "ABS" in final_b else f"FAIL ({final_b!r})")
        if "ABS" not in final_b:
            return m7.m7_verdict(results)
        time.sleep(2.0)
        out = slice_and_params(session, results, "B slice (ABS)",
                               "m8d_abs.gcode")
        if not out:
            return m7.m7_verdict(results)
        used, pb = out
        results["B job on slot1"] = (
            "PASS" if used == [1] else f"FAIL (used={used})")
        results["#113/#122 MODE flips 1->3"] = (
            "PASS" if (pa and pb and pa["MODE"] == "1" and pb["MODE"] == "3")
            else f"FAIL (A={pa and pa['MODE']}, B={pb and pb['MODE']})")
        # #113 expects the keep-warm branch (DESIRE_TEMP=45). Measured
        # 09-20: the 09-16 staged template branches on filament[0] only and
        # every reachable dropdown preset (OrcaFilamentLibrary) carries
        # filament_is_high_temperature=0, so ABS lands on the WEAK branch
        # (DESIRE_TEMP=0). The keep-warm branch is unreachable black-box —
        # recorded as a build-vs-record gap for product confirmation.
        results["#113 keep-warm DESIRE_TEMP=45"] = (
            "PASS" if pb and pb["DESIRE_TEMP"] == "45" else
            "FAIL (build gap: ABS -> weak DESIRE_TEMP="
            f"{pb and pb['DESIRE_TEMP']}; keep-warm 45 branch "
            "unreachable, dropdown presets all high_temp=0)")
        results["#113 DELAY_OFF present"] = (
            "PASS" if pb and pb["DELAY_OFF"] is not None
            else f"FAIL ({pb})")
        results["#113/#126 no ALARM_TEMP (keep-warm)"] = (
            "PASS" if pb and pb["ALARM_TEMP"] is None else f"FAIL ({pb})")
        results["#128 params complete"] = (
            "PASS" if pb and all(pb.get(k) is not None for k in
                                 ("MODE", "DESIRE_TEMP", "FAN_SPEED",
                                  "DELAY_OFF")) else f"FAIL ({pb})")

        # --- C: PC also classifies keep-warm (#127) ------------------------
        # 'Generic PC' is high=1 (keep-warm by the same derivation);
        # 'Bambu PC' is high=0 -> weak, not the branch #127 asks for
        final_c = m8.switch_filament_preset(session, slot=1,
                                            target_substr="Generic PC",
                                            excludes=("PCTG",),
                                            seek="Generic PC")
        print(f"{LOG} slot1 -> {final_c!r}")
        pc_ok = "PC" in final_c and "PCTG" not in final_c
        if pc_ok:
            results["slot1 -> PC"] = "PASS"
        else:
            # staged dropdown may lack a PC row — ABS-GF is the same
            # high-temp keep-warm family; label the substitute honestly
            final_c = m8.switch_filament_preset(session, slot=1,
                                                target_substr="ABS-GF")
            print(f"{LOG} PC unavailable, slot1 -> {final_c!r}")
            pc_ok = "ABS-GF" in final_c
            results["slot1 -> PC"] = (
                "PASS (ABS-GF proxy, no PC row in dropdown)"
                if pc_ok else f"FAIL ({final_c!r})")
        if pc_ok:
            time.sleep(2.0)
            out = slice_and_params(session, results, "C slice (PC/high-T)",
                                   "m8d_pc.gcode")
            if out:
                _used, pc = out
                results["#127 PC keep-warm"] = (
                    "PASS" if pc and pc["MODE"] == "3"
                    and pc["DESIRE_TEMP"] == "45" else
                    "FAIL (build gap: PC -> weak DESIRE_TEMP="
                    f"{pc and pc['DESIRE_TEMP']}; same unreachable "
                    "keep-warm branch as #113)")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
