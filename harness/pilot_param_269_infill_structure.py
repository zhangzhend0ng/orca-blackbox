"""Feishu #269 (强度高级, P1): advanced infill structure combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 188.
Two divergences (2026-11-23, upstream SnapmakerOrca source):
- internal_bridge_support_thickness is in the config loader's ignore list
  (PrintConfig.cpp:7281, the same list that drops overhang_totally_speed in
  #272) - this app cannot write it, so it stays out of VALUES.
- ensure_vertical_shell_thickness is a 4-slot enum (PrintConfig.cpp:1663-
  1676: none / ensure_critical_only / ensure_moderate / ensure_all). The
  table's '=1' is the fork's numeric slot 1 = ensure_critical_only ('Critical
  Only'); the fixture sits at 'ensure_all', so the combo moves All ->
  Critical Only (popup target one word: 'Critical' - the popup matcher is
  word-level containment, the #259 lesson).
detect_narrow_internal_solid_infill already equals the fixture value 1 -
assertion-only. The rows live in the Strength 'Advanced' group
(Tab.cpp:2407-2417); enabling infill_combination only appends its max-layer
sub-row BELOW the edited rows, and the combo runs last because a combo
commit rebuilds the page. Infill structure rewrites interior paths, not the
layer grid: 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_269_infill_structure"
GOAL = ("Enable infill combination, set minimum sparse infill threshold to "
        "10 mm2, external bridge infill direction to 45 deg and vertical "
        "shell thickness to critical-only, keeping narrow internal solid "
        "infill detection on. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
VALUES = {"infill_combination": "1", "minimum_sparse_infill_area": "10",
          "bridge_angle": "45", "detect_narrow_internal_solid_infill": "1",
          "ensure_vertical_shell_thickness": "ensure_critical_only"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
