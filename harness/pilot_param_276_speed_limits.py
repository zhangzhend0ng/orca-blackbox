"""Feishu #276 (常用工艺参数, P0): speed/flow + machine-limit combination.

Snapshot row: docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/
tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 195. The table asks for
outer_wall_speed=700, layer_height=0.20, outer_wall_line_width=0.42,
filament_max_volumetric_speed=15 and machine_max_speed_x=500. The last two
live outside the process panel (filament profile / machine limits - the
fixture already stores machine_max_speed_x=500), so the V3 oracle proves
the three process-scope settings; divergence recorded here.

layer_height 0.20 re-grids the 27 mm cube: first 0.40 + 133 x 0.20 = 27.0
exactly -> 134 layers (same arithmetic as the #254 precedent, measured
135/27.05 for the 0.25 initial)."""
from .param_case_lib import make_verify
from .param_comparison import make_comparison_verify

CASE_ID = "param_276_speed_limits"
GOAL = ("Set outer wall speed to 700 mm/s, layer height to 0.20 mm and outer "
        "wall line width to 0.42 mm. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
VALUES = {"outer_wall_speed": "700", "layer_height": "0.2", "outer_wall_line_width": "0.42"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 134, "last_z": "27"})

COMPARISON_GOAL = (
    "On the standard cube, set process outer wall speed to 700 mm/s, layer height to 0.20 mm "
    "and outer wall line width to 0.42 mm. Set filament slot 1 PLA maximum volumetric speed "
    "to 15 mm³/s and confirm the printer's normal-mode X maximum speed is 500 mm/s. "
    "Preserve the other machine-limit mode, geometry, placement, material assignment, "
    "all other filament slots and unrelated settings."
)
verify_comparison = make_comparison_verify(
    "276", VALUES, {"filament_max_volumetric_speed": "15"}, {"machine_max_speed_x": "500"},
)
