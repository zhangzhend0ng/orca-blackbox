"""Project batch audit over synthetic local evidence; no GUI/model/VM."""
from datetime import datetime, timezone
import hashlib
import json
import struct

import pytest

from harness.agent_layer_verify import request_digest
from harness.agent_project_verify import verify_project
from harness.run_evidence import _json as canonical_json
from harness.run_verdict import aggregate_result, contract_digest
from tools.v3_project_audit import audit_project, main
from unit_tests.test_agent_project_verify import project_evidence
from unit_tests.test_agent_layer_verify import evidence, gcode, persist, write_json


def data(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(root, run_id, status):
    rows = [("runtime_started", "guest_agent", None), ("execution_finished", status, None)]
    if status == "completed":
        rows += [("verification_started", None, None), ("verification_finished", "completed", None)]
    for i in range(2 if status == "completed" else 1):
        rows += [("cleanup_started", None, f"operation_{i}"), ("cleanup_finished", "confirmed", f"operation_{i}")]
    rows += [("runtime_finished", status, None)]
    previous, raw = "", []
    for i, (message, state, step) in enumerate(rows):
        row = {"timestamp": datetime.fromtimestamp(2 + i, timezone.utc).isoformat(), "level": "INFO", "message": message,
            "context": {"run_id": run_id, "step_id": step, "status": state, "evidence": None}, "sequence": i, "previous_sha256": previous}
        line = canonical_json(row); raw.append(line + b"\n"); previous = hashlib.sha256(line).hexdigest()
    (root / "events.ndjson").write_bytes(b"".join(raw))


def verdict(root, snapshot, status="completed"):
    check = verify_project(snapshot)
    result = aggregate_result(snapshot.contract, status, check.checks,
        evidence_complete=check.evidence_complete, execution_compliant=check.execution_compliant).to_dict()
    result.update(mode="agent_shadow", runtime_status=status, release_eligible=False, cleanup_confirmed=True, gui_execution_requested=True)
    write_json(root / "result.json", result)
    events(root, snapshot.run_id, status)


def host_records(host, snapshot, trace, fault=None):
    host.mkdir()
    actions = []
    source = "fault_probe_project_" + fault if fault else "codex_cli"
    for i, pair in enumerate(trace[1:], 1):
        request, obs = pair["request"], trace[i - 1]["response"]["observation"]
        action = {"tool": request["method"], "observation_id": request["observation_id"], "x": None, "y": None, "text": None}
        action.update(request["arguments"]); actions.append(action)
        write_json(host / f"action_{i:04d}.json", action)
        image = (snapshot.artifact_dir / obs["image"]["path"]).read_bytes()
        (host / f"observation_{i:04d}.png").write_bytes(image)
        if fault:
            call = host / f"model_{i:04d}"; call.mkdir()
            write_json(call / "summary.json", {"source": source, "model_inference": False, "ai_trial": False,
                "image_sha256": obs["image"]["sha256"], "observation_id": obs["id"], "action": action,
                "created_at_ns": obs["frames"][-1]["captured_at_ns"] + 100_000_000})
        else:
            call = host / f"model_{i:04d}" / ("call-" + f"{i:032x}"); call.mkdir(parents=True)
            usage = {"input_tokens": 100, "output_tokens": 10}
            raw = [{"type": "thread.started"}, {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(action)}},
                {"type": "turn.completed", "usage": usage}]
            (call / "stdout.jsonl").write_text("".join(json.dumps(x) + "\n" for x in raw), encoding="utf-8")
            write_json(call / "summary.json", {"provider": "codex", "model": None, "usage": usage, "dollar_cost": None,
                "action": action, "proxy_source": "none", "input_image_sha256": hashlib.sha256(image).hexdigest(),
                "prompt_sha256": "a" * 64, "cli_executable_sha256": "b" * 64,
                "started_at_ns": obs["frames"][-1]["captured_at_ns"] + 100_000_000,
                "finished_at_ns": obs["frames"][-1]["captured_at_ns"] + 200_000_000})
    complete = trace[-1]["response"]["finished"]
    write_json(host / "host_run.json", {"schema_version": 1, "run_id": snapshot.run_id, "case_id": snapshot.contract.case_id,
        "model_source": source, "finished": complete, "release_eligible": False, "dollar_cost": None,
        "started_at_ns": 2_000_000_000, "finished_at_ns": 100_000_000_000, "actions": actions, "model_calls": len(actions)})
    if fault:
        write_json(host / "fault_probe.json", {"schema_version": 1, "run_id": snapshot.run_id, "case_id": snapshot.contract.case_id,
            "fault": fault, "source": source, "ai_trial": False, "model_inference": False, "expected_release_verdict": "NON_GREEN",
            "release_eligible": False, "observed_release_verdict": None, "cleanup_confirmed": None,
            "disposition": "awaiting_independent_guest_evidence", "host_finished": complete, "host_error_type": None if complete else "RuntimeError"})


@pytest.fixture
def audited_project(project_evidence, tmp_path):
    snapshot, trace, receipts = project_evidence
    root = tmp_path / "guest"; root.mkdir(); artifacts = root / "artifacts"; artifacts.mkdir()
    for item in list(tmp_path.iterdir()):
        if item != root:
            item.rename(artifacts / item.name)
    snapshot.artifact_dir = artifacts
    manifest = {"schema_version": 1, "run_id": snapshot.run_id, "case_id": snapshot.contract.case_id, "executor": "agent_mcp",
        "started_at": "1970-01-01T00:00:01+00:00", "started_at_ns": 1_000_000_000,
        "contract_sha256": contract_digest(snapshot.contract), "metadata": {}}
    write_json(root / "manifest.json", manifest)
    (root / "contract.json").write_bytes(canonical_json(snapshot.contract.to_dict()) + b"\n")
    verdict(root, snapshot)
    host = tmp_path / "native_host"; host_records(host, snapshot, trace)
    return root, host, snapshot, trace, receipts


def make_project_fault(audited_project, fault, *, cached_export=False):
    root, old_host, snapshot, trace, receipts = audited_project
    artifacts = snapshot.artifact_dir
    pixels = b"\x20\x20\x20\xff" + b"\x50\x50\x50\xff" * (1920 * 1032 - 1)
    bitmap = b"BM" + struct.pack("<III", 54 + len(pixels), 0, 54) + struct.pack("<IiiHHIIIIII", 40, 1920, -1032, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels
    for pair in trace:
        obs = pair["response"]["observation"]; obs["window"].update(width=1920, height=1032)
        for frame in obs["frames"]:
            frame.update(width=1920, height=1032, sha256=hashlib.sha256(bitmap).hexdigest())
            (artifacts / frame["path"]).write_bytes(bitmap)
    trace[1]["request"]["arguments"].update(x=298, y=764)
    if fault == "save_before_edit":
        trace[1]["request"].update(method="save_project", arguments={}); trace[1]["response"]["tool"] = "save_project"
        trace[2]["request"].update(method="edit", arguments={"x": 298, "y": 764, "text": "0.24"}); trace[2]["response"]["tool"] = "edit"
        old_edit, old_save = receipts[1]["details"], receipts[2]["details"]
        receipts[1].update(method="save_project", details=old_save); receipts[2].update(method="edit", details=old_edit)
        saved = (artifacts / "input/fixture.3mf").read_bytes(); (artifacts / "projects/0001.3mf").write_bytes(saved)
        for row in (receipts[1], receipts[3]): row["details"].update(sha256=hashlib.sha256(saved).hexdigest(), size_bytes=len(saved))
        raw = gcode(); (artifacts / "exports/0001.gcode").write_bytes(raw)
        receipts[-1]["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    elif fault == "missing_reopen":
        trace[3]["request"].update(method="observe", arguments={}); trace[3]["response"]["tool"] = "observe"
        receipts = [x for x in receipts if x["seq"] != 4]
        for pair in trace[3:]: pair["response"]["observation"]["window"].update(pid=200, hwnd=300)
        for item in receipts: item["window"].update(pid=200, hwnd=300)
        report = data(artifacts / "agent_report.json"); report.update(app_pid=200, hwnd=300); write_json(artifacts / "agent_report.json", report)
    else:
        trace[4]["request"].update(method="observe", arguments={}); trace[4]["response"]["tool"] = "observe"
        receipts = [x for x in receipts if x["seq"] != 5]
        if not cached_export:
            trace = trace[:6]; trace[-1]["response"].update(is_error=True, error_code="export_not_ready", observation=None)
            receipts = [x for x in receipts if x["seq"] != 6]
            (artifacts / "exports/0001.gcode").unlink()
            report = data(artifacts / "agent_report.json"); report.update(calls=6, status="failed"); write_json(artifacts / "agent_report.json", report)
            process = data(artifacts / "process.json"); process["exit_code"] = 1; write_json(artifacts / "process.json", process)
    for item in receipts[1:]: item["request_sha256"] = request_digest(trace[item["seq"] - 1]["request"])
    persist(snapshot, trace, receipts)
    verdict(root, snapshot, "completed" if trace[-1]["response"]["finished"] else "failed")
    host = old_host.with_name("fault_host"); host_records(host, snapshot, trace, fault)
    return root, host, snapshot, trace, receipts


def test_positive_composes_real_oracles_native_cli_and_natural_cleanup(audited_project):
    root, host, *_ = audited_project
    result = audit_project(root, host)
    assert result["audit_ok"], result
    assert result["status"] == "SHADOW" and result["cleanup_confirmed"]
    assert result["full_verification"] and result["gcode"]["layer_count"] == 112
    assert result["model_lineage"]["calls"] == 6 and result["model_lineage"]["usage"]["input_tokens"] == 600


@pytest.mark.parametrize("fault", ["save_before_edit", "missing_reopen", "missing_slice"])
def test_each_fault_must_hit_its_own_persistence_path_and_related_rejection(audited_project, fault):
    root, host, *_ = make_project_fault(audited_project, fault)
    result = audit_project(root, host, fault)
    assert result["audit_ok"], result
    assert result["status"] == "EXPECTED_NON_GREEN" and result["cleanup_confirmed"]
    assert result["fault_source"] == "fault_probe_project_" + fault and not result["ai_trial"]
    assert result["model_lineage"]["model_inference"] is False
    if fault == "save_before_edit": assert result["project"]["layer_height"] == result["gcode"]["layer_height"] == "0.4"
    if fault == "missing_reopen": assert result["project"]["layer_height"] == result["gcode"]["layer_height"] == "0.24"
    if fault == "missing_slice": assert result["tool_rejection"] == "export_not_ready" and not result["gcode_exists"]


def test_available_export_still_cannot_replace_explicit_slice(audited_project):
    root, host, *_ = make_project_fault(audited_project, "missing_slice", cached_export=True)
    result = audit_project(root, host, "missing_slice")
    assert result["audit_ok"] and result["checks"]["path"]["detail"] == "operation_order"
    assert result["gcode_exists"] and result["gcode"]["layer_height"] == "0.24"


@pytest.mark.parametrize("mutation", ["source", "hash", "profile", "identity", "unrelated-error"])
def test_non_green_alone_does_not_establish_a_registered_project_fault(audited_project, mutation):
    root, host, snapshot, trace, receipts = make_project_fault(audited_project, "missing_slice")
    if mutation == "source":
        path = host / "fault_probe.json"; value = data(path); value["model_inference"] = True; write_json(path, value)
    elif mutation in ("hash", "profile"):
        receipts[3]["details"]["sha256" if mutation == "hash" else "datadir"] = "0" * 64 if mutation == "hash" else "profile"
    elif mutation == "identity":
        trace[4]["response"]["observation"]["window"]["pid"] = 999
    else:
        trace[-1]["response"]["error_code"] = "tool_error"
    persist(snapshot, trace, receipts)
    assert not audit_project(root, host, "missing_slice")["audit_ok"]


def test_wrong_saved_or_final_values_cannot_fake_save_before_edit_hit(audited_project):
    root, host, snapshot, trace, receipts = make_project_fault(audited_project, "save_before_edit")
    raw = gcode("0.24"); (snapshot.artifact_dir / "exports/0001.gcode").write_bytes(raw)
    receipts[-1]["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    persist(snapshot, trace, receipts)
    assert not audit_project(root, host, "save_before_edit")["audit_ok"]


def test_missing_report_or_unknown_fault_never_becomes_a_full_positive(audited_project):
    root, host, snapshot, *_ = audited_project
    assert not audit_project(root, host, "invented")["audit_ok"]
    (snapshot.artifact_dir / "agent_report.json").unlink()
    result = audit_project(root, host)
    assert not result["audit_ok"] and result["status"] == "NOT_ACCEPTED"


def test_cli_json_has_fixed_batch_consumption_fields(audited_project, capsys):
    root, host, *_ = audited_project
    assert main([str(root), "--host-dir", str(host)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["audit_ok"] is True and value["status"] == "SHADOW" and value["cleanup_confirmed"] is True
