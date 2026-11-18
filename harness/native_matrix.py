"""Finite, trusted setup registry. These routes are never sent to the model."""
from __future__ import annotations

from .native_diagnostic_recovery import COMMIT_SCENARIO, SCENARIO as DIAGNOSTIC_SCENARIO

CANVAS_REPLACE_SCENARIO = "canvas_replace_trial"
UIA_SAVE_SCENARIO = "uia_save_as"
SCALE_SCENARIOS = ("general_scale_quality", "general_scale_others")
CANVAS_REPLACE_SCENARIOS = frozenset((CANVAS_REPLACE_SCENARIO, *SCALE_SCENARIOS))
CANVAS_SCENARIOS = CANVAS_REPLACE_SCENARIOS | {"canvas_trial"}
GENERALIZATION = (
    "general_wall", "general_slot2", "general_top_strength", "general_top_quality",
    *SCALE_SCENARIOS, "general_combo", "general_combo_dialog",
)
SAVE_CLEAR_SCENARIOS = frozenset((COMMIT_SCENARIO, CANVAS_REPLACE_SCENARIO, *GENERALIZATION))

SCENARIOS = {
    "base": ("Quality", None),
    "quality_a": ("Quality", None), "quality_b": ("Quality", None),
    "strength_a": ("Strength", None), "strength_b": ("Strength", None),
    "others_a": ("Others", None), "others_b": ("Others", None),
    "save_dialog": ("Quality", "save_dialog"),
    UIA_SAVE_SCENARIO: ("Quality", "save_dialog"),
    "overwrite": ("Quality", "overwrite"),
    "safety_cancel": ("Quality", "cancel"),
    "safety_timeout": ("Quality", "timeout"),
    "safety_guard_disconnect": ("Quality", "guard_disconnect"),
    "pilot_strength": ("Quality", None),
    "pilot_transform": ("Quality", None),
    "pilot_material": ("Quality", None),
    "pilot_infill": ("Others", None),
    "pilot_material3": ("Quality", None),
    "canvas_probe": ("Quality", None),
    "recovery_owned_edit": ("Others", None),
    DIAGNOSTIC_SCENARIO: ("Others", None),
    COMMIT_SCENARIO: ("Others", None),
    "canvas_trial": ("Quality", None),
    CANVAS_REPLACE_SCENARIO: ("Quality", None),
    "general_wall": ("Quality", None),
    "general_slot2": ("Quality", None),
    "general_top_strength": ("Strength", None),
    "general_top_quality": ("Quality", None),
    "general_scale_quality": ("Quality", None),
    "general_scale_others": ("Others", None),
    "general_combo": ("Quality", None),
    "general_combo_dialog": ("Quality", "save_dialog"),
    "authority_probe": ("Quality", None),
}
BUSINESS = ("quality_a", "quality_b", "strength_a", "strength_b", "others_a", "others_b", "save_dialog", "overwrite")
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
    limit = 4_000_000
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    except FileNotFoundError:
        return []
    if len(raw) > limit:
        raise ValueError("native_progress_limit")
    complete, separator, _ = raw.rpartition(b"\n")
    if not separator:
        return []
    record = json.loads(complete.rsplit(b"\n", 1)[-1])
    return [c for c in record.get("native_tool_calls", []) if c.get("status") == "completed"]
