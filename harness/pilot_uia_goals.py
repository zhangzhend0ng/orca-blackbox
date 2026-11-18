"""Frozen business goals for UIA-first generalization and compound replay."""
import hashlib
from types import SimpleNamespace

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .pilot_common import QUALITY_ENUMS, inspect_preserved_settings, require_gcode_settings
from .pilot_material3 import _verify_logical_slot
from .pilot_top_layers import verify_shell_layers
from .pilot_transform import verify_translation
from .project_3mf import _archive, inspect_project
from .script_verify import _json


def bottom_layers(project, fixture, gcode, *, cancelled):
    return verify_shell_layers(project, fixture, gcode, surface="Bottom", count=6, cancelled=cancelled)


def move_y(project, fixture, gcode, *, cancelled):
    return verify_translation(project, fixture, gcode, axis="y", distance=8, cancelled=cancelled)


def walls_and_slot(project, fixture, gcode, *, cancelled):
    wall = {"wall_loops": "3"}
    summary = _verify_logical_slot(project, fixture, gcode, slot=2, cancelled=cancelled, allowed_changes=wall)
    require_gcode_settings(gcode, wall, "uia_combo_gcode_setting")
    return dict(summary, wall_loops=3, physical_wall_count_verified=False)


def quality_enums(project, fixture, gcode, *, cancelled):
    _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "quality_enums_fixture")
    original = _json(_archive(fixture, cancelled)["Metadata/project_settings.config"])
    actual = _json(_archive(project, cancelled)["Metadata/project_settings.config"])
    _require(original["ironing_type"] == "no ironing" and original["seam_position"] == "aligned",
             "quality_enums_initial_settings")
    project_info = inspect_project(project, fixture, layer_height="0.4", cancelled=cancelled)
    inspect_preserved_settings(actual, original, allowed_changes=QUALITY_ENUMS, cancelled=cancelled)
    require_gcode_settings(gcode, QUALITY_ENUMS, "quality_enums_gcode_setting")
    layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
    _require(layers["layer_count"] == 68 and layers["object_tools"] == [0], "quality_enums_toolpath")
    return {"project": project_info, "gcode": layers, "verified_settings": QUALITY_ENUMS}


def move_layer(project, fixture, gcode, *, cancelled):
    return verify_translation(project, fixture, gcode, axis="x", distance=10, cancelled=cancelled, layer_edit=True)


GOALS = {
    "bottom": SimpleNamespace(CASE_ID="general_bottom_shell_layers", verify_business=bottom_layers,
        GOAL="Set Bottom shell layers to 6. Preserve the sole cube, its placement, material and every other setting."),
    "move_y": SimpleNamespace(CASE_ID="general_move_y", verify_business=move_y,
        GOAL="Move the sole cube exactly 8 mm in the positive global Y direction from its loaded position. "
             "Preserve its dimensions, rotation, X/Z placement, material assignment and all project settings."),
    "combo": SimpleNamespace(CASE_ID="general_wall_loops_slot2", verify_business=walls_and_slot,
        GOAL="Set Wall loops to 3 and assign the whole cube to existing filament slot 2. "
             "Preserve geometry, placement, other project settings and global material/nozzle mappings."),
    "quality_enums": SimpleNamespace(CASE_ID="uia_quality_enums", verify_business=quality_enums,
        GOAL="On the loaded project, set Ironing Type to Topmost surface and Seam position to Random. "
             "Preserve the sole cube, material assignment, and all other settings."),
    "move_layer": SimpleNamespace(CASE_ID="uia_move_layer", verify_business=move_layer,
        GOAL="Move the sole cube exactly +10 mm in global X and set regular Layer height to 0.24 mm. "
             "Preserve First layer height 0.40 mm, Y/Z placement, shape, dimensions, rotation, "
             "materials and all other settings."),
}
