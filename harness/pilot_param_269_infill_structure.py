"""Feishu #269 (强度高级, P1): advanced infill structure combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 188.
internal_bridge_support_thickness is ignored by this build's config loader
(PrintConfig.cpp:7281). The Feishu expectation calls for a complete vertical
shell. The fixture already uses ensure_all, so require it in the saved copy
alongside detect_narrow_internal_solid_infill. The driver edits the remaining
three values on the Strength page.
"""
from .param_case_lib import make_verify

CASE_ID = "param_269_infill_structure"
GOAL = ("Enable infill combination, set minimum sparse infill threshold to "
        "10 mm2, external bridge infill direction to 45 deg and preserve vertical "
        "shell thickness at All, keeping narrow internal solid "
        "infill detection on. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
VALUES = {"infill_combination": "1", "minimum_sparse_infill_area": "10",
          "bridge_angle": "45", "detect_narrow_internal_solid_infill": "1",
          "ensure_vertical_shell_thickness": "ensure_all"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
