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


def _r(milestone: str, tier: str) -> dict:
    """Shorthand for an enabled regression-suite entry (file filled below)."""
    return {"file": None, "milestone": milestone, "tier": tier,
            "suite": "regression", "enabled": True}


def _o(milestone: str, tier: str) -> dict:
    """Shorthand for an enabled but not-in-any-suite entry (file filled below)."""
    return {"file": None, "milestone": milestone, "tier": tier,
            "suite": None, "enabled": True}


CASES: dict[str, dict] = {
    # --- smoke (engine / chain checks) --------------------------------------
    "m0_boot_check": {
        "file": "m0_boot_check.py", "milestone": "m0", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m1_minimal_loop": {
        "file": "m1_minimal_loop.py", "milestone": "m1", "tier": "A",
        "suite": "smoke", "enabled": True,
    },
    "m1b_maa": {
        "file": "m1b_maa.py", "milestone": "m1", "tier": "A",
        "suite": None, "enabled": False,  # engine experiment (m0: MaaFw rejected)
    },
    "m2_slice_chain": {
        "file": "m2_slice_chain.py", "milestone": "m2", "tier": "A",
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
    "m3s_mixing_hover": _r("m3", "B"),   # #8 hover tooltips — 降级/PARTIAL in BLACKBOX_CASES.md L85
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
    "m4e_mixing_paint": _r("m4", "B"),   # 表1#39 部分 — BLACKBOX_CASES.md L96
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
}


# fill file= from the key (stem == file stem by construction) AFTER the _r/_o calls
for _k, _v in CASES.items():
    if _v["file"] is None:
        _v["file"] = f"{_k}.py"


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
    """Enabled case names, optionally filtered to a suite (None = all enabled)."""
    return [k for k, v in CASES.items()
            if v["enabled"] and (suite is None or v["suite"] == suite)]


def case_path(name: str) -> Path | None:
    v = CASES.get(name)
    return HERE / v["file"] if v else None
