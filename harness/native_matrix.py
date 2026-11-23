"""Finite, trusted setup registry. These routes are never sent to the model."""
from __future__ import annotations

from .native_diagnostic_recovery import COMMIT_SCENARIO, SCENARIO as DIAGNOSTIC_SCENARIO
from .native_pairwise import PAIR_CASES, PAIR_ENUM_CASES, PAIR_MOVE_CASES
from .model_move_pilot import SCENARIO as BOUND_MODEL_MOVE

CANVAS_REPLACE_SCENARIO = "canvas_replace_trial"
UIA_SAVE_SCENARIO = "uia_save_as"
UIA_LAYER_SCENARIO = "uia_hybrid_layer"
UIA_LAYER_STRENGTH_SCENARIO = "uia_hybrid_layer_strength"
UIA_CANVAS_SCENARIO = "uia_hybrid_canvas"
UIA_PROCESS_COMBO = "uia_process_combo"
UIA_MIX_RECIPES = "uia_mix_recipes"
UIA_QUALITY_ENUMS = "uia_quality_enums"
UIA_MOVE_LAYER = "uia_move_layer"
UIA_REPLAY_SCENARIO = "uia_replay_layer"
UIA_REPLAY_SAVE = "uia_replay_save"
UIA_REPLAY_CANVAS = "uia_replay_canvas"
UIA_REPLAY_PROCESS = "uia_replay_process"
UIA_REPLAY_MIX = "uia_replay_mix"
UIA_REPLAY_ENUMS = "uia_replay_enums"
UIA_REPLAY_MOVE_LAYER = "uia_replay_move_layer"
REPLAY_SOURCES = {UIA_REPLAY_SCENARIO: UIA_LAYER_SCENARIO, UIA_REPLAY_SAVE: UIA_SAVE_SCENARIO,
                  UIA_REPLAY_CANVAS: UIA_CANVAS_SCENARIO, UIA_REPLAY_PROCESS: UIA_PROCESS_COMBO,
                  UIA_REPLAY_MIX: UIA_MIX_RECIPES, UIA_REPLAY_ENUMS: UIA_QUALITY_ENUMS,
                  UIA_REPLAY_MOVE_LAYER: UIA_MOVE_LAYER}
RECORDED_SCENARIOS = frozenset(REPLAY_SOURCES) | PAIR_CASES.keys()
UIA_ENUM_SCENARIOS = frozenset((UIA_QUALITY_ENUMS, UIA_REPLAY_ENUMS)) | PAIR_ENUM_CASES
UIA_PROCESS_SCENARIOS = frozenset((UIA_PROCESS_COMBO, UIA_REPLAY_PROCESS)) | UIA_ENUM_SCENARIOS
# The filament-slot dropdown in the object list is the same wxWindowNR
# "panel" popup as the process-value combos (measured: run 26739846 got
# stuck on it with no legal way to click inside), but its item list is
# taller than a single-value combo. Bind it under the same ownership and
# time limits with a taller height budget.
UIA_FILAMENT_SCENARIOS = frozenset(("uia_general_slot2", "general_slot2", "pilot_material", "pilot_material3"))
POPUP_BIND_SCENARIOS = UIA_PROCESS_SCENARIOS | UIA_FILAMENT_SCENARIOS
UIA_MOVE_LAYER_SCENARIOS = frozenset((UIA_MOVE_LAYER, UIA_REPLAY_MOVE_LAYER))
UIA_MIX_SCENARIOS = frozenset((UIA_MIX_RECIPES, UIA_REPLAY_MIX))
UIA_SAVE_SCENARIOS = frozenset((UIA_SAVE_SCENARIO, UIA_REPLAY_SAVE))
SCRIPT_COMPARISON_SCENARIOS = (UIA_LAYER_SCENARIO, UIA_CANVAS_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO, UIA_SAVE_SCENARIO,
                               UIA_PROCESS_COMBO, UIA_MIX_RECIPES, UIA_QUALITY_ENUMS, UIA_MOVE_LAYER)
FIXTURE_SCENARIOS = ("fixture_cold", "fixture_shared")
SCRIPT_SCENARIOS = (*SCRIPT_COMPARISON_SCENARIOS, *REPLAY_SOURCES, *PAIR_CASES, *FIXTURE_SCENARIOS, BOUND_MODEL_MOVE,
    # deterministic positive control for the filament-slot business: the
    # ZCode route (uia_general_slot2/pilot_material) never passed end to
    # end, so the script baseline proves the path and oracle first.
    "pilot_material",
    # Feishu #254 layer-height combination on the standard fixture.
    "uia_param_layer_pair", "uia_param_ironing_top", "uia_param_wall_thin",
    "uia_param_shells_pattern", "uia_param_infill_combo", "uia_param_bridge",
    "uia_param_first_speeds", "uia_param_feature_speeds", "uia_param_fuzzy",
    # Feishu batch 3: overhang tiered speeds, acceleration combo, skirt, brim.
    "uia_param_overhang_speeds", "uia_param_accelerations", "uia_param_skirt",
    "uia_param_brim",
    # Feishu #276-279 speed/support/raft batch + #292-294 others batch.
    "uia_param_speed_limits", "uia_param_support_basic", "uia_param_raft",
    "uia_param_support_filament", "uia_param_by_object", "uia_param_spiral_vase",
    "uia_param_timelapse",
    # Feishu #255-257/#260-261 quality batch + #272-273 speed batch.
    "uia_param_line_width_all", "uia_param_seam_wipe", "uia_param_precision_comp",
    "uia_param_wall_generator", "uia_param_single_wall_avoid",
    "uia_param_overhang_bridge", "uia_param_travel_speed",
    # Feishu #258/#262/#265/#269/#275 P1 batch + #283/#285 multimaterial batch.
    "uia_param_arc_resolution", "uia_param_surface_flow",
    "uia_param_overhang_curl", "uia_param_infill_structure", "uia_param_jerk",
    "uia_param_prime_tower", "uia_param_ooze_prevention",
    # Feishu #280-282/#284/#286/#287/#296/#297 param-family finale (B4).
    # #288/#289 mixed-color rows are skipped - mix engine required (see
    # the attribution note in native_pilots.TRIALS).
    "uia_param_support_ironing", "uia_param_support_interface",
    "uia_param_tree_support", "uia_param_filament_features",
    "uia_param_flush_options", "uia_param_material_advanced",
    "uia_param_gcode_output", "uia_param_exclude_objects",
    # Probe (2026-11-23): dumps the titled panel windows, wheel/focus and
    # popup geometry the param engine relies on; ends before the save phase.
    "uia_param_census",
    # Probe (2026-11-24): the same dump with the app in DEVELOP mode
    # (SCENARIO_CONF seeds user_mode=develop) - the comDevelop rows, e.g.
    # 'Add line number' of #296, exist only there.
    "uia_param_census_develop",
    # Probe (2026-11-24): the sidebar's Color Mixing panel, the Add Mix
    # dialog's four tabs and an entry's Options menu - do the mixed-filament
    # project settings of #288/#289 have any control on this build?
    "uia_param_mix_census")
UIA_Y_SCENARIOS = ("uia_general_y_quality", "uia_general_y_others")
UIA_DISTURBANCE_SCENARIO = "uia_general_combo_dialog"
UIA_GENERALIZATION = ("uia_general_wall", "uia_general_slot2",
    "uia_general_bottom_strength", "uia_general_bottom_quality", *UIA_Y_SCENARIOS,
    "uia_general_combo", UIA_DISTURBANCE_SCENARIO)
UIA_HYBRID_SCENARIOS = (frozenset((*SCRIPT_COMPARISON_SCENARIOS, *UIA_GENERALIZATION)) | RECORDED_SCENARIOS) - UIA_SAVE_SCENARIOS
SCALE_SCENARIOS = ("general_scale_quality", "general_scale_others")
CANVAS_REPLACE_SCENARIOS = frozenset((CANVAS_REPLACE_SCENARIO, UIA_CANVAS_SCENARIO, UIA_REPLAY_CANVAS, *SCALE_SCENARIOS, *UIA_Y_SCENARIOS)) | UIA_MOVE_LAYER_SCENARIOS | PAIR_MOVE_CASES
CANVAS_SCENARIOS = CANVAS_REPLACE_SCENARIOS | {"canvas_trial"}
GENERALIZATION = (
    "general_wall", "general_slot2", "general_top_strength", "general_top_quality",
    *SCALE_SCENARIOS, "general_combo", "general_combo_dialog",
)
SAVE_CLEAR_SCENARIOS = frozenset((COMMIT_SCENARIO, CANVAS_REPLACE_SCENARIO, *GENERALIZATION))

GUARD_DISCONNECT_SCENARIO = "safety_guard_disconnect"

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
    **dict.fromkeys(UIA_ENUM_SCENARIOS | UIA_MOVE_LAYER_SCENARIOS, ("Quality", None)),
    **dict.fromkeys(FIXTURE_SCENARIOS, ("Quality", None)),
    **dict.fromkeys(PAIR_CASES, ("Quality", None)),
    BOUND_MODEL_MOVE: ("Quality", None),
    "overwrite": ("Quality", "overwrite"),
    "safety_cancel": ("Quality", "cancel"),
    "safety_timeout": ("Quality", "timeout"),
    GUARD_DISCONNECT_SCENARIO: ("Quality", "guard_disconnect"),
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
    "uia_param_layer_pair": ("Quality", None),
    "uia_param_ironing_top": ("Quality", None),
    "uia_param_wall_thin": ("Strength", None),
    "uia_param_shells_pattern": ("Strength", None),
    "uia_param_infill_combo": ("Strength", None),
    "uia_param_bridge": ("Quality", None),
    "uia_param_first_speeds": ("Speed", None),
    "uia_param_feature_speeds": ("Speed", None),
    "uia_param_fuzzy": ("Others", None),  # atlas+band 244ae35e: fuzzy rows live on Others
    "uia_param_overhang_speeds": ("Speed", None),
    "uia_param_accelerations": ("Speed", None),
    "uia_param_skirt": ("Others", None),
    "uia_param_brim": ("Others", None),
    "uia_param_census": ("Quality", None),  # probe: switches tabs itself
    "uia_param_census_develop": ("Quality", None),  # probe, develop mode
    "uia_param_mix_census": ("Quality", None),      # probe: the mix dialog
    # Feishu #276-279/#292-294: the starting page each case's ops first edit
    # lives on (#276 begins on Quality, the speed row closes the sequence).
    "uia_param_speed_limits": ("Quality", None),
    "uia_param_support_basic": ("Support", None),
    "uia_param_raft": ("Support", None),
    "uia_param_support_filament": ("Support", None),
    "uia_param_by_object": ("Others", None),
    "uia_param_spiral_vase": ("Others", None),
    "uia_param_timelapse": ("Others", None),
    # Feishu #255-257/#260-261 all live on Quality; #272-273 on Speed.
    "uia_param_line_width_all": ("Quality", None),
    "uia_param_seam_wipe": ("Quality", None),
    "uia_param_precision_comp": ("Quality", None),
    "uia_param_wall_generator": ("Quality", None),
    "uia_param_single_wall_avoid": ("Quality", None),
    "uia_param_overhang_bridge": ("Speed", None),
    "uia_param_travel_speed": ("Speed", None),
    # Feishu #258/#262 Quality, #265/#275 Speed, #269 Strength;
    # #283/#285 begin on the Multimaterial page (verified by 'tower').
    "uia_param_arc_resolution": ("Quality", None),
    "uia_param_surface_flow": ("Quality", None),
    "uia_param_overhang_curl": ("Speed", None),
    "uia_param_infill_structure": ("Strength", None),
    "uia_param_jerk": ("Speed", None),
    "uia_param_prime_tower": ("Multimaterial", None),
    "uia_param_ooze_prevention": ("Multimaterial", None),
    # Feishu #280-282/#284 begin on the Support page; #286/#287 on
    # Multimaterial (verified by 'tower'); #296/#297 on Others (no
    # tab_hint - the param_tab:Others lesson).
    "uia_param_support_ironing": ("Support", None),
    "uia_param_support_interface": ("Support", None),
    "uia_param_tree_support": ("Support", None),
    "uia_param_filament_features": ("Support", None),
    "uia_param_flush_options": ("Multimaterial", None),
    "uia_param_material_advanced": ("Multimaterial", None),
    "uia_param_gcode_output": ("Others", None),
    "uia_param_exclude_objects": ("Others", None),
    "authority_probe": ("Quality", None),
}
BUSINESS = ("quality_a", "quality_b", "strength_a", "strength_b", "others_a", "others_b", "save_dialog", "overwrite")
SAFETY = tuple(k for k in SCENARIOS if k.startswith("safety_"))


def scenario_spec(actor, scenario):
    if actor == "script":
        if scenario not in SCRIPT_SCENARIOS:
            raise ValueError("native_script_scenario_not_registered")
        return SCENARIOS[scenario]
    if (actor not in {"codex", "zcode"} or scenario not in SCENARIOS
            or scenario in RECORDED_SCENARIOS or scenario in FIXTURE_SCENARIOS or scenario == BOUND_MODEL_MOVE):
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
