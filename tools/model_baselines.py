"""What each fixture's export looks like before any row touches it - the
reference the rows' own-model runs are compared against.

    python tools/model_baselines.py <repo-root> [--write <file>]

For every save-only baseline (harness/agent_protocol.BASELINES, plus the
cube's control) takes the latest harvested run and reduces its export with
tools/gcode_facts.py to the facts the Feishu rows' expected results talk
about: layers and Z, every feed per feature and layer band, the direction of
bridges and infill, where support starts and ends, which tool prints which
feature, the fan's steps, the wipe moves, travels. Read-only unless --write
is given. The harvest is looked up under ORCA_BB_HARVEST, else under
<repo-root>/artifacts/windows_mcp_harvest.

"Measure first, then pin": an assertion for a row is written against these
numbers (a bridge direction that the row changes away from the baseline, a
support block count that starts at zero), never against the row's wording
alone - the 0.20mm Standard preset runs its walls at the volumetric cap, has
the fan at 100% from layer 2, and interpolates the overhang bands.
"""
import glob
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root = sys.argv[1]
sys.path.insert(0, root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcode_facts import gcode_facts  # noqa: E402
from harness.agent_protocol import BASELINES, FIXTURE_SUFFIXES, LAYER_FIXTURE_SHA256  # noqa: E402

HARVEST = os.environ.get("ORCA_BB_HARVEST") or os.path.join(root, "artifacts", "windows_mcp_harvest")
shas = {sha: suffix for suffix, (_path, sha) in FIXTURE_SUFFIXES.items()}
shas[LAYER_FIXTURE_SHA256] = "(cube)"
out = {}
for name in ["uia_param_save_only"] + [baseline for baseline, _case in BASELINES.values()]:
    best = None
    for d in glob.glob(os.path.join(HARVEST, "*") + os.sep):
        try:
            scope = json.load(open(d + "scope.json", encoding="utf-8-sig"))
            proc = json.load(open(d + "process.json", encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if scope.get("scenario") == name and proc.get("started_at_ns"):
            if best is None or proc["started_at_ns"] > best[0]:
                best = (proc["started_at_ns"], d)
    if not best:
        continue
    d = best[1]
    result = json.load(open(d + "result.json", encoding="utf-8-sig"))
    gcode = glob.glob(d + "exports/*.gcode")
    if result.get("release_verdict") != "SHADOW" or not gcode:
        continue
    facts = gcode_facts(gcode[0])
    out[name] = {
        "run": os.path.basename(d.rstrip(os.sep))[:8],
        "machine": "fa" if b"ORCA_BB_ALLOW_TESTBOX" in open(d + "native_worker.log", "rb").read() else "vm",
        "layers": facts["layers"], "first_z": facts["z_first"], "last_z": facts["z_last"],
        "features": {kind: {"blocks": f["blocks"], "moves": f["moves"], "feeds": f["feeds"],
                            "e_per_mm": f["e_per_mm"], "direction": f["angle_top"], "z": f["z"],
                            "layers_with": f["layers_with"], "e_by_tool": f["e_by_tool"]}
                     for kind, f in facts["features"].items()},
        "travel": facts["travel_feeds"],
        "fan": facts["fan"], "fan_steps": facts["fan_changes"], "wipe": facts["wipe"],
        "arcs": facts["arcs"], "tools": len(facts["tools"]), "e_by_tool": facts["e_by_tool"],
        "accel": facts["accel"],
    }
text = json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1)
if "--write" in sys.argv:
    path = sys.argv[sys.argv.index("--write") + 1]
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text + "\n")
    print("written:", path, "| baselines:", len(out))
else:
    print(text)
