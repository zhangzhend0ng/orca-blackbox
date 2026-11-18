"""Independent saved top-shell setting and resliced object evidence."""
from decimal import Decimal
import hashlib

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .pilot_common import inspect_preserved_settings, require_gcode_settings
from .pilot_infill import _feature_extrusion_moves
from .project_3mf import _archive, inspect_project
from .script_verify import _json

CASE_ID = "general_top_shell_layers"
GOAL = ("Set Top shell layers to 5 for the loaded cube. Preserve geometry, placement, "
        "material assignment, and every other project setting.")


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "top_fixture_identity")
    summary = inspect_project(project, fixture, layer_height="0.4", cancelled=cancelled)
    actual = _json(_archive(project, cancelled)["Metadata/project_settings.config"])
    baseline = _json(_archive(fixture, cancelled)["Metadata/project_settings.config"])
    inspect_preserved_settings(actual, baseline, allowed_changes={"top_shell_layers": "5"}, cancelled=cancelled)
    layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
    require_gcode_settings(gcode, {"top_shell_layers": "5"}, "top_gcode_setting")
    _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2")
             and layers["object_tools"] == [0], "top_layer_or_tool_schedule")
    moves = _feature_extrusion_moves(gcode, cancelled, "Top surface")
    _require(moves > 0, "top_surface_no_extrusion")
    return dict(project=summary, gcode=layers, top_shell_layers=5,
                top_surface_positive_xy_e_moves=moves, physical_shell_count_verified=False)
