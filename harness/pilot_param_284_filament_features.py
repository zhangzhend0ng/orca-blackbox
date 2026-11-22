"""Feishu #284 (特征用耗材-塔与支撑映射, P0): feature-filament mapping combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 203.
wipe_tower_filament=0, support_filament=1, support_interface_filament=0.
wipe_tower_filament actually lives on the Multimaterial page's
'Filament for Features' group (Tab.cpp:2574-2577), not the Support page
- it and support_interface_filament already sit at 0 in the fixture
config, so both stay assertion-only and the single op is the proven
#279 support body selector (rowcombo on the painted 'Support/Interface
filament' row). The table's two-filament precondition diverges: the
standard cube fixture carries a single filament, and single-material
G-code never tool-changes, so the mapping is proven as a config write
while the schedule keeps 68 x 0.4 / 27.2 (#279 precedent)."""
from .param_case_lib import make_verify

CASE_ID = "param_284_filament_features"
GOAL = ("Set the support body filament to 1 while the wipe tower and "
        "support interface filaments stay 0. Preserve the cube geometry, "
        "its placement, material assignment and every other setting.")
VALUES = {"wipe_tower_filament": "0", "support_filament": "1",
          "support_interface_filament": "0"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
