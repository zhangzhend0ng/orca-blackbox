"""Feishu #254 (常用工艺参数, P0): layer-height combination.

Set regular layer height 0.20 mm with the initial layer raised to 0.25 mm on
the fixture the scenario opens - the standard V3 cube, or (a suffixed scenario)
one of the Feishu rows' models on the precondition settings - then verify the
combination from the frozen 3MF and an independently resliced G-code: the two
settings written, every other process setting preserved, first Z at 0.25 and
every layer after it stepping by 0.20. How many layers that makes and where
the top one lies belongs to the fixture, not to the case (SCHEDULE_BY_FIXTURE,
the way param_case_lib keeps a case's schedule): asserted where a measured run
pinned it, recorded where none has. The table asks for a sphere on the 0.20
preset; the V3 oracle checks the same parameter semantics on the standard cube
fixture (divergence recorded in the migration ledger)."""
from decimal import Decimal
import hashlib

from .agent_layer_verify import analyze_gcode
from .agent_verify import _require
from .pilot_common import LAYER_PAIR, inspect_preserved_settings
from .project_3mf import _settings
from .agent_protocol import LAYER_FIXTURE_SHA256, MODEL_FIXTURES, STD_FIXTURE_SHA256

CASE_ID = "param_layer_pair_254"
GOAL = ("Set regular layer height to 0.20 mm and initial layer print height to 0.25 mm. "
        "Preserve the cube geometry, its placement, material assignment and every other setting.")
FIRST_Z = Decimal("0.25")
REGULAR = Decimal("0.2")
# 0.25 + 134 * 0.2 = 27.05 -> 135 object Z layers.
EXPECTED_LAYERS = 135
EXPECTED_LAST_Z = "27.05"

# sha256 of the fixture bytes -> the layers the pair produces on it:
#   height_mm              the object's top: the analyzer's own sanity bound (the
#                          last layer within one layer height of it)
#   layer_count, last_z    what a run measured on it: asserted.
# A fixture outside the table is recorded the same way, with no bound on its
# height and nothing asserted about count or top; so is one whose entry has
# height_mm only, while it is being measured.
#   cube (27 mm)              the pair proven on the guest: 0.25 + 134 x 0.20
#   precondition cube (27 mm) fa706g3 run 66cbd0c1 (_std02), 2026-11-24
#   sphere (20 mm across)     fa706g3 run 8e6363ab (_sphere), 2026-11-24: the
#                             layer at 20.05 still prints, so 100, not 99
# The last two were measured in those runs (the fixtures then unpinned: recorded)
# and asserted end to end, pins in the code, in fa706g3 runs eeaa8ff6 (_std02)
# and 345b87c6 (_sphere), 2026-11-24.
SCHEDULE_BY_FIXTURE = {
    LAYER_FIXTURE_SHA256: {"height_mm": "27", "layer_count": EXPECTED_LAYERS, "last_z": EXPECTED_LAST_Z},
    STD_FIXTURE_SHA256: {"height_mm": "27", "layer_count": 135, "last_z": "27.05"},
    MODEL_FIXTURES["_sphere"][1]: {"height_mm": "20", "layer_count": 100, "last_z": "20.05"},
}


def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
    actual, original = _settings(project, cancelled), _settings(fixture, cancelled)
    inspect_preserved_settings(actual, original, allowed_changes=LAYER_PAIR, cancelled=cancelled)
    _require(actual.get("layer_height") == "0.2", "layer_pair_regular_value")
    _require(actual.get("initial_layer_print_height") == "0.25", "layer_pair_initial_value")
    schedule = SCHEDULE_BY_FIXTURE.get(hashlib.sha256(fixture).hexdigest(), {})
    # analyze_gcode requires the first layer at 0.25 and every layer after it
    # 0.20 above the previous one, whatever the fixture.
    layers = analyze_gcode(gcode, layer_height="0.2", first_layer_height="0.25", cancelled=cancelled,
                           expected_height_mm=Decimal(schedule["height_mm"]) if "height_mm" in schedule else None)
    _require(Decimal(layers["first_z"]) == FIRST_Z, "layer_pair_first_z")
    result = {"case_id": CASE_ID, "layer_height": actual["layer_height"],
              "initial_layer_print_height": actual["initial_layer_print_height"],
              "layer_count": layers["layer_count"], "first_z": layers["first_z"],
              "last_z": layers["last_z"], "gcode_sha256": layers["sha256"],
              "other_settings_preserved": True}
    if "layer_count" in schedule:
        _require(Decimal(layers["last_z"]) == Decimal(schedule["last_z"]), "layer_pair_last_z")
        _require(layers["layer_count"] == schedule["layer_count"], "layer_pair_layer_count")
    result["schedule_asserted"] = "layer_count" in schedule
    return result
