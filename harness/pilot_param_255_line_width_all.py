"""Feishu #255 (常用工艺参数, P0): full line-width combination.

Snapshot row: docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/
tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 174. The table's seven
line_width keys match the fixture 3MF config keys exactly (all sit at
0.82 there, fixtures/agent_layer_cube.3mf). Widths never re-grid the
cube: the object schedule stays 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_255_line_width_all"
GOAL = ("Set default line width to 0.42 mm, initial layer line width to 0.50 mm, "
        "outer wall to 0.42 mm, inner wall to 0.45 mm, top surface to 0.40 mm, "
        "sparse infill to 0.45 mm and support to 0.42 mm. Preserve the cube "
        "geometry, its placement, material assignment and every other setting.")
VALUES = {"line_width": "0.42", "initial_layer_line_width": "0.5",
          "outer_wall_line_width": "0.42", "inner_wall_line_width": "0.45",
          "top_surface_line_width": "0.4", "sparse_infill_line_width": "0.45",
          "support_line_width": "0.42"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
