"""Feishu #291 (常用工艺参数, P0): brim width/gap + type."""
from .param_case_lib import make_verify

CASE_ID = "param_291_brim"
GOAL = ("Set brim width to 5 mm, brim object gap to 0.2 mm and brim type to outer walls only. "
        "Preserve the cube geometry, its placement, material and every other setting.")
# brim_type serializes as the enum key "outer_only" (PrintConfig s_keys_map_BrimType).
VALUES = {"brim_width": "5", "brim_object_gap": "0.2", "brim_type": "outer_only"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
