"""Save-only controls for the parameter cases: what a save with no edit changes.

Every parameter case ends in "GUI save, freeze, reopen with a new profile, slice,
export" and is judged on its own values plus "every other setting preserved"
(pilot_common.inspect_preserved_settings, which admits the reviewed 2.3.6 -> 2.4.0
representation migrations and nothing else). A 2026-11-24 review of the Mac runs
noted that 35 other keys differ between the fixture's config and the saved one in
each passing case, and that no save-only control was run. These are it:

  uia_param_save_only        the cube, fixtures/agent_layer_cube.3mf
  uia_param_std_save_only    the precondition cube, fixtures/feishu_std_cube.3mf
                             (U1 0.4 nozzle, 0.20mm Standard, PLA)
  uia_param_shapes_save_only  the five-object shapes plate
  uia_param_<x>_save_only    one per fixture that carries the rows' own models on
                             the precondition settings - x in boat, boat2, fdmt,
                             fdmt2, cubes2, sphere, cyl, bunny, hell
                             (agent_protocol.BASELINES is the list)

All run the cases' path with an empty op list (native_script_baseline.PARAM_OPS)
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
from .agent_protocol import BASELINES
from .param_case_lib import make_verify
from .project_3mf import _settings

VALUES = {}
GOAL = ("Save the loaded project without changing any setting. Preserve the models' geometry, "
        "its placement, material assignment and every setting.")
LIMIT = 120
SAMPLE = 6          # changed keys shown with their values; the rest by name
KEYS_CHARS = 1500   # room for the changed keys' names
DETAIL_ROOM = 3800  # what the result may take of the 4096-character check detail


def _cut(value):
    text = json.dumps(value, ensure_ascii=False)
    return value if len(text) <= LIMIT else text[:LIMIT] + "..."


def _config_changes(project, fixture, cancelled):
    """{"count", "keys", "sample"} of the keys whose value differs between the two
    project configs, raw comparison: a key added by the save or rewritten in form
    counts. The whole list is recomputed offline from the two 3MFs (the proof and
    input/fixture.3mf of the run); the result carries what fits in a check's detail."""
    saved, original = _settings(project, cancelled), _settings(fixture, cancelled)
    changed = sorted(key for key in set(saved) | set(original) if saved.get(key) != original.get(key))
    return {"count": len(changed),
            "keys": " ".join(changed)[:KEYS_CHARS],
            "sample": [{"key": key, "before": _cut(original.get(key)), "after": _cut(saved.get(key))}
                       for key in changed[:SAMPLE]]}


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
    """{feature: {"blocks": n, "first": "2100x4 2563.154x44", "other": "1864x31 ..."}} - the
    four most used feeds per layer band, feed x moves. feature_speeds() reads a
    file, so the exported bytes go to one for the call."""
    with tempfile.TemporaryDirectory(prefix="orca-bb-feeds-") as folder:
        path = Path(folder) / "export.gcode"
        path.write_bytes(gcode)
        table = feature_speeds(str(path), travel=True)
    name = lambda feed: str(int(feed)) if feed == int(feed) else str(round(feed, 3))
    top = lambda row: " ".join("%sx%d" % (name(feed), moves)
                               for feed, moves in sorted(row.items(), key=lambda kv: -kv[1])[:4]) or "-"
    return {kind: {"blocks": row["blocks"], "first": top(row["first"]), "other": top(row["other"])}
            for kind, row in table.items()}


def _control(case_id):
    preserved = make_verify(case_id, VALUES)

    def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
        result = preserved(project, fixture, gcode, cancelled=cancelled)
        settings = _settings(project, cancelled)
        text = gcode.decode("utf-8", errors="replace")
        result.update(_layers(gcode, settings))
        result["layer_change_lines"] = sum(1 for line in text.splitlines() if line.startswith(";LAYER_CHANGE"))
        result["feature_speeds"] = _feeds(gcode)
        result["config_changes"] = _config_changes(project, fixture, cancelled)
        # The result IS the business check's detail, bounded to 4096 characters
        # (run_verdict.CheckResult) - the first control run (baa3168) overflowed it
        # and was reported native_evidence_unavailable. Give up the sample first,
        # then the key list; the counts always stay.
        for droppable in ("sample", "keys"):
            if len(json.dumps(result, sort_keys=True)) <= DETAIL_ROOM:
                break
            result["config_changes"][droppable] = "(dropped: over the check's detail bound)"
        if len(json.dumps(result, sort_keys=True)) > DETAIL_ROOM:
            # A plate with many features (a 3DBenchy adds overhang, bridge and
            # internal-bridge blocks) can still be over the bound without the two
            # dropped parts: keep the twelve features with the most moves.
            moves = lambda row: sum(int(part.split("x")[-1]) for part in row["other"].split() if "x" in part)
            keep = sorted(result["feature_speeds"], key=lambda k: -moves(result["feature_speeds"][k]))[:12]
            result["feature_speeds"] = dict({k: result["feature_speeds"][k] for k in keep},
                                            other_features="(dropped: over the check's detail bound)")
        return result

    return verify_business


# One module, the controls: native_pilots.pilot_module hands back the one asked for.
# The cube's control by hand; one baseline per other fixture from agent_protocol.BASELINES
# (the precondition cube, the shapes plate, the rows' own models on the precondition
# settings).
CASES = {
    "uia_param_save_only": SimpleNamespace(CASE_ID="param_save_only_control", VALUES=VALUES, GOAL=GOAL,
                                           verify_business=_control("param_save_only_control")),
}
for _baseline, _case in BASELINES.values():
    CASES[_baseline] = SimpleNamespace(CASE_ID=_case, VALUES=VALUES, GOAL=GOAL, verify_business=_control(_case))
