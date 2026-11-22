"""Feishu #275 (抖动, P1): per-feature jerk combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 194.
All six keys are plain float rows in the Speed 'Jerk(XY)' group
(Tab.cpp:2468-2477) - no master switch gates them. infill_jerk already
equals the fixture value 9 = the target, so it stays assertion-only; the
other five move (fixture paints default 0 / outer 9 / inner 9 / initial 9 /
travel 12). The rows paint SHORT feature names ('Default' / 'Outer wall' /
'Inner wall' / 'Initial layer' / 'Travel') shared with the speed and
acceleration groups ABOVE - but Jerk(XY) is the second group from the page
bottom, so scrolling it into view pushes all of those out of the band. The
value-anchored phrase candidates (#272 recipe) lead anyway, re-anchored per
edit to the values the previous edit painted; the plain fallbacks resolve
top-down to the jerk rows ('Default' matches default_jerk above
'Default junction deviation'). Jerk limits corner speed only - the layer
grid keeps the 68 x 0.4 / 27.2 schedule."""
from .param_case_lib import make_verify

CASE_ID = "param_275_jerk"
GOAL = ("Set default jerk to 8, initial layer jerk to 4, outer wall jerk to "
        "5, inner wall jerk to 6 and travel jerk to 10, keeping infill jerk "
        "at 9. Preserve the cube geometry, its placement, material "
        "assignment and every other setting.")
VALUES = {"default_jerk": "8", "initial_layer_jerk": "4",
          "outer_wall_jerk": "5", "inner_wall_jerk": "6",
          "infill_jerk": "9", "travel_jerk": "10"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
