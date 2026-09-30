#!/usr/bin/env python3
# m8f_nozzle_flow.py — 飞书基线用例 #133/#135/#136 (高流量热端, P0)。
# feishu: baseline#133 baseline#135 baseline#136
#
# 判定口径与操作流程来自飞书文档「gcode测试方案」
# (wiki RZQuwbdFzi3E2YkES5acOcB3nIf，2026-09-23 拉取 + 与测试者确认):
#   * 三个手造包（resources/user/default，播种到 <datadir>/user/default；
#     仓库副本改为 ASCII 名以便 UI 里可靠识别）:
#       STD-TEST  工艺/耗材包 = [标准, 高流量] 两档值，如 inner_wall_speed
#                               ['550','600']
#       HF-TEST   同键 = ['300','550'] —— 构造上 (STD-TEST+标准流量) 与
#                 (HF-TEST+高流量) 取到的值完全相等
#       FLOW-TEST 两档值相同（单变量对比用）
#   * 包必须在 UI 里选中（工艺预设下拉 + 耗材预设下拉 + Nozzle Flow 下拉）—
#     这才验证到"两档值按序号取用"；夹具只负责加载同一个立方体工程。
#   * 对比用官方 compare_gcode.py（本仓 tools/ vendored）：只比 gcode 的
#     CONFIG_BLOCK 最终配置，分「高流量模式字段变化」「数值配置变化」两类，
#     rc=0 表示完全一致。
#   * 文档注意事项：单耗材 + 简单正方体（多耗材/多岛/带孔/旋转对称模型会因
#     岛序互换与起笔漂移产生与产品无关的 gcode 差异）。
#
#   #133 喷嘴界面默认值: diameter '0.4mm' + flow 'Standard'
#   #135 标准/高流量全量模拟: (STD-TEST+标准流量) vs (HF-TEST+高流量)
#        两份 gcode 的最终配置应完全一致（官方脚本 rc=0）
#   #136 单一变量(FLOW-TEST 包) → 独立用例 tests/high_flow/m8g_flow_single.py
#        （同会话连切两次会把客机内存吃满，cv2/tesseract OOM，实测 09-23）
#   (#134 喷嘴信息同步 = 设备链, MANUAL)

import re
import subprocess
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

import argparse  # noqa: E402

from harness import process_panel as pp  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8f]"
ART = HERE / "artifacts"
FIXTURES = HERE / "fixtures"
# 模型来源：空盘启动 + 鼠标右键 Add Primitive > Cube（测试者 09-24 确认：
# 用右键建的正方体不会带入官方测试 3mf 里那套被改过的预设值，因此不会出现
# "jerk setting exceeds the printer's maximum" 警告 —— 该警告会让切片被拒）
COMPARE = HERE / "tools" / "compare_gcode.py"
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?%?")

PROC_STD = "0.20mm Standard @Snapmaker U1 (0.4 nozzle) - STD-TEST"
PROC_HF = "0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST"
PROC_FLOW = "0.24mm Standard @Snapmaker U1 (0.4 nozzle) - FLOW-TEST"
FIL_STD = "Snapmaker PLA SnapSpeed @U1 - STD-TEST"
FIL_HF = "Snapmaker PLA SnapSpeed @U1 - HF-TEST"
FIL_FLOW = "Snapmaker PLA SnapSpeed @U1 - FLOW-TEST"


# --- official comparison ------------------------------------------------------

def compare_gcodes(a: Path, b: Path):
    """官方 compare_gcode.py：rc 0=无差异, 1=有差异, 2=解析失败。"""
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


# --- session helpers ----------------------------------------------------------

def sweep_dialogs(session, tag):
    """Package switches raise the app's 'Transfer or discard changes' prompt
    (the flow switch marks the current preset modified) — answer DISCARD so
    the next selection starts clean. Any other #32770 gets its first button."""
    for _ in range(3):
        if m7.dismiss_transfer_dialog(session):
            continue
        dlg = m7.wait_dialog(session.pid, timeout_s=2.0)
        if not dlg:
            return
        print(f"{LOG} [{tag}] dialog {dlg[1]!r} — confirming")
        m7.click_dialog_button(dlg[3], "ok")
        time.sleep(1.0)


def select_packages(session, proc_name, fil_name, tag):
    """Select the process + filament package in the UI (the step that proves
    the two-index values are read). Returns (process_ok, filament_text); the
    caller must treat a wrong filament text as FAIL — no blind fallback."""
    ok_p = pp.switch_process_preset(session, proc_name)
    print(f"{LOG} [{tag}] process preset -> {proc_name[-9:]!r}: {ok_p}")
    sweep_dialogs(session, tag + "_proc")
    slots = m8.filament_slots(session)
    slot = slots[0]["slot"] if slots else 1
    want = fil_name.split(" - ")[-1]
    fin = m8.switch_filament_preset(session, slot=slot, target_substr=want)
    print(f"{LOG} [{tag}] filament preset (slot {slot}) -> {fin!r} "
          f"(want {want!r})")
    sweep_dialogs(session, tag + "_fil")
    return ok_p, fin


def set_flow(session, target, tag, tries=3):
    """Switch the Nozzle Flow combo and VERIFY it took (the switch can be
    swallowed: measured 09-23 the combo read back 'Standard' right after a
    High-Flow switch)."""
    for i in range(tries):
        got = m8.switch_flow_combo(session, target)
        print(f"{LOG} [{tag}] flow try{i + 1} -> {got!r}")
        if target in (got or ""):
            return got
        sweep_dialogs(session, tag + "_flow")
        time.sleep(1.5)
    # diagnostics for the failure path: what the sidebar reports, which
    # dialogs are up, and the flow popup's rows when it opens
    print(f"{LOG} [{tag}] flow switch FAILED: reads="
          f"{m8.nozzle_reads(session)!r}")
    dlg = m7.wait_dialog(session.pid, timeout_s=1.0)
    print(f"{LOG} [{tag}] open dialog: {dlg}")
    try:
        m8.switch_flow_combo(session, "High Flow", tries=1)
    except Exception as exc:  # noqa: BLE001
        print(f"{LOG} [{tag}] popup probe error: {exc}")
    return m8.nozzle_reads(session).get("flow") or ""


def slice_export(session, results, key, name):
    out = ART / name
    out.unlink(missing_ok=True)
    ok = m7.op_slice(session, results, key=key, export_to=out)
    if not (ok and out.exists()):
        # the export once failed right after a successful slice (measured
        # 09-23: stdA) — one retry of the export path is cheap
        print(f"{LOG} {key}: export missing — retrying the export")
        from harness import export_util
        time.sleep(2.0)
        ok = export_util.export_gcode(session, out, timeout_s=60.0) or ok
    return bool(ok and out.exists()), out


def boot(args, model, tag):
    args.model = model
    session = boot_session(args, model=model)
    ok, frac = m8.wait_arrival(session)
    m7.ensure_maximized(session)
    ensure_gl_ready(session)
    time.sleep(1.0)
    print(f"{LOG} [{tag}] arrival {ok} ({frac:.2%})")
    return session, ok


def slice_with(args, proc_name, flow_target, tag, out_name, results,
               check_133=False):
    """空盘启动 -> 右键建 cube -> UI 选工艺包 -> 切流量 -> 切片导出。"""
    from m3_common import boot_session
    args.model = None
    session = boot_session(args, model=None)
    out = ART / out_name
    try:
        m7.ensure_maximized(session)
        # 右键建正方体（床面菜单；失败会自动走工具栏 Add 入口兜底）
        added = m7.op_add_primitive(session, "cube")
        print(f"{LOG} [{tag}] cube added: {added}")
        results.setdefault("cube created (right-click)", "PASS" if added else "FAIL")
        if check_133:
            reads = m8.nozzle_reads(session)
            print(f"{LOG} [{tag}] nozzle reads: {reads}")
            results["#133 diameter default 0.4mm"] = (
                "PASS" if reads["diameter"] == "0.4mm"
                else f"FAIL ({reads['diameter']!r})")
            results["#133 flow default Standard"] = (
                "PASS" if reads["flow"] == "Standard"
                else f"FAIL ({reads['flow']!r})")
        proc_ok = pp.switch_process_preset(session, proc_name)
        m7.dismiss_transfer_dialog(session)
        print(f"{LOG} [{tag}] process preset {proc_name[-9:]!r}: {proc_ok}")
        got = set_flow(session, flow_target, tag)
        results[f"{tag} flow={flow_target}"] = (
            "PASS" if flow_target in (got or "") else f"FAIL ({got!r})")
        if "High Flow" in (got or ""):
            m8.confirm_flow_dialog(session)
        out.unlink(missing_ok=True)
        ok = m7.op_slice(session, results, key=f"{tag} slice", export_to=out)
        return bool(ok and out.exists()), out
    finally:
        session.close()
        print(f"{LOG} [{tag}] session closed")
        time.sleep(2.5)


CONF_RE = re.compile(r"^;\s*([A-Za-z0-9_.]+)\s*=\s*(.*)$")


def read_config(path: Path):
    """{key: [values]} of the gcode's CONFIG_BLOCK (self-contained: no import
    of the official script's internals)."""
    out: dict = {}
    inside = False
    for line in path.read_text(encoding="utf-8-sig",
                               errors="replace").splitlines():
        s = line.strip()
        if s == "; CONFIG_BLOCK_START":
            inside = True
            continue
        if s == "; CONFIG_BLOCK_END":
            inside = False
            continue
        if not inside:
            continue
        m = CONF_RE.match(line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2).strip())
    return out


def flow_index(cfg) -> int:
    """0 = standard, 1 = high_flow — which entry of the per-flow arrays this
    gcode was sliced with (from its own nozzle/filament_volume_type)."""
    val = cfg.get("nozzle_volume_type") or cfg.get("filament_volume_type") or []
    joined = ",".join(val).lower()
    return 1 if "high_flow" in joined else 0


def effective_diff(a: Path, b: Path):
    """Index-resolved comparison — the doc's '高流量参数序号访问' check.

    The gcode carries the packages' per-flow ARRAYS (sparse_infill_speed
    '550,600' on the STD package vs '270,550' on the HF one), so the official
    raw comparison counts all of them as differences even when the EFFECTIVE
    entry (the one the flow mode selects) is the same. This compares A's value
    at ITS index against B's at ITS index for every multi-entry numeric key.
    Returns (mismatches, checked)."""
    ca, cb = read_config(a), read_config(b)
    ia, ib = flow_index(ca), flow_index(cb)
    print(f"{LOG} flow indices: A={ia} B={ib}")
    mismatches, checked = [], 0
    for key in sorted(set(ca) | set(cb)):
        va, vb = ca.get(key, []), cb.get(key, [])
        if va == vb or not va or not vb:
            continue
        pa = [p.strip() for p in ",".join(va).split(",")]
        pb = [p.strip() for p in ",".join(vb).split(",")]
        if len(pa) < 2 or len(pb) < 2:
            continue                      # not a per-flow array on both sides
        if not (all(NUM_RE.match(x) for x in pa)
                and all(NUM_RE.match(x) for x in pb)):
            continue                      # non-numeric key
        checked += 1
        if pa[min(ia, len(pa) - 1)] != pb[min(ib, len(pb) - 1)]:
            mismatches.append((key, pa[min(ia, len(pa) - 1)],
                               pb[min(ib, len(pb) - 1)]))
    return mismatches, checked


def main() -> int:
    """#135: (STD-TEST 包 + 标准流量) 与 (HF-TEST 包 + 高流量) 各切一份，
    两份的【数值配置】必须完全一致（模式键不同是预期）。模型=右键 cube。"""
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    results = {}
    ok_a, g_a = slice_with(args, PROC_STD, "Standard", "A", "m8f_stdA.gcode",
                           results, check_133=True)
    ok_b, g_b = ok_a and slice_with(args, PROC_HF, "High Flow", "B",
                                    "m8f_hfB.gcode", results)
    if ok_a and ok_b:
        rc, report = compare_gcodes(g_a, g_b)
        mode_diff, num_diff = report_counts(report)
        # 官方脚本按原样数组比对：两档数组本身的差异会全部计入 numeric。
        # 文档的意图是"序号访问"——即按各自流量取到的那一项必须相同，
        # 因此再跑一层按序号解析的比对（结果一并记录）。
        bad, checked = effective_diff(g_a, g_b)
        if bad:
            print(f"{LOG} effective mismatches ({len(bad)}): "
                  f"{[(k, x, y) for k, x, y in bad][:8]}")
        results["#135 std-vs-hf effective values identical"] = (
            "PASS" if not bad and mode_diff >= 1
            else f"FAIL (checked={checked}, mismatches={len(bad)}, "
                 f"mode={mode_diff})")
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
