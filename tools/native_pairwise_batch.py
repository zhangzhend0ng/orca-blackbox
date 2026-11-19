"""Generate the admitted operation pairs and run each through hv_go and harvest."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from harness.agent_protocol import valid_run_id
from harness.native_pairwise import PAIR_CASES
from harness.native_uia_replay import read_recipe


def read_if_present(directory, name):
    path = directory / (name + ".json")
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def collect(run_id, elapsed, returncode):
    evidence = REPO / "artifacts/windows_mcp_harvest" / run_id
    host = read_if_present(REPO / "artifacts/native_save_demo" / run_id, "summary")
    outcome = read_if_present(evidence, "result")
    worker = read_if_present(evidence, "native_worker")
    receipt = read_if_present(evidence, "teardown")
    setup = read_if_present(evidence, "setup")
    manifest = read_if_present(evidence, "manifest")
    proof = read_if_present(evidence, "proof")
    cleaned = (receipt.get("run_id") == run_id and receipt.get("cleanup_confirmed") is True
               and receipt.get("active_processes") == 0 and receipt.get("token_exists") is False)
    passed = cleaned and outcome.get("verified_pass") is True and returncode == 0
    failure = None
    if not passed:
        failure = worker.get("error")
        if not failure:
            failure = outcome.get("checks", {}).get("business", {}).get("detail")
            if not failure or failure == "not checked":
                failure = "guest_result_or_cleanup_unavailable"
    return {"status": "SHADOW" if passed else "NON_GREEN", "cleanup_confirmed": cleaned,
            "failure": failure, "replay_cursor": worker.get("replay_cursor"),
            "prepare_s": (setup["finished_at_ns"] - manifest["started_at_ns"]) / 1e9 if setup and manifest else None,
            "script_s": worker["script_action_elapsed_ns"] / 1e9 if "script_action_elapsed_ns" in worker else None,
            "reopen_export_s": (proof["exported_at_ns"] - proof["reopen_started_at_ns"]) / 1e9 if proof else None,
            "host_wall_s": host.get("host_wall_seconds", elapsed),
            "old_pid": proof.get("old_pid"), "reopened_pid": proof.get("reopened_pid")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--case", action="append", choices=PAIR_CASES)
    args = parser.parse_args()
    batch_id = args.batch_id or uuid.uuid4().hex
    valid_run_id(batch_id)
    cases = tuple(dict.fromkeys(args.case or PAIR_CASES))
    rows = []
    for scenario in cases:
        recipe, digest = read_recipe(scenario)
        rows.append({"scenario": scenario, "order": PAIR_CASES[scenario], "recipe_sha256": digest,
                     "run_id": uuid.uuid5(uuid.UUID(hex=batch_id), scenario).hex,
                     "segments": recipe["segments"], "steps": recipe["steps"]})
    plan = {"batch_id": batch_id, "release_eligible": False, "cases": rows}
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "tools/native_pairwise_batch.py"], cwd=REPO).returncode:
        raise ValueError("pairwise_batch_source_changed")
    subprocess.run(["git", "ls-files", "--error-unmatch", "tools/native_pairwise_batch.py"], cwd=REPO, check=True)
    plan["source_sha"] = head
    root = REPO / "artifacts/native_pairwise" / batch_id
    root.mkdir(parents=True, exist_ok=False)
    (root / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    results = []
    started = time.monotonic()
    with (root / "results.ndjson").open("x", encoding="utf-8") as stream:
        for row in rows:
            ident, scenario = row["run_id"], row["scenario"]
            result = {"scenario": scenario, "order": row["order"], "run_id": ident}
            if results and not results[-1]["cleanup_confirmed"]:
                result.update(status="NOT_RUN", cleanup_confirmed=False, failure="previous_cleanup_unconfirmed")
            else:
                begin = time.monotonic()
                with (root / (scenario + ".log")).open("x", encoding="utf-8") as log:
                    rc = subprocess.run([sys.executable, "-B", str(REPO / "tools/native_save_demo.py"),
                        "--actor", "script", "--scenario", scenario, "--run-id", ident],
                        cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
                result.update(collect(ident, time.monotonic() - begin, rc))
            results.append(result)
            line = json.dumps(result)
            stream.write(line + "\n")
            stream.flush()
            print(line, flush=True)
    passed = sum(row["status"] == "SHADOW" for row in results)
    summary = {"batch_id": batch_id, "source_sha": head, "cases": results, "passed": passed,
               "planned": len(rows), "attempted": sum(row["status"] != "NOT_RUN" for row in results),
               "wall_s": time.monotonic() - started, "release_eligible": False}
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
