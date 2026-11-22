"""Finite business experiments; never a model-selected verifier or import path."""
from importlib import import_module
from .native_matrix import (CANVAS_REPLACE_SCENARIO, SCALE_SCENARIOS, UIA_CANVAS_SCENARIO,
    UIA_DISTURBANCE_SCENARIO, UIA_MIX_RECIPES, UIA_MIX_SCENARIOS, UIA_MOVE_LAYER,
    UIA_PROCESS_COMBO, UIA_QUALITY_ENUMS, UIA_Y_SCENARIOS)

PILOTS = {
    "pilot_strength": "pilot_strength",
    "pilot_transform": "pilot_transform",
    "pilot_material": "pilot_material",
    "pilot_infill": "pilot_infill",
    "pilot_material3": "pilot_material3",
}
PILOT_BLOCKS = {
    "pilot_transform": "scene_numeric_range_and_canvas_edit_authority_not_ready",
}
TRIALS = {
    "canvas_trial": "pilot_transform", CANVAS_REPLACE_SCENARIO: "pilot_transform",
    UIA_CANVAS_SCENARIO: "pilot_transform",
    # the script positive control for the slot2 business runs the same
    # module/oracle as its zcode scenarios; without this key the script
    # verifier fell through to the layer-height default and rejected the
    # correctly-unchanged 0.4 mm project (measured run e6668fef).
    "pilot_material": "pilot_material",
    UIA_PROCESS_COMBO: "pilot_process_combo",
    UIA_MIX_RECIPES: "pilot_mix_recipes",
    UIA_QUALITY_ENUMS: "quality_enums", UIA_MOVE_LAYER: "move_layer",
    "general_wall": "pilot_strength", "general_slot2": "pilot_material",
    "general_top_strength": "pilot_top_layers", "general_top_quality": "pilot_top_layers",
    **dict.fromkeys(SCALE_SCENARIOS, "pilot_scale_x"),
    "general_combo": "pilot_infill_material", "general_combo_dialog": "pilot_infill_material",
    "uia_general_wall": "pilot_strength", "uia_general_slot2": "pilot_material",
    "uia_general_bottom_strength": "bottom", "uia_general_bottom_quality": "bottom",
    **dict.fromkeys(UIA_Y_SCENARIOS, "move_y"),
    "uia_general_combo": "combo", UIA_DISTURBANCE_SCENARIO: "combo",
    "uia_param_layer_pair": "pilot_param_layer_pair",
    "uia_param_ironing_top": "pilot_param_259_ironing_top",
    "uia_param_wall_thin": "pilot_param_266_wall_thin",
    "uia_param_shells_pattern": "pilot_param_267_shells_pattern",
    "uia_param_infill_combo": "pilot_param_268_infill_combo",
    "uia_param_bridge": "pilot_param_263_bridge",
    "uia_param_first_speeds": "pilot_param_270_first_speeds",
    "uia_param_feature_speeds": "pilot_param_271_feature_speeds",
    "uia_param_fuzzy": "pilot_param_295_fuzzy",
    "uia_param_overhang_speeds": "pilot_param_264_overhang_speeds",
    "uia_param_accelerations": "pilot_param_274_accelerations",
    "uia_param_skirt": "pilot_param_290_skirt",
    "uia_param_brim": "pilot_param_291_brim",
    # Feishu #276-279 speed/support/raft batch + #292-294 others batch.
    "uia_param_speed_limits": "pilot_param_276_speed_limits",
    "uia_param_support_basic": "pilot_param_277_support_basic",
    "uia_param_raft": "pilot_param_278_raft",
    "uia_param_support_filament": "pilot_param_279_support_filament",
    "uia_param_by_object": "pilot_param_292_by_object",
    "uia_param_spiral_vase": "pilot_param_293_spiral_vase",
    "uia_param_timelapse": "pilot_param_294_timelapse",
    # Feishu #255-257/#260-261 quality batch + #272-273 speed batch.
    "uia_param_line_width_all": "pilot_param_255_line_width_all",
    "uia_param_seam_wipe": "pilot_param_256_seam_wipe",
    "uia_param_precision_comp": "pilot_param_257_precision_comp",
    "uia_param_wall_generator": "pilot_param_260_wall_generator",
    "uia_param_single_wall_avoid": "pilot_param_261_single_wall_avoid",
    "uia_param_overhang_bridge": "pilot_param_272_overhang_bridge",
    "uia_param_travel_speed": "pilot_param_273_travel_speed",
}


def native_fixture(scenario):
    if scenario in UIA_MIX_SCENARIOS:
        from .pilot_mix_recipes import FIXTURE, FIXTURE_SHA256
        return FIXTURE, FIXTURE_SHA256
    from .agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
    return LAYER_FIXTURE, LAYER_FIXTURE_SHA256


def require_pilot_ready(scenario):
    from .native_matrix import SCENARIOS
    if type(scenario) is not str or scenario not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    if scenario in PILOT_BLOCKS:
        raise RuntimeError("native_pilot_capability_blocked:"+PILOT_BLOCKS[scenario])


def pilot_module(scenario):
    if type(scenario) is not str or scenario not in {**PILOTS, **TRIALS}:
        raise ValueError("native_pilot_not_registered")
    module = {**PILOTS, **TRIALS}[scenario]
    if module in {"bottom", "move_y", "combo", "quality_enums", "move_layer"}:
        return import_module(".pilot_uia_goals", __package__).GOALS[module]
    return import_module("."+module, __package__)


def business_goal(scenario):
    if scenario in {**PILOTS, **TRIALS}:
        return pilot_module(scenario).GOAL
    from .native_matrix import SCENARIOS
    if scenario not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    return ("Set regular Layer height to 0.24 mm, preserve First layer height 0.40 mm "
            "and the cube model. Do not change other settings.")


def verify_business(scenario, project, fixture, gcode, *, cancelled=lambda: False):
    return pilot_module(scenario).verify_business(project, fixture, gcode, cancelled=cancelled)
