"""Feishu #258 (精度, P1): arc fitting + precise Z + resolution/gap closing.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 177.
All four keys live in the Quality 'Precision' group (Tab.cpp:2292-2305);
resolution and slice_closing_radius already equal the fixture config values
(0.012 / 0.049 - measured in fixtures/agent_layer_cube.3mf; the Feishu names
match the config keys exactly), so they stay assertion-only. Only the two
checkboxes move (enable_arc_fitting / precise_z_height, both coBool,
PrintConfig.cpp:3063 / :3054, fixture 0 -> 1).

Recorded (2026-11-24, VM runs 0fe51b33 / 56846c08): all four values
land, but the uniform 0.4 oracle does not hold under precise Z - and the
docstring above was wrong about the cube. The mesh is 27.0 mm tall
(-13.5..13.5). Without precise Z the slicer prints 68 layers on the 0.4
grid and the top one at Z 27.2 (the grid rounded up: what the
'68 x 0.4 / 27.2' oracle of the other cases measures). With precise Z the
grid ends exactly at the object: 63 steps of 0.4, then five of 0.36, last
Z 27.0. analyze_gcode requires uniform steps, so this case proves the
four writes + settings preservation; the measured grid is on file here
instead of an oracle (schedule=None, precedent #278)."""
from .param_case_lib import make_verify

CASE_ID = "param_258_arc_resolution"
GOAL = ("Enable arc fitting and precise Z height, keep resolution at 0.012 mm "
        "and slice gap closing radius at 0.049 mm. Preserve the cube geometry, "
        "its placement, material assignment and every other setting.")
VALUES = {"enable_arc_fitting": "1", "precise_z_height": "1",
          "resolution": "0.012", "slice_closing_radius": "0.049"}
verify_business = make_verify(CASE_ID, VALUES)
