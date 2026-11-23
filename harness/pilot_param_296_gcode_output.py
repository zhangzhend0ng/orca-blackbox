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
writes + full settings preservation (#278 raft precedent).

2026-11-24, the G-code itself is asserted now - and fails. The Feishu row
expects "G-code包含注释、行号和对象标签" (expected result 2). With all four
keys written (fa runs 6c091f2e and 908ca2d, the second with the reopen
session in develop mode as well) the exported file has 0 numbered lines
of 6135 and 0 EXCLUDE_OBJECT lines - the same as a default run (comment
lines 2002 vs 2003, TYPE comments 206 both). So the values are written and
verified, but two of the three effects the case asks for are not in the
G-code this build exports for the U1 profile. Until that is explained the
case is NON_GREEN with param_gcode_line_number_missing (the values part
still has to pass for the message to be reached).
Filename format: the row writes {input_filename}_{plate_name}.gcode; the
app's placeholder is input_filename_base (PrintConfig filename_format),
so VALUES uses that. The exported file is named by the harness, not by
the app - "文件名匹配格式" is not checked."""
from .pilot_common import _require
from .param_case_lib import make_verify

CASE_ID = "param_296_gcode_output"
GOAL = ("Enable verbose G-code comments, line numbers and object labels, and "
        "set the filename format to {input_filename_base}_{plate_name}.gcode. "
        "Preserve the cube geometry, its placement, material assignment and "
        "every other setting.")
VALUES = {"gcode_comments": "1", "gcode_add_line_number": "1",
          "gcode_label_objects": "1",
          "filename_format": "{input_filename_base}_{plate_name}.gcode"}
_values_verified = make_verify(CASE_ID, VALUES)


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    result = _values_verified(project, fixture, gcode, cancelled=cancelled)
    text = gcode.decode("utf-8", errors="replace") if isinstance(gcode, bytes) else str(gcode)
    numbered = sum(1 for line in text.splitlines()
                   if line[:1] == "N" and line[1:2].isdigit())
    result["numbered_lines"] = numbered
    result["object_labels"] = "EXCLUDE_OBJECT" in text
    _require(numbered > 0, "param_gcode_line_number_missing")
    _require(result["object_labels"], "param_gcode_object_label_missing")
    return result
