"""Feishu #258 (精度, P1): arc fitting + precise Z + resolution/gap closing.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 177.
All four keys live in the Quality 'Precision' group (Tab.cpp:2292-2305);
resolution and slice_closing_radius already equal the fixture config values
(0.012 / 0.049 - measured in fixtures/agent_layer_cube.3mf; the Feishu names
match the config keys exactly), so they stay assertion-only. Only the two
checkboxes move (enable_arc_fitting / precise_z_height, both coBool,
PrintConfig.cpp:3063 / :3054, fixture 0 -> 1). Arcs and precise Z rewrite
extrusion geometry, not the layer grid: 27.2 mm is an exact 68 x 0.4
multiple, so precise Z keeps the 68 x 0.4 / 27.2 schedule."""
from .param_case_lib import make_verify

CASE_ID = "param_258_arc_resolution"
GOAL = ("Enable arc fitting and precise Z height, keep resolution at 0.012 mm "
        "and slice gap closing radius at 0.049 mm. Preserve the cube geometry, "
        "its placement, material assignment and every other setting.")
VALUES = {"enable_arc_fitting": "1", "precise_z_height": "1",
          "resolution": "0.012", "slice_closing_radius": "0.049"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
