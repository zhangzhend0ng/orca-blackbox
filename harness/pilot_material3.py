"""Finite slot-3 material goal, sharing slot-2's plate and parser semantics."""
from decimal import Decimal
import hashlib
import xml.etree.ElementTree as ET
import zipfile

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .pilot_common import inspect_preserved_settings
from .pilot_material import _plate_mapping
from .project_3mf import _archive, inspect_project
from .script_verify import _InvalidEvidence, _check_cancel, _json

CASE_ID = "pilot_material_slot3"
GOAL = ("Assign the existing whole cube to filament slot 3 and save the project. "
        "Keep the cube geometry, regular and first layer heights at 0.40 mm, "
        "all global filament/nozzle mappings, material presets and other process settings unchanged. "
        "Do not add materials, paint the model, or change printer presets.")

_SLOTS = {2: ("pilot_material_slot2", 1), 3: (CASE_ID, 2)}


def _verify_logical_slot(project, fixture, gcode, *, slot, cancelled, allowed_changes=None):
    """Trusted finite helper; public entry pins 3, not an actor-selected parameter.

    The root may later route the old slot-2 entry here without copying this
    parser. This task deliberately does not edit that existing entry.
    """
    _require(type(slot) is int and slot in _SLOTS, "material_target_not_registered")
    _check_cancel(cancelled)
    _require(type(fixture) is bytes and hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256,
             "material_fixture_identity")
    case_id, tool = _SLOTS[slot]
    try:
        actual, original = _archive(project, cancelled), _archive(fixture, cancelled)
        original_config = _json(original["Metadata/project_settings.config"])
        names = original_config.get("filament_settings_id")
        _require(type(names) is list and len(names) == 5 and type(names[slot-1]) is str
                 and bool(names[slot-1]), "material_fixture_slot_missing")
        summary = inspect_project(project, fixture, layer_height="0.4", expected_extruder=str(slot),
                                  cancelled=cancelled)
        inspect_preserved_settings(_json(actual["Metadata/project_settings.config"]), original_config,
                                  allowed_changes=allowed_changes, cancelled=cancelled)
        _require(_plate_mapping(actual) == _plate_mapping(original), "material_plate_mapping_changed")
        layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
        _require(layers["object_tools"] == [tool], "material_object_tool_not_T"+str(tool))
        _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2"),
                 "material_layer_schedule")
        _check_cancel(cancelled)
        return {"case_id": case_id, "project_sha256": summary["sha256"],
                "gcode_sha256": layers["sha256"], "object_filament_slot": slot,
                "object_tools": layers["object_tools"], "layer_count": layers["layer_count"],
                "last_z": layers["last_z"], "geometry_unchanged": True,
                "physical_nozzle_mapping_verified": False, "printing_verified": False}
    except _InvalidEvidence:
        raise
    except (ValueError, TypeError, KeyError, ArithmeticError, ET.ParseError, zipfile.BadZipFile,
            RuntimeError, RecursionError) as exc:
        raise _InvalidEvidence("material_evidence_invalid") from exc


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    """Require slot 3 and actual object T2; runtime owns the reopen provenance."""
    return _verify_logical_slot(project, fixture, gcode, slot=3, cancelled=cancelled)
