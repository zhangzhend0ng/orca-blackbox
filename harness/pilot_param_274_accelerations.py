"""Feishu #274 (常用工艺参数, P0): acceleration feature combination."""
from .param_case_lib import make_verify

CASE_ID = "param_274_accelerations"
GOAL = ("Set default acceleration to 3000, initial layer acceleration to 500, outer wall to "
        "2000, inner wall to 4000, sparse infill to 5000 and travel acceleration to 8000. "
        "Preserve the cube geometry, its placement, material and every other setting.")
VALUES = {"default_acceleration": "3000", "initial_layer_acceleration": "500",
          "outer_wall_acceleration": "2000", "inner_wall_acceleration": "4000",
          "sparse_infill_acceleration": "5000", "travel_acceleration": "8000"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
