"""Feishu #290 (常用工艺参数, P0): skirt loops/height/distance + draft shield."""
from .param_case_lib import make_verify

CASE_ID = "param_290_skirt"
GOAL = ("Set skirt loops to 3, skirt height to 2, skirt distance to 5 mm and enable the draft "
        "shield. Preserve the cube geometry, its placement, material and every other setting.")
# draft_shield serializes as the lowercase enum key (Preset.json evidence).
VALUES = {"skirt_loops": "3", "skirt_height": "2", "skirt_distance": "5",
          "draft_shield": "enabled"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
