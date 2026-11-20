"""Read-only +10mm global-X pilot. No GUI actions or acceptance self-signing."""
from decimal import Decimal
import hashlib
import io
import zipfile
import xml.etree.ElementTree as ET

from .agent_layer_verify import analyze_gcode, _LABEL
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .project_3mf import _archive, _geometry, _xml, _CORE, inspect_project
from .script_verify import _json, _check_cancel
from .pilot_common import MOVE_LAYER, inspect_preserved_settings, require_gcode_settings

CASE_ID = "pilot_model_move_x"
GOAL = ("Move the sole cube exactly 10 mm in the positive global X direction from its loaded position. "
        "Preserve its shape, dimensions, rotation, Y/Z position, regular Layer height 0.40 mm, "
        "First layer height 0.40 mm, material assignment and all printer/filament/process settings. "
        "Save the whole project at the assigned 3MF path.")


def _expected_fixture(fixture, cancelled, *, axis="x", distance=10):
    """Derive expected geometry from trusted fixture, never from AI output."""
    files = _archive(fixture, cancelled)
    _, _, original = _geometry(files)
    index = {"x": 9, "y": 10}[axis]
    wanted = original[:index] + (original[index] + distance,) + original[index + 1:]
    return _fixture_with_transform(files, wanted), wanted, original


def _fixture_with_transform(files, wanted):
    model = _xml(files["3D/3dmodel.model"])
    item = model.find(_CORE+"build/"+_CORE+"item")
    item.set("transform", " ".join(map(str, wanted)))
    files["3D/3dmodel.model"] = ET.tostring(model, encoding="utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return output.getvalue()


def _object_xy(raw, bounds, cancelled, *, minimum_span=(23, 23)):
    """Add XY scope to the shared layer/mode validator; ignore purge and travel."""
    lines = raw.decode("utf-8").splitlines()
    lo, hi = lines.index("; EXECUTABLE_BLOCK_START"), lines.index("; EXECUTABLE_BLOCK_END")
    body = lines[lo+1:hi]
    exclude = any(s.startswith("EXCLUDE_OBJECT_START NAME=") for s in body)
    active, absolute, relative_e = False, None, None
    pos = dict.fromkeys("XYZE")
    minimum, maximum = [None, None], [None, None]
    count = 0
    for index, line in enumerate(body):
        if index % 256 == 0:
            _check_cancel(cancelled)
        if exclude and line.startswith("EXCLUDE_OBJECT_"):
            if line.startswith("EXCLUDE_OBJECT_START NAME="): active = True
            elif line.startswith("EXCLUDE_OBJECT_END NAME="): active = False
            continue
        if not exclude and line.startswith(("; printing object", "; stop printing object")):
            match = _LABEL.fullmatch(line)
            _require(match is not None, "transform_gcode_label")
            active = match[1] == "printing"
            continue
        command = line.split(";", 1)[0].strip().split()
        if not command: continue
        op, *words = command
        if op in ("G90", "G91"): absolute = op == "G90"
        elif op in ("M82", "M83"): relative_e = op == "M83"
        elif op.startswith("T") and op[1:].isdigit(): pos["E"] = None
        elif op == "G28": pos = dict.fromkeys("XYZE")
        elif op in ("G2", "G3"):
            for axis in "XYZ": pos[axis] = None
        elif op in ("G0", "G1", "G92"):
            values = {word[0]: Decimal(word[1:]) for word in words}
            if op == "G92":
                pos.update({k:v for k,v in values.items() if k in pos})
                continue
            old = dict(pos)
            for axis in "XYZ":
                if axis in values:
                    pos[axis] = values[axis] if absolute else (None if old[axis] is None else old[axis]+values[axis])
            delta = Decimal(0)
            if "E" in values:
                delta = values["E"] if relative_e else values["E"]-old["E"]
                pos["E"] = (None if old["E"] is None else old["E"]+values["E"]) if relative_e else values["E"]
            if active and delta > 0 and any(axis in values and old[axis] != pos[axis] for axis in "XY"):
                _require(all(old[a] is not None and pos[a] is not None for a in "XY"), "transform_xy_unknown")
                for point in ((old["X"], old["Y"]), (pos["X"], pos["Y"])):
                    _require(all(bounds[a][0]-1 <= point[a] <= bounds[a][1]+1 for a in (0,1)),
                             "transform_gcode_outside_moved_cube")
                    count += 1
                    for a in (0,1):
                        minimum[a] = point[a] if minimum[a] is None else min(minimum[a], point[a])
                        maximum[a] = point[a] if maximum[a] is None else max(maximum[a], point[a])
    _require(count > 0, "transform_gcode_no_xy")
    extent = list(zip(minimum, maximum))
    _require(all(b-a >= span for (a,b), span in zip(extent, minimum_span)), "transform_gcode_footprint_too_small")
    return [[str(v) for v in pair] for pair in extent]


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    return verify_translation(project, fixture, gcode, axis="x", distance=10, cancelled=cancelled)


def verify_translation(project, fixture, gcode, *, axis, distance, cancelled, layer_edit=False, pair_settings=None):
    _require(type(fixture) is bytes and hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256,
             "transform_fixture_identity")
    expected, wanted, original_transform = _expected_fixture(fixture, cancelled, axis=axis, distance=distance)
    files = _archive(project, cancelled)
    geometry, _, transform = _geometry(files)
    _require(transform == wanted, "transform_build_delta")
    layer = "0.24" if layer_edit else "0.4"
    count, final_z = (112, "27.04") if layer_edit else (68, "27.2")
    summary = inspect_project(project, expected, layer_height=layer, cancelled=cancelled,
        expected_assembly_transform=original_transform)
    settings = pair_settings if pair_settings is not None else MOVE_LAYER if layer_edit else None
    inspect_preserved_settings(_json(files["Metadata/project_settings.config"]),
        _json(_archive(fixture, cancelled)["Metadata/project_settings.config"]),
        allowed_changes=settings, cancelled=cancelled)
    if settings:
        require_gcode_settings(gcode, settings, "transform_layer_echo" if pair_settings is None else "pair_gcode_settings")
    layers = analyze_gcode(gcode, layer_height=layer, cancelled=cancelled)
    _require(layers["layer_count"] == count and Decimal(layers["last_z"]) == Decimal(final_z)
             and layers["object_tools"] == [0], "transform_layer_or_tool_schedule")
    vertices = {point for triangle in geometry for point in triangle}
    bounds = [(min(p[a] for p in vertices),max(p[a] for p in vertices)) for a in (0,1)]
    xy = _object_xy(gcode, bounds, cancelled)
    summary["geometry_unchanged"] = False  # World placement deliberately changed.
    summary["shape_preserved"] = True
    return {"detail": f"Cube moved +{distance}mm global {axis.upper()}; layer heights {layer}/0.4; actual {count}-layer extrusion in moved XY bounds",
            "project": summary, "gcode": layers, f"translation_{axis}_mm": str(distance),
            "object_xy_bounds": xy, "other_fixture_settings_preserved": True}
