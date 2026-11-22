"""Feishu #257 (常用工艺参数, P0): precision dimensional compensation combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 176.
elefant_foot_compensation already equals the table's 0.15 in the fixture
config (fixtures/agent_layer_cube.3mf), so the ops move X-Y hole to
-0.10, X-Y contour to 0.10 and tick Precise wall. Compensations shift
wall paths only - the layer grid stays 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_257_precision_comp"
GOAL = ("Keep elephant foot compensation 0.15 mm, set X-Y hole compensation "
        "to -0.10 mm, X-Y contour compensation to 0.10 mm and enable precise "
        "wall. Preserve the cube geometry, its placement, material assignment "
        "and every other setting.")
VALUES = {"elefant_foot_compensation": "0.15", "xy_contour_compensation": "0.1",
          "xy_hole_compensation": "-0.1", "precise_outer_wall": "1"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
