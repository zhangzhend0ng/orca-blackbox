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
# Recorded deviation (2026-11-24, VM run 49723134): the app will not keep
# 'every other setting'. Ticking Spiral vase on a multi-wall preset opens
# its own Yes/No box - 'Spiral mode only works when wall loops is 1,
# support is disabled, top shell layers is 0, sparse infill density is 0
# and timelapse type is traditional. Change these settings automatically?'
# (ConfigManipulation.cpp:321-351): Yes applies wall_loops 1 /
# top_shell_layers 0 / sparse_infill_density 0 (the other conditions
# already hold in the fixture), No switches spiral mode back off. The case
# is driven with Yes and the three app-applied keys are asserted here.
VALUES = {"spiral_mode": "1", "seam_position": "nearest",
          "wall_loops": "1", "top_shell_layers": "0",
          "sparse_infill_density": "0%"}
verify_business = make_verify(CASE_ID, VALUES)
