"""Frozen business goals for the UIA-first generalization comparison."""
from types import SimpleNamespace

from .pilot_common import require_gcode_settings
from .pilot_material3 import _verify_logical_slot
from .pilot_top_layers import verify_shell_layers
from .pilot_transform import verify_translation


def bottom_layers(project, fixture, gcode, *, cancelled):
    return verify_shell_layers(project, fixture, gcode, surface="Bottom", count=6, cancelled=cancelled)


def move_y(project, fixture, gcode, *, cancelled):
    return verify_translation(project, fixture, gcode, axis="y", distance=8, cancelled=cancelled)


def walls_and_slot(project, fixture, gcode, *, cancelled):
    wall = {"wall_loops": "3"}
    summary = _verify_logical_slot(project, fixture, gcode, slot=2, cancelled=cancelled, allowed_changes=wall)
    require_gcode_settings(gcode, wall, "uia_combo_gcode_setting")
    return dict(summary, wall_loops=3, physical_wall_count_verified=False)


GOALS = {
    "bottom": SimpleNamespace(CASE_ID="general_bottom_shell_layers", verify_business=bottom_layers,
        GOAL="Set Bottom shell layers to 6. Preserve the sole cube, its placement, material and every other setting."),
    "move_y": SimpleNamespace(CASE_ID="general_move_y", verify_business=move_y,
        GOAL="Move the sole cube exactly 8 mm in the positive global Y direction from its loaded position. "
             "Preserve its dimensions, rotation, X/Z placement, material assignment and all project settings."),
    "combo": SimpleNamespace(CASE_ID="general_wall_loops_slot2", verify_business=walls_and_slot,
        GOAL="Set Wall loops to 3 and assign the whole cube to existing filament slot 2. "
             "Preserve geometry, placement, other project settings and global material/nozzle mappings."),
}
