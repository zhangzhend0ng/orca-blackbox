"""Feishu #261 (常用工艺参数, P0): single-wall + avoid-crossing-walls combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 180.
only_one_wall_top=1 and min_width_top_surface=200% already equal the
fixture config values (fixtures/agent_layer_cube.3mf), so the ops tick
only_one_wall_first_layer and reduce_crossing_wall, then set the detour
length. The table writes the detour as '2mm' - the config stores the
bare number ('0' in the fixture), so the target is '2'. None of these
re-grid the cube: 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_261_single_wall_avoid"
GOAL = ("Keep single wall on top surfaces and the 200% one-wall threshold, "
        "enable single wall on the first layer, avoid crossing walls with a "
        "2 mm maximum detour length. Preserve the cube geometry, its "
        "placement, material assignment and every other setting.")
VALUES = {"only_one_wall_top": "1", "min_width_top_surface": "200%",
          "only_one_wall_first_layer": "1", "reduce_crossing_wall": "1",
          "max_travel_detour_distance": "2"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
