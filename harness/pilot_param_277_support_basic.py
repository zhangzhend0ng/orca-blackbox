"""Feishu #277 (常用工艺参数, P0): support enable + base structure combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 196.
enable_support=1, support_threshold_angle=45, support_type=normal(auto),
support_on_build_plate_only=0, support_critical_regions_only=0. The two
flags already sit at 0 in the fixture config (verified against
fixtures/agent_layer_cube.3mf), so ops only touch the first three. The
support-overhang precondition (欧特克FDM测试 model) diverges: the standard
cube generates no supports, so the config write + unchanged schedule is
what this oracle proves."""
from .param_case_lib import make_verify

CASE_ID = "param_277_support_basic"
GOAL = ("Enable support with threshold angle 45 deg and support type normal "
        "(auto). Preserve the cube geometry, its placement, material "
        "assignment and every other setting.")
VALUES = {"enable_support": "1", "support_threshold_angle": "45", "support_type": "normal(auto)",
          "support_on_build_plate_only": "0", "support_critical_regions_only": "0"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
