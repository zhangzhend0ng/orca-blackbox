"""Independent global X dimension, unchanged center/Y/Z, and resliced XY proof."""
from decimal import Decimal
import hashlib

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .pilot_common import inspect_preserved_settings
from .pilot_transform import _fixture_with_transform, _object_xy
from .project_3mf import _archive, _geometry, inspect_project
from .script_verify import _json

CASE_ID = "general_scale_cube_x"
GOAL = ("Resize the sole cube to a global X size of 40.5 mm. Preserve its 27 mm Y and Z "
        "sizes, keep the center and rotation unchanged, and preserve all project settings "
        "and material assignment. Edit the size using the visible canvas numeric field.")


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "scale_fixture_identity")
    baseline = _archive(fixture, cancelled)
    _, _, transform = _geometry(baseline)
    wanted = tuple(value * Decimal("1.5") if index in {0, 3, 6} else value
                   for index, value in enumerate(transform))
    expected = _fixture_with_transform(baseline, wanted)
    summary = inspect_project(project, expected, layer_height="0.4",
                              expected_assembly_transform=transform, cancelled=cancelled)
    actual = _archive(project, cancelled)
    geometry, _, _ = _geometry(actual)
    points = {point for face in geometry for point in face}
    bounds = [(min(p[axis] for p in points), max(p[axis] for p in points)) for axis in range(3)]
    _require(tuple(hi - lo for lo, hi in bounds) == (Decimal("40.5"), 27, 27), "scale_dimensions")
    inspect_preserved_settings(_json(actual["Metadata/project_settings.config"]),
        _json(baseline["Metadata/project_settings.config"]), cancelled=cancelled)
    layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
    _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2")
             and layers["object_tools"] == [0], "scale_layer_or_tool_schedule")
    xy = _object_xy(gcode, bounds, cancelled, minimum_span=(37, 23))
    summary["geometry_unchanged"] = False
    return dict(project=summary, gcode=layers, dimensions_mm=["40.5", "27", "27"],
                center_preserved=True, object_xy_bounds=xy)
