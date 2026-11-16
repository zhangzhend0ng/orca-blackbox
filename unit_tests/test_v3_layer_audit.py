"""Read-only batch audit challenges using synthetic receipts, never GUI runs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from harness.agent_layer_verify import verify_layer
from harness.agent_session import agent_contract
from harness.run_evidence import _json as canonical_json
from harness.run_verdict import aggregate_result, contract_digest
from tools.v3_layer_audit import AuditError, _read_at, audit_run, main
from unit_tests.test_agent_layer_verify import evidence, gcode, persist, write_json


@pytest.fixture
def audited(evidence, tmp_path):
    snapshot, trace, _ = evidence
    snapshot.contract = agent_contract("m3d_param_reslice")
    root, host = tmp_path / "guest", tmp_path / "host"
    root.mkdir(); host.mkdir()
    # The imported pure fixture uses tmp_path itself as artifacts. Move only its
    # files into the guest root; never copy live evidence into mutable test data.
    if snapshot.artifact_dir == tmp_path:
        artifacts = root / "artifacts"
        artifacts.mkdir()
        for item in list(tmp_path.iterdir()):
            if item not in (root, host):
                item.rename(artifacts / item.name)
        snapshot.artifact_dir = artifacts
    manifest = {"schema_version": 1, "run_id": snapshot.run_id, "case_id": snapshot.contract.case_id,
        "executor": "agent_mcp", "started_at": "1970-01-01T00:00:01+00:00", "started_at_ns": 1_000_000_000,
        "contract_sha256": contract_digest(snapshot.contract), "metadata": {}}
    (root / "contract.json").write_bytes(canonical_json(snapshot.contract.to_dict()) + b"\n")
    write_json(root / "manifest.json", manifest)
    write_json(snapshot.artifact_dir / "ready.json", {"schema_version": 1, "run_id": snapshot.run_id,
        "case_id": snapshot.contract.case_id, "driver_pid": 100, "app_pid": 200, "hwnd": 300,
        "contract_sha256": manifest["contract_sha256"]})
    check = verify_layer(snapshot)
    assert check.evidence_complete
    result = aggregate_result(snapshot.contract, "completed", check.checks,
        evidence_complete=True, execution_compliant=True).to_dict()
    result.update(mode="agent_shadow", runtime_status="completed", cleanup_confirmed=True, release_eligible=False, gui_execution_requested=True)
    write_json(root / "result.json", result)
    events = [("runtime_started", "guest_agent", None), ("execution_finished", "completed", None),
        ("verification_started", None, None), ("verification_finished", "completed", None),
        ("cleanup_started", None, "operation_0"), ("cleanup_finished", "confirmed", "operation_0"),
        ("cleanup_started", None, "operation_1"), ("cleanup_finished", "confirmed", "operation_1"),
        ("runtime_finished", "completed", None)]
    previous, lines = "", []
    for i, (message, status, step) in enumerate(events):
        event = {"timestamp": datetime.fromtimestamp(2 + i, timezone.utc).isoformat(), "level": "INFO",
            "message": message, "context": {"run_id": snapshot.run_id, "step_id": step, "status": status, "evidence": None},
            "sequence": i, "previous_sha256": previous}
        raw = canonical_json(event)
        lines.append(raw + b"\n"); previous = hashlib.sha256(raw).hexdigest()
    (root / "events.ndjson").write_bytes(b"".join(lines))
    actions = []
    for i, pair in enumerate(trace[1:], 1):
        req, observation = pair["request"], trace[i - 1]["response"]["observation"]
        action = {"tool": req["method"], "observation_id": req["observation_id"], "x": None, "y": None, "text": None}
        action.update(req["arguments"]); actions.append(action)
        prefix = host / f"model_{i:04d}" / ("call-" + f"{i:032x}")
        prefix.mkdir(parents=True)
        write_json(host / f"action_{i:04d}.json", action)
        image = (snapshot.artifact_dir / observation["image"]["path"]).read_bytes()
        (host / f"observation_{i:04d}.png").write_bytes(image)
        usage = {"input_tokens": 100, "output_tokens": 10}
        raw_events = [{"type": "thread.started"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(action)}},
            {"type": "turn.completed", "usage": usage}]
        (prefix / "stdout.jsonl").write_text("".join(json.dumps(x) + "\n" for x in raw_events), encoding="utf-8")
        write_json(prefix / "summary.json", {"provider": "codex", "model": None, "usage": usage,
            "dollar_cost": None, "action": action, "proxy_source": "none", "input_image_sha256": hashlib.sha256(image).hexdigest(),
            "prompt_sha256": "a" * 64, "cli_executable_sha256": "b" * 64,
            "started_at_ns": observation["frames"][-1]["captured_at_ns"] + 100_000_000,
            "finished_at_ns": observation["frames"][-1]["captured_at_ns"] + 200_000_000})
    write_json(host / "host_run.json", {"schema_version": 1, "run_id": snapshot.run_id, "case_id": snapshot.contract.case_id,
        "model_source": "codex_cli", "finished": True, "release_eligible": False, "dollar_cost": None,
        "started_at_ns": 2_000_000_000, "finished_at_ns": 100_000_000_000, "actions": actions, "model_calls": len(actions)})
    return root, host


def data(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summary(host, index=1):
    return next((host / f"model_{index:04d}").glob("call-*/summary.json"))


def test_complete_local_evidence_audit_is_shadow_and_read_only(audited):
    root, host = audited
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for base in (root, host) for p in base.rglob("*") if p.is_file()}
    result = audit_run(root, host)
    assert result["audit_ok"] and result["status"] == "SHADOW"
    assert result["full_verification"] and result["natural_cleanup"] and not result["release_eligible"]
    assert result["model_lineage"]["calls"] == 6
    assert result["model_lineage"]["usage"] == {"input_tokens": 600, "output_tokens": 60}
    assert result["exports"][0]["layer_count"] == 68 and result["exports"][1]["layer_count"] == 112
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


@pytest.mark.parametrize("field,value", [("input_image_sha256", "0" * 64), ("finished_at_ns", 999_000_000_000),
    ("usage", {"input_tokens": 1, "output_tokens": 1}), ("provider", "manual")])
def test_model_summary_cannot_replace_raw_cli_image_usage_or_time(audited, field, value):
    root, host = audited
    path = summary(host); value_map = data(path); value_map[field] = value; write_json(path, value_map)
    assert not audit_run(root, host)["audit_ok"]


@pytest.mark.parametrize("kind", ["tool", "invalid-utf8", "truncated", "oversized"])
def test_raw_cli_output_must_be_bounded_complete_utf8_without_tools(audited, kind):
    root, host = audited
    path = summary(host).with_name("stdout.jsonl")
    if kind == "tool":
        path.write_bytes(path.read_bytes() + b'{"type":"item.completed","item":{"type":"command_execution"}}\n')
    elif kind == "invalid-utf8":
        path.write_bytes(b"\xff")
    elif kind == "truncated":
        path.write_bytes(b'{"type":"turn.started"}\n')
    else:
        path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    assert not audit_run(root, host)["audit_ok"]


@pytest.mark.parametrize("name", ["agent_report.json", "process.json", "operation_receipts.ndjson"])
def test_missing_required_guest_evidence_is_never_a_path_pass_or_expected_fault(audited, name):
    root, host = audited
    (root / "artifacts" / name).unlink()
    result = audit_run(root, host)
    assert not result["audit_ok"] and not result["full_verification"]
    assert result["checks"]["path"]["status"] != "pass"
    assert not result["expected_NON_GREEN"] and result["fault_source"] is None


def test_event_chain_edit_is_detected_even_with_valid_guest_artifacts(audited):
    root, host = audited
    path = root / "events.ndjson"
    path.write_bytes(path.read_bytes().replace(b'"level":"INFO"', b'"level":"WARN"', 1))
    assert audit_run(root, host)["error"] == "event_chain_invalid"


def test_self_consistent_modified_goal_is_not_the_registered_contract(audited):
    root, host = audited
    contract = data(root / "contract.json")
    contract["steps"][1]["goal"] = "accept any output"
    raw = canonical_json(contract) + b"\n"
    (root / "contract.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    for path in (root / "manifest.json", root / "artifacts/ready.json"):
        value = data(path); value["contract_sha256"] = digest; write_json(path, value)
    assert audit_run(root, host)["error"] == "unregistered_contract"


@pytest.mark.parametrize("mutation", ["reorder", "missing-cleanup"])
def test_rehashed_event_chain_still_requires_complete_ordered_lifecycle(audited, mutation):
    root, host = audited
    path = root / "events.ndjson"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    if mutation == "reorder":
        rows[1]["message"], rows[3]["message"] = rows[3]["message"], rows[1]["message"]
    else:
        rows = [x for x in rows if x["context"]["step_id"] != "operation_1"]
    previous, output = "", []
    for index, row in enumerate(rows):
        row.update(sequence=index, previous_sha256=previous)
        raw = canonical_json(row); output.append(raw + b"\n"); previous = hashlib.sha256(raw).hexdigest()
    path.write_bytes(b"".join(output))
    assert audit_run(root, host)["error"] == "events_not_completed"


@pytest.mark.parametrize("target", ["action", "extra-call", "model-version", "contract", "forced-cleanup", "claim"])
def test_stale_actions_extra_calls_version_changes_and_claims_fail_closed(audited, target):
    root, host = audited
    if target == "action":
        path = host / "action_0001.json"; value = data(path); value["observation_id"] = "old"; write_json(path, value)
    elif target == "extra-call":
        (host / "model_0007").mkdir()
    elif target == "model-version":
        path = summary(host, 2); value = data(path); value["cli_executable_sha256"] = "c" * 64; write_json(path, value)
    elif target == "contract":
        path = root / "contract.json"; path.write_bytes(path.read_bytes() + b" ")
    elif target == "forced-cleanup":
        path = root / "artifacts/process.json"; value = data(path); value["forced_termination"] = True; write_json(path, value)
    else:
        path = root / "result.json"; value = data(path); value["verified_pass"] = 1; write_json(path, value)
    assert not audit_run(root, host)["audit_ok"]


def test_unknown_fault_label_is_not_an_expected_non_green_success(audited):
    assert audit_run(*audited, expected_fault="invented")["error"] == "expected_fault_not_registered"


def test_unknown_usage_and_unrecorded_versions_stay_unknown(audited):
    root, host = audited
    path = summary(host); value = data(path); value["usage"] = None; write_json(path, value)
    raw = path.with_name("stdout.jsonl")
    lines = [json.loads(x) for x in raw.read_text(encoding="utf-8").splitlines()]
    lines[-1]["usage"] = None
    raw.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    result = audit_run(root, host)
    assert result["audit_ok"] and result["model_lineage"]["usage"] is None
    assert result["model_lineage"]["usage_known"] is False
    assert all(value is None for value in result["version_metadata"].values())


@pytest.mark.parametrize("name", ["../private.json", "C:/private.json", "/private.json", "a\\private.json", "a/./private.json"])
def test_evidence_reader_does_not_accept_untrusted_paths(audited, name):
    with pytest.raises(AuditError, match="unsafe_evidence_path"):
        _read_at(audited[0], name, 65536)


def test_reparse_root_is_rejected_without_following_it(audited, monkeypatch):
    root, host = audited
    original = Path.lstat
    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400) if path == host else info
    monkeypatch.setattr(Path, "lstat", reparse)
    assert audit_run(root, host)["error"] == "root_link_rejected"


def test_model_call_identifier_is_not_a_file_path_from_evidence(audited):
    root, host = audited
    old = summary(host).parent
    old.rename(old.with_name("call-not-a-trusted-uuid"))
    assert audit_run(root, host)["error"] == "model_call_directory"


def test_cli_emits_json_and_uses_failure_exit_status(audited, capsys):
    root, host = audited
    assert main([str(root), "--host-dir", str(host)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "SHADOW"
    (root / "artifacts/agent_report.json").unlink()
    assert main([str(root), "--host-dir", str(host)]) == 1
    assert not json.loads(capsys.readouterr().out)["audit_ok"]


def make_fault(audited, fault, *, blocked_export=False):
    root, old_host = audited
    host = old_host.with_name("fault_host"); host.mkdir()
    artifacts = root / "artifacts"
    trace = [json.loads(x) for x in (artifacts / "trace.ndjson").read_text().splitlines()]
    receipts = [json.loads(x) for x in (artifacts / "operation_receipts.ndjson").read_text().splitlines()]
    pixels = b"\x20\x20\x20\xff" + b"\x50\x50\x50\xff" * (1920 * 1032 - 1)
    bitmap = (b"BM" + struct.pack("<III", 54 + len(pixels), 0, 54)
        + struct.pack("<IiiHHIIIIII", 40, 1920, -1032, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels)
    for pair in trace:
        obs = pair["response"]["observation"]
        obs["window"].update(width=1920, height=1032)
        for frame in obs["frames"]:
            frame.update(width=1920, height=1032, sha256=hashlib.sha256(bitmap).hexdigest())
            (artifacts / frame["path"]).write_bytes(bitmap)
    trace[3]["request"]["arguments"].update(x=298, y=794 if fault == "wrong_parameter" else 764)
    from harness.agent_layer_verify import request_digest
    receipts[3]["request_sha256"] = request_digest(trace[3]["request"])
    if fault == "wrong_parameter":
        raw = gcode("0.4", "0.24")
        (artifacts / "exports/0002.gcode").write_bytes(raw)
        receipts[-1]["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    elif fault == "missing_reslice":
        trace[4]["request"].update(method="observe", arguments={}); trace[4]["response"]["tool"] = "observe"
        receipts = [x for x in receipts if x["seq"] != 5]
    terminal_error = fault == "export_collision" or blocked_export
    if terminal_error:
        trace = trace[:6]
        trace[-1]["response"].update(is_error=True,
            error_code="export_exists" if fault == "export_collision" else "export_not_ready", observation=None)
        receipts = receipts[:-1]
        (artifacts / "agent_report.json").unlink()
        process = data(artifacts / "process.json")
        process.update(exit_code=1, forced_termination=True, cancel_reason="cancelled")
        write_json(artifacts / "process.json", process)
    manifest = data(root / "manifest.json")
    snapshot = SimpleNamespace(artifact_dir=artifacts)
    persist(snapshot, trace, receipts)
    snapshot = SimpleNamespace(contract=agent_contract("m3d_param_reslice"), artifact_dir=artifacts,
        run_id=manifest["run_id"], manifest=manifest)
    check = verify_layer(snapshot)
    status = "cancelled" if terminal_error else "completed"
    result = aggregate_result(snapshot.contract, status, check.checks,
        evidence_complete=check.evidence_complete, execution_compliant=check.execution_compliant).to_dict()
    result.update(mode="agent_shadow", runtime_status=status, cleanup_confirmed=True, release_eligible=False, gui_execution_requested=True)
    write_json(root / "result.json", result)
    if terminal_error:
        rows = [json.loads(x) for x in (root / "events.ndjson").read_text().splitlines()]
        rows = [rows[0], rows[1], rows[4], rows[5], rows[-1]]
        rows[1]["context"]["status"] = rows[-1]["context"]["status"] = status
        previous, output = "", []
        for i, row in enumerate(rows):
            row.update(sequence=i, previous_sha256=previous)
            raw = canonical_json(row); output.append(raw + b"\n"); previous = hashlib.sha256(raw).hexdigest()
        (root / "events.ndjson").write_bytes(b"".join(output))
    source, actions = "fault_probe_" + fault, []
    for i, pair in enumerate(trace[1:], 1):
        req, obs = pair["request"], trace[i - 1]["response"]["observation"]
        action = {"tool": req["method"], "observation_id": req["observation_id"], "x": None, "y": None, "text": None}
        action.update(req["arguments"]); actions.append(action)
        (host / f"model_{i:04d}").mkdir()
        write_json(host / f"action_{i:04d}.json", action)
        (host / f"observation_{i:04d}.png").write_bytes((artifacts / obs["image"]["path"]).read_bytes())
        write_json(host / f"model_{i:04d}/summary.json", {"source": source, "model_inference": False,
            "ai_trial": False, "image_sha256": obs["image"]["sha256"], "observation_id": obs["id"],
            "action": action, "created_at_ns": obs["frames"][-1]["captured_at_ns"] + 100_000_000})
    host_report = data(old_host / "host_run.json")
    host_report.update(model_source=source, actions=actions, model_calls=len(actions), finished=not terminal_error)
    write_json(host / "host_run.json", host_report)
    write_json(host / "fault_probe.json", {"schema_version": 1, "run_id": snapshot.run_id, "case_id": snapshot.contract.case_id,
        "fault": fault, "source": source, "ai_trial": False, "model_inference": False,
        "expected_release_verdict": "NON_GREEN", "release_eligible": False, "observed_release_verdict": None,
        "cleanup_confirmed": None, "disposition": "awaiting_independent_guest_evidence",
        "host_finished": not terminal_error, "host_error_type": "RuntimeError" if terminal_error else None})
    if fault == "export_collision":
        sentinel = b"orca-v3-export-collision-v1\n"; digest = hashlib.sha256(sentinel).hexdigest()
        request = {"schema_version": 1, "run_id": snapshot.run_id, "fault": fault, "source": source, "operation": "create_new",
            "path": "exports/0002.gcode", "content_ascii": sentinel.decode(), "sha256": digest, "size_bytes": len(sentinel)}
        write_json(host / "fault_injection_request.json", request)
        ack = {k: request[k] for k in ("schema_version", "run_id", "fault", "path", "sha256", "size_bytes")}; ack["created_new"] = True
        write_json(host / "fault_injection_ack.json", ack); write_json(host / "fault_injection_accepted.json", ack)
        write_json(artifacts / "fault_injection.json", {**ack, "source": source,
            "request_sha256": hashlib.sha256((host / "fault_injection_request.json").read_bytes()).hexdigest(),
            "case_id": snapshot.contract.case_id, "contract_sha256": manifest["contract_sha256"],
            "observation_id": f"{snapshot.run_id}_0005", "created_at_ns": 51_050_000_000})
        (artifacts / "exports/0002.gcode").write_bytes(sentinel)
    return root, host


@pytest.mark.parametrize("fault", ["wrong_parameter", "missing_reslice", "export_collision"])
def test_expected_fault_requires_specific_hit_and_rejection_not_ai_success(audited, fault):
    root, host = make_fault(audited, fault)
    result = audit_run(root, host, expected_fault=fault)
    assert result["audit_ok"], result
    assert result["status"] == "EXPECTED_NON_GREEN" and result["expected_NON_GREEN"]
    assert result["fault_source"] == "fault_probe_" + fault and result["ai_trial"] is False
    assert result["model_lineage"]["model_inference"] is False and result["model_lineage"]["usage"] is None
    assert not result["full_verification"] and not result["release_eligible"]


def test_forced_cleanup_and_missing_report_do_not_establish_collision_without_receipt(audited):
    root, host = make_fault(audited, "export_collision")
    (root / "artifacts/fault_injection.json").unlink()
    result = audit_run(root, host, expected_fault="export_collision")
    assert not result["audit_ok"] and not result["expected_NON_GREEN"]


def test_unrelated_tool_failure_does_not_establish_the_registered_fault(audited):
    root, host = make_fault(audited, "export_collision")
    path = root / "artifacts/trace.ndjson"
    path.write_text(path.read_text().replace('"export_exists"', '"tool_error"'))
    assert audit_run(root, host, expected_fault="export_collision")["error"] == "unrelated_fault_error"


def test_missing_reslice_export_not_ready_is_a_related_tool_rejection(audited):
    root, host = make_fault(audited, "missing_reslice", blocked_export=True)
    result = audit_run(root, host, expected_fault="missing_reslice")
    assert result["audit_ok"], result
    assert result["tool_rejection"] == "export_not_ready" and not result["natural_cleanup"]
    assert result["checks"]["path"]["status"] != "pass"


@pytest.mark.parametrize("part", ["sentinel", "ack", "request-hash"])
def test_collision_requires_unchanged_file_and_bound_typed_injection_records(audited, part):
    root, host = make_fault(audited, "export_collision")
    if part == "sentinel":
        (root / "artifacts/exports/0002.gcode").write_bytes(b"changed")
    elif part == "ack":
        path = host / "fault_injection_ack.json"; value = data(path); value["created_new"] = 1; write_json(path, value)
    else:
        path = root / "artifacts/fault_injection.json"; value = data(path); value["request_sha256"] = "0" * 64; write_json(path, value)
    assert not audit_run(root, host, expected_fault="export_collision")["audit_ok"]


def test_wrong_parameter_probe_requires_actual_wrong_first_layer_not_just_non_green(audited):
    root, host = make_fault(audited, "wrong_parameter")
    raw = gcode("0.24")
    (root / "artifacts/exports/0002.gcode").write_bytes(raw)
    path = root / "artifacts/operation_receipts.ndjson"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[-1]["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    assert not audit_run(root, host, expected_fault="wrong_parameter")["audit_ok"]
