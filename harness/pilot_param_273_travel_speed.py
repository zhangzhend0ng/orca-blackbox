"""Feishu #273 (常用工艺参数, P0): global travel-speed mapping.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 192.
travel_speed lives in the Speed tab 'Travel speed' group (Tab.cpp:2452,
row label L("Travel")); the fixture stores 500. One write to 300; the
layer grid is untouched (68 x 0.4 / 27.2)."""
from .param_case_lib import make_verify

CASE_ID = "param_273_travel_speed"
GOAL = ("Set travel speed to 300 mm/s. Preserve the cube geometry, its "
        "placement, material assignment and every other setting.")
VALUES = {"travel_speed": "300"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
