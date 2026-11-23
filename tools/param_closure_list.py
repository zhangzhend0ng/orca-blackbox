"""Which parameter cases have a SHADOW run on record, and where it ran.

    python tools/param_closure_list.py              # one line per case
    python tools/param_closure_list.py --ids        # compact: the case ids per line
    python tools/param_closure_list.py --json PATH  # the same as JSON
    python tools/param_closure_list.py --harvest DIR # another worktree's harvest

Reads every harvested run under artifacts/windows_mcp_harvest/<run>/ and
counts a case closed when at least one run of its scenario says
release_verdict SHADOW (result.json). The execution line comes from the
worker log: a run that printed the ORCA_BB_ALLOW_TESTBOX line or worked
under orca-blackbox-glm ran on the fa706g3 test box, anything else on the
Hyper-V guest. Read-only; this is the number the run record and the ledger
quote - do not count by hand (the night of 2026-11-23/24 a hand count was
one too high for hours).

Verdict policy is not changed here: this script track only ever yields
SHADOW (harness/native_fixture_suite.py writes release_eligible False).
"""
import glob
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import native_pilots  # noqa: E402

HARVEST = ROOT / "artifacts" / "windows_mcp_harvest"


def case_number(case_id):
    """'param_278_raft' -> 278; 'param_layer_pair_254' -> 254 (the number is
    wherever it sits in the id)."""
    import re
    found = re.findall(r"\d+", case_id)
    return int(found[-1]) if found else 999


def execution_line(run_dir):
    """'fa706g3' or 'vm-guest' - from what the worker log says about itself."""
    try:
        with open(run_dir / "native_worker.log", encoding="utf-8", errors="replace") as stream:
            for _index, line in enumerate(stream):
                if "ORCA_BB_ALLOW_TESTBOX" in line or "orca-blackbox-glm" in line:
                    return "fa706g3"
                if _index > 400:
                    break
    except OSError:
        pass
    return "vm-guest"


def load(path):
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def closure():
    cases = {}
    for scenario, module in sorted(native_pilots.TRIALS.items()):
        if scenario.startswith("uia_param_"):
            pilot = importlib.import_module("harness." + module)
            cases[scenario] = {"case_id": pilot.CASE_ID, "runs": []}
    for run_dir in sorted(glob.glob(str(HARVEST / "*") + os.sep), key=os.path.getmtime):
        result = load(Path(run_dir) / "result.json")
        scope = load(Path(run_dir) / "scope.json")
        if not result or not scope:
            continue
        scenario = scope.get("scenario")
        if scenario not in cases:
            continue
        cases[scenario]["runs"].append({
            "run": os.path.basename(run_dir.rstrip("/\\")),
            "verdict": result.get("release_verdict"),
            "ended": os.path.getmtime(run_dir),
            "line": execution_line(Path(run_dir)),
        })
    rows = []
    for scenario, case in cases.items():
        shadow = [r for r in case["runs"] if r["verdict"] == "SHADOW"]
        best = max(shadow, key=lambda r: r["ended"]) if shadow else None
        rows.append({
            "scenario": scenario, "case_id": case["case_id"], "closed": bool(shadow),
            "run": best["run"][:8] if best else None, "line": best["line"] if best else None,
            "shadow_runs": len(shadow), "runs": len(case["runs"]),
        })
    rows.sort(key=lambda r: case_number(r["case_id"]))
    return rows


def main():
    global HARVEST
    if "--harvest" in sys.argv:
        HARVEST = Path(sys.argv[sys.argv.index("--harvest") + 1])
    rows = closure()
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    closed = [r for r in rows if r["closed"]]
    if "--ids" in sys.argv:
        print("closed %d/%d" % (len(closed), len(rows)))
        for line in ("vm-guest", "fa706g3"):
            print("  %-9s %s" % (line, " ".join("#%d" % case_number(r["case_id"]) for r in closed if r["line"] == line)))
        print("  open      %s" % " ".join("#%d" % case_number(r["case_id"]) for r in rows if not r["closed"]))
        return 0
    for r in rows:
        print("%-30s %-24s %s %-9s x%d/%d" % (
            r["case_id"], r["scenario"].replace("uia_param_", ""),
            r["run"] or "-", r["line"] or "-", r["shadow_runs"], r["runs"]))
    print("closed %d of %d parameter cases; %d on the guest, %d on fa706g3" % (
        len(closed), len(rows), sum(1 for r in closed if r["line"] == "vm-guest"),
        sum(1 for r in closed if r["line"] == "fa706g3")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
