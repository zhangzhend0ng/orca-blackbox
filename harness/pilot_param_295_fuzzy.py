"""Feishu #295 (常用工艺参数, P0): fuzzy-surface combination."""
from .param_case_lib import make_verify

CASE_ID = "param_295_fuzzy"
GOAL = ("Set fuzzy skin to external walls only with point distance 0.6 mm and thickness "
        "0.3 mm. Preserve the cube geometry, its placement, material and every other setting.")
VALUES = {"fuzzy_skin": "external", "fuzzy_skin_point_distance": "0.6",
          "fuzzy_skin_thickness": "0.3"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
