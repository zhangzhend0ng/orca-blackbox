"""Feishu #279 (常用工艺参数, P0): support body/interface filament combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 198.
support_filament=1, support_interface_filament=0. Measured on the 2.4.0
guest build (census c814315c, 2026-11-23): the support body filament is the
'Support/raft base' row of the Support tab's 'Filament for Supports' group -
there is no 'Support/Interface filament' row - and that row is greyed until
support is enabled. The ops therefore enable support first, and
enable_support=1 is admitted below as a recorded deviation from the case
text. The interface key already sits at 0 in the fixture config, so ops only
drive the body selector. The table's two-filament precondition (欧特克FDM测试
+ 2 耗材) diverges: the standard cube fixture carries one object filament."""
from .param_case_lib import make_verify

CASE_ID = "param_279_support_filament"
GOAL = ("Set the support body filament to 1 while the interface filament stays "
        "0. Preserve the cube geometry, its placement, material assignment and "
        "every other setting.")
# enable_support: the row is disabled while support is off (see above).
# enable_support, support_type: the row is disabled while support is off,
# and Tree (auto) support is not sliceable on this fixture (queue20 run
# a2d4a0f0) - both recorded deviations (see above).
VALUES = {"support_filament": "1", "support_interface_filament": "0",
          "enable_support": "1", "support_type": "normal(auto)"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
