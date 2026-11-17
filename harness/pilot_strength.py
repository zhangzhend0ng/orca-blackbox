"""Read-only wall-loop pilot oracle; runtime custody remains the caller's job."""
from decimal import Decimal
import hashlib

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .gcode_check import config_value_all
from .project_3mf import _archive, inspect_project
from .script_verify import _json

CASE_ID = "pilot_strength_wallloops"
GOAL = ("Set Wall loops to 3 in the loaded cube project. Preserve regular Layer height 0.40 mm, "
        "First layer height 0.40 mm, the cube geometry and placement, all other settings, "
        "and printer/filament/process presets. Save the whole project at the assigned 3MF path.")

from .pilot_common import inspect_preserved_settings


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    """Require saved intent and resliced extrusion; does not count physical walls."""
    _require(type(fixture) is bytes and hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256,
             "strength_fixture_identity")
    summary = inspect_project(project, fixture, layer_height="0.4", cancelled=cancelled)
    config = _json(_archive(project, cancelled)["Metadata/project_settings.config"])
    original = _json(_archive(fixture, cancelled)["Metadata/project_settings.config"])
    inspect_preserved_settings(config, original, allowed_changes={"wall_loops": "3"}, cancelled=cancelled)
    layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
    lines = gcode.decode("utf-8").splitlines()
    lo, hi = lines.index("; CONFIG_BLOCK_START"), lines.index("; CONFIG_BLOCK_END")
    echoes = config_value_all("\n".join(lines[lo+1:hi]).encode("utf-8"), "wall_loops")
    _require(bool(echoes) and all(x == "3" for x in echoes), "strength_gcode_wall_loops")
    _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2")
             and layers["object_tools"] == [0], "strength_layer_or_tool_schedule")
    return {"detail": "Wall loops 3 saved; unchanged .4/.4 cube; reopened 68-layer extrusion",
            "project": summary, "gcode": layers, "wall_loops": 3,
            "other_fixture_settings_preserved": True, "physical_wall_count_verified": False}
