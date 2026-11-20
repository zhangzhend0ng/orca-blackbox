"""Independent persistence check for the two recipes in the m4i-style case."""
import hashlib
import re

from .agent_verify import _require
from .gcode_check import config_value_all
from .project_3mf import _archive, _geometry, _xml
from .script_verify import _json

FIXTURE = "fixtures/mixed_filament_test.3mf"
FIXTURE_SHA256 = "ea00678017a7b6d7d65a4280b8f80c2d441493fd15998a924c66998ac946ccf0"
CASE_ID = "uia_mix_recipes"
GOAL = ("Keep the existing mixing scheme and add two new custom schemes for the compatible PLA pair F3 and F2. "
        "Add one 50/50 Ratio scheme and one Gradient scheme with the original 80% to 20% endpoints. Keep the current object's assignment, "
        "geometry, placement, and other project settings unchanged. Save all three schemes in the project.")


def definitions(serialized):
    """Index the frozen SUT's serialized mix rows by stable ID."""
    _require(type(serialized) is str and 1 <= len(serialized) <= 16384, "mix_definition_scope")
    rows = {}
    for value in serialized.split(";"):
        row = tuple(value.split(","))
        _require(len(row) >= 16 and re.fullmatch(r"u[1-9][0-9]*", row[14]) is not None
                 and row[14] not in rows, "mix_definition_identity")
        rows[row[14]] = row
    return rows


def verify_definitions(before, after, exported):
    original, saved, echoed = map(definitions, (before, after, exported))
    _require(len(original) == 1 and len(saved) == 3 and saved == echoed
             and all(saved.get(key) == row for key, row in original.items()), "mix_definition_persistence")
    added = [row for key, row in saved.items() if key not in original]
    _require(all(set(row[:2]) == {"2", "3"} and row[2:4] == ("1", "1") and row[12] == "d0" for row in added),
             "mix_definition_components")
    _require({row[15] for row in added} == {"cm0", "cm3"}, "mix_definition_modes")
    for row in added:
        gradients = [part for part in row[16:] if part.startswith("r1/")]
        if row[15] == "cm0":
            _require(row[4] == "50" and not gradients, "mix_definition_ratio")
        else:
            _require(len(gradients) == 1 and gradients[0] in {"r1/0.8000/0.2000", "r1/0.2000/0.8000"},
                     "mix_definition_gradient")
    return sorted(saved.keys() - original.keys())


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    _require(hashlib.sha256(fixture).hexdigest() == FIXTURE_SHA256, "mix_fixture_identity")
    saved, original = _archive(project, cancelled), _archive(fixture, cancelled)
    geometry, object_id, transform = _geometry(saved, allow_colour_paint=True)
    original_geometry, original_id, original_transform = _geometry(original, allow_colour_paint=True)
    _require((geometry, transform) == (original_geometry, original_transform), "mix_geometry_changed")
    for files, identity in ((saved, object_id), (original, original_id)):
        settings = _xml(files["Metadata/model_settings.config"])
        objects = settings.findall("object")
        _require(len(objects) == 1 and objects[0].get("id") == identity
                 and [item.get("value") for item in objects[0].findall("metadata[@key='extruder']")] == ["6"],
                 "mix_existing_assignment_changed")
    cfg_name = "Metadata/project_settings.config"
    before, after = (_json(files[cfg_name]) for files in (original, saved))
    stable = ("filament_type", "filament_colour", "nozzle_diameter", "layer_height", "initial_layer_print_height")
    _require(all(key in before and before[key] == after.get(key) for key in stable), "mix_fixture_settings_changed")
    start, end = b"; EXECUTABLE_BLOCK_START\n", b"; EXECUTABLE_BLOCK_END"
    normalized = gcode.replace(b"\r\n", b"\n")
    _require(normalized.count(start) == normalized.count(end) == 1 and normalized.index(start) < normalized.index(end),
             "mix_gcode_scope")
    body = normalized.split(start, 1)[1].split(end, 1)[0]
    _require(re.search(rb"^G1 (?=[^\n]*[XY]-?\d)(?=[^\n]* E(?:[1-9]\d*|0\.\d*[1-9]))[^\n]*$", body, re.M),
             "mix_gcode_extrusion_missing")
    definitions_echo = config_value_all(normalized, "mixed_filament_definitions")
    _require(len(definitions_echo) == 1, "mix_gcode_definitions")
    added = verify_definitions(before["mixed_filament_definitions"], after["mixed_filament_definitions"], definitions_echo[0])
    return {"preserved_assignment": 6, "new_recipe_ids": added, "modes": ["Ratio", "Gradient"],
            "gcode_recipe_use_verified": False}
