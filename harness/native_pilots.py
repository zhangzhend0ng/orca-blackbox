"""Finite business experiments; never a model-selected verifier or import path."""
from importlib import import_module
from .native_matrix import (CANVAS_REPLACE_SCENARIO, SCALE_SCENARIOS, UIA_CANVAS_SCENARIO,
    UIA_DISTURBANCE_SCENARIO, UIA_MIX_RECIPES, UIA_MIX_SCENARIOS, UIA_PROCESS_COMBO, UIA_Y_SCENARIOS)

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
    UIA_PROCESS_COMBO: "pilot_process_combo",
    UIA_MIX_RECIPES: "pilot_mix_recipes",
    "general_wall": "pilot_strength", "general_slot2": "pilot_material",
    "general_top_strength": "pilot_top_layers", "general_top_quality": "pilot_top_layers",
    **dict.fromkeys(SCALE_SCENARIOS, "pilot_scale_x"),
    "general_combo": "pilot_infill_material", "general_combo_dialog": "pilot_infill_material",
    "uia_general_wall": "pilot_strength", "uia_general_slot2": "pilot_material",
    "uia_general_bottom_strength": "bottom", "uia_general_bottom_quality": "bottom",
    **dict.fromkeys(UIA_Y_SCENARIOS, "move_y"),
    "uia_general_combo": "combo", UIA_DISTURBANCE_SCENARIO: "combo",
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
    if module in {"bottom", "move_y", "combo"}:
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
