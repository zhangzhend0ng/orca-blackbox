"""Feishu #264 (常用工艺参数, P0): overhang detection + tiered overhang speeds."""
from .param_case_lib import make_verify

CASE_ID = "param_264_overhang_speeds"
GOAL = ("Enable detect overhang wall and slow down for overhang, then set the five overhang "
        "degree-band speeds to 40/30/20/10/5. Preserve the cube geometry, its placement, "
        "material and every other setting.")
# Stored booleans as "1" per the #266 wall_thin precedent (run 05dd9020).
# Enum-free: overhang_* are coFloatsOrPercents written as plain numbers.
VALUES = {"detect_overhang_wall": "1", "enable_overhang_speed": "1",
          "overhang_1_4_speed": "40", "overhang_2_4_speed": "30",
          "overhang_3_4_speed": "20", "overhang_4_4_speed": "10",
          "overhang_totally_speed": "5"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
