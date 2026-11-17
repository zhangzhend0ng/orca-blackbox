"""Finite, trusted setup registry. These routes are never sent to the model."""
from __future__ import annotations

SCENARIOS = {
    "base": ("Quality", None),
    "quality_a": ("Quality", None), "quality_b": ("Quality", None),
    "strength_a": ("Strength", None), "strength_b": ("Strength", None),
    "others_a": ("Others", None), "others_b": ("Others", None),
    "save_dialog": ("Quality", "save_dialog"),
    "overwrite": ("Quality", "overwrite"),
    "safety_cancel": ("Quality", "cancel"),
    "safety_timeout": ("Quality", "timeout"),
    "safety_guard_disconnect": ("Quality", "guard_disconnect"),
}
BUSINESS = tuple(k for k in SCENARIOS if k != "base" and not k.startswith("safety_"))
SAFETY = tuple(k for k in SCENARIOS if k.startswith("safety_"))


def scenario_spec(actor, scenario):
    if actor not in {"codex", "zcode"} or scenario not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    if actor != "zcode" and scenario != "base":
        raise ValueError("native_matrix_requires_zcode")
    return SCENARIOS[scenario]


def completed_progress(path):
    """Read complete append-only records only; a partial tail is not a trigger."""
    import json
    if not path.exists():
        return []
    if path.stat().st_size > 4_000_000:
        raise ValueError("native_progress_limit")
    raw = path.read_bytes()
    lines = raw.split(b"\n")[:-1]
    if not lines:
        return []
    record = json.loads(lines[-1])
    return [c for c in record.get("native_tool_calls", []) if c.get("status") == "completed"]
