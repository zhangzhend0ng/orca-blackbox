"""Feishu #270 (常用工艺参数, P0): first-layer speed chain."""
from .param_case_lib import make_verify

CASE_ID = "param_270_first_speeds"
GOAL = ("Set initial layer speed to 30, initial layer infill speed to 40 and initial layer "
        "travel speed to 150. Preserve the cube geometry, its placement, material and every other setting.")
VALUES = {"initial_layer_speed": "30", "initial_layer_infill_speed": "40",
          "initial_layer_travel_speed": "150%"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
