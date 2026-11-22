"""Feishu #265 (悬垂, P1): overhang forced cooling + curled-perimeter slow-down.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 184.
Divergence (2026-11-23, upstream SnapmakerOrca source): the three fan keys
are FILAMENT-scope rows - they live on the Filament preset's Cooling page
'Part cooling fan' group (Tab.cpp:3847-3865), not on any process-panel page,
so the declarative process ops cannot reach them (#276 precedent). The
fixture also serializes them as per-slot vectors (enable_overhang_bridge_fan
['1'x5] = already at the target 1; overhang_fan_threshold ['10%','50'..'..']
with slot 0 already at the 10% target; overhang_fan_speed slot 0 '90' vs the
80% target - unreachable) and the scalar verifier only normalizes
one-element lists, so they stay out of VALUES entirely. The fourth key is
process-scope: slowdown_for_curled_perimeters (coBool,
PrintConfig.cpp:1245) on the Speed tab's 'Overhang speed' group
(Tab.cpp:2438), fixture 0 -> 1 via its checkbox. Slow-down changes speeds,
not the layer grid: 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_265_overhang_curl"
GOAL = ("Enable slow down for curled perimeters. Preserve the cube geometry, "
        "its placement, material assignment and every other setting.")
VALUES = {"slowdown_for_curled_perimeters": "1"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
