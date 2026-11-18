"""Finite business experiments; never a model-selected verifier or import path."""
from importlib import import_module
from .native_matrix import CANVAS_SCENARIOS

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
TRIALS = dict.fromkeys(CANVAS_SCENARIOS, "pilot_transform")


def require_pilot_ready(scenario):
    from .native_matrix import SCENARIOS
    if type(scenario) is not str or scenario not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    if scenario in PILOT_BLOCKS:
        raise RuntimeError("native_pilot_capability_blocked:"+PILOT_BLOCKS[scenario])


def pilot_module(scenario):
    if type(scenario) is not str or scenario not in {**PILOTS, **TRIALS}:
        raise ValueError("native_pilot_not_registered")
    return import_module("."+{**PILOTS, **TRIALS}[scenario], __package__)


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
