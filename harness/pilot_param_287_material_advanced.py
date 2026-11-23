"""Feishu #287 (材料高级-界面外壳与工具, P1): interface shells + tool combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 206.
interface_shells=2, support_filament=1, support_interface_filament=0.
Recorded divergence: interface_shells is coBool
(PrintConfig.cpp:3473 'Interface shells') - the table's '=2 layer count'
is not representable; the checkbox writes 1 and the header records the
deviation (#267 precedent). The row sits in the Multimaterial page's
'Advanced' group (Tab.cpp:2590) with no gating toggle found - 'shells'
is the band-unique containment word (OCR-safe, no leading I).
support_filament repeats the #279 ops on the Support page: enable support,
then the 'Support/raft base' selector (the row is greyed while support is
off; census c814315c) - so enable_support=1 is admitted below as a recorded
deviation, like in #279 (support_interface_filament already 0 -
assertion-only). The single-material cube keeps the schedule at 68 x 0.4 /
27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_287_material_advanced"
GOAL = ("Enable interface shells, set the support body filament to 1 while "
        "the support interface filament stays 0. Preserve the cube geometry, "
        "its placement, material assignment and every other setting.")
# enable_support, support_type: as in #279.
VALUES = {"interface_shells": "1", "support_filament": "1",
          "support_interface_filament": "0", "enable_support": "1",
          "support_type": "normal(auto)"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
