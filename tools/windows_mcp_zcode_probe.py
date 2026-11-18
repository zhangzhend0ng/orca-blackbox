"""Native ZCode actor, explicitly pinned to the existing Snapmaker provider."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from harness.agent_model import _child_environment
from harness.agent_protocol import valid_run_id
from harness.ip_guard import IPGuard
from harness.native_save_policy import native_tools
from harness.native_diagnostic_recovery import COMMIT_SCENARIO, DIAGNOSTIC_SCENARIOS
from harness.native_authority import RECOVERY_SCENARIOS
from harness.native_matrix import (CANVAS_REPLACE_SCENARIOS, CANVAS_SCENARIOS, SAVE_CLEAR_SCENARIOS,
    UIA_HYBRID_SCENARIOS, UIA_SAVE_SCENARIO)
from harness.win32_job import OwnedJobProcess
from runner.windows_mcp_bridge import GuestHTTP


def provider_metadata(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = data["config"]["providerConfigRules"]["providerRules"]
    row = next(r for r in rows if r["providerId"] == "new-provider")
    config = row["config"]
    endpoint = urlsplit(config["api"]["baseUrl"])
    if (row.get("providerName") != "Snapmaker" or config["api"]["type"] != "anthropic-messages"
            or endpoint.scheme != "http" or endpoint.hostname != "ai-gateway.s.com"
            or endpoint.port not in (None, 80) or endpoint.path.rstrip("/") != "/v1"
            or endpoint.query or endpoint.fragment or endpoint.username or endpoint.password
            or config["access"]["type"] != "api-key" or not config["access"].get("apiKey")
            or "glm-5.3-flash" not in config["personalModelIds"]):
        raise ValueError("zcode_snapmaker_provider_changed")
    return {"provider_id": "new-provider", "provider_name": "Snapmaker", "model_id": "glm-5.3-flash",
            "endpoint_scheme": endpoint.scheme, "endpoint_host": endpoint.hostname, "protocol": "anthropic-messages"}


def model_io_summary(root, scenario="base"):
    records = []
    allowed = {"mcp__windows_mcp__"+name for name in native_tools(scenario)}
    for path in sorted((root/"storage/cli/rollout").glob("model-io-*.jsonl")):
        if path.stat().st_size > 64*1024*1024:
            raise ValueError("zcode_model_io_limit")
        for line in path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            if data.get("type") != "model.request.completed":
                # Installed builds use a different event label; identify the
                # native completed provider receipt by its explicit fields.
                if not all(k in data for k in ("request", "response", "model")):
                    continue
            model = data["model"]
            if model.get("providerId") != "new-provider" or model.get("modelId") != "glm-5.3-flash":
                raise ValueError("zcode_native_model_changed")
            names = data["request"].get("toolNames")
            if type(names) is not list or set(names) != allowed or len(names) != len(allowed):
                raise ValueError("zcode_native_toolset_mismatch")
            records.append({"model": model, "tool_names": names,
                "usage": data["response"].get("usage"), "duration_ms": data.get("durationMs"),
                "response_model": data["response"].get("modelId")})
    if not records:
        raise ValueError("zcode_model_io_missing")
    return records


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    from harness.native_matrix import SCENARIOS, scenario_spec, completed_progress
    parser.add_argument("--scenario", choices=tuple(s for s in SCENARIOS if s not in {"canvas_probe", "authority_probe"}), default="base")
    args = parser.parse_args(argv)
    _, disturbance = scenario_spec("zcode", args.scenario)
    from harness.native_pilots import require_pilot_ready
    require_pilot_ready(args.scenario)
    valid_run_id(args.run_id)
    root = REPO/"artifacts/windows_mcp_host"/args.run_id
    root.mkdir(parents=True, exist_ok=False)
    workspace = root/"workspace"
    workspace.mkdir()
    provider = Path.home()/".zcode/v2/provider_config.json"
    sources = [provider, Path.home()/".zcode/cli/config.json", Path.home()/".zcode/v2/config.json"]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    control = GuestHTTP(r"C:\coil\orca-blackbox-v3-r1", args.run_id,
                        deadline=time.monotonic()+1000, channel="control", goal_save=True)
    report = {"run_id": args.run_id, "actor": "zcode", "error": None, "release_eligible": False,
              "native_tool_calls": [], "toolset_verified": False, "guard_checked": False, "scenario": args.scenario}
    process, transport = None, None
    timeout_stop = False
    try:
        report.update(provider_metadata(provider))
        if disturbance == "guard_disconnect":
            from harness.guard_fault import GuardTransport
            transport = GuardTransport()
        guard = IPGuard(status_port=transport.port) if transport else IPGuard()
        report["guard_checks"] = [guard.check()]
        report["guard_checked"] = True
        for _ in range(50):
            ready = control.remote({"op": "ready"})
            if ready.get("ready") is True:
                break
            time.sleep(2)
        else:
            raise TimeoutError("zcode_guest_not_ready")
        from harness.native_save_session import native_contract
        from harness.run_verdict import contract_digest
        expected_contract = contract_digest(native_contract("zcode", args.scenario))
        if ready.get("contract_sha256") != expected_contract:
            raise ValueError("zcode_guest_contract_mismatch")
        ready_received = time.monotonic()
        remaining = ready.get("remaining_s")
        if type(remaining) not in (int, float) or not 0 < remaining <= 900:
            raise ValueError("zcode_guest_deadline_missing")
        case_cutoff = ready_received+remaining
        output = r"C:\coil\orca-blackbox-v3-r1\artifacts\v3"+"\\"+args.run_id+r"\artifacts\projects\0001.3mf"
        if ready.get("output_path") != output:
            raise ValueError("zcode_guest_output_mismatch")
        from harness.native_pilots import business_goal
        prompt = ("Use only windows_mcp tools in the isolated Windows guest to achieve this goal in the already loaded Snapmaker Orca: "
            +business_goal(args.scenario)+" Save the whole project as a 3MF at this exact absolute path: "+output+". "
            "Do not switch global printer/filament/process presets. Preserve settings not expressly targeted in the goal. "
            "Choose the UI route and coordinates yourself from fresh screenshots. "
            "Click and Type use loc=[x,y] desktop pixels; label inputs are unavailable. "
            "Screenshot takes no arguments: cropping/region/display/save_path options are unavailable. "
            "Wait requires duration as whole seconds from 0 to 5; fractional waits are unavailable. "
            "Type supports clear=true and press_enter=true. Only numeric strings and the full assigned save path are permitted. "
            "Shortcuts allowed: ctrl+s, ctrl+shift+s, enter, tab, shift+tab, esc. "
            "Only the owned application and its dialogs may receive input. Never open other apps or use other tools. "
            "Inspect screenshots after changes and confirm saving through the UI. "
            "Do not close, reopen, slice or export: independent verification handles that. "
            "Finish with ControlStatus(release=true), then describe observations without claiming test pass.")
        if args.scenario in RECOVERY_SCENARIOS | DIAGNOSTIC_SCENARIOS:
            prompt += " A recoverable pre-dispatch refusal requires a fresh Snapshot/Screenshot before any further input. A fatal refusal ends this run."
        if args.scenario == COMMIT_SCENARIO:
            prompt += (" Use clear=true and press_enter=true together in each numeric Type, with the caret left idle."
                       " After the tool reads the desired value back, inspect the committed result instead of typing it again."
                       " Once committed, proceed directly to Save As. No click is needed just to drop focus.")
        if args.scenario in SAVE_CLEAR_SCENARIOS:
            prompt += (" In the Save As file name Edit, always use clear=true when typing the exact assigned path. "
                       "The dialog pre-fills a file name that must be replaced.")
        if args.scenario == "canvas_trial":
            prompt = prompt.replace("Type supports clear=true and press_enter=true.",
                "For numeric Type use clear=false, caret_position=idle and press_enter=false; ordinary Edit replacement options are available only for the exact SaveAs path.")
            prompt += (" This is a controlled canvas numeric-input capability trial. Every canvas numeric Type consumes a successful Click at that same visually chosen loc from the last 30 seconds."
                       " On the canvas use clear=false, caret_position=idle, press_enter=false only; the field must already be ready to replace its current value."
                       " Inspect the actual result; do not assume typing replaced existing text. Only the exact SaveAs path retains ordinary Edit replacement options.")
        if args.scenario in CANVAS_REPLACE_SCENARIOS:
            prompt = prompt.replace("Type supports clear=true and press_enter=true.",
                "For canvas numbers use clear=false, caret_position=idle and press_enter=true.")
            prompt += (" Activate an inactive numeric field with one left Click chosen from the screenshot, then Type at "
                       "the same loc within 30 seconds. Type sends numeric keys and Enter directly without clicking again. "
                       "Inspect the committed value before saving.")
        if args.scenario == UIA_SAVE_SCENARIO:
            prompt = ("The isolated Snapmaker Orca Save As dialog is already open. Save the current project unchanged as a 3MF "
                      "at this exact assigned path: " + output + ". Use Snapshot for the UIA properties of the filename "
                      "Edit and Save button, Type with the exact Edit target and assigned path, and Click with the exact "
                      "Save button target. Read back the value from the Type result. Confirm the dialog closed with Snapshot "
                      "and finish with ControlStatus(release=true). Independent verification will reopen and slice.")
        elif args.scenario in UIA_HYBRID_SCENARIOS:
            prompt = ("Use Windows-MCP in the isolated Snapmaker Orca window. " + business_goal(args.scenario)
                      + " Save the whole project at this exact assigned 3MF path: " + output + ". "
                      "Start with Snapshot. For a native control, copy its exact target object from Snapshot. "
                      "If a wx label is drawn and missing from the tree, use a local crop to match the label to its Edit bounds. "
                      "Use Type with that Edit's target object to change the value; no coordinate click is needed for a listed Edit. "
                      "Use Screenshot with region=[left,top,right,bottom] contained in one listed visual_regions box only "
                      "when the needed drawn wx or ImGui control is absent from the UIA list. The returned image starts at "
                      "[left,top]; add that offset once to image-relative pixels. Before Click, verify the final loc lies inside "
                      "the most recent crop: left <= x < right and top <= y < bottom. Send loc as a JSON integer array. "
                      "For an ImGui number, Click once and Type at the same "
                      "location within 30 seconds with press_enter=true, then inspect the new value with a crop. "
                      "If work starts with a Save As blocking unfinished edits, invoke its available Cancel target and Snapshot again. "
                      "After edits, open Save As with Shortcut ctrl+shift+s. Snapshot the dialog, Type the full path into the Edit target, "
                      "read its returned value, Click the Save button target and Snapshot to confirm closure. "
                      "Finish with ControlStatus(release=true). Preserve unrelated settings. Independent verification reopens and slices.")
            if args.scenario in CANVAS_SCENARIOS:
                prompt += (" For a scene-editing goal, start by observing the listed imgui_canvas rectangle as one crop. "
                           "When selection changes, the gizmo and scene can redraw. Observe that same canvas region again "
                           "until you see the target controls, then use a smaller crop if you need more detail.")
        (root/"prompt.txt").write_text(prompt, encoding="utf-8")
        bundle = Path(r"C:\Program Files\ZCode\resources\glm\zcode.cjs")
        report["bundle_sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
        spec = {"root": str(root), "workspace": str(workspace), "run_id": args.run_id,
                "bundle": str(bundle), "python": sys.executable,
                "bridge": str(REPO/"runner/windows_mcp_bridge.py"), "prompt": prompt,
                "authority_protocol": "native-authority-1", "authority_log": str(root/"authority.ndjson"),
                "recovery_enabled": args.scenario in RECOVERY_SCENARIOS, "scenario": args.scenario,
                "tools": sorted(native_tools(args.scenario))}
        (root/"spec.json").write_text(json.dumps(spec), encoding="utf-8")
        env, report["proxy_source"] = _child_environment()
        env.update(ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=str(provider),
            ZCODE_BUILTIN_PROVIDER_CONFIG_FILE=r"C:\Program Files\ZCode\resources\config\provider\zcode-builtin.json",
            ZCODE_STORAGE_DIR=str(root/"storage"), ZCODE_SESSION_DB_PATH=str(root/"storage/sessions.sqlite"),
            ZCODE_LOG_DIR=str(root/"storage/logs"), ZCODE_HTTP_PROXY=env.get("HTTPS_PROXY", ""),
            ZCODE_NO_PROXY="127.0.0.1,localhost")
        report["guard_checks"].append(guard.check())
        process = OwnedJobProcess.start([r"C:\Program Files\nodejs\node.exe", str(REPO/"tools/zcode_session_driver.mjs"),
            str(root/"spec.json")], cwd=workspace, env=env, log_path=root/"zcode.log")
        cutoff, next_guard = time.monotonic()+630, 0
        while True:
            calls = completed_progress(root/"progress.ndjson")
            inputs = [c for c in calls if c.get("tool") in {"Click", "Type", "Shortcut"}]
            if disturbance in {"cancel", "timeout", "guard_disconnect"} and inputs and "fault_event" not in report:
                report["fault_event"] = {"kind": disturbance, "observed_at_ns": time.time_ns(),
                    "completed_input_tools": [c["tool"] for c in inputs]}
                if disturbance == "cancel":
                    raise RuntimeError("zcode_injected_cancellation")
                if disturbance == "guard_disconnect":
                    transport.close()
                    # Same fail-closed path as an actual unreachable status service.
                    guard.check()
                    raise RuntimeError("zcode_guard_disconnect_did_not_fail_closed")
            if disturbance == "timeout" and time.monotonic() >= case_cutoff:
                timeout_stop = True
                report["timeout_observed_at_ns"] = time.time_ns()
                raise TimeoutError("zcode_contract_deadline")
            if time.monotonic() >= next_guard:
                report["guard_checks"].append(guard.check())
                next_guard = time.monotonic()+3
            code, active = process.poll()
            if code is not None and active == 0:
                report["zcode_exit"] = code
                break
            if time.monotonic() >= cutoff or (root/"zcode.log").stat().st_size > 2_000_000:
                raise TimeoutError("zcode_deadline_or_output_limit")
            time.sleep(.2)
        actor = json.loads((root/"actor.json").read_text(encoding="utf-8"))
        report["native_tool_calls"] = actor.get("native_tool_calls", [])
        report["selection"] = actor.get("selection")
        if code or actor.get("error"):
            raise RuntimeError("zcode_actor_failed:"+str(actor.get("error")))
        if args.scenario in DIAGNOSTIC_SCENARIOS:
            report["diagnostic_turn"] = actor["diagnostic_turn"]
        report["model_io"] = model_io_summary(root, args.scenario)
        report["toolset_verified"] = True
    except Exception as exc:
        report["error"] = type(exc).__name__+":"+str(exc)[:240]
    finally:
        if process:
            forced = process.poll()[1] != 0
            if forced:
                process.terminate()
            for _ in range(100):
                code, active = process.poll()
                if active == 0:
                    break
                time.sleep(.1)
            report["host_job"] = {"active_processes": active, "forced_termination": forced, "stopped_at_ns": time.time_ns()}
            if active == 0:
                process.close()
            else:
                report["error"] = "zcode_cleanup_unconfirmed"
        if report.get("fault_event"):
            try:
                report["model_io"] = model_io_summary(root, args.scenario)
                report["toolset_verified"] = True
            except Exception as exc:
                report["fault_model_io_error"] = type(exc).__name__
        if transport:
            transport.close()
            try:
                report["global_guard_after"] = IPGuard().check()
            except Exception as exc:
                report["global_guard_after_error"] = type(exc).__name__
        report["sources_unchanged"] = all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[p] for p in sources)
        if not report["sources_unchanged"]:
            report["error"] = report["error"] or "zcode_personal_sources_changed"
        try:
            receipt = {"run_id": args.run_id, "native_ok": report["error"] is None,
                "host_active_processes": report.get("host_job", {}).get("active_processes", 0),
                "host_forced": report.get("host_job", {}).get("forced_termination", False),
                "tool_count": len(report["native_tool_calls"]), "actor": "zcode",
                "provider_id": "new-provider", "model_id": "glm-5.3-flash",
                "guard_checked": report["guard_checked"], "sources_unchanged": report["sources_unchanged"],
                "toolset_verified": report["toolset_verified"]}
            if "expected_contract" in locals():
                receipt.update(contract_sha256=expected_contract, scenario=args.scenario)
            if "diagnostic_turn" in report:
                receipt["diagnostic_turn"] = report["diagnostic_turn"]
            if report.get("host_job", {}).get("forced_termination"):
                # Let the final single-slot relay launch return; its detached
                # HTTP ferry never submits further relay commands.
                time.sleep(3)
            if report.get("host_job", {}).get("active_processes", 0) != 0:
                raise RuntimeError("zcode_control_requires_empty_host_job")
            # The relay is single-slot. Control resumes only after every actor
            # descendant (including the data ferry) has stopped.
            if disturbance in {"cancel", "guard_disconnect"} and report.get("fault_event"):
                report["cancel"] = control.remote({"op": "cancel"})
            elif disturbance == "timeout" and timeout_stop:
                pass  # Guest runtime owns this deadline; cancellation would mask it.
            else:
                report["done"] = control.remote({"op": "done", "receipt": receipt})
            cutoff = min(control.deadline, time.monotonic()+240)
            while time.monotonic() < cutoff:
                result = control.remote({"op": "result"})
                if result.get("pending") is not True:
                    report["guest_result"] = result
                    if result.get("verified_pass") is not True:
                        report["error"] = report["error"] or "zcode_independent_proof_failed"
                    break
                time.sleep(2)
            else:
                report["error"] = report["error"] or "zcode_result_timeout"
        except Exception as exc:
            report["error"] = report["error"] or "zcode_completion_unconfirmed:"+type(exc).__name__
        (root/"host.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 1 if report["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
