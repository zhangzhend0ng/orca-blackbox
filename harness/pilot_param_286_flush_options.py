"""Feishu #286 (换料冲刷-去向与体积, P0): flush destinations + prime volume.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 205.
flush_into_infill=1, flush_into_objects=1, flush_into_support=1,
prime_volume=40. The three flush checkboxes sit in the Multimaterial
page's 'Flush options' group (Tab.cpp:2584-2587) and toggle on
have_prime_tower (ConfigManipulation.cpp:795; fixture enable_prime_tower
=1), flush_into_support already at 1 - assertion-only. Checkbox anchors
are band-scoped words from the painted labels 'Flush into objects'
infill / 'this object' / 'objects' support: 'objects' hits the infill
row (the group's first row, top-down first match) even if the apostrophe
is dropped, 'this' is unique to the middle row; the group title's own
'Flush' word is deliberately NOT used (a title has no checkbox).
prime_volume repeats the calibrated #283 op ('Prime volume' float, Prime
tower group, tab verified by 'tower'). The single-material cube never
tool-changes, so no flush volume moves and the schedule keeps
68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_286_flush_options"
GOAL = ("Enable flushing into the object's infill, into the object and into "
        "its support, and set the prime volume to 40 mm3. Preserve the cube "
        "geometry, its placement, material assignment and every other "
        "setting.")
# Recorded deviation (2026-11-24, queue21 VM run, param_checkbox:this):
# flush_into_objects dropped. Its row 'Flush into this object' is not
# painted in the GLOBAL config on the 2.4.0 build (ConfigManipulation.cpp
# :886 toggle_line("flush_into_objects", !is_global_config)); the page's
# Flush options group is 'Flush into objects' infill' / '... support' only
# (row fixture tools/param_ui_rows_2.4.0.json). The key stays at its
# fixture value 0 and is not asserted. Precedent: #278 raft_expansion.
VALUES = {"flush_into_infill": "1", "flush_into_support": "1",
          "prime_volume": "40"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
