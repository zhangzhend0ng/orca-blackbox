"""Read-only logical filament-slot proof; no claim about physical printer mapping."""
from decimal import Decimal
import hashlib
import xml.etree.ElementTree as ET
import zipfile

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .project_3mf import _archive, _xml, inspect_project
from .script_verify import _InvalidEvidence, _check_cancel, _json

CASE_ID = "pilot_material_slot2"
GOAL = ("Assign the existing whole cube to filament slot 2 and save the project. "
        "Keep the cube geometry, regular and first layer heights at 0.40 mm, "
        "all global filament/nozzle mappings, material presets and other process settings unchanged. "
        "Do not add materials, paint the model, or change printer presets.")

from .pilot_common import inspect_preserved_settings


def _plate_mapping(files):
    root = _xml(files["Metadata/model_settings.config"])
    plates = root.findall("plate")
    _require(len(plates) == 1, "material_plate_count")
    result = {}
    for row in plates[0].findall("metadata"):
        key = row.get("key")
        if key in {"filament_map_mode", "filament_maps"}:
            _require(key not in result, "material_duplicate_mapping")
            result[key] = row.get("value")
    _require(set(result) == {"filament_map_mode", "filament_maps"}, "material_mapping_missing")
    return result


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    """Validate saved slot 2 AND T1 on actual object XY/E moves after trusted reopen.

    Phase custody/reopen provenance belongs to the enclosing native runtime.
    Synthetic tests exercise this parser, never prove GUI execution or printing.
    """
    _check_cancel(cancelled)
    _require(type(fixture) is bytes and hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256,
             "material_fixture_identity")
    try:
        summary = inspect_project(project, fixture, layer_height="0.4", expected_extruder="2",
                                  cancelled=cancelled)
        actual, original = _archive(project, cancelled), _archive(fixture, cancelled)
        inspect_preserved_settings(_json(actual["Metadata/project_settings.config"]),
                                    _json(original["Metadata/project_settings.config"]), cancelled=cancelled)
        _require(_plate_mapping(actual) == _plate_mapping(original), "material_plate_mapping_changed")
        layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
        _require(layers["object_tools"] == [1], "material_object_tool_not_T1")
        _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2"),
                 "material_layer_schedule")
        _check_cancel(cancelled)
        return {"case_id": CASE_ID, "project_sha256": summary["sha256"],
                "gcode_sha256": layers["sha256"], "object_filament_slot": 2,
                "object_tools": layers["object_tools"], "layer_count": layers["layer_count"],
                "last_z": layers["last_z"], "geometry_unchanged": True,
                "physical_nozzle_mapping_verified": False, "printing_verified": False}
    except _InvalidEvidence:
        raise
    except (ValueError, TypeError, KeyError, ArithmeticError, ET.ParseError, zipfile.BadZipFile,
            RuntimeError, RecursionError) as exc:
        raise _InvalidEvidence("material_evidence_invalid") from exc
