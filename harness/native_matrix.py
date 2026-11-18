"""Finite, trusted setup registry. These routes are never sent to the model."""
from __future__ import annotations

from .native_diagnostic_recovery import COMMIT_SCENARIO, SCENARIO as DIAGNOSTIC_SCENARIO

CANVAS_REPLACE_SCENARIO = "canvas_replace_trial"
UIA_SAVE_SCENARIO = "uia_save_as"
UIA_LAYER_SCENARIO = "uia_hybrid_layer"
UIA_LAYER_STRENGTH_SCENARIO = "uia_hybrid_layer_strength"
UIA_CANVAS_SCENARIO = "uia_hybrid_canvas"
UIA_PROCESS_COMBO = "uia_process_combo"
UIA_MIX_RECIPES = "uia_mix_recipes"
UIA_REPLAY_SCENARIO = "uia_replay_layer"
UIA_REPLAY_SAVE = "uia_replay_save"
UIA_REPLAY_CANVAS = "uia_replay_canvas"
UIA_REPLAY_PROCESS = "uia_replay_process"
UIA_REPLAY_MIX = "uia_replay_mix"
REPLAY_SOURCES = {UIA_REPLAY_SCENARIO: UIA_LAYER_SCENARIO, UIA_REPLAY_SAVE: UIA_SAVE_SCENARIO,
                  UIA_REPLAY_CANVAS: UIA_CANVAS_SCENARIO, UIA_REPLAY_PROCESS: UIA_PROCESS_COMBO,
                  UIA_REPLAY_MIX: UIA_MIX_RECIPES}
UIA_PROCESS_SCENARIOS = frozenset((UIA_PROCESS_COMBO, UIA_REPLAY_PROCESS))
UIA_MIX_SCENARIOS = frozenset((UIA_MIX_RECIPES, UIA_REPLAY_MIX))
UIA_SAVE_SCENARIOS = frozenset((UIA_SAVE_SCENARIO, UIA_REPLAY_SAVE))
SCRIPT_COMPARISON_SCENARIOS = (UIA_LAYER_SCENARIO, UIA_CANVAS_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO, UIA_SAVE_SCENARIO,
                               UIA_PROCESS_COMBO, UIA_MIX_RECIPES)
SCRIPT_SCENARIOS = (*SCRIPT_COMPARISON_SCENARIOS, *REPLAY_SOURCES)
UIA_Y_SCENARIOS = ("uia_general_y_quality", "uia_general_y_others")
UIA_DISTURBANCE_SCENARIO = "uia_general_combo_dialog"
UIA_GENERALIZATION = ("uia_general_wall", "uia_general_slot2",
    "uia_general_bottom_strength", "uia_general_bottom_quality", *UIA_Y_SCENARIOS,
    "uia_general_combo", UIA_DISTURBANCE_SCENARIO)
UIA_HYBRID_SCENARIOS = frozenset((*SCRIPT_SCENARIOS, *UIA_GENERALIZATION)) - UIA_SAVE_SCENARIOS
SCALE_SCENARIOS = ("general_scale_quality", "general_scale_others")
CANVAS_REPLACE_SCENARIOS = frozenset((CANVAS_REPLACE_SCENARIO, UIA_CANVAS_SCENARIO, UIA_REPLAY_CANVAS, *SCALE_SCENARIOS, *UIA_Y_SCENARIOS))
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
    UIA_LAYER_SCENARIO: ("Quality", None),
    UIA_LAYER_STRENGTH_SCENARIO: ("Strength", None),
    UIA_CANVAS_SCENARIO: ("Quality", None),
    UIA_PROCESS_COMBO: ("Quality", None),
    UIA_MIX_RECIPES: ("Quality", None),
    UIA_REPLAY_SCENARIO: ("Quality", None),
    UIA_REPLAY_SAVE: ("Quality", "save_dialog"),
    UIA_REPLAY_CANVAS: ("Quality", None),
    UIA_REPLAY_PROCESS: ("Quality", None),
    UIA_REPLAY_MIX: ("Quality", None),
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
    "uia_general_wall": ("Quality", None),
    "uia_general_slot2": ("Quality", None),
    "uia_general_bottom_strength": ("Strength", None),
    "uia_general_bottom_quality": ("Quality", None),
    "uia_general_y_quality": ("Quality", None),
    "uia_general_y_others": ("Others", None),
    "uia_general_combo": ("Quality", None),
    UIA_DISTURBANCE_SCENARIO: ("Quality", "save_dialog"),
    "authority_probe": ("Quality", None),
}
BUSINESS = ("quality_a", "quality_b", "strength_a", "strength_b", "others_a", "others_b", "save_dialog", "overwrite")
SAFETY = tuple(k for k in SCENARIOS if k.startswith("safety_"))


def scenario_spec(actor, scenario):
    if actor == "script":
        if scenario not in SCRIPT_SCENARIOS:
            raise ValueError("native_script_scenario_not_registered")
        return SCENARIOS[scenario]
    if actor not in {"codex", "zcode"} or scenario not in SCENARIOS or scenario in REPLAY_SOURCES:
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
