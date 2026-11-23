"""Feishu #281 (支撑高级-距离与界面, P0): support distances + interface combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 200.
support_top_z_distance=0.20, support_bottom_z_distance=0.20,
support_object_xy_distance=0.50, support_interface_top_layers=3,
support_interface_spacing=0, support_interface_pattern=rectilinear.
All six keys sit in the Support page's 'Advanced' group (Tab.cpp:2516-
2530); every one toggles on have_support_material
(ConfigManipulation.cpp:680-682), so the Enable checkbox leads
(enable_support=1 joins VALUES; #291 brim-type precedent). Top/bottom Z
distances already sit at 0.2 in the fixture config - assertion-only.
The pattern combo runs LAST (page rebuild, #269 recipe): its painted
value 'Auto' is single-band-unique once the Advanced group pre-scroll
pushes the Support group's 'Tree (auto)' out of band, and the popup's
first top-down 'Rectilinear' word is the plain pattern (before
'Rectilinear Interlaced'); a mis-land still fails loudly at the
painted-value verify. Labels with OCR leading-I get both spellings
('Top lnterface ...' first - the quirk is the measured default)."""
from .param_case_lib import make_verify

CASE_ID = "param_281_support_interface"
GOAL = ("Enable supports with top and bottom Z distance 0.2 mm, object xy "
        "distance 0.5 mm, 3 top interface layers, interface spacing 0 and "
        "interface pattern rectilinear. Preserve the cube geometry, its "
        "placement, material assignment and every other setting.")
# support_type: Tree (auto) support is not sliceable on this fixture
# (queue20 run 30a605d1) - the ops switch to Normal; recorded deviation.
VALUES = {"enable_support": "1", "support_type": "normal(auto)",
          "support_top_z_distance": "0.2",
          "support_bottom_z_distance": "0.2", "support_object_xy_distance": "0.5",
          "support_interface_top_layers": "3", "support_interface_spacing": "0",
          "support_interface_pattern": "rectilinear"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
