"""Independent m5e-style cross-tab settings check on the frozen cube."""
from decimal import Decimal
import hashlib

from .agent_layer_verify import analyze_gcode
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_verify import _require
from .pilot_common import PROCESS_COMBO, inspect_preserved_settings, require_gcode_settings
from .project_3mf import _archive, inspect_project
from .script_verify import _json

CASE_ID = "uia_process_combo"
GOAL = ("On the loaded cube, set regular Layer height to 0.30 mm and Sparse infill density to 30%. "
        "Enable support and select Normal (auto) support type. Keep first layer height 0.40 mm, "
        "Grid infill, geometry, placement, material assignment, and other settings unchanged.")


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "process_combo_fixture")
    project_info = inspect_project(project, fixture, layer_height="0.3", expected_support="1", cancelled=cancelled)
    actual = _json(_archive(project, cancelled)["Metadata/project_settings.config"])
    before = _json(_archive(fixture, cancelled)["Metadata/project_settings.config"])
    _require(all(before.get(k) == v for k, v in {"layer_height": "0.4", "sparse_infill_density": "15%",
             "enable_support": "0", "support_type": "tree(auto)"}.items()), "process_combo_initial_values")
    inspect_preserved_settings(actual, before, allowed_changes=PROCESS_COMBO, cancelled=cancelled)
    require_gcode_settings(gcode, PROCESS_COMBO | {"sparse_infill_pattern": "grid"}, "process_combo_gcode_setting")
    layers = analyze_gcode(gcode, layer_height="0.3", cancelled=cancelled)
    _require(layers["layer_count"] == 90 and Decimal(layers["last_z"]) == Decimal("27.1")
             and layers["object_tools"] == [0], "process_combo_layer_schedule")
    return {"project": project_info, "gcode": layers, "verified_settings": PROCESS_COMBO}
