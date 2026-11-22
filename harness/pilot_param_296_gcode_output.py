"""Feishu #296 (G-code输出-注释/行号/标签/文件名, P0): output annotations combo.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 215.
gcode_comments=1, gcode_add_line_number=1, gcode_label_objects=1,
filename_format={input_filename_base}_{plate_name}.gcode. All four keys
sit in the Others page's 'G-code output' group (Tab.cpp:2652-2659); the
Others switch carries NO tab_hint (param_tab:Others three-failure
lesson). gcode_label_objects already at 1 - assertion-only. Checkbox
anchors: 'Verbose' (gcode_comments paints 'Verbose G-code') and
'number' ('Add line number') are band-unique. filename_format is the
one non-numeric Edit in this family - the uia float driver's digit-only
readback cannot confirm braces, so the VALUES assertion is the real
gate; the multiline Edit height (option.opt.multiline, Tab.cpp:2655)
may defeat the 14 px row-y pairing - the guest run decides.

schedule: intentionally None - enabling gcode_add_line_number rewrites
EVERY exported line as 'N<n> ...' including comments
(GCode/PostProcessor.cpp:198-221), and analyze_gcode's block markers
are exact-match ('; EXECUTABLE_BLOCK_START', agent_layer_verify.py:58)
- the numbered file fails that parse before any layer count. Until the
analyzer grows N-prefix tolerance the oracle proves the four config
writes + full settings preservation (#278 raft precedent)."""
from .param_case_lib import make_verify

CASE_ID = "param_296_gcode_output"
GOAL = ("Enable verbose G-code comments, line numbers and object labels, and "
        "set the filename format to {input_filename_base}_{plate_name}.gcode. "
        "Preserve the cube geometry, its placement, material assignment and "
        "every other setting.")
VALUES = {"gcode_comments": "1", "gcode_add_line_number": "1",
          "gcode_label_objects": "1",
          "filename_format": "{input_filename_base}_{plate_name}.gcode"}
verify_business = make_verify(CASE_ID, VALUES)
