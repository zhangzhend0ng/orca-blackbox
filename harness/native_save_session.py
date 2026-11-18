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
from .native_diagnostic_recovery import COMMIT_SCENARIO, DIAGNOSTIC_SCENARIOS
from .native_matrix import (CANVAS_REPLACE_SCENARIO, CANVAS_REPLACE_SCENARIOS, CANVAS_SCENARIOS,
    GENERALIZATION, UIA_HYBRID_SCENARIOS, UIA_SAVE_SCENARIO)
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


def native_contract(actor="codex", scenario="base"):
    from .native_matrix import scenario_spec
    scenario_spec(actor, scenario)
    if actor not in {"codex", "zcode"}:
        raise ValueError("native_actor_not_registered")
    data = {"schema_version": 1, "case_id": "m3g_export_3mf",
        "contract_version": "native-save-1" if actor == "codex" else "native-save-zcode-1", "executor": "agent_mcp",
        "required_checks": ["path", "business"], "steps": [
            {"id": "goal", "goal": ("Native Codex" if actor == "codex" else "Native ZCode with Snapmaker glm-5.3-flash")+" independently edits regular layer height to .24, preserves initial .4 and cube, then GUI saves."},
            {"id": "proof", "goal": "After MCP stops and old SUT exits, freeze saved bytes, reopen with an independent profile and GUI reslice/export."},
            {"id": "close", "goal": "Independently inspect 3MF/G-code and confirm owned Job is empty."}],
        "limits": {"timeout_s": 900, "max_actions": 40, "max_retries": 0, "max_cost_usd": 0}}
    if scenario != "base":
        data["contract_version"] = "native-save-zcode-matrix-1-"+scenario
        data["steps"].insert(0, {"id": "setup", "goal": "Trusted initial condition: "+scenario})
        if scenario == "safety_timeout":
            data["limits"]["timeout_s"] = 120
        from .native_pilots import PILOTS, TRIALS, pilot_module
        if scenario == UIA_SAVE_SCENARIO:
            data["case_id"] = "uia_save_as"
            data["contract_version"] = "native-uia-save-zcode-1"
            data["steps"][1]["goal"] = ("Locate Save As controls by UIA properties, set and read back the exact assigned path "
                                       "using ValuePattern and invoke Save using InvokePattern. Preserve the project unchanged.")
        elif scenario in {**PILOTS, **TRIALS}:
            pilot = pilot_module(scenario)
            data["case_id"] = pilot.CASE_ID
            data["contract_version"] = "native-pilot-zcode-1-"+scenario
            data["steps"][1]["goal"] = "Native ZCode with Snapmaker glm-5.3-flash: "+pilot.GOAL
            if scenario == "canvas_trial":
                data["contract_version"] = "native-canvas-trial-zcode-1-observed-wxglcanvas-v1"
                data["steps"].insert(1, {"id": "canvas_authority", "goal": "Explicit observed-wxglcanvas-v1 numeric-only capability trial; fixed diagnostic/SUT hashes; clear=false/caret=idle/press_enter=false; prior successful same-loc Click. PFD and internal field activation unproven; at most two proven owned numeric pre-dispatch refusals with fresh observation."})
            elif scenario in CANVAS_REPLACE_SCENARIOS:
                data["contract_version"] = "native-canvas-replace-zcode-1"
                if scenario != CANVAS_REPLACE_SCENARIO:
                    data["contract_version"] = "native-canvas-replace-zcode-2-" + scenario
                data["steps"].insert(1, {"id": "canvas_authority", "goal": "Bound wxGLCanvas numeric replacement using one successful same-position single Click, focused numeric keys without another click, then one Enter. Recheck the owned destination before every key. Confirm using the saved 3MF and new-profile G-code."})
        elif scenario in {"canvas_probe", "authority_probe"}:
            data["case_id"] = "diagnostic_canvas_input"
            data["contract_version"] = "native-canvas-probe-1"
            data["steps"] = [{"id": "probe", "goal": "Trusted guest-only read-only window/pixel-format census; no MCP or model."},
                             {"id": "close", "goal": "Close the diagnostic SUT and confirm owned cleanup; never business GREEN."}]
            if scenario == "authority_probe":
                data["case_id"] = "diagnostic_authority_stop"
                data["contract_version"] = "native-authority-stop-probe-1"
                data["steps"][0]["goal"] = "Two negative original-MCP requests: foreign Click refused before dispatch, then owned Click refused by permanent stop latch. No model or successful GUI input; never business GREEN."
        elif scenario == "recovery_owned_edit":
            data["contract_version"] = "native-recovery-zcode-1-owned-edit"
            data["steps"].insert(1, {"id": "recovery", "goal": "At most two proven owned numeric non-Edit refusals before dispatch; fresh observation before any further input; every other refusal durably stops authority."})
        elif scenario in DIAGNOSTIC_SCENARIOS:
            data["contract_version"] = "native-diagnostic-recovery-zcode-1"
            data["steps"].insert(1, {"id": "recovery", "goal": "Inject one refusal after the owned numeric Edit guard allows it and before dispatch. In a single native turn, observe again and correct the numeric edit. Independently verify the business result. Mechanism evidence only."})
            if scenario == COMMIT_SCENARIO:
                data["contract_version"] = "native-diagnostic-recovery-zcode-2-commit"
                data["steps"][1]["goal"] += " Replace and commit the native Edit with clear=true and press_enter=true in the same Type."
        if scenario in UIA_HYBRID_SCENARIOS:
            data["contract_version"] = "native-uia-hybrid-zcode-1-" + scenario
            data["steps"].insert(1, {"id": "uia_authority", "goal": "Use owned UIA target properties and readback for native controls. Use a crop only for drawn wx or ImGui surfaces. Require the UIA Save As trace and independent saved-file verification."})
    return validate_contract(data)


def native_spec(digest):
    from .native_matrix import SCENARIOS
    for actor in ("codex", "zcode"):
        for scenario in (("base",) if actor == "codex" else SCENARIOS):
            if digest == contract_digest(native_contract(actor, scenario)):
                return actor, scenario
    raise ValueError("native_contract_digest")


def native_actor(digest):
    return native_spec(digest)[0]


class NativeSaveExecutor:
    synthetic, kind = False, "agent_mcp"

    def __init__(self, digest):
        self.actor, self.scenario = native_spec(digest)
        from .native_pilots import require_pilot_ready
        require_pilot_ready(self.scenario)
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
            "--run-id", context.run_id, "--actor", self.actor, "--scenario", self.scenario], cwd=REPO, log_path=artifacts / "native_worker.log", env=env)
        return NativeSaveHandle(process, context, started)


def verify_saved(snapshot, *, cancelled=lambda: False):
    from .script_verify import _read, _json, _InvalidEvidence
    from .agent_verify import _require
    from .project_3mf import inspect_project
    from .agent_layer_verify import analyze_gcode
    from decimal import Decimal
    refs = []
    recovery_summary = None
    diagnostic_summary = None
    uia_summary = None
    try:
        actor, scenario = native_spec(contract_digest(snapshot.contract))
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
        if actor == "zcode":
            _require(host.get("actor") == "zcode" and host.get("provider_id") == "new-provider"
                     and host.get("model_id") == "glm-5.3-flash"
                     and host.get("guard_checked") is True and host.get("sources_unchanged") is True
                     and host.get("toolset_verified") is True, "native_zcode_identity_or_gate")
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
        _require(all(x["finished_at_ns"] <= times[0] for x in trace), "native_trace_late_input")
        if scenario in CANVAS_SCENARIOS | set(GENERALIZATION) | {"recovery_owned_edit"}:
            from .native_recovery import audit_trace
            recovery_summary = audit_trace(trace, snapshot.run_id, enabled=True)
        elif scenario in DIAGNOSTIC_SCENARIOS:
            from .native_diagnostic_recovery import audit_diagnostic_trace, verify_diagnostic_calls
            _require(host.get("contract_sha256") == contract_digest(snapshot.contract)
                     and host.get("scenario") == scenario, "native_diagnostic_host_contract")
            turn = host.get("diagnostic_turn")
            diagnostic_summary = audit_diagnostic_trace(trace, snapshot.run_id, enabled=True, turn_receipt=turn)
            diagnostic_summary.update(verify_diagnostic_calls(trace, turn, proof["old_pid"],
                require_commit=scenario == COMMIT_SCENARIO))
        else:
            _require(all(x["error"] is None for x in trace), "native_trace_error_or_late_input")
        _require(any(x["tool"] == "Type" and x["arguments"].get("text") == proof["output_path"] for x in trace), "native_gui_save_path")
        for x in trace:
            if x["tool"] in {"Click", "Type", "Shortcut"} and x["error"] is None:
                _require(x["window"]["app_pid"] == proof["old_pid"], "native_input_ownership")
        canvas_summary = None
        if scenario in CANVAS_SCENARIOS:
            from .native_canvas_verify import verify_canvas_trace
            canvas_summary = verify_canvas_trace(trace, _json(read("scope.json", 65536)),
                _json(read("canvas_setup.json", 400000)), run_id=snapshot.run_id,
                contract_sha256=contract_digest(snapshot.contract), read_artifact=read)
        if scenario != "base":
            setup = _json(read("setup.json", 65536))
            initial = read("initial.png", 16*1024*1024)
            from .native_matrix import scenario_spec
            tab, disturbance = scenario_spec(actor, scenario)
            _require(setup.get("run_id") == snapshot.run_id and setup.get("scenario") == scenario
                     and setup.get("app_pid") == proof["old_pid"] and setup.get("tab_clicked") == tab
                     and setup.get("initial_sha256") == hashlib.sha256(initial).hexdigest()
                     and type(setup.get("finished_at_ns")) is int
                     and setup["finished_at_ns"] <= min(x["started_at_ns"] for x in trace), "native_initial_setup")
            if disturbance == "overwrite":
                _require(setup.get("baseline_sha256") == LAYER_FIXTURE_SHA256
                         and digest != setup["baseline_sha256"], "native_overwrite_not_proven")
            if disturbance == "save_dialog":
                _require(type(setup.get("dialog_hwnd")) is int and setup["dialog_hwnd"] > 0,
                         "native_initial_dialog_not_proven")
        if scenario == UIA_SAVE_SCENARIO:
            from .native_uia import verify_uia_save
            _require(host.get("contract_sha256") == contract_digest(snapshot.contract)
                     and host.get("scenario") == scenario, "native_uia_host_contract")
            uia_summary = verify_uia_save(trace, run_id=snapshot.run_id, app_pid=proof["old_pid"],
                dialog_hwnd=setup["dialog_hwnd"], output_path=proof["output_path"])
        elif scenario in UIA_HYBRID_SCENARIOS:
            from .native_uia_hybrid import verify_hybrid_trace
            scope = _json(read("scope.json", 65536))
            _require(host.get("contract_sha256") == contract_digest(snapshot.contract)
                     and host.get("scenario") == scenario and scope["app_pid"] == proof["old_pid"],
                     "native_uia_host_contract")
            uia_summary = verify_hybrid_trace(trace, run_id=snapshot.run_id, app_pid=proof["old_pid"],
                main_hwnd=scope["hwnd"], output_path=proof["output_path"], scenario=scenario)
        gcode = read("exports/0001.gcode", 64*1024*1024)
        _require(hashlib.sha256(gcode).hexdigest() == proof["gcode_sha256"], "native_gcode_binding")
        from .native_pilots import PILOTS, TRIALS, verify_business
        if scenario == UIA_SAVE_SCENARIO:
            from .pilot_common import inspect_preserved_settings
            from .project_3mf import _archive
            inspect_project(frozen, fixture, layer_height="0.4", cancelled=cancelled)
            saved_settings = _json(_archive(frozen, cancelled)["Metadata/project_settings.config"])
            fixture_settings = _json(_archive(fixture, cancelled)["Metadata/project_settings.config"])
            inspect_preserved_settings(saved_settings, fixture_settings, cancelled=cancelled)
            layers = analyze_gcode(gcode, layer_height="0.4", cancelled=cancelled)
            _require(layers["layer_count"] == 68 and Decimal(layers["last_z"]) == Decimal("27.2")
                     and layers["object_tools"] == [0], "native_uia_saved_layer_schedule")
            detail = "UIA Save As preserved all fixture settings and geometry; fresh-profile reopen produced 68 layers; "
            detail += json.dumps(uia_summary, sort_keys=True)
        elif scenario in {**PILOTS, **TRIALS}:
            _require(host.get("contract_sha256") == contract_digest(snapshot.contract)
                     and host.get("scenario") == scenario, "native_pilot_host_contract")
            business = verify_business(scenario, frozen, fixture, gcode, cancelled=cancelled)
            detail = snapshot.contract.case_id+": "+json.dumps(business, sort_keys=True, ensure_ascii=True)
        else:
            project = inspect_project(frozen, fixture, cancelled=cancelled)
            layers = analyze_gcode(gcode, layer_height="0.24", cancelled=cancelled)
            _require(layers["layer_count"] == 112 and Decimal(layers["last_z"]) == Decimal("27.04"), "native_layer_schedule")
            detail = "Saved .24/initial .4, unchanged cube, reopened actual 112-layer G-code"
        refs = ("artifact:proof.json", "artifact:process.json", "artifact:native_trace.ndjson",
                "artifact:proof/0001.3mf:sha256:"+digest, "artifact:exports/0001.gcode:sha256:"+proof["gcode_sha256"])
        if recovery_summary is not None:
            detail += "; native_recovery="+json.dumps(recovery_summary, sort_keys=True)
        if diagnostic_summary is not None:
            detail += "; native_diagnostic_recovery="+json.dumps(diagnostic_summary, sort_keys=True)
        if canvas_summary is not None:
            detail += "; canvas_input="+json.dumps(canvas_summary, sort_keys=True)
        if uia_summary is not None and scenario in UIA_HYBRID_SCENARIOS:
            detail += "; native_uia="+json.dumps(uia_summary, sort_keys=True)
        return VerificationOutcome({"path": CheckResult("pass", "Native GUI save; stopped input; old exit; frozen-file fresh-profile reslice", refs),
            "business": CheckResult("pass", detail, refs)}, True, True,
            recovery_used=bool(diagnostic_summary or recovery_summary and recovery_summary["recoveries"]),
            recovery_recorded=diagnostic_summary is not None or recovery_summary is not None)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,
            struct.error, DecimalException, ET.ParseError, zipfile.BadZipFile,
            zipfile.LargeZipFile, zlib.error, EOFError, NotImplementedError) as exc:
        detail = str(exc) if isinstance(exc, _InvalidEvidence) else "native_evidence_unavailable"
        return VerificationOutcome({"path": CheckResult("unknown", detail, tuple(refs)),
                                    "business": CheckResult("unknown", detail, tuple(refs))}, False, False,
            recovery_used=bool(recovery_summary and recovery_summary["recoveries"]),
            recovery_recorded=recovery_summary is not None)


class NativeSaveVerifier:
    synthetic = False

    def start(self, snapshot):
        from .agent_layer_verify import _Handle
        return _Handle(snapshot, check=verify_saved)


def run_native_save(run_id, actor="codex", scenario="base"):
    from .runtime import run_once
    from .script_session import SCRIPT_ROOT
    valid_run_id(run_id)
    root = SCRIPT_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    contract = native_contract(actor, scenario)
    digest = contract_digest(contract)
    return run_once(contract, NativeSaveExecutor(digest), {digest: NativeSaveVerifier()},
        root=root, run_id=run_id, desktop_id="guest-console", execution_mode="guest_native",
        verify_timeout_s=40, cleanup_timeout_s=30,
        cancelled=lambda: (root / run_id / "artifacts/control_cancel.json").exists())
