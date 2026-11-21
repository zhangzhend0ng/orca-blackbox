"""Feishu #267 (常用工艺参数, P0): shell layers and surface patterns.

top_shell_layers=5, bottom_shell_layers=3, top_surface_pattern=concentric,
bottom_surface_pattern=rectilinear. The table also lists
top_color_penetration_layers=3, which the fixture's settings do not carry
(no painted colors on the plain cube): recorded scope reduction in the
migration ledger; the four carried keys are verified fully."""
from .param_case_lib import make_verify

CASE_ID = "param_267_shells_pattern"
GOAL = ("Set top shell layers to 5, bottom shell layers to 3, top surface pattern to concentric "
        "and bottom surface pattern to rectilinear. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
VALUES = {"top_shell_layers": "5", "bottom_shell_layers": "3",
          "top_surface_pattern": "concentric", "bottom_surface_pattern": "rectilinear"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
