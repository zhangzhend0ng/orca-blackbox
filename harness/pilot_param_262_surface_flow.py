"""Feishu #262 (墙壁和表面, P1): surface flow ratio combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 181.
All three keys sit in the Quality 'Walls and surfaces' group (Tab.cpp:2329-
2331); print_flow_ratio ('Flow ratio') already equals the fixture value 1 =
the 1.0 target, so it stays assertion-only. Only top 1 -> 1.1 and bottom
1 -> 0.9 move. Flow ratios rescale extrusion only - the layer grid keeps
the 68 x 0.4 / 27.2 schedule."""
from .param_case_lib import make_verify

CASE_ID = "param_262_surface_flow"
GOAL = ("Set top surface flow ratio to 1.1 and bottom surface flow ratio to "
        "0.9, keeping the flow ratio at 1. Preserve the cube geometry, its "
        "placement, material assignment and every other setting.")
VALUES = {"top_solid_infill_flow_ratio": "1.1",
          "bottom_solid_infill_flow_ratio": "0.9",
          "print_flow_ratio": "1"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
