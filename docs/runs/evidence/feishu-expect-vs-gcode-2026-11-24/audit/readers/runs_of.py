"""List, for each of the 44 rows, every harvested run of its scenario on its fixture:
start time, verdict, error, whether a G-code exists. Also dump the structure of
one run's contract.json / result.json checks (keys only + short values).

    python -B runs_of.py <repo-root> [out.txt]
"""
import datetime
import glob
import io
import json
import os
import sys

root = sys.argv[1]
sys.path.insert(0, root + "/tools")
from feishu_model_fixtures import feishu_rows, row_plan  # noqa: E402

HARVEST = os.environ["ORCA_BB_HARVEST"]


def load(path):
    try:
        with open(path, encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def all_runs():
    out = []
    for d in glob.glob(os.path.join(HARVEST, "*") + os.sep):
        scope = load(d + "scope.json")
        proc = load(d + "process.json")
        if not scope or not proc:
            continue
        result = load(d + "result.json") or {}
        worker = load(d + "native_worker.json") or {}
        out.append({
            "dir": d, "id": os.path.basename(d.rstrip("\\/")),
            "scenario": scope.get("scenario"), "start": proc.get("started_at_ns"),
            "verdict": result.get("release_verdict"), "status": result.get("execution_status"),
            "error": worker.get("error"), "gcode": bool(glob.glob(d + "exports/*.gcode")),
            "host": scope.get("actor"),
        })
    out.sort(key=lambda r: r["start"] or 0)
    return out


runs = all_runs()
by_scn = {}
for r in runs:
    by_scn.setdefault(r["scenario"], []).append(r)

if len(sys.argv) > 2 and sys.argv[2] == "--structure":
    d = [r for r in runs if r["id"].startswith("2779be8f")][0]["dir"]
    contract = load(d + "contract.json")
    print("contract keys:", sorted(contract.keys()) if isinstance(contract, dict) else type(contract))
    print(json.dumps(contract, ensure_ascii=False, indent=1)[:6000])
    result = load(d + "result.json")
    print("result.checks:", json.dumps(result.get("checks"), ensure_ascii=False, indent=1)[:5000])
    print("reasons:", json.dumps(result.get("reasons"), ensure_ascii=False)[:1500])
    sys.exit(0)

out = io.open(sys.argv[2], "w", encoding="utf-8") if len(sys.argv) > 2 else sys.stdout
out.write("harvest runs with scope+process: %d of %d dirs\n" % (
    len(runs), len(glob.glob(os.path.join(HARVEST, "*") + os.sep))))
for suffix, items in row_plan(root).items():
    for number, scenario in items:
        if not scenario:
            out.write("#%d  (no scenario)\n" % number)
            continue
        full = scenario + suffix
        out.write("#%d  %s\n" % (number, full))
        for r in by_scn.get(full, []):
            stamp = datetime.datetime.fromtimestamp(r["start"] / 1e9).strftime("%m-%d %H:%M") if r["start"] else "?"
            out.write("     %s %s %-10s %-14s gcode=%s err=%s\n" % (
                stamp, r["id"][:8], r["verdict"], r["status"], r["gcode"], (r["error"] or "")[:110]))
if out is not sys.stdout:
    out.close()
