"""Finite business experiments; never a model-selected verifier or import path."""
from importlib import import_module
from .agent_protocol import BASELINES, base_scenario, suffixed_fixture
from .native_matrix import (CANVAS_REPLACE_SCENARIO, SCALE_SCENARIOS, UIA_CANVAS_SCENARIO,
    UIA_DISTURBANCE_SCENARIO, UIA_MIX_RECIPES, UIA_MIX_SCENARIOS, UIA_MOVE_LAYER,
    UIA_PROCESS_COMBO, UIA_QUALITY_ENUMS, UIA_Y_SCENARIOS, std_base)

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
    # Feishu #258/#262/#265/#269/#275 P1 batch + #283/#285 multimaterial batch.
    "uia_param_arc_resolution": "pilot_param_258_arc_resolution",
    "uia_param_surface_flow": "pilot_param_262_surface_flow",
    "uia_param_overhang_curl": "pilot_param_265_overhang_curl",
    "uia_param_infill_structure": "pilot_param_269_infill_structure",
    "uia_param_jerk": "pilot_param_275_jerk",
    "uia_param_prime_tower": "pilot_param_283_prime_tower",
    "uia_param_ooze_prevention": "pilot_param_285_ooze_prevention",
    # Feishu #280-282 support batch + #284/#286/#287 material batch +
    # #296/#297 gcode-output batch (fa706 B4, param-family finale).
    "uia_param_support_ironing": "pilot_param_280_support_ironing",
    "uia_param_support_interface": "pilot_param_281_support_interface",
    "uia_param_tree_support": "pilot_param_282_tree_support",
    "uia_param_filament_features": "pilot_param_284_filament_features",
    "uia_param_flush_options": "pilot_param_286_flush_options",
    "uia_param_material_advanced": "pilot_param_287_material_advanced",
    "uia_param_gcode_output": "pilot_param_296_gcode_output",
    "uia_param_exclude_objects": "pilot_param_297_exclude_objects",
    # Feishu #288/#289 (snapshot lines 207/208, 材料-混色) are SKIPPED for
    # the param engine: mixed_filament_definitions / _component_bias_enabled
    # / mixed_color_layer_height_a/b / _gradient_mode / _pointillism_* /
    # _region_collapse / _surface_indentation have NO row on any Tab.cpp
    # options page (the process panel's Color Mixing group carries only the
    # three dithering_local_z_* keys, Tab.cpp:2631-2634) - they are
    # project-config scope driven from the Plater sidebar mixed-filament
    # panel (Plater.cpp update_mixed_filament_panel, Tab.cpp:1882-1919
    # sync). Reaching them needs the mix engine chain (uia_mix_recipes /
    # mixing_util, the Add-Mix dialog contract), not process-panel ops -
    # no param modules fabricated for them (2026-11-23, fa706 B4).
}
# Save-only controls, not Feishu cases: param_closure_list / param_oracle_surface /
# export_param_cases / rejudge_shadows count and export TRIALS, and the closure
# number (40 of 44 on 2026-11-24) is quoted from there. One module holds them all
# (its CASES, one per scenario): what a save with no edit changes, on the cube and
# on every other fixture (agent_protocol.BASELINES).
CONTROLS = {"uia_param_save_only": "pilot_param_save_only",
            **{baseline: "pilot_param_save_only" for baseline, _case in BASELINES.values()}}


def native_fixture(scenario):
    if scenario in UIA_MIX_SCENARIOS:
        from .pilot_mix_recipes import FIXTURE, FIXTURE_SHA256
        return FIXTURE, FIXTURE_SHA256
    # a suffixed name or a save-only baseline opens its own fixture
    other = suffixed_fixture(scenario)
    if other:
        return other
    from .agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
    return LAYER_FIXTURE, LAYER_FIXTURE_SHA256


def require_pilot_ready(scenario):
    from .native_matrix import SCENARIOS
    base = std_base(scenario)
    if base not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    if base in PILOT_BLOCKS:
        raise RuntimeError("native_pilot_capability_blocked:"+PILOT_BLOCKS[base])


def pilot_module(scenario):
    # A `_std02` scenario runs its base's pilot: only the fixture differs.
    base = std_base(scenario)
    if type(scenario) is not str or base not in {**PILOTS, **TRIALS, **CONTROLS}:
        raise ValueError("native_pilot_not_registered")
    module = {**PILOTS, **TRIALS, **CONTROLS}[base]
    if module in {"bottom", "move_y", "combo", "quality_enums", "move_layer"}:
        return import_module(".pilot_uia_goals", __package__).GOALS[module]
    loaded = import_module("."+module, __package__)
    # A module that holds one case per scenario names them in CASES.
    cases = getattr(loaded, "CASES", None)
    return cases[base] if type(cases) is dict and base in cases else loaded


def business_goal(scenario):
    if base_scenario(scenario) in {**PILOTS, **TRIALS, **CONTROLS}:
        return pilot_module(scenario).GOAL
    from .native_matrix import SCENARIOS
    if base_scenario(scenario) not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    return ("Set regular Layer height to 0.24 mm, preserve First layer height 0.40 mm "
            "and the cube model. Do not change other settings.")


def verify_business(scenario, project, fixture, gcode, *, cancelled=lambda: False):
    return pilot_module(scenario).verify_business(project, fixture, gcode, cancelled=cancelled)
