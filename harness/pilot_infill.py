"""Bounded infill intent plus actual object sparse-extrusion presence oracle."""
from decimal import Decimal
import hashlib
import re

from .agent_layer_verify import analyze_gcode, _LABEL
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .gcode_check import config_value_all
from .pilot_common import inspect_preserved_settings
from .project_3mf import _archive, inspect_project
from .script_verify import _check_cancel, _json

CASE_ID = "pilot_strength_infill30"
GOAL = ("Set Sparse infill density to 30% in the loaded cube project. Preserve its Grid sparse "
        "infill pattern, Wall loops 2, regular Layer height 0.40 mm, First layer height 0.40 mm, "
        "cube geometry and placement, materials, presets and every other setting. "
        "Save the whole project at the assigned 3MF path.")


def _feature_extrusion_moves(raw, cancelled, feature):
    """Called only after analyze_gcode validates this exact byte stream.

    Feature labels classify the region; actual coordinates and positive E
    establish extrusion. We do not infer geometric density from the label.
    """
    lines = raw.decode("utf-8").splitlines()
    lo, hi = lines.index("; EXECUTABLE_BLOCK_START"), lines.index("; EXECUTABLE_BLOCK_END")
    exclude_mode = any(line.startswith("EXCLUDE_OBJECT_") and not line.startswith("EXCLUDE_OBJECT_DEFINE")
                       for line in lines[lo+1:hi])
    xyz_absolute = e_relative = None
    pos = {k: None for k in "XYE"}
    active = sparse = False
    moves = 0
    for index, line in enumerate(lines[lo+1:hi]):
        if index % 256 == 0:
            _check_cancel(cancelled)
        if line.startswith("EXCLUDE_OBJECT_START NAME="):
            active, sparse = True, False
            continue
        if line.startswith("EXCLUDE_OBJECT_END NAME="):
            active, sparse = False, False
            continue
        label = None if exclude_mode else _LABEL.fullmatch(line)
        if label:
            active, sparse = label.group(1) == "printing", False
            continue
        if line.startswith(";TYPE:"):
            sparse = line == ";TYPE:" + feature
            continue
        words = line.split(";", 1)[0].split()
        if not words:
            continue
        op = words[0]
        if op in {"G90", "G91"}:
            xyz_absolute = op == "G90"
        elif op in {"M82", "M83"}:
            e_relative = op == "M83"
        elif re.fullmatch(r"T\d+", op):
            pos["E"] = None
        elif op in {"G2", "G3", "G28"}:
            pos["X"] = pos["Y"] = None
            if op == "G28":
                pos["E"] = None
        elif op in {"G0", "G1", "G92"}:
            values = {w[0]: Decimal(w[1:]) for w in words[1:]}
            if op == "G92":
                if "E" in values:
                    pos["E"] = values["E"]
                continue
            old = dict(pos)
            for axis in "XY":
                if axis in values:
                    pos[axis] = values[axis] if xyz_absolute else (
                        None if old[axis] is None else old[axis]+values[axis])
            delta_e = Decimal(0)
            if "E" in values:
                if e_relative:
                    delta_e = values["E"]
                    pos["E"] = None if old["E"] is None else old["E"]+delta_e
                else:
                    _require(old["E"] is not None, "infill_unknown_absolute_e")
                    delta_e = values["E"]-old["E"]
                    pos["E"] = values["E"]
            known = all(old[a] is not None and pos[a] is not None for a in "XY")
            moved = any(a in values and pos[a] != old[a] for a in "XY")
            if active and sparse and known and moved and delta_e > 0:
                moves += 1
    return moves


def _sparse_extrusion_moves(raw, cancelled):
    moves = _feature_extrusion_moves(raw, cancelled, "Sparse infill")
    _require(moves > 0, "infill_missing_sparse_xy_extrusion")
    return moves


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    _require(type(fixture) is bytes and hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256,
             "infill_fixture_identity")
    model = inspect_project(project, fixture, layer_height="0.4", cancelled=cancelled)
    config = _json(_archive(project, cancelled)["Metadata/project_settings.config"])
    original = _json(_archive(fixture, cancelled)["Metadata/project_settings.config"])
    _require(original.get("sparse_infill_density") == "15%"
             and config.get("sparse_infill_density") == "30%"
             and config.get("sparse_infill_pattern") == "grid"
             and config.get("wall_loops") == "2", "infill_target_settings")
    inspect_preserved_settings(config, original,
        allowed_changes={"sparse_infill_density": "30%"}, cancelled=cancelled)
    layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
    _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2")
             and layers["object_tools"] == [0], "infill_layer_or_tool_schedule")
    lines = gcode.decode("utf-8").splitlines()
    lo, hi = lines.index("; CONFIG_BLOCK_START"), lines.index("; CONFIG_BLOCK_END")
    block = "\n".join(lines[lo+1:hi]).encode("utf-8")
    for key, value in (("sparse_infill_density", "30%"), ("sparse_infill_pattern", "grid"), ("wall_loops", "2")):
        echoes = config_value_all(block, key)
        _require(bool(echoes) and all(v == value for v in echoes), "infill_gcode_setting_mismatch")
    moves = _sparse_extrusion_moves(gcode, cancelled)
    return {"detail": "Infill 30% saved; unchanged .4/.4 cube; actual sparse XY/E extrusion",
            "project": model, "gcode": layers, "sparse_infill_density": "30%",
            "sparse_positive_xy_e_moves": moves, "other_fixture_settings_preserved": True,
            "physical_density_ratio_verified": False}
