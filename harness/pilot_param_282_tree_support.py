"""Feishu #282 (支撑高级-树状支撑, P1): tree support branch combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 201.
support_type=tree(auto), tree_support_branch_angle=40,
tree_support_branch_diameter=2, tree_support_adaptive_layer_height=1,
tree_support_wall_count=1, max_bridge_length=30. support_type already
sits at 'tree(auto)' in the fixture config - assertion-only. Recorded
engine divergence (the case's central finding): this fork defaults
support_style to 'default' and treats that as ORGANIC
(ConfigManipulation.cpp:691-703 'Orca: use organic as default'), which
hides tree_support_branch_angle / tree_support_adaptive_layer_height /
max_bridge_length (organic trees use bridge_no_support instead). The
table's combination is only reachable with a SlimTree style, so the ops
set support_style=tree_slim ('Tree Slim', popup word 'Slim' unique) -
support_style joins VALUES as a documented addition. branch_diameter and
adaptive_layer_height already equal the targets - assertion-only. The
Style combo sits mid-sequence (rows appear only after it); every later
float op re-anchors by its own group scroll, and locate 'Default' is
top-down-first at the Support group's Style row (the Advanced group's
same-valued Base pattern row sits below). tree_support_wall_count and
max_bridge_length live in the 'Advanced' group (Tab.cpp:2518/2533),
branch_angle in 'Tree supports' (Tab.cpp:2544). The cube carries no
overhangs, so no tree branches enter the G-code and the schedule keeps
68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_282_tree_support"
GOAL = ("Enable supports with type tree (auto) and style Tree Slim, set "
        "branch angle to 40 deg, support wall loops to 1 and max bridge "
        "length to 30 mm, keeping branch diameter 2 mm and adaptive layer "
        "height on. Preserve the cube geometry, its placement, material "
        "assignment and every other setting.")
VALUES = {"enable_support": "1", "support_type": "tree(auto)",
          "support_style": "tree_slim", "tree_support_branch_angle": "40",
          "tree_support_branch_diameter": "2",
          "tree_support_adaptive_layer_height": "1",
          "tree_support_wall_count": "1", "max_bridge_length": "30"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
