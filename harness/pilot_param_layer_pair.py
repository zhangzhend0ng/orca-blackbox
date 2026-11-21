"""Feishu #254 (常用工艺参数, P0): layer-height combination.

Set regular layer height 0.20 mm with the initial layer raised to 0.25 mm
on the standard V3 cube fixture, then verify the combination from the
frozen 3MF and an independently resliced G-code: the two settings written,
every other process setting preserved, first Z at 0.25 and the remaining
layers stepping by 0.20 up to the cube's 27 mm height. The table asks for
a sphere on the 0.20 preset; the V3 oracle checks the same parameter
semantics on the standard cube fixture (divergence recorded in the
migration ledger)."""
from decimal import Decimal

from .agent_layer_verify import analyze_gcode
from .agent_verify import _require
from .pilot_common import LAYER_PAIR, inspect_preserved_settings
from .project_3mf import _archive, _json

CASE_ID = "param_layer_pair_254"
GOAL = ("Set regular layer height to 0.20 mm and initial layer print height to 0.25 mm. "
        "Preserve the cube geometry, its placement, material assignment and every other setting.")
FIRST_Z = Decimal("0.25")
CUBE_HEIGHT = Decimal(27)
REGULAR = Decimal("0.2")
# 0.25 + 134 * 0.2 = 27.05 -> 135 object Z layers.
EXPECTED_LAYERS = 135
EXPECTED_LAST_Z = "27.05"


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    actual, original = (_json(a["Metadata/project_settings.config"])
                        for a in (_archive(project, cancelled), _archive(fixture, cancelled)))
    inspect_preserved_settings(actual, original, allowed_changes=LAYER_PAIR, cancelled=cancelled)
    _require(actual.get("layer_height") == "0.2", "layer_pair_regular_value")
    _require(actual.get("initial_layer_print_height") == "0.25", "layer_pair_initial_value")
    layers = analyze_gcode(gcode, layer_height="0.2", first_layer_height="0.25", cancelled=cancelled)
    _require(Decimal(layers["first_z"]) == FIRST_Z, "layer_pair_first_z")
    _require(Decimal(layers["last_z"]) == Decimal(EXPECTED_LAST_Z), "layer_pair_last_z")
    _require(layers["layer_count"] == EXPECTED_LAYERS, "layer_pair_layer_count")
    return {"case_id": CASE_ID, "layer_height": actual["layer_height"],
            "initial_layer_print_height": actual["initial_layer_print_height"],
            "layer_count": layers["layer_count"], "first_z": layers["first_z"],
            "last_z": layers["last_z"], "gcode_sha256": layers["sha256"],
            "other_settings_preserved": True}
