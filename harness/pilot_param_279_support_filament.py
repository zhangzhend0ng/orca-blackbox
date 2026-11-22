"""Feishu #279 (常用工艺参数, P0): support body/interface filament combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 198.
support_filament=1, support_interface_filament=0. The table's two-filament
precondition (欧特克FDM测试 + 2 耗材) diverges: the standard cube fixture
carries a single filament, and the 'Support/Interface filament' row may be
hidden on a single-extruder machine - the guest run decides. The interface
key already sits at 0 in the fixture config, so ops only drive the body
selector."""
from .param_case_lib import make_verify

CASE_ID = "param_279_support_filament"
GOAL = ("Set the support body filament to 1 while the interface filament stays "
        "0. Preserve the cube geometry, its placement, material assignment and "
        "every other setting.")
VALUES = {"support_filament": "1", "support_interface_filament": "0"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
