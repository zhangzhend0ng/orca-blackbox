"""Feishu #297 (G-code输出-排除对象与填充回抽, P1): exclude-object combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 216.
exclude_object=1, reduce_infill_retraction=1. Both keys sit in the
Others page's 'G-code output' group (Tab.cpp:2651-2654); the Others
switch carries NO tab_hint (param_tab:Others three-failure lesson).
reduce_infill_retraction already at 1 - assertion-only, so the single
op is the 'Exclude objects' checkbox ('Exclude' is band-unique).
analyze_gcode natively parses EXCLUDE_OBJECT_START/END scope markers
when the flag is on (agent_layer_verify.py:66-88), so the schedule
oracle stands at 68 x 0.4 / 27.2 - the single unexcluded cube keeps
every object layer."""
from .param_case_lib import make_verify

CASE_ID = "param_297_exclude_objects"
GOAL = ("Enable the exclude-object G-code feature while reduce infill "
        "retraction stays on. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
VALUES = {"exclude_object": "1", "reduce_infill_retraction": "1"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
