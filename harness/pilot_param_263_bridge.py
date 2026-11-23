"""Feishu #263 (常用工艺参数, P0): bridge quality combination."""
from .param_case_lib import make_verify

CASE_ID = "param_263_bridge"
GOAL = ("Set bridge flow to 1.0, bridge density to 100%, enable thick bridges and max bridge "
        "length to 30 mm. Preserve the cube geometry, its placement, material and every other setting.")
# 2026-11-23: max_bridge_length dropped - the params page has no such row
# (source atlas places it on no page; precedent: raft_expansion).
VALUES = {"bridge_flow": "1", "bridge_density": "100%", "thick_bridges": "1",
          "bridge_angle": "0"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
