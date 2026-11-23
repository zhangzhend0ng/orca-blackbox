"""Feishu #280 (支撑熨烫, P0): support ironing enable/flow/spacing combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 199.
support_ironing=1, support_ironing_flow=10%, support_ironing_spacing=0.15,
support_ironing_pattern=rectilinear. All four keys live on the Support
page's 'Support ironing' group (Tab.cpp:2506-2510). ConfigManipulation
gates the checkbox on can_ironing_support = have_raft || (supports on &&
interface_top_layers > 0) (ConfigManipulation.cpp:712) - the fixture has
enable_support=0 / interface_top_layers=2, so the Enable checkbox leads
(enable_support=1 joins VALUES; #291 brim-type precedent for un-graying a
row). Flow already sits at '10%' and pattern at 'rectilinear' in the
fixture config - assertion-only. OCR paints the checkbox row 'lroning
Support lnterface' (leading-I quirk); 'roning' is the containment word
whose top-down first hit is the group's FIRST row - the checkbox itself
(the pattern/flow/spacing rows below have no checkbox). The cube carries
no overhangs, so no support/ironing geometry enters the G-code and the
schedule keeps 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_280_support_ironing"
GOAL = ("Enable supports, then enable support ironing and set its line "
        "spacing to 0.15 mm while flow stays 10% and pattern rectilinear. "
        "Preserve the cube geometry, its placement, material assignment and "
        "every other setting.")
# support_type: Tree (auto) support is not sliceable on this fixture - the
# ops switch to Normal (queue20, 2026-11-23); recorded deviation.
VALUES = {"enable_support": "1", "support_type": "normal(auto)", "support_ironing": "1",
          "support_ironing_flow": "10%", "support_ironing_spacing": "0.15",
          "support_ironing_pattern": "rectilinear"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
