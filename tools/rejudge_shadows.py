"""Re-judge every parameter case's LATEST SHADOW run with the CURRENT
pilots (offline, read-only): the oracles can get stronger after a run.

    python rejudge_shadows.py <repo-root> [--all]

For each case take its latest harvested run whose verdict was SHADOW, then
run the pilot's verify_business on that run's proof 3mf, fixture 3mf and
exported G-code. Prints one line per case: OK, or the error the current
oracle raises. --all also judges the cases whose latest run is not SHADOW.
"""
import glob
import importlib
import io
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from harness import native_pilots  # noqa: E402

HARVEST = Path(os.environ.get("ORCA_BB_HARVEST", str(root / "artifacts" / "windows_mcp_harvest")))
out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

runs = {}
for d in glob.glob(str(HARVEST / "*") + os.sep):
    try:
        r = json.load(open(d + "result.json", encoding="utf-8-sig"))
        s = json.load(open(d + "scope.json", encoding="utf-8-sig"))
    except (OSError, ValueError):
        continue
    sc = s.get("scenario")
    if sc and sc.startswith("uia_param_"):
        runs.setdefault(sc, []).append((os.path.getmtime(d), d, r.get("release_verdict")))

ok = bad = skipped = 0
for scenario, module in sorted(native_pilots.TRIALS.items()):
    if not scenario.startswith("uia_param_"):
        continue
    if scenario not in runs:
        continue
    mine = sorted(runs[scenario])
    latest = mine[-1]
    shadow = [x for x in mine if x[2] == "SHADOW"]
    if not shadow:
        out.write("%-32s NO SHADOW RUN ON RECORD (latest %s)\n" % (scenario, latest[2]))
        skipped += 1
        continue
    d = (shadow[-1] if "--all" not in sys.argv else latest)[1]
    try:
        pilot = importlib.import_module("harness." + module)
        verify = getattr(pilot, "verify_business", None)
        if verify is None:
            out.write("%-32s pilot has no verify_business\n" % scenario)
            skipped += 1
            continue
        proof = glob.glob(d + "proof/*.3mf")
        gcode = glob.glob(d + "exports/*.gcode")
        if not proof or not gcode:
            out.write("%-32s %s  ARTIFACTS MISSING proof=%d gcode=%d\n" % (scenario, Path(d).name[:8], len(proof), len(gcode)))
            bad += 1
            continue
        result = verify(open(proof[0], "rb").read(), open(d + "input/fixture.3mf", "rb").read(),
                        open(gcode[0], "rb").read(), cancelled=lambda: False)
        out.write("%-32s %s  OK  %s\n" % (scenario, Path(d).name[:8], json.dumps({k: v for k, v in result.items() if k in ("layer_count", "last_z", "first_z")}, ensure_ascii=False)))
        ok += 1
    except Exception as exc:  # noqa: BLE001
        out.write("%-32s %s  FAIL %s: %s\n" % (scenario, Path(d).name[:8], type(exc).__name__, exc))
        bad += 1
out.write("re-judged with the current pilots: %d OK, %d fail, %d skipped\n" % (ok, bad, skipped))
out.flush()
