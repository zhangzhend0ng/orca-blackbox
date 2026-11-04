"""cases.py — the single source of truth for runnable black-box cases.

Pure data, no batch logic. Every batch entry point (run_regression.sh,
runner/hv_go.ps1, mcp_server.py run_case/list_cases) consumes THIS dict —
never keep a second hardcoded list anywhere.

Rules:
- key = script stem; keys are stable IDs, NEVER rename (push_verify.py /
  zlog.ps1 / Feishu tables index history by case name).
- add a case = add one entry (+ the script); disable = enabled: False
  (soft-off — logs/history stay intact). Do not physically delete entries.
- suite: "regression" = the nightly suite; "smoke" = m0/m1/m2 engine/chain
  checks; None = registered & runnable via MCP but not in any default batch
  (m3a-m3i early business-path cases, m1b engine experiment).
- tier: coverage tier from BLACKBOX_CASES.md (A strong / B weak / C
  not-blackbox-testable). "TBD" = not yet registered in BLACKBOX_CASES.md
  (the m5 series — its pitfalls live in PITFALLS_0901.md instead).
- summary: NOT stored — extracted live from the script's line-2 header
  comment ("# <stem>.py — ..."), so the script stays the single home for
  it (sync enforced by tools/check_registry.py).
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _r(milestone: str, tier: str, **extra) -> dict:
    """Shorthand for an enabled regression-suite entry (file filled below).
    known_limitation=True = documented PARTIAL/降级 (BLACKBOX_CASES.md) — the
    pytest shell maps it to xfail(strict=False)."""
    d = {"file": None, "milestone": milestone, "tier": tier,
         "suite": "regression", "enabled": True}
    d.update(extra)
    return d


def _o(milestone: str, tier: str, **extra) -> dict:
    """Shorthand for an enabled but not-in-any-suite entry (file filled
    below). Extra kwargs mirror _r (e.g. known_limitation)."""
    d = {"file": None, "milestone": milestone, "tier": tier,
         "suite": None, "enabled": True}
    d.update(extra)
    return d


CASES: dict[str, dict] = {
    # --- smoke (engine / chain checks) --------------------------------------
    # file= is filled in below from the on-disk layout: cases live in
    # tests/<group>/ keyed by the Feishu baseline table's 二级分类 (see
    # GROUP_LABELS); unclassified engine/chain cases live in tests/engine/.
    "m0_boot_check": {
        "milestone": "m0", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m0_anchor_health": {
        "milestone": "m0", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m1_minimal_loop": {
        "milestone": "m1", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m1b_maa": {
        "milestone": "m1", "tier": "A",
        "suite": None, "enabled": False,  # engine experiment (m0: MaaFw rejected)
    },
    "m2_slice_chain": {
        "milestone": "m2", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    # --- m3a-m3i: early business-path cases (runnable, not in the suite) -----
    "m3a_empty_slice": _o("m3", "A"),
    "m3b_delete_scene": _o("m3", "A"),
    "m3c_corrupt_3mf": _o("m3", "A"),
    "m3d_param_reslice": _o("m3", "A"),
    "m3e_preset_switch": _o("m3", "A"),
    "m3f_multi_plate": _o("m3", "A"),
    "m3g_export_3mf": _o("m3", "A"),
    "m3h_undo_redo": _o("m3", "A"),
    "m3i_view_menu": _o("m3", "A"),
    # --- regression suite: mixing (m3j-m4j) ----------------------------------
    "m3j_mixing_entry": _r("m3", "A"),
    "m3k_mixing_match": _r("m3", "A"),
    "m3l_mixing_delta": _r("m3", "A"),
    "m3m_mixing_filaments": _r("m3", "A"),
    "m3n_mixing_cancel": _r("m3", "A"),
    "m3o_mixing_nomodel": _r("m3", "A"),
    "m3p_mixing_persist": _r("m3", "A"),
    "m3q_mixing_view": _r("m3", "A"),
    "m3r_mixing_progress": _r("m3", "A"),
    "m3s_mixing_hover": _r("m3", "B", known_limitation=True),   # #8 hover tooltips — 降级/PARTIAL in BLACKBOX_CASES.md L85
    "m3t_mixing_add_ratio": _r("m3", "A"),
    "m3u_mixing_ratio_flow": _r("m3", "A"),
    "m3v_mixing_cycle_input": _r("m3", "A"),
    "m3w_mixing_cycle_flow": _r("m3", "A"),
    "m3x_mixing_match": _r("m3", "A"),
    "m3y_mixing_gradient": _r("m3", "A"),
    "m3z_mixing_compat": _r("m3", "A"),
    "m4a_mixing_gates": _r("m4", "A"),
    "m4b_batch_manual": _r("m4", "A"),
    "m4c_mixing_panel": _r("m4", "A"),
    "m4d_mixing_filops": _r("m4", "A"),
    "m4e_mixing_paint": _r("m4", "B", known_limitation=True),   # 表1#39 部分 — BLACKBOX_CASES.md L96
    "m4f_mixing_cap64": _r("m4", "A"),
    "m4g_mixing_sublayer": _r("m4", "A"),
    "m4h_mixing_templates": _r("m4", "A"),
    "m4i_mixing_slice": _r("m4", "A"),
    "m4j_mixing_samecolor": _r("m4", "A"),
    # --- regression suite: process params (m5a-m5h) --------------------------
    # tier TBD: not registered in BLACKBOX_CASES.md (pitfalls in PITFALLS_0901.md)
    "m5a_preset_cycle": _r("m5", "TBD"),
    "m5b_quality_params": _r("m5", "TBD"),
    "m5c_strength_infill": _r("m5", "TBD"),
    "m5d_support_enable": _r("m5", "TBD"),
    "m5e_combo_params": _r("m5", "TBD"),
    "m5f_negative_params": _r("m5", "TBD"),
    "m5g_preset_manage": _r("m5", "TBD"),
    "m5h_ironing_combos": _r("m5", "TBD"),
    # --- m6: transform via artifact (absorbed from white-box ab3b34adf5:459) --
    "m6a_transform_verify": _r("m6", "A"),
    # --- regression suite: main flow (m7, Feishu 测试用例 base tblLR8zYgwBuggDI
    #     — GUI业务 #7-#24 原子 + 主流程-模板 O/M 链; mapping in FEISHU_MAINFLOW.md)
    "m7a_boot_shutdown": _r("m7", "A"),
    "m7b_new_project": _r("m7", "A"),
    "m7c_import_stl": _r("m7", "A"),
    "m7d_import_corrupt": _r("m7", "A"),
    "m7e_rotate45": _r("m7", "A"),
    "m7f_scale120": _r("m7", "A"),
    "m7g_arrange": _r("m7", "A"),
    "m7h_context_delete": _r("m7", "A"),
    "m7i_add_primitive": _r("m7", "A"),
    "m7j_change_filament": _r("m7", "A"),
    "m7k_flush_options": _r("m7", "B", known_limitation=True),
    "m7t72": _r("m7", "A"),
    "m7t73": _r("m7", "A"),
    "m7t74": _r("m7", "A"),
    "m7t75": _r("m7", "B"),
    "m7t77": _r("m7", "B"),
    "m7t78": _r("m7", "B"),
    "m7t79": _r("m7", "B", known_limitation=True),
    "m7t80": _r("m7", "B"),
    "m7t81": _r("m7", "B", known_limitation=True),
    "m7t82": _r("m7", "B"),
    "m7t83": _r("m7", "A"),
    "m7t84": _r("m7", "B", known_limitation=True),
    "m7t86": _r("m7", "B"),
    "m7t87": _r("m7", "B"),
    "m7t88": _r("m7", "B"),
    "m7t89": _r("m7", "B"),
    "m7t109": _r("m7", "B", known_limitation=True),
    # --- m8 (2026-09-17 批次: 飞书基线用例 base EDUAbYWcbaL2HOsgFM1cXmBpn5f,
    #     Fit/官方颜色/温类门/净化器/高流量; 2026-09-21 用户确认 b/c/d/f 也挂进
    #     regression —— 此前 suite=None 导致"实现了却没人跑"，是覆盖盲区) ------
    "m8a_fit_view": _r("m8", "A"),                       # GREEN 09-17 客机
    "m8b_official_color": _r("m8", "A", known_limitation=True),
    "m8c_temp_mix_gate": _r("m8", "A", known_limitation=True),
    "m8d_purifier_gcode": _r("m8", "A", known_limitation=True),
    "m8e_purifier_weakcool": _r("m8", "A"),              # GREEN 09-17 客机
    "m8f_nozzle_flow": _r("m8", "A", known_limitation=True),
    # 2026-09-23 拆分: #136 单一变量对比独立成例（同会话连切两次会把客机
    # 内存吃满 → cv2/tesseract OOM；各流量状态一个会话后不再撞墙）
    "m8g_flow_single": _r("m8", "A"),
    # 2026-09-28 新增 #123（软化温度 → 温类归类 → GCode 更新）: 编辑器里
    # 'Softening temperature' 就是 temperature_vitrification；改它并走
    # "Save Filament as" 保存后重切，顶盖 SET_PURIFIER_MODE 的分支翻转
    # （vitr<=50 → 强冷 MODE=1，>50 → 保温 MODE=3）。
    "m8x_123_softening_temp": _r("m8", "A"),
    # 2026-09-29 新增 #137（三类配置带流量喷嘴标志的参数对比）: 面在**0.4 喷嘴机型的
    # 0.20mm Standard 工艺预设**里——工艺参数面板会出现 Standard / High Flow 两个 tab；
    # 喷嘴区那个 Flow 组合框不是这条用例的面（0.8 喷嘴机型上它不可交互）。
    "m8x_137_flow_param_tabs": _r("m8", "A"),
    # 2026-09-29 新增 #125（工艺全局辅材冲突，打开偏好后可切片）: 测试方口径
    # **主材 = 对象的耗材丝、辅材 = 涂色**；面在准备页耗材列 + 涂色 gizmo +
    # 切片按钮门禁 + Preferences 的 "Allow high/low temperature filament mixing"。
    "m8x_125_aux_mix_pref": _r("m8", "A"),
}


# 分组目录的 slug ↔ 飞书基线表「二级分类」中文名（目录命名用 slug，避开非 ASCII
# 路径在这条 PowerShell/PSDirect 工具链上的编码坑；中文名只作展示与映射）。
GROUP_LABELS: dict[str, str] = {
    "mixing_match": "混色匹配映射",
    "mixing": "混色功能",
    "mainflow": "主流程-用例",
    "gui": "GUI业务",
    "topcap": "顶盖1.4.0",
    "filament": "耗材管理",
    "fit_view": "一键还原视图",
    "high_flow": "高流量热端",
    "engine": "(无基线映射 / 引擎与链路用例)",
}

# 归属特例（迁移时人工判定，2026-09-21）：用例覆盖的飞书记录跨多个二级分类，或某条
# 映射只是 PARTIAL 交叉引用 —— 此时用例的实际分组与记录的分组不同，校验器
# （tools/check_feishu_map.py）把这些登记为已知例外。
GROUP_OVERRIDES: dict[str, str] = {
    "m4d_mixing_filops": "记录跨「混色功能」+「主流程-用例」→ 归更具体的功能组",
    "m4i_mixing_slice": "记录跨「混色功能」+「主流程-用例」→ 归更具体的功能组",
    "m4e_mixing_paint": "仅一条 PARTIAL 主流程引用 → 留在混色功能组",
    "m2_slice_chain": "仅一条 PARTIAL 耗材管理引用 → 留在 engine（核心切片引擎）",
}


def _group_of(stem: str) -> str | None:
    """tests/ 下持有该用例脚本的分组目录名（None = 还没归组）。"""
    tdir = HERE / "tests"
    for d in sorted(tdir.iterdir()):
        if d.is_dir() and not d.name.startswith("__") and (d / f"{stem}.py").exists():
            return d.name
    return None


# file= 由磁盘布局推导（键名 == 脚本 stem）：tests/<group>/<key>.py。移动脚本
# 只需挪文件，注册表自动跟随。
for _k, _v in CASES.items():
    if _v.get("file") is None:
        _g = _group_of(_k)
        _v["file"] = f"tests/{_g}/{_k}.py" if _g else f"tests/{_k}.py"
    _v["group"] = _group_of(_k) or "engine"


def group_label(name: str) -> str:
    """用例所属分组的飞书二级分类中文名（无映射的为 engine 的说明文案）。"""
    g = CASES.get(name, {}).get("group", "engine")
    return GROUP_LABELS.get(g, g)


# 每个用例脚本头部声明其飞书来源，形如：
#     # feishu: baseline#164 baseline#156      （多条用空格分隔）
#     # feishu: none                            （引擎/链路用例，无基线记录）
# 注解是"代码 → 飞书"的唯一权威来源；tools/check_feishu_map.py 做双向校验。
_FEISHU_RE = re.compile(r"^#\s*feishu:\s*(.+?)\s*$")


def feishu_refs(name: str) -> list[str] | None:
    """脚本注解里声明的飞书引用。

    None = 没有注解（校验器会报错：新用例漏加注解）
    []   = 显式 none
    else = ["baseline#164", ...]
    """
    path = case_path(name)
    if not path or not path.exists():
        return None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
        m = _FEISHU_RE.match(ln.strip())
        if m:
            val = m.group(1).strip()
            return [] if val.lower().startswith("none") else val.split()
    return None


def summary(name: str) -> str:
    """Live-extract the case's summary from its line-2 header comment
    ("# <stem>.py — ..."); empty string when the script has none."""
    meta = CASES.get(name)
    if not meta:
        return ""
    try:
        head = (HERE / meta["file"]).read_text(
            encoding="utf-8", errors="replace").splitlines()[:5]
    except OSError:
        return ""
    for ln in head:
        m = re.match(rf"#\s*{re.escape(name)}\.py\s*[—-]?\s*(.+)$", ln.strip())
        if m:
            return m.group(1).strip()
    return ""


def enabled_cases(suite: str | None = None) -> list[str]:
    """Enabled case names, optionally filtered to a suite (None = all enabled).

    suite="baseline" = 只在飞书基线表里有映射的用例（注解 `# feishu: baseline#N`），
    即"基线用例文档里"的那些 —— 日常只跑它们即可，其余引擎/链路用例按需再跑。
    """
    if suite == "baseline":
        return baseline_cases()
    return [k for k, v in CASES.items()
            if v["enabled"] and (suite is None or v["suite"] == suite)]


def baseline_cases() -> list[str]:
    """启用的、在飞书基线表里有用例映射的用例（按注册表顺序）。"""
    return [k for k, v in CASES.items()
            if v["enabled"] and any(r.startswith("baseline#")
                                    for r in (feishu_refs(k) or []))]


def case_path(name: str) -> Path | None:
    v = CASES.get(name)
    return HERE / v["file"] if v else None
