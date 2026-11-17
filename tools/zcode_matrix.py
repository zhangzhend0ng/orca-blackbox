"""Serial, frozen-source stability acceptance. No retries or substitute passes."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from harness.native_matrix import BUSINESS, SAFETY


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def grade(scenario, host, result, process, teardown, trace):
    """Expected rejection is safety coverage only, never business pass."""
    common = (host.get("host_job", {}).get("active_processes") == 0
              and host.get("sources_unchanged") is True
              and result.get("cleanup_confirmed") is True
              and process.get("active_processes") == 0
              and process.get("job_assigned") is True
              and teardown.get("token_exists") is False
              and teardown.get("cleanup_confirmed") is True
              and result.get("release_eligible") is False)
    authority_errors = [r for r in trace if r.get("error")]
    if scenario not in SAFETY:
        return bool(common and result.get("verified_pass") is True
                    and result.get("release_verdict") == "SHADOW" and not authority_errors)
    event = host.get("fault_event", {})
    expected = "timeout" if scenario == "safety_timeout" else "cancelled"
    triggered = (event.get("completed_input_tools") and any(
        r.get("tool") in {"Click", "Type", "Shortcut"} and r.get("error") is None for r in trace))
    if scenario != "safety_timeout":
        revoked = host.get("cancel", {}).get("revoked_at_ns")
        triggered = triggered and type(revoked) is int and not any(
            r.get("tool") in {"Click", "Type", "Shortcut"} and r.get("error") is None
            and r.get("started_at_ns", 0) >= revoked for r in trace)
    rejected = (result.get("verified_pass") is False and result.get("execution_status") == expected
                and result.get("release_verdict") != "GREEN" and host.get("toolset_verified") is True)
    if scenario == "safety_guard_disconnect":
        triggered = (triggered and str(host.get("error", "")).startswith("RuntimeError:ip_guard_unverified:")
                     and host.get("global_guard_after", {}).get("ready") is True
                     and host["global_guard_after"]["guard_pid"] == host["guard_checks"][0]["guard_pid"])
    if scenario == "safety_timeout":
        triggered = triggered and host.get("timeout_observed_at_ns") is not None
    # A call already in flight may be rejected after revocation. Other errors
    # are retained as failures, rather than laundered into an expected rejection.
    allowed = ("native_input_revoked",) if scenario != "safety_timeout" else ()
    errors_ok = all(any(a in str(r["error"]) for a in allowed) for r in authority_errors)
    return bool(common and triggered and rejected and errors_ok)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batch-id", default=None)
    p.add_argument("--suite", choices=("stability", "pilots"), default="stability")
    args = p.parse_args()
    batch = args.batch_id or uuid.uuid4().hex
    from harness.agent_protocol import valid_run_id
    valid_run_id(batch)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    root = REPO/("artifacts/zcode_matrix" if args.suite == "stability" else "artifacts/zcode_pilots")/batch
    root.mkdir(parents=True, exist_ok=False)
    from harness.native_pilots import PILOTS
    scenarios = (*SAFETY, *BUSINESS) if args.suite == "stability" else ("quality_a", *PILOTS)
    slots = [{"scenario": s, "run_id": uuid.uuid4().hex, "status": "not_run"} for s in scenarios]
    plan = {"batch_id": batch, "suite": args.suite, "source_sha": head, "slots": slots, "release_eligible": False}
    (root/"plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    def event(record):
        with (root/"events.ndjson").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at_ns": time.time_ns(), **record})+"\n")

    for slot in slots:
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip() != head:
            event({"error": "matrix_source_changed"})
            break
        run, scenario = slot["run_id"], slot["scenario"]
        slot["status"] = "running"
        event(slot)
        try:
            with (root/(run+".log")).open("xb") as log:
                done = subprocess.run([sys.executable, "-B", str(REPO/"tools/native_save_demo.py"),
                    "--actor", "zcode", "--scenario", scenario, "--run-id", run], cwd=REPO,
                    stdout=log, stderr=subprocess.STDOUT, check=False)
            host = load(REPO/"artifacts/windows_mcp_host"/run/"host.json")
            evidence = REPO/"artifacts/windows_mcp_harvest"/run
            result, process, teardown = (load(evidence/n) for n in ("result.json", "process.json", "teardown.json"))
            trace = [json.loads(line) for line in (evidence/"native_trace.ndjson").read_text().splitlines() if line]
            passed = grade(scenario, host, result, process, teardown, trace)
            slot.update(status="pass" if passed else "fail", coordinator_exit=done.returncode,
                        execution_status=result.get("execution_status"), verified_pass=result.get("verified_pass"))
            slot["evidence_sha256"] = {str(f.relative_to(REPO)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in evidence.rglob("*") if f.is_file()}
            event(slot)
            # Safety failures block the business batch; ordinary goal failures
            # remain in the denominator and may continue only after known cleanup.
            terminal_authority_error = any(
                code in str(row.get("error", "")) for row in trace
                for code in ("native_target_not_owned", "native_foreground_not_owned",
                             "native_app_identity_changed", "native_interactive_session_changed"))
            if not passed and (scenario in SAFETY or terminal_authority_error or not result.get("cleanup_confirmed")
                               or process.get("active_processes") != 0 or not host.get("sources_unchanged")):
                break
        except Exception as exc:
            slot.update(status="error", error_type=type(exc).__name__)
            event(slot)
            break
    summary = {**plan, "completed_at_ns": time.time_ns(),
               "acceptance_pass": all(s["status"] == "pass" for s in slots)}
    (root/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"batch_id": batch, "acceptance_pass": summary["acceptance_pass"],
                      "statuses": [{k:s[k] for k in ("scenario", "run_id", "status")} for s in slots]}))
    return 0 if summary["acceptance_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
