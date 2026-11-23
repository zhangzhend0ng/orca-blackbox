"""Feishu #292 (常用工艺参数, P0): by-object print sequence + clearances.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 211.
print_sequence=by object, extruder_clearance_radius=20,
extruder_clearance_height_to_rod=30. Stored enum spells 'by object' with
a space (fixture default 'by layer', read from the fixture config). The
table's two-object precondition diverges: the standard single cube makes
by-object a no-op for sequencing, so the oracle proves the config writes
and the unchanged schedule."""
from .param_case_lib import make_verify

CASE_ID = "param_292_by_object"
GOAL = ("Set print sequence to by object with extruder clearance radius 20 mm "
        "and height to rod 30 mm. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
# 2026-11-23: extruder_clearance_* dropped - atlas places them on the
# PRINTER settings page (Basic information), unreachable from the process
# panel (precedent: raft_expansion).
VALUES = {"print_sequence": "by object"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
