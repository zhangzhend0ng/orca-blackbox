"""Status of the suffixed runs on one fixture build: every harvested run whose
scenario carries the suffix and whose input fixture has the given sha256.

    python tools/suffixed_status.py <repo-root> <suffix> <fixture-sha256> [--verbose]

Prints one line per scenario (latest run of that scenario only): verdict, the
machine (vm / fa by the worker log), the worker error or the verifier detail,
and a tally. Read-only."""
import glob
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root, suffix, sha = sys.argv[1], sys.argv[2], sys.argv[3]
verbose = "--verbose" in sys.argv
runs = {}
for d in glob.glob(os.path.join(root, "artifacts", "windows_mcp_harvest", "*") + os.sep):
    try:
        r = json.load(open(d + "result.json", encoding="utf-8-sig"))
        s = json.load(open(d + "scope.json", encoding="utf-8-sig"))
    except (OSError, ValueError):
        continue
    sc = s.get("scenario") or ""
    if not sc.endswith(suffix):
        continue
    try:
        fixture_sha = hashlib.sha256(open(d + "input/fixture.3mf", "rb").read()).hexdigest()
    except OSError:
        continue
    if fixture_sha != sha:
        continue
    try:
        w = json.load(open(d + "native_worker.json", encoding="utf-8-sig"))
    except OSError:
        w = {}
    try:
        machine = "fa" if b"ORCA_BB_ALLOW_TESTBOX" in open(d + "native_worker.log", "rb").read() else "vm"
    except OSError:
        machine = "?"
    det = (r.get("checks", {}).get("business") or {}).get("detail") or ""
    runs.setdefault(sc, []).append((os.path.getmtime(d), os.path.basename(d.rstrip(os.sep))[:8], r.get("release_verdict"),
                                    machine, w.get("error") or "", det))
tally = {}
for sc in sorted(runs):
    latest = sorted(runs[sc])[-1]
    tag = latest[2] if latest[2] in ("SHADOW", "NON_GREEN", "GREEN") else (latest[2] or "?")
    if tag != "SHADOW":
        tag += ":" + (latest[4] or str(latest[5])[:60]).replace(" ", "")[:70]
    tally[tag] = tally.get(tag, 0) + 1
    if verbose or latest[2] != "SHADOW":
        print("%s %s %-40s %s" % (latest[1], latest[3], sc, tag))
print("scenarios with a run on fixture %s: %d" % (sha[:8], len(runs)))
for tag, n in sorted(tally.items(), key=lambda kv: -kv[1]):
    print("   %3d  %s" % (n, tag))
if not verbose:
    print("   SHADOW:", " ".join(sc.replace("uia_param_", "").replace(suffix, "") for sc in sorted(runs)
                                if sorted(runs[sc])[-1][2] == "SHADOW"))
