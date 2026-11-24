"""Every harvested run of one time window as a timeline, with each machine's
busy time and idle gaps - the account a "why was it slow" question needs.

    python tools/run_timeline.py <repo-root> <YYYY-MM-DD> <from HH:MM> <to HH:MM> [--table] [--csv <file>]

Times come from each run's process.json (started_at_ns / finished_at_ns, Unix
nanoseconds -> local time). The machine is read from the worker log (fa706g3
runs carry the ORCA_BB_ALLOW_TESTBOX opt-in line). Read-only.

First used on the night of 2026-11-24 (02:00-09:45): 194 runs, 533 machine-
minutes; the guest busy 67%, fa706g3 48% with 163 idle minutes in twelve gaps
- the three longest (30, 29 and 17 minutes) were all waits for a host-side
fix. Before this the same account was done by hand out of queue logs.
"""
import csv
import datetime as dt
import glob
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
root, day, t_from, t_to = args[0], args[1], args[2], args[3]


def stamp(hhmm):
    return dt.datetime.strptime(day + " " + hhmm, "%Y-%m-%d %H:%M").timestamp() * 1e9


lo, hi = stamp(t_from), stamp(t_to)
rows = []
for d in glob.glob(os.path.join(root, "artifacts", "windows_mcp_harvest", "*") + os.sep):
    try:
        scope = json.load(open(d + "scope.json", encoding="utf-8-sig"))
        proc = json.load(open(d + "process.json", encoding="utf-8-sig"))
    except (OSError, ValueError):
        continue
    start, end = proc.get("started_at_ns"), proc.get("finished_at_ns")
    if not start or not end or not (lo <= start <= hi):
        continue
    try:
        result = json.load(open(d + "result.json", encoding="utf-8-sig"))
        worker = json.load(open(d + "native_worker.json", encoding="utf-8-sig"))
    except (OSError, ValueError):
        result, worker = {}, {}
    try:
        machine = "fa" if b"ORCA_BB_ALLOW_TESTBOX" in open(d + "native_worker.log", "rb").read() else "vm"
    except OSError:
        machine = "?"
    detail = str(((result.get("checks") or {}).get("business") or {}).get("detail") or "")
    rows.append({
        "start": dt.datetime.fromtimestamp(start / 1e9).strftime("%H:%M:%S"),
        "end": dt.datetime.fromtimestamp(end / 1e9).strftime("%H:%M:%S"),
        "s": start, "e": end, "min": round((end - start) / 60e9, 1), "machine": machine,
        "run": os.path.basename(d.rstrip(os.sep))[:8], "scenario": scope.get("scenario") or "",
        "verdict": result.get("release_verdict") or "",
        "error": (worker.get("error") or detail)[:70].replace("\n", " "),
    })
if not rows:
    raise SystemExit("no harvested run started between %s %s and %s under %s" % (day, t_from, t_to, root))
rows.sort(key=lambda r: r["s"])
window = (hi - lo) / 60e9
print("runs %s %s-%s: %d (vm %d, fa %d), %.1f machine-minutes" % (
    day, t_from, t_to, len(rows), sum(r["machine"] == "vm" for r in rows), sum(r["machine"] == "fa" for r in rows),
    sum(r["e"] - r["s"] for r in rows) / 60e9))
for machine in ("vm", "fa"):
    mine = [r for r in rows if r["machine"] == machine]
    if not mine:
        continue
    busy = sum(r["e"] - r["s"] for r in mine) / 60e9
    gaps, last = [], lo
    for r in mine:
        if (r["s"] - last) / 60e9 >= 4:
            gaps.append(((r["s"] - last) / 60e9, dt.datetime.fromtimestamp(last / 1e9).strftime("%H:%M"),
                         dt.datetime.fromtimestamp(r["s"] / 1e9).strftime("%H:%M")))
        last = max(last, r["e"])
    if (hi - last) / 60e9 >= 4:
        gaps.append(((hi - last) / 60e9, dt.datetime.fromtimestamp(last / 1e9).strftime("%H:%M"), t_to))
    print("%s: %3d runs, busy %5.1f min of %5.1f (%2d%%); idle gaps >= 4 min: %5.1f min in %d gaps" % (
        machine, len(mine), busy, window, round(100 * busy / window), sum(g[0] for g in gaps), len(gaps)))
    for minutes, a, b in sorted(gaps, reverse=True)[:12]:
        print("      idle %5.1f min  %s - %s" % (minutes, a, b))
if "--table" in sys.argv:
    for r in rows:
        print("%s-%s %4s %s %-8s %-36s %-9s %s" % (
            r["start"], r["end"][:5], r["min"], r["machine"], r["run"], r["scenario"][:36], r["verdict"], r["error"]))
if "--csv" in sys.argv:
    path = sys.argv[sys.argv.index("--csv") + 1]
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["start", "end", "min", "machine", "run", "scenario", "verdict", "error"])
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in writer.fieldnames})
    print("csv:", path)
