"""Save-only controls for the parameter cases: what a save with no edit changes.

Every parameter case ends in "GUI save, freeze, reopen with a new profile, slice,
export" and is judged on its own values plus "every other setting preserved"
(pilot_common.inspect_preserved_settings, which admits the reviewed 2.3.6 -> 2.4.0
representation migrations and nothing else). A 2026-11-24 review of the Mac runs
noted that 35 other keys differ between the fixture's config and the saved one in
each passing case, and that no save-only control was run. These two are it:

  uia_param_save_only        the cube, fixtures/agent_layer_cube.3mf
  uia_param_std_save_only    the precondition fixture, fixtures/feishu_std_cube.3mf
                             (U1 0.4 nozzle, 0.20mm Standard, PLA)

Both run the cases' path with an empty op list (native_script_baseline.PARAM_OPS)
and are judged by the same make_verify as the cases, with empty VALUES: "values
preserved / other settings preserved" is the existing rule's verdict. Nothing is
asserted about the layer schedule. The G-code facts are RECORDED, not judged - the
precondition fixture's schedule is pending exactly this run
(param_case_lib.SCHEDULE_BY_FIXTURE):

  layer_change_lines   ";LAYER_CHANGE" lines
  layer_count          object layers as analyze_gcode counts them
  first_z / last_z     first and last object layer Z
  feature_speeds       feeds per feature type and layer band, from
                       tools/gcode_feature_speeds.py (imported: feature_speeds is
                       the one reader of feeds; a copy would drift)
  schedule_error       the analyzer's reason when it cannot read the layers
  config_changes       keys whose value differs between the fixture and the saved
                       project, before -> after, raw comparison (no migration
                       rule), values cut to LIMIT characters: what the save alone
                       rewrote, and what the app re-applied from the installed
                       presets on load
"""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from tools.gcode_feature_speeds import feature_speeds

from .agent_layer_verify import analyze_gcode
from .param_case_lib import make_verify
from .project_3mf import _archive, _json

VALUES = {}
GOAL = ("Save the loaded project without changing any setting. Preserve the cube geometry, "
        "its placement, material assignment and every setting.")
LIMIT = 120


def _cut(value):
    text = json.dumps(value, ensure_ascii=False)
    return value if len(text) <= LIMIT else text[:LIMIT] + "..."


def _config_changes(project, fixture, cancelled):
    """[{key, before, after}] of the keys whose value differs between the two project
    configs, raw comparison: a key added by the save or rewritten in form counts."""
    saved, original = (_json(archive["Metadata/project_settings.config"])
                       for archive in (_archive(project, cancelled), _archive(fixture, cancelled)))
    return [{"key": key, "before": _cut(original.get(key)), "after": _cut(saved.get(key))}
            for key in sorted(set(saved) | set(original)) if saved.get(key) != original.get(key)]


def _layers(gcode, settings):
    """The layer facts analyze_gcode reads from the export, or its reason for none.
    Recorded either way: a schedule nobody has pinned yet is not a verdict."""
    try:
        layers = analyze_gcode(gcode, layer_height=str(settings.get("layer_height", "0.4")),
                               first_layer_height=str(settings.get("initial_layer_print_height", "0.4")))
    except ValueError as exc:
        return {"schedule_error": str(exc)[:120]}
    return {"layer_count": layers["layer_count"], "first_z": layers["first_z"],
            "last_z": layers["last_z"]}


def _feeds(gcode):
    """feature_speeds() reads a file, so the exported bytes go to one for the call.
    Its feed keys are floats ("1800.0" once serialised): a whole feed is written as
    its integer."""
    with tempfile.TemporaryDirectory(prefix="orca-bb-feeds-") as folder:
        path = Path(folder) / "export.gcode"
        path.write_bytes(gcode)
        table = feature_speeds(str(path), travel=True)
    name = lambda feed: str(int(feed)) if feed == int(feed) else str(feed)
    return {kind: {"blocks": row["blocks"],
                   "first": {name(feed): moves for feed, moves in sorted(row["first"].items())},
                   "other": {name(feed): moves for feed, moves in sorted(row["other"].items())}}
            for kind, row in table.items()}


def _control(case_id):
    preserved = make_verify(case_id, VALUES)

    def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
        result = preserved(project, fixture, gcode, cancelled=cancelled)
        settings = _json(_archive(project, cancelled)["Metadata/project_settings.config"])
        text = gcode.decode("utf-8", errors="replace")
        result.update(_layers(gcode, settings))
        result["layer_change_lines"] = sum(1 for line in text.splitlines() if line.startswith(";LAYER_CHANGE"))
        result["feature_speeds"] = _feeds(gcode)
        result["config_changes"] = _config_changes(project, fixture, cancelled)
        return result

    return verify_business


# One module, the controls: native_pilots.pilot_module hands back the one asked for.
CASES = {
    "uia_param_save_only": SimpleNamespace(CASE_ID="param_save_only_control", VALUES=VALUES, GOAL=GOAL,
                                           verify_business=_control("param_save_only_control")),
    "uia_param_std_save_only": SimpleNamespace(CASE_ID="param_std_save_only", VALUES=VALUES, GOAL=GOAL,
                                               verify_business=_control("param_std_save_only")),
    "uia_param_shapes_save_only": SimpleNamespace(CASE_ID="param_shapes_save_only", VALUES=VALUES, GOAL=GOAL,
                                                  verify_business=_control("param_shapes_save_only")),
}
