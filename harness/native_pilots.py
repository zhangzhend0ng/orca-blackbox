"""Finite business experiments; never a model-selected verifier or import path."""
from importlib import import_module

PILOTS = {
    "pilot_strength": "pilot_strength",
    "pilot_transform": "pilot_transform",
    "pilot_material": "pilot_material",
}


def pilot_module(scenario):
    if type(scenario) is not str or scenario not in PILOTS:
        raise ValueError("native_pilot_not_registered")
    return import_module("."+PILOTS[scenario], __package__)


def business_goal(scenario):
    if scenario in PILOTS:
        return pilot_module(scenario).GOAL
    from .native_matrix import SCENARIOS
    if scenario not in SCENARIOS:
        raise ValueError("native_scenario_not_registered")
    return ("Set regular Layer height to 0.24 mm, preserve First layer height 0.40 mm "
            "and the cube model. Do not change other settings.")


def verify_business(scenario, project, fixture, gcode, *, cancelled=lambda: False):
    return pilot_module(scenario).verify_business(project, fixture, gcode, cancelled=cancelled)
