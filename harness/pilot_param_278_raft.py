"""Feishu #278 (常用工艺参数, P0): raft structure/spacing/expansion combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 197.
raft_layers=3, raft_contact_distance=0.20, raft_expansion=5,
raft_first_layer_density=100%, raft_first_layer_expansion=5. Percent keys
keep the stored '%' suffix (fixture default '90%', #268 '20%' precedent).

schedule: intentionally None - three raft layers print BELOW the model, so
the 68 x 0.4 / 27.2 object oracle does not apply and no measured raft
schedule is on file yet. The first guest run records the measured
layer_count/last_z and pins them here; until then the oracle proves the
five config writes + full settings preservation."""
from .param_case_lib import make_verify

CASE_ID = "param_278_raft"
GOAL = ("Set raft layers to 3, contact distance 0.2 mm, expansion 5 mm, first "
        "layer density 100% and first layer expansion 5 mm. Preserve the cube "
        "geometry, its placement, material assignment and every other setting.")
# 2026-11-23: raft_expansion dropped - no UI row exists on the params page
# (Tab.cpp line 2928-2921 appends only the other four). Recorded deviation
# from the Feishu row, precedent: #267 top_color_penetration_layers.
VALUES = {"raft_layers": "3", "raft_contact_distance": "0.2",
          "raft_first_layer_density": "100%", "raft_first_layer_expansion": "5"}
verify_business = make_verify(CASE_ID, VALUES)
