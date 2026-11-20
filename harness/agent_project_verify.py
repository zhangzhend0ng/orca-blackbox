"""Independent save/reopen/reslice oracle, limited to the fixed cube project."""
from decimal import Decimal, DecimalException
import hashlib
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib

from .agent_layer_verify import _Handle, _RECEIPT, analyze_gcode, request_digest
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_trace_verify import read_completion, verify_trace
from .agent_verify import _fields, _identity, _int, _require
from .project_3mf import inspect_project
from .run_verdict import CheckResult, contract_digest
from .runtime_ports import VerificationOutcome
from .script_verify import _InvalidEvidence, _json, _read


def verify_project(snapshot, *, cancelled=lambda: False):
    refs, path_checked = [], False
    try:
        from .agent_session import agent_contract
        contract = snapshot.contract
        _require(contract.case_id == "m3g_export_3mf" and contract.contract_version == "ai-project-1"
                 and contract_digest(contract) == contract_digest(agent_contract("m3g_export_3mf")), "unsupported_contract")
        root, start = snapshot.artifact_dir, snapshot.manifest["started_at_ns"]
        read = lambda name, limit: _read(root, name, start, limit, cancelled)
        process, report = read_completion(snapshot, read)
        ready = _json(read("ready.json", 65536))
        _fields(ready, {"schema_version", "run_id", "case_id", "driver_pid", "app_pid", "hwnd", "contract_sha256"}, "ready_schema")
        _identity(ready, snapshot.run_id)
        _require(ready["case_id"] == contract.case_id and ready["contract_sha256"] == contract_digest(contract)
                 and type(ready["driver_pid"]) is int and ready["driver_pid"] == process["pid"]
                 and _int(ready["app_pid"], 1) and ready["app_pid"] != ready["driver_pid"]
                 and _int(ready["hwnd"], 1), "ready_identity")
        trace, operations, bounds = verify_trace(snapshot, report, read, refs, cancelled,
            project_initial={"hwnd": ready["hwnd"], "pid": ready["app_pid"]})
        _require(trace[-1]["request"]["method"] == "finish"
                 and sum(x["request"]["method"] == "click" for x in trace) == report["clicks"]
                 and [x[1] for x in operations] == ["edit", "save_project", "reopen_project", "slice", "export_gcode"], "operation_order")
        raw = read("operation_receipts.ndjson", 1024 * 1024)
        _require(raw.endswith(b"\n"), "receipts_truncated")
        receipts = [_json(x) for x in raw.splitlines()]
        _require(len(receipts) == 6, "receipt_count")
        for item in receipts:
            _fields(item, _RECEIPT, "receipt_schema")
            _identity(item, snapshot.run_id)
            _fields(item["window"], {"pid", "hwnd"}, "receipt_window_schema")
            _require(all(type(v) is int for v in item["window"].values()), "receipt_window_identity")
        boot = receipts[0]
        _require(type(boot["seq"]) is int and boot["seq"] == 0 and boot["method"] == "boot"
                 and boot["request_sha256"] is None and boot["window"] == {"hwnd": ready["hwnd"], "pid": ready["app_pid"]}
                 and _int(boot["started_at_ns"], report["started_at_ns"])
                 and _int(boot["finished_at_ns"], boot["started_at_ns"], trace[0]["response"]["observation"]["frames"][0]["captured_at_ns"]), "boot_receipt")
        _fields(boot["details"], {"fixture_path", "fixture_sha256", "datadir", "driver_pid"}, "boot_details")
        _require(boot["details"] == {"fixture_path": "input/fixture.3mf", "fixture_sha256": LAYER_FIXTURE_SHA256,
            "datadir": "profile", "driver_pid": report["driver_pid"]}, "fixture_identity")
        fixture = read("input/fixture.3mf", 1024 * 1024)
        _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "fixture_hash")
        saved, saved_details, gcode = None, None, None
        for receipt, (seq, method, request) in zip(receipts[1:], operations):
            lower, upper = bounds[seq]
            window = trace[seq - 1]["response"]["observation"]["window"]
            _require(_int(receipt["seq"], 1, 12) and receipt["seq"] == seq and receipt["method"] == method
                     and receipt["request_sha256"] == request_digest(request)
                     and receipt["window"] == {"hwnd": window["hwnd"], "pid": window["pid"]}
                     and _int(receipt["started_at_ns"], lower)
                     and _int(receipt["finished_at_ns"], receipt["started_at_ns"], upper), "receipt_lineage_or_time")
            details = receipt["details"]
            if method == "edit":
                _fields(details, {"target_hwnd", "control_class", "before_text", "after_text"}, "edit_receipt")
                _require(_int(details["target_hwnd"], 1) and details["control_class"] == "Edit"
                         and type(details["before_text"]) is str and Decimal(details["before_text"]) == Decimal("0.4")
                         and type(details["after_text"]) is str and Decimal(details["after_text"]) == Decimal("0.24"), "edit_control_or_value")
            elif method in ("save_project", "export_gcode"):
                _fields(details, {"dialog_hwnd", "edit_hwnd", "path", "sha256", "size_bytes"}, "file_receipt")
                name = "projects/0001.3mf" if method == "save_project" else "exports/0001.gcode"
                _require(_int(details["dialog_hwnd"], 1) and _int(details["edit_hwnd"], 1) and details["path"] == name
                         and _int(details["size_bytes"], 1, 16 * 1024 * 1024 if method == "save_project" else 64 * 1024 * 1024), "file_identity")
                content = read(name, 16 * 1024 * 1024 if method == "save_project" else 64 * 1024 * 1024)
                _require(len(content) == details["size_bytes"] and hashlib.sha256(content).hexdigest() == details["sha256"], "file_hash")
                refs.append("artifact:" + name + ":sha256:" + details["sha256"])
                if method == "save_project":
                    saved, saved_details = content, details
                else:
                    gcode = content
            elif method == "reopen_project":
                _fields(details, {"path", "sha256", "size_bytes", "datadir", "old_pid", "old_hwnd", "old_exit_code",
                    "old_closed_at_ns", "new_pid", "new_hwnd", "new_started_at_ns", "driver_pid"}, "reopen_receipt")
                _require(saved is not None and all(type(details[k]) is type(saved_details[k]) and details[k] == saved_details[k]
                    for k in ("path", "sha256", "size_bytes")) and details["datadir"] == "profile_reopen"
                    and all(type(details[k]) is int for k in ("old_pid", "old_hwnd", "old_exit_code", "new_pid", "new_hwnd", "driver_pid"))
                    and details["old_pid"] == ready["app_pid"] and details["old_hwnd"] == ready["hwnd"]
                    and details["new_pid"] == report["app_pid"] and details["new_hwnd"] == report["hwnd"]
                    and details["driver_pid"] == report["driver_pid"] and details["old_exit_code"] == 0
                    and _int(details["old_closed_at_ns"], receipt["started_at_ns"])
                    and _int(details["new_started_at_ns"], details["old_closed_at_ns"], receipt["finished_at_ns"]), "reopen_identity_file_or_lifecycle")
            else:
                _fields(details, {"button_hwnd", "done_observed"}, "slice_receipt")
                _require(_int(details["button_hwnd"], 1) and details["done_observed"] is True, "slice_control_or_wait")
        refs += ["artifact:trace.ndjson", "artifact:operation_receipts.ndjson", "artifact:process.json", "artifact:ready.json", "artifact:input/fixture.3mf"]
        path_checked = True
        project = inspect_project(saved, fixture, cancelled=cancelled)
        target = analyze_gcode(gcode, layer_height="0.24", cancelled=cancelled)
        _require(target["layer_count"] == 112 and Decimal(target["last_z"]) == Decimal("27.04"), "project_final_layer_schedule")
        evidence = tuple(refs)
        return VerificationOutcome({"path": CheckResult("pass", "GUI edit/save/reopen/slice/export and natural close observed", evidence),
            "business": CheckResult("pass", "3MF .24/initial .4 and unchanged cube; reopened object 112 layers .24/first .4", evidence)}, True, True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, struct.error,
            DecimalException, ET.ParseError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError, NotImplementedError) as exc:
        code = str(exc) if isinstance(exc, _InvalidEvidence) else "project_evidence_unavailable"
        status = "fail" if path_checked and isinstance(exc, _InvalidEvidence) else "unknown"
        return VerificationOutcome({"path": CheckResult("pass" if path_checked else "unknown", code, tuple(refs)),
            "business": CheckResult(status, code, tuple(refs))}, False, path_checked)


class AgentProjectVerifier:
    synthetic = False

    def start(self, snapshot):
        return _Handle(snapshot, check=verify_project)
