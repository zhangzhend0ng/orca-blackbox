"""Feishu #284 (特征用耗材-塔与支撑映射, P0): feature-filament mapping combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 203.
wipe_tower_filament=0, support_filament=1, support_interface_filament=0.
Measured on the 2.4.0 guest build (census 40989dec / c814315c, 2026-11-23):
the Multimaterial page's 'Filament for Features' group holds Walls / Infill
/ Solid infill / Wipe tower only - no support row - and the support body
filament is the 'Support/raft base' row of the Support tab (#279), which is
greyed until support is enabled. wipe_tower_filament and
support_interface_filament already sit at 0 in the fixture config, so both
stay assertion-only; the ops are the #279 ops (enable support, then the
'Support/raft base' selector), and enable_support=1 is admitted below as a
recorded deviation from the case text. The table's two-filament precondition
diverges: the standard cube fixture carries one object filament, and
single-material G-code never tool-changes, so the mapping is proven as a
config write while the schedule keeps 68 x 0.4 / 27.2 (#279 precedent)."""
from .param_case_lib import make_verify

CASE_ID = "param_284_filament_features"
GOAL = ("Set the support body filament to 1 while the wipe tower and "
        "support interface filaments stay 0. Preserve the cube geometry, "
        "its placement, material assignment and every other setting.")
# enable_support, support_type: as in #279 (row disabled while support is
# off; Tree (auto) support is not sliceable on this fixture).
VALUES = {"wipe_tower_filament": "0", "support_filament": "1",
          "support_interface_filament": "0", "enable_support": "1",
          "support_type": "normal(auto)"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
