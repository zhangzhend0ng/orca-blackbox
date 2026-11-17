"""Registered native-agent save goal and read-only business proof adapter."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time
import struct
import zipfile
import zlib
import xml.etree.ElementTree as ET
from decimal import DecimalException

from .agent_protocol import LAYER_FIXTURE_SHA256, valid_run_id
from .run_contract import validate_contract
from .run_verdict import CheckResult, contract_digest
from .runtime_ports import VerificationOutcome
from .script_executor import _ScriptHandle

REPO = Path(__file__).resolve().parents[1]
NATIVE_SUT_SHA256 = "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf"


class NativeSaveHandle(_ScriptHandle):
    """Allow natural helper teardown, then bound an orphaned owned tree."""
    def __init__(self, *args):
        super().__init__(*args)
        self.worker_exited_at = None

    def poll(self):
        code, active = self.process.poll()
        if code is not None and active:
            if self.worker_exited_at is None:
                self.worker_exited_at = time.monotonic()
            if code != 0 or time.monotonic()-self.worker_exited_at >= 10:
                self.cancel("adapter_error")
        return super().poll()


def native_contract():
    return validate_contract({"schema_version": 1, "case_id": "m3g_export_3mf",
        "contract_version": "native-save-1", "executor": "agent_mcp",
        "required_checks": ["path", "business"], "steps": [
            {"id": "goal", "goal": "Native Codex independently edits regular layer height to .24, preserves initial .4 and cube, then GUI saves."},
            {"id": "proof", "goal": "After MCP stops and old SUT exits, freeze saved bytes, reopen with an independent profile and GUI reslice/export."},
            {"id": "close", "goal": "Independently inspect 3MF/G-code and confirm owned Job is empty."}],
        "limits": {"timeout_s": 900, "max_actions": 40, "max_retries": 0, "max_cost_usd": 0}})


class NativeSaveExecutor:
    synthetic, kind = False, "agent_mcp"

    def __init__(self, digest):
        if digest != contract_digest(native_contract()):
            raise ValueError("native_contract_digest")
        self.contract_sha256 = digest

    def start(self, context):
        from . import host_guard
        from .win32_job import OwnedJobProcess
        if not host_guard.in_guest() or contract_digest(context.contract) != self.contract_sha256:
            raise PermissionError("native_registered_guest_only")
        artifacts = context.artifact_dir.resolve(strict=True)
        if any(artifacts.iterdir()):
            raise FileExistsError("native_artifacts_not_empty")
        env = {k: v for k, v in os.environ.items() if not k.upper().endswith(("_TOKEN", "_SECRET", "_API_KEY"))}
        for key in ("ORCA_BB_ALLOW_HOST", "ORCA_BB_CONF_EXTRA", "ORCA_GUI_TEST_MODE"):
            env.pop(key, None)
        env["PYTHONIOENCODING"] = "utf-8"
        started = time.time_ns()
        process = OwnedJobProcess.start([sys.executable, "-B", str(REPO / "tools/native_save_guest.py"),
            "--run-id", context.run_id], cwd=REPO, log_path=artifacts / "native_worker.log", env=env)
        return NativeSaveHandle(process, context, started)


def verify_saved(snapshot, *, cancelled=lambda: False):
    from .script_verify import _read, _json, _InvalidEvidence
    from .agent_verify import _require
    from .project_3mf import inspect_project
    from .agent_layer_verify import analyze_gcode
    from decimal import Decimal
    refs = []
    try:
        _require(contract_digest(snapshot.contract) == contract_digest(native_contract()), "native_contract")
        read = lambda n, limit: _read(snapshot.artifact_dir, n, snapshot.manifest["started_at_ns"], limit, cancelled)
        process, proof = _json(read("process.json", 65536)), _json(read("proof.json", 65536))
        host = _json(read("host_done.json", 65536))
        _require(all(type(process[k]) is int for k in ("exit_code", "active_processes"))
                 and process["run_id"] == snapshot.run_id and process["exit_code"] == 0
                 and process["active_processes"] == 0 and process["job_assigned"] is True
                 and process["forced_termination"] is False, "native_process_cleanup")
        _require(type(host["host_active_processes"]) is int and type(host["tool_count"]) is int
                 and host["run_id"] == snapshot.run_id and host["native_ok"] is True
                 and host["host_active_processes"] == 0 and host["host_forced"] is False, "native_host_receipt")
        _require(all(type(proof[k]) is int for k in ("mcp_active_processes", "old_exit_code", "reopened_exit_code", "old_pid"))
                 and proof["old_pid"] > 0 and proof["sut_sha256"] == NATIVE_SUT_SHA256
                 and proof["run_id"] == snapshot.run_id and proof["contract_sha256"] == contract_digest(snapshot.contract)
                 and proof["mcp_active_processes"] == 0 and proof["old_exit_code"] == 0
                 and proof["reopened_closed"] is True and proof["reopened_exit_code"] == 0, "native_custody")
        times = [proof[k] for k in ("input_stopped_at_ns", "old_closed_at_ns", "frozen_at_ns", "reopen_started_at_ns", "exported_at_ns")]
        _require(all(type(x) is int for x in times) and times == sorted(times)
                 and times[0] >= snapshot.manifest["started_at_ns"], "native_phase_order")
        fixture, frozen = read("input/fixture.3mf", 16*1024*1024), read("proof/0001.3mf", 16*1024*1024)
        saved = read("projects/0001.3mf", 16*1024*1024)
        _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "native_fixture")
        digest = hashlib.sha256(frozen).hexdigest()
        _require(saved == frozen and digest == proof["project_sha256"], "native_frozen_file_binding")
        trace = [_json(line) for line in read("native_trace.ndjson", 256000).splitlines() if line]
        _require(1 <= len(trace) <= 40 and len(trace) == host["tool_count"], "native_trace_count")
        _require(all(x["error"] is None and x["finished_at_ns"] <= times[0] for x in trace), "native_trace_error_or_late_input")
        _require(any(x["tool"] == "Type" and x["arguments"].get("text") == proof["output_path"] for x in trace), "native_gui_save_path")
        for x in trace:
            if x["tool"] in {"Click", "Type", "Shortcut"}:
                _require(x["window"]["app_pid"] == proof["old_pid"], "native_input_ownership")
        project = inspect_project(frozen, fixture, cancelled=cancelled)
        gcode = read("exports/0001.gcode", 64*1024*1024)
        _require(hashlib.sha256(gcode).hexdigest() == proof["gcode_sha256"], "native_gcode_binding")
        layers = analyze_gcode(gcode, layer_height="0.24", cancelled=cancelled)
        _require(layers["layer_count"] == 112 and Decimal(layers["last_z"]) == Decimal("27.04"), "native_layer_schedule")
        refs = ("artifact:proof.json", "artifact:process.json", "artifact:native_trace.ndjson",
                "artifact:proof/0001.3mf:sha256:"+digest, "artifact:exports/0001.gcode:sha256:"+proof["gcode_sha256"])
        return VerificationOutcome({"path": CheckResult("pass", "Native GUI save; stopped input; old exit; frozen-file fresh-profile reslice", refs),
            "business": CheckResult("pass", "Saved .24/initial .4, unchanged cube, reopened actual 112-layer G-code", refs)}, True, True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,
            struct.error, DecimalException, ET.ParseError, zipfile.BadZipFile,
            zipfile.LargeZipFile, zlib.error, EOFError, NotImplementedError) as exc:
        detail = str(exc) if isinstance(exc, _InvalidEvidence) else "native_evidence_unavailable"
        return VerificationOutcome({"path": CheckResult("unknown", detail, tuple(refs)),
                                    "business": CheckResult("unknown", detail, tuple(refs))}, False, False)


class NativeSaveVerifier:
    synthetic = False

    def start(self, snapshot):
        from .agent_layer_verify import _Handle
        return _Handle(snapshot, check=verify_saved)


def run_native_save(run_id):
    from .runtime import run_once
    from .script_session import SCRIPT_ROOT
    valid_run_id(run_id)
    root = SCRIPT_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    contract = native_contract()
    digest = contract_digest(contract)
    return run_once(contract, NativeSaveExecutor(digest), {digest: NativeSaveVerifier()},
        root=root, run_id=run_id, desktop_id="guest-console", execution_mode="guest_native",
        verify_timeout_s=40, cleanup_timeout_s=30,
        cancelled=lambda: (root / run_id / "artifacts/control_cancel.json").exists())
