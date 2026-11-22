"""Feishu #256 (常用工艺参数, P0): seam position/gap + wipe combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 175.
Three of the five targets already sit at the fixture values
(seam_position=aligned, seam_gap=15%, role_based_wipe_speed=1 - measured
in fixtures/agent_layer_cube.3mf), so only wipe_on_loops 0->1 and
wipe_speed 80%->50 move. wipe_speed is a coFloatOrPercent; the table's
absolute 50 mm/s is typed as a plain number, matching how the edit
serializes non-percent input."""
from .param_case_lib import make_verify

CASE_ID = "param_256_seam_wipe"
GOAL = ("Keep seam position aligned and seam gap 15%, enable wipe on loops "
        "with wipe speed 50 mm/s and role based wipe speed on. Preserve "
        "the cube geometry, its placement, material assignment and every "
        "other setting.")
VALUES = {"seam_position": "aligned", "seam_gap": "15%", "wipe_on_loops": "1",
          "wipe_speed": "50", "role_based_wipe_speed": "1"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
