"""Export the Feishu parameter cases (ops + expected values) as one JSON file
for ports that do not import the Windows harness - the macOS port reads
tools/param_cases_export.json instead of native_script_baseline.

    python tools/export_param_cases.py            # prints the file
    python tools/export_param_cases.py --write    # writes tools/param_cases_export.json

A case = {scenario, case_id, goal, values, ops, kinds}. `ops` is the
PARAM_OPS entry as the Windows engine runs it; `kinds` is the set of op
kinds it uses, so a port can pick what it supports. `values` is the
pilot's VALUES (the keys the saved project must show). Nothing here is
Mac-specific: labels, groups and values are the case; how to reach a row
is the port's business.
"""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import native_pilots  # noqa: E402
from harness.native_script_baseline import PARAM_OPS, SCENARIO_CONF  # noqa: E402


def export():
    cases = []
    for scenario, module in sorted(native_pilots.TRIALS.items()):
        if not scenario.startswith("uia_param_") or scenario not in PARAM_OPS:
            continue
        pilot = importlib.import_module("harness." + module)
        ops = PARAM_OPS[scenario]
        cases.append(_case(scenario, pilot, ops))
    # #254 is driven by edit_param_layer_pair(), not by the ops table: the
    # same two edits in table form, so the port sees every case alike.
    pilot = importlib.import_module("harness." + native_pilots.TRIALS["uia_param_layer_pair"])
    cases.append(_case("uia_param_layer_pair", pilot, [
        {"tab": "Quality", "op": "float", "label": ["^Layer height"], "value": "0.2",
         "group": "Layer height"},
        {"op": "float", "label": ["^First layer height"], "value": "0.25", "group": "Layer height"},
    ]))
    cases.sort(key=lambda c: c["scenario"])
    return {"meta": META, "cases": cases}


def _case(scenario, pilot, ops):
    return {
        "scenario": scenario,
        "case_id": pilot.CASE_ID,
        "goal": pilot.GOAL,
        "values": pilot.VALUES,
        "ops": ops,
        "kinds": sorted({op["op"] for op in ops}),
        "field_ops": sum(1 for op in ops if op.get("field") is not None or op.get("below")),
        "app_conf": SCENARIO_CONF.get(scenario),
    }


META = {
    "source": "harness/native_script_baseline.py PARAM_OPS + the pilots' VALUES",
    "note": "Written by tools/export_param_cases.py; regenerate after changing an op. "
            "ops use the Windows engine's vocabulary: tab / op=float|checkbox|combo|"
            "rowcombo / label (str or candidates, '^' anchors the row start) / group / "
            "value / field (index into a vertical stack of boxes) / below / target / "
            "current (the value a combo paints) / answer + dialog (a box the op must "
            "answer). 'combo' ops are located by the value they paint, 'rowcombo' ops by "
            "their row label. A port that cannot reach a row reports it; it never edits config. "
            "app_conf is app config the case needs beyond the default (develop mode); a port "
            "that cannot seed it reports the case as not reachable, not as failed.",
}


def main():
    data = export()
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if "--write" in sys.argv:
        (ROOT / "tools" / "param_cases_export.json").write_text(text + "\n", encoding="utf-8", newline="\n")
        print("wrote tools/param_cases_export.json:", len(data["cases"]), "cases")
    else:
        print(text)
    only = [c["scenario"] for c in data["cases"]
            if set(c["kinds"]) <= {"float", "checkbox"} and not c["field_ops"]]
    print("float/checkbox only, no stacked fields: %d" % len(only))
    for sc in only:
        print("  ", sc)


if __name__ == "__main__":
    main()
