"""Feishu #283 (擦拭塔, P0): prime tower structure / purging / adhesion.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 202.
All eight keys live on the process panel's Multimaterial page, 'Prime
tower' group (Tab.cpp:2552-2571); the page switch is already calibrated -
click_tab verifies Multimaterial by the page-unique word 'tower'
(process_panel.py:283). Five targets already equal the fixture values
(enable_prime_tower 1, prime_tower_width 30, prime_tower_brim_width 5,
wipe_tower_wall_type 'rib', wipe_tower_filament 0 - measured in
fixtures/agent_layer_cube.3mf; the Feishu names match the config keys
exactly), so they stay assertion-only. Only prime_volume 90 -> 40,
wipe_tower_no_sparse_layers 0 -> 1 and wipe_tower_cone_angle 30 -> 15 move.
The single-material cube never tool-changes, so no tower geometry enters
the G-code and the schedule keeps 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_283_prime_tower"
GOAL = ("Keep the prime tower enabled at width 30 mm with rib walls, 5 mm "
        "brim and filament 0, set prime volume to 40 mm3, stabilization cone "
        "apex angle to 15 deg and enable no sparse layers. Preserve the cube "
        "geometry, its placement, material assignment and every other "
        "setting.")
VALUES = {"enable_prime_tower": "1", "prime_tower_width": "30",
          "prime_volume": "40", "prime_tower_brim_width": "5",
          "wipe_tower_wall_type": "rib", "wipe_tower_no_sparse_layers": "1",
          "wipe_tower_cone_angle": "15", "wipe_tower_filament": "0"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
