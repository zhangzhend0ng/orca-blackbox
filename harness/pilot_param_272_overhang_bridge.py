"""Feishu #272 (常用工艺参数, P0): tiered overhang speeds + bridging.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 191.
Key calibration 2026-11-22 (upstream SnapmakerOrca source): the fork has
NO overhang_totally_speed option - PrintConfig.cpp:7282 drops it in the
config loader's ignore list and Tab.cpp:2436 builds the Overhang speed
row from FOUR inline edits (overhang_1_4..4_4). The table's fifth tier
cannot be written by this app and stays out of VALUES. enable_overhang_
speed=1 and bridge_speed=30 already equal the fixture values, so the
case proves the four tier writes; divergence recorded here."""
from .param_case_lib import make_verify

CASE_ID = "param_272_overhang_bridge"
GOAL = ("Keep slow-down-for-overhang enabled and bridge speed at 30 mm/s, "
        "and set the four overhang degree bands to 40/30/20/10 mm/s. "
        "Preserve the cube geometry, its placement, material assignment "
        "and every other setting.")
VALUES = {"enable_overhang_speed": "1", "overhang_1_4_speed": "40",
          "overhang_2_4_speed": "30", "overhang_3_4_speed": "20",
          "overhang_4_4_speed": "10", "bridge_speed": "30"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
