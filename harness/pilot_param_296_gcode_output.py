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

2026-11-24, the G-code itself is checked. The Feishu row expects "G-code
包含注释、行号和对象标签" (expected result 2). On the U1 fixture three
different things happen, each measured on the exported file:
- gcode_comments=1 takes effect: 3028 command lines carry a trailing
  comment ("M106 S0 ; disable fan") against 2 in a default run (fa run
  908ca2d vs tree_support run 2f5c45ad). Counting lines that START with
  ';' cannot see it (2002 vs 2003) - verbose comments are end-of-line
  annotations. Asserted: param_gcode_verbose_comments_missing.
- gcode_add_line_number=1 is written but no line is numbered (0 of 6135,
  fa 6c091f2e / 908ca2d, VM queue25), with the reopen session in develop
  mode too, and the file is never rewritten (its LastWriteTime is the temp
  file's). Source (2.3.5 tree on fa706g3, main@c98c6d3; 2.4.0 has no
  source): the only call, gcode_add_line_number in
  BackgroundSlicingProcess::export_gcode (:901), is reached only when the
  printer is a BBL machine (process_fff :246-252); any other printer goes
  through finalize_gcode, which copies the file. The build agrees: its
  export header has no "; model label id:" (written for BBL printers
  only). So on the Snapmaker U1 this option cannot take effect - a limit
  of the product for this machine, recorded here, not asserted.
- "标注模型" is not gcode_label_objects: that key is 1 by default in the
  Snapmaker common preset and only writes "; printing object" comments
  (136 lines, same as a default run). The EXCLUDE_OBJECT labels come with
  exclude_object (GCode.cpp:6595), which is 0 by default: 0 lines here,
  137 in the #297 run (1b0c899d) where it is on. Not asserted here.
Recorded deviations from the row: two of its three expected effects are
not reachable through these settings on this machine.
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
    lines = text.splitlines()
    result["verbose_comment_lines"] = sum(
        1 for line in lines if line[:1] in "GM" and " ; " in line)
    result["numbered_lines"] = sum(1 for line in lines if line[:1] == "N" and line[1:2].isdigit())
    result["object_labels"] = "EXCLUDE_OBJECT" in text
    _require(result["verbose_comment_lines"] > 1000, "param_gcode_verbose_comments_missing")
    return result
