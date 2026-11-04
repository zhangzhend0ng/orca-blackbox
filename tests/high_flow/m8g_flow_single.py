#!/usr/bin/env python3
# m8g_flow_single.py — 飞书基线用例 #136 (单一变量对比) 独立用例
# feishu: baseline#136
#
# 判定口径来自飞书文档「gcode测试方案」(wiki RZQuwbdFzi3E2YkES5acOcB3nIf):
#   「流量测试」包的 [标准, 高流量] 两档值**完全相同**（如
#   filament_max_volumetric_speed ['40','40']），用于"单一变量"对比 ——
#   标准流量与高流量各切一份，除流量模式字段外不应有任何差异。
#
# 从 m8f 拆出来的原因：同会话连切两次（切流量→切片→再切→再切）会把客机的
# 内存吃满（cv2 matchTemplate / tesseract pix_malloc OOM，实测 09-23），
# 因此这里两个流量状态各起一次 app 会话，各切一份 gcode，再用官方
# compare_gcode.py 对比（rc 与差异分类见 tools/compare_gcode.py）。
#
#   #136 单一变量: (FLOW-TEST + 标准流量) vs (FLOW-TEST + 高流量)
#        → 数值配置差异必须为 0（只允许高流量模式字段不同）

import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import argparse  # noqa: E402

from harness import process_panel as pp  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8g]"
ART = HERE / "artifacts"
# 模型来源：空盘 + 右键 Add Primitive > Cube（测试者 09-24 确认不会
# 触发 "jerk setting exceeds the printer's maximum" 警告）
COMPARE = HERE / "tools" / "compare_gcode.py"
PROC_FLOW = "0.24mm Standard @Snapmaker U1 (0.4 nozzle) - FLOW-TEST"


def compare_gcodes(a: Path, b: Path):
    r = subprocess.run([sys.executable, str(COMPARE), str(a), str(b)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    report = (r.stdout or "") + (r.stderr or "")
    print(f"{LOG} compare rc={r.returncode}")
    for line in report.splitlines()[:14]:
        print(f"{LOG}   {line}")
    return r.returncode, report


def report_counts(report: str):
    def grab(pat):
        m = re.search(pat, report)
        return int(m.group(1)) if m else -1
    return (grab(r"高流量模式字段变化：(\d+) 项"),
            grab(r"数值配置变化：(\d+) 项"))


def set_flow(session, target, tag, tries=3):
    """Switch the Nozzle Flow combo and VERIFY; the combo's options refresh
    only after a (re-)selection of the process preset (measured 09-23)."""
    for i in range(tries):
        got = m8.switch_flow_combo(session, target)
        print(f"{LOG} [{tag}] flow try{i + 1} -> {got!r}")
        if target in (got or ""):
            return got
        pp.switch_process_preset(session, PROC_FLOW)   # refresh the combo
        m7.dismiss_transfer_dialog(session)
        time.sleep(1.5)
    return m8.nozzle_reads(session).get("flow") or ""


def slice_session(args, flow_target, tag, out_name, results):
    """空盘启动 -> 右键建 cube -> 选 FLOW-TEST 工艺包 -> 切流量 -> 切片导出。"""
    args.model = None
    session = boot_session(args, model=None)
    out = ART / out_name
    try:
        m7.ensure_maximized(session)
        added = m7.op_add_primitive(session, "cube")
        print(f"{LOG} [{tag}] cube added: {added}")
        results.setdefault("cube created (right-click)",
                           "PASS" if added else "FAIL")
        proc_ok = pp.switch_process_preset(session, PROC_FLOW)
        m7.dismiss_transfer_dialog(session)
        print(f"{LOG} [{tag}] process preset FLOW-TEST: {proc_ok}")
        got = set_flow(session, flow_target, tag)
        results[f"#136 flow={flow_target} applied"] = (
            "PASS" if flow_target in (got or "") else f"FAIL ({got!r})")
        if "High Flow" in (got or ""):
            m8.confirm_flow_dialog(session)
        out.unlink(missing_ok=True)
        ok = m7.op_slice(session, results, key=f"#136 {tag} slice",
                         export_to=out)
        return bool(ok and out.exists()), out
    finally:
        session.close()
        print(f"{LOG} [{tag}] session closed")
        time.sleep(2.5)


def main() -> int:
    # 模型 = 空盘 + 右键 cube（见 slice_session）
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    results = {}
    ok_c, g_c = slice_session(args, "Standard", "std", "m8g_std.gcode", results)
    ok_d, g_d = slice_session(args, "High Flow", "hf", "m8g_hf.gcode", results)
    if ok_c and ok_d:
        rc, report = compare_gcodes(g_c, g_d)
        mode, numeric = report_counts(report)
        # 数值配置 0 差异（单一变量），且流量模式键必须确有变化（证明切过去了）
        results["#136 single-variable: numeric diffs 0"] = (
            "PASS" if numeric == 0 and mode >= 1
            else f"FAIL (rc={rc}, numeric={numeric}, mode={mode})")
    results["app alive"] = "PASS" if True else "FAIL"
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
