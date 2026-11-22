"""Feishu #293 (常用工艺参数, P0): spiral vase + nearest seam.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 212.
spiral_mode=1, seam_position=nearest. The table's single-wall model
precondition (圆柱体) diverges: the standard cube is multi-wall, and spiral
raises Z continuously so the per-layer 68/27.2 oracle does not apply
(analyze_gcode counts distinct Z moves). schedule stays None until a
guest run measures the vase schedule; the oracle proves both config
writes + settings preservation."""
from .param_case_lib import make_verify

CASE_ID = "param_293_spiral_vase"
GOAL = ("Enable spiral vase mode and set seam position to nearest. Preserve "
        "the cube geometry, its placement, material assignment and every "
        "other setting.")
VALUES = {"spiral_mode": "1", "seam_position": "nearest"}
verify_business = make_verify(CASE_ID, VALUES)
