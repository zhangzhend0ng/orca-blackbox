"""Feishu #271 (常用工艺参数, P0): per-feature speed combination."""
from .param_case_lib import make_verify

CASE_ID = "param_271_feature_speeds"
GOAL = ("Set outer wall speed 100, inner wall speed 150, sparse infill speed 200, top surface "
        "speed 120, small perimeter threshold 10 and small perimeter speed 50. Preserve the cube "
        "geometry, its placement, material and every other setting.")
VALUES = {"outer_wall_speed": "100", "inner_wall_speed": "150", "sparse_infill_speed": "200",
          "top_surface_speed": "120", "small_perimeter_threshold": "10",
          "small_perimeter_speed": "50%"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
