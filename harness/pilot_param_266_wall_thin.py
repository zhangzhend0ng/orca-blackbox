"""Feishu #266 (常用工艺参数, P0): wall loops + thin-wall detection.

wall_loops=4 with detect_thin_wall=1 on the standard cube; the object
schedule stays 68 x 0.4 / 27.2 and every other setting is preserved."""
from .param_case_lib import make_verify

CASE_ID = "param_266_wall_thin"
GOAL = ("Set wall loops to 4 and enable detect thin wall. "
        "Preserve the cube geometry, its placement, material assignment and every other setting.")
VALUES = {"wall_loops": "4", "detect_thin_wall": "1"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
