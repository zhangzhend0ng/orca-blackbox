"""Read-only composition audit for the whole fixed project persistence chain."""
from __future__ import annotations

import argparse
from decimal import DecimalException
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.agent_layer_verify import _PROCESS, analyze_gcode
from harness.agent_project_verify import verify_project
from harness.agent_session import agent_contract
from harness.project_3mf import inspect_project
from harness.run_contract import validate_contract
from harness.run_evidence import _id
from harness.run_verdict import aggregate_result, contract_digest
from harness.script_verify import _json
from tools.v3_layer_audit import (AuditError, _data, _events, _fields, _integer, _model_lineage,
                                 _need, _probe_lineage, _read_at, _root)

FAULTS = ("save_before_edit", "missing_reopen", "missing_slice")


def _project_fault(root, host, artifacts, manifest, ready, process, result, verification, output, fault):
    start = manifest["started_at_ns"]
    _need(result.get("release_verdict") == "NON_GREEN" and result.get("verified_pass") is False
          and result.get("runtime_status") == result.get("execution_status") in ("completed", "failed", "cancelled"), "fault_not_rejected")
    trace, lineage = _probe_lineage(host, artifacts, manifest, ready, process, fault)
    output["model_lineage"] = lineage
    output["events"] = _events(root, manifest, execution_status=result["execution_status"],
                                has_verification=result["execution_status"] == "completed")
    fixture = _read_at(artifacts, "input/fixture.3mf", 1024 * 1024, start)
    saved = _read_at(artifacts, "projects/0001.3mf", 16 * 1024 * 1024, start)
    # The fixed fixture identity is also bound by the boot receipt checked by
    # the shared probe lineage/receipts, never inferred from a model statement.
    from harness.agent_protocol import LAYER_FIXTURE_SHA256
    _need(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "fault_fixture_identity")
    expected_layer = "0.4" if fault == "save_before_edit" else "0.24"
    output["project"] = inspect_project(saved, fixture, layer_height=expected_layer)
    methods = [x["request"]["method"] for x in trace]
    rejection = verification.checks["path"].detail
    final_path = artifacts / "exports/0001.gcode"
    output["gcode_exists"] = final_path.exists()
    if fault in ("save_before_edit", "missing_reopen"):
        _need(output["natural_cleanup"] and result["execution_status"] == "completed"
              and verification.checks["path"].status != "pass" and rejection in
              (("operation_order",) if fault == "save_before_edit" else ("reopen_count", "operation_order")), "fault_path_rejection_missing")
        _need(methods.index("save_project") < methods.index("edit") if fault == "save_before_edit" else
              "reopen_project" not in methods, "fault_sequence_not_hit")
        output["gcode"] = analyze_gcode(_read_at(artifacts, "exports/0001.gcode", 64 * 1024 * 1024, start), layer_height=expected_layer)
        _need(output["gcode"]["layer_count"] == (68 if fault == "save_before_edit" else 112), "fault_gcode_not_proven")
    else:
        _need("slice" not in methods, "fault_slice_not_missing")
        if trace[-1]["response"]["is_error"]:
            _need(trace[-1]["response"]["error_code"] == "export_not_ready" and not final_path.exists(), "fault_export_rejection_missing")
            output["gcode"] = None
        else:
            _need(output["natural_cleanup"] and rejection == "operation_order" and verification.checks["path"].status != "pass",
                  "fault_path_rejection_missing")
            raw = _read_at(artifacts, "exports/0001.gcode", 64 * 1024 * 1024, start)
            output["gcode"] = {"verified": False, "actual_layer_height": None}
            for height in ("0.24", "0.4"):
                try:
                    output["gcode"] = analyze_gcode(raw, layer_height=height)
                    break
                except ValueError:
                    continue
    output.update(audit_ok=True, status="EXPECTED_NON_GREEN", fault_source="fault_probe_project_" + fault,
        expected_NON_GREEN=True, ai_trial=False, tool_rejection=trace[-1]["response"]["error_code"])
    return output


def audit_project(run_dir, host_dir, expected_fault=None):
    """Compose existing independent checks; no launch, extraction or write APIs."""
    output = {"schema_version": 1, "audit_ok": False, "status": "NOT_ACCEPTED", "cleanup_confirmed": False,
        "fault_source": None, "expected_NON_GREEN": False, "release_eligible": False, "batch_binding_verified": False}
    try:
        _need(expected_fault is None or expected_fault in FAULTS, "expected_fault_not_registered")
        root, host = _root(run_dir), _root(host_dir)
        manifest = _data(root, "manifest.json")
        _fields(manifest, {"schema_version", "run_id", "case_id", "executor", "started_at", "started_at_ns", "contract_sha256", "metadata"}, "manifest_schema")
        run_id, start = _id(manifest["run_id"]), manifest["started_at_ns"]
        _need(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and _integer(start, 1)
              and manifest["case_id"] == "m3g_export_3mf" and manifest["executor"] == "agent_mcp", "manifest_identity")
        raw = _read_at(root, "contract.json", 65536, start)
        contract = validate_contract(_json(raw))
        _need(hashlib.sha256(raw).hexdigest() == manifest["contract_sha256"] == contract_digest(contract)
              == contract_digest(agent_contract("m3g_export_3mf")), "unregistered_contract")
        artifacts = _root(root / "artifacts")
        ready, process, result = _data(artifacts, "ready.json", start), _data(artifacts, "process.json", start), _data(root, "result.json", start)
        _fields(ready, {"schema_version", "run_id", "case_id", "driver_pid", "app_pid", "hwnd", "contract_sha256"}, "ready_schema")
        _fields(process, _PROCESS, "process_schema")
        _need(all(type(x["schema_version"]) is int and x["schema_version"] == 1 and x["run_id"] == run_id
              and x["case_id"] == contract.case_id for x in (ready, process))
              and all(_integer(ready[k], 1) for k in ("driver_pid", "app_pid", "hwnd"))
              and ready["driver_pid"] != ready["app_pid"] and type(process["pid"]) is int and process["pid"] == ready["driver_pid"]
              and process["backend"] == "win32_job" and process["job_assigned"] is True
              and type(process["active_processes"]) is int and process["active_processes"] == 0
              and type(process["forced_termination"]) is bool and type(process["exit_code"]) is int
              and process["cancel_reason"] in (None, "cancelled") and _integer(process["started_at_ns"], start)
              and _integer(process["finished_at_ns"], process["started_at_ns"])
              and ready["contract_sha256"] == manifest["contract_sha256"] and result.get("cleanup_confirmed") is True
              and result.get("release_eligible") is False and result.get("mode") == "agent_shadow", "cleanup_or_identity_unconfirmed")
        output.update(run_id=run_id, contract_sha256=manifest["contract_sha256"], cleanup_confirmed=True,
            natural_cleanup=process["exit_code"] == 0 and process["forced_termination"] is False and process["cancel_reason"] is None,
            process={k: process[k] for k in ("exit_code", "forced_termination", "active_processes", "cancel_reason")})
        snapshot = SimpleNamespace(contract=contract, artifact_dir=artifacts, run_id=run_id, manifest=manifest)
        verification = verify_project(snapshot)
        output["checks"] = {k: {"status": v.status, "detail": v.detail} for k, v in verification.checks.items()}
        output["full_verification"] = verification.evidence_complete and verification.execution_compliant
        if expected_fault is not None:
            return _project_fault(root, host, artifacts, manifest, ready, process, result, verification, output, expected_fault)
        _need(output["natural_cleanup"] and output["full_verification"] and all(verification.checks[k].status == "pass" for k in ("path", "business"))
              and result.get("runtime_status") == result.get("execution_status") == "completed", "whole_project_not_verified")
        expected = aggregate_result(contract, "completed", verification.checks, evidence_complete=True, execution_compliant=True).to_dict()
        expected["mode"] = "agent_shadow"
        _need(all(result.get(k) == v and type(result.get(k)) is type(v) for k, v in expected.items()), "persisted_verdict_mismatch")
        trace = [_json(x) for x in _read_at(artifacts, "trace.ndjson", 1024 * 1024, start).splitlines()]
        output["events"] = _events(root, manifest)
        output["model_lineage"] = _model_lineage(host, trace, run_id, contract.case_id, start)
        output["project"] = inspect_project(_read_at(artifacts, "projects/0001.3mf", 16 * 1024 * 1024, start),
                                             _read_at(artifacts, "input/fixture.3mf", 1024 * 1024, start))
        output["gcode"] = analyze_gcode(_read_at(artifacts, "exports/0001.gcode", 64 * 1024 * 1024, start), layer_height="0.24")
        output.update(audit_ok=True, status="SHADOW", ai_trial=True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, RecursionError, DecimalException,
            ET.ParseError, zipfile.BadZipFile, zlib.error, EOFError) as exc:
        output["error"] = str(exc) if isinstance(exc, AuditError) else "invalid_or_unavailable_evidence"
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--host-dir", type=Path, required=True)
    parser.add_argument("--expected-fault", choices=FAULTS)
    args = parser.parse_args(argv)
    result = audit_project(args.run_dir, args.host_dir, args.expected_fault)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["audit_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
