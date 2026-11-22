"""Feishu #285 (Ooze预防, P0): standby temperature + preheat combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 204.
All four keys live on the process panel's Multimaterial page, 'Ooze
prevention' group (Tab.cpp:2579-2584); the page switch is already
calibrated - click_tab verifies Multimaterial by the page-unique word
'tower' (process_panel.py:283). ooze_prevention already equals the fixture
value 1 - assertion-only. standby_temperature_delta is scalar here
(PrintConfig.cpp:5036, coInt, label 'Temperature variation') and moves
-150 -> -100; preheat_time 30 -> 15 and preheat_steps 1 -> 2 (labels
'Preheat time' / 'Preheat steps' - phrase-join tells the adjacent rows
apart). Temperature strategy changes no geometry: 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_285_ooze_prevention"
GOAL = ("Keep ooze prevention enabled, set standby temperature delta to "
        "-100 degC, preheat steps to 2 and preheat time to 15 s. Preserve "
        "the cube geometry, its placement, material assignment and every "
        "other setting.")
VALUES = {"ooze_prevention": "1", "standby_temperature_delta": "-100",
          "preheat_steps": "2", "preheat_time": "15"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
