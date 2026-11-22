"""Feishu #294 (常用工艺参数, P1 - dispatched with the P0 batch): timelapse
+ slicing-mode combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 213.
timelapse_type=2 (smooth), slicing_mode=regular. slicing_mode already
sits at 'regular' in the fixture config (verified), so ops only drive the
timelapse selector. Smooth timelapse parks/photographs per layer but adds
no object layers, so the schedule oracle stands."""
from .param_case_lib import make_verify

CASE_ID = "param_294_timelapse"
GOAL = ("Set timelapse type to smooth while slicing mode stays regular. "
        "Preserve the cube geometry, its placement, material assignment and "
        "every other setting.")
VALUES = {"timelapse_type": "2", "slicing_mode": "regular"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
