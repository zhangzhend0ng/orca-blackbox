"""INTERACTIVE worker: AI saves; trusted post-AI phase proves recovery."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import socket
import sys
import time
import secrets
import stat

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def atomic_json(path, data):
    from harness.agent_protocol import write_json_once

    pending = path.with_name(path.name+".pending")
    write_json_once(pending, data)
    pending.rename(path)


class NativeInput:
    def __init__(self, root, run_id, guard):
        self.root, self.run_id, self.guard = root, run_id, guard
        self.server = None

    def stop(self):
        root = self.root
        (root / "input_revoked").touch(exist_ok=True)
        if self.server is not None:
            self.server.terminate()  # Only the exact owned MCP server tree.
            cutoff = time.monotonic()+15
            while self.server.poll()[1] and time.monotonic() < cutoff:
                time.sleep(.1)
            if self.server.poll()[1]:
                raise RuntimeError("native_mcp_stop_unconfirmed")
            self.server.close()
            self.server = None
        return time.time_ns()

    def start(self):
        from harness.win32_job import OwnedJobProcess

        root, run_id = self.root, self.run_id
        (root / "token").write_text(secrets.token_hex(32), encoding="ascii")
        (root / "config.toml").write_text("", encoding="utf-8")
        env = os.environ.copy()
        env.update(POSTHOG_API_KEY="", ANONYMIZED_TELEMETRY="false",
                   WINDOWS_MCP_AUTH_KEY=(root / "token").read_text(), PYTHONIOENCODING="utf-8")
        self.server = OwnedJobProcess.start([r"C:\coil\tools\windows-mcp-0.8.9\python.exe", "-B",
            str(REPO / "tools/native_save_server.py"), "--run-id", run_id],
            cwd=REPO, env=env, log_path=root / "server.log")
        for _ in range(60):
            self.guard()
            if self.server.poll()[0] is not None:
                raise RuntimeError("native_server_exited")
            try:
                socket.create_connection(("127.0.0.1", 18789), timeout=1).close()
                return
            except OSError:
                time.sleep(1)
        raise TimeoutError("native_server_not_ready")


def bind_native_canvas(ui, scope, root, sut_sha):
    run_id = scope["run_id"]
    from harness.canvas_approval import resolve_approval
    from harness.canvas_input import collect_window_evidence, bind_canvas, binding_to_json
    diagnostic = REPO / "contracts/evidence/canvas-diagnostic-bb64.json"
    diagnostic_sha = hashlib.sha256(diagnostic.read_bytes()).hexdigest()
    approval = resolve_approval("observed-wxglcanvas-v1", diagnostic_sha256=diagnostic_sha, sut_sha256=sut_sha)
    evidence = collect_window_evidence(run_id, ui.app.pid, ui.app.hwnd)
    candidates = [w for w in evidence["windows"] if w.get("pid") == ui.app.pid
        and w.get("exists") is True and w.get("visible") is True and w.get("is_main_child") is True
        and w.get("class") == approval.window_class and w.get("title") == approval.window_title]
    if len(candidates) != 1:
        raise RuntimeError("canvas_trial_candidate_ambiguous")
    binding = bind_canvas(evidence, candidates[0]["hwnd"], approved_class=approval.window_class,
                          diagnostic_id=approval.diagnostic_run_id, approval=approval)
    scope.update(canvas_binding_json=binding_to_json(binding), canvas_approval_profile=approval.profile_id,
                 canvas_diagnostic_sha256=diagnostic_sha, canvas_sut_sha256=sut_sha)
    atomic_json(root / "canvas_setup.json", {"run_id": run_id, "contract_sha256": scope["contract_sha256"],
        "binding": json.loads(scope["canvas_binding_json"]), "evidence": evidence,
        "pfd_verified": False, "internal_numeric_field_verified": False})
    return binding


def prove_project(ui, root, run_id, contract_sha256, guard, sut_sha, stopped, old, closed, *,
                  saved_sha=None, probe_boot=False, probe_waits=False, report=None):
    from harness.agent_guest import _WindowsUI, _encode_capture
    from harness.agent_protocol import write_json_once
    from harness.perf_monitor import launch_phase
    if probe_waits:
        from harness.mix_dialog_util import mix_entry_labels
    output = ui._project_path()
    saved = ui._snapshot()
    with output.open("rb") as stream:
        raw = stream.read(16*1024*1024+1)
    if (hashlib.sha256(raw).hexdigest() != saved["sha256"]
            or (saved_sha is not None and saved["sha256"] != saved_sha)):
        raise RuntimeError("native_saved_changed")
    frozen = root / "proof/0001.3mf"
    with frozen.open("xb") as stream:
        stream.write(raw)
    frozen.chmod(stat.S_IREAD)
    frozen_ns = time.time_ns()
    started = time.time_ns()
    options = {"boot_ready": lambda app: len(mix_entry_labels(app)) == 3, "guard": guard} if probe_boot else {}
    with launch_phase("proof_reopen", run_id):
        base = _WindowsUI(root, model=frozen, profile_name="profile_reopen", **options)
    if probe_boot:
        report["mix_boot_probe"]["reopen"] = base.boot_scan
    ui.base, ui.app, ui.wu = base, base.app, base.winutil
    ui._close_requested = False
    if probe_waits:
        ui.wait(lambda: len(mix_entry_labels(ui.app)) == 3, 30)
        ui.maximize_ready()

        def slice_ready():
            _, button = ui.eu.find_slice_buttons(ui.app.hwnd)
            return button and ui.owned(button[2]) and ui.wu.user32.IsWindowEnabled(button[2])

        ui.wait(slice_ready, 15)
        report["mix_wait_probe"]["ready_to_slice_at_ns"] = time.time_ns()
    else:
        ui.pause(12)
        ui.wu.user32.ShowWindow(ui.app.hwnd, 3)
        ui.pause(2)
    ui.slice()
    if probe_waits:
        report["mix_wait_probe"]["slice_ready_for_export_at_ns"] = time.time_ns()
    exported = ui.export_gcode()
    exported_ns = time.time_ns()
    (root / "proof_final.png").write_bytes(_encode_capture(ui.identity()[1])[1])
    ui.close()
    write_json_once(root / "proof.json", {"run_id": run_id,
        "sut_sha256": sut_sha,
        "contract_sha256": contract_sha256, "output_path": str(output),
        "input_stopped_at_ns": stopped, "mcp_active_processes": 0,
        "old_pid": old.pid, "old_exit_code": old.popen.poll(), "old_closed_at_ns": closed,
        "frozen_at_ns": frozen_ns, "project_sha256": saved["sha256"],
        "reopen_started_at_ns": started, "reopened_pid": ui.app.pid,
        "reopened_closed": not ui.app.alive(), "reopened_exit_code": ui.app.popen.poll(), "exported_at_ns": exported_ns,
        "gcode_sha256": exported["sha256"]})


def worker(run_id, actor="codex", scenario="base"):
    from harness import host_guard
    from harness.agent_protocol import valid_run_id, write_json_once
    from harness.agent_project_ui import ProjectUI
    from harness.agent_guest import _encode_capture
    from harness.native_save_session import native_contract, NATIVE_SUT_SHA256
    from harness.run_verdict import contract_digest
    from harness.native_matrix import BOUND_MODEL_MOVE, FIXTURE_SCENARIOS
    if actor == "script" and scenario in FIXTURE_SCENARIOS:
        from harness.native_fixture_suite import run_fixture_worker
        return run_fixture_worker(run_id, scenario)
    valid_run_id(run_id)
    if not host_guard.in_guest():
        raise PermissionError("native worker requires guest")
    root = REPO / "artifacts/v3" / run_id / "artifacts"
    deadline = time.monotonic()+840
    def guard():
        if (time.monotonic() >= deadline or (root / "control_cancel.json").exists()
                or (root / "authority_abort.json").exists()):
            raise TimeoutError("native_worker_deadline_or_cancel")
    ui, video = None, None
    report = {"run_id": run_id, "error": None, "app_closed": False,
              "release_eligible": False, "contract_sha256": contract_digest(native_contract(actor, scenario))}
    native = NativeInput(root, run_id, guard)

    try:
        from harness.launcher import default_exe
        sut_sha = hashlib.sha256(default_exe().read_bytes()).hexdigest()
        if sut_sha != NATIVE_SUT_SHA256:
            raise RuntimeError("native_frozen_sut_changed")
        request = REPO / "artifacts/native_video_requests" / run_id
        if request.is_file():
            from harness.native_desktop_video import DesktopVideo
            request.unlink()
            video = DesktopVideo(root)
            video.start()
        from harness.native_pilots import native_fixture
        from harness.native_matrix import UIA_REPLAY_MIX
        request = REPO / "artifacts/native_mix_wait_requests" / run_id
        probe_waits = request.is_file()
        boot_request = REPO / "artifacts/native_mix_boot_requests" / run_id
        probe_boot = boot_request.is_file()
        if probe_boot and not probe_waits:
            raise ValueError("native_mix_boot_probe_scope")
        ready_on_open = None
        if probe_waits:
            if actor != "script" or scenario != UIA_REPLAY_MIX:
                raise ValueError("native_mix_wait_probe_scope")
            request.unlink()
            if probe_boot:
                boot_request.unlink()
            from harness.mix_dialog_util import mix_entry_labels

            def ready_on_open(app):
                return len(mix_entry_labels(app)) == 1

            report["mix_wait_probe"] = {"initial_started_at_ns": time.time_ns()}
        bound_plan = None
        if scenario == BOUND_MODEL_MOVE:
            from harness.agent_protocol import read_json
            from harness.model_move_pilot import canonical, digest, instance, read_request
            bound_plan, path = read_request(run_id)
            if bound_plan != read_json(root / "resolved_plan.json"):
                raise ValueError("model_worker_plan_changed")
            fixture = (path, bound_plan["prepared_sha256"])
            _, _, initial_transform = instance(path.read_bytes(), lambda: False)
            report["resolved_plan_sha256"] = digest(canonical(bound_plan))
        else:
            fixture = native_fixture(scenario)
        ui = ProjectUI(root, guard, fixture=fixture, ready_on_open=ready_on_open, probe_boot=probe_boot)
        if probe_boot:
            report["mix_boot_probe"] = {"initial": ui.base.boot_scan}
        (root / "input/fixture.3mf").chmod(stat.S_IREAD)
        (root / "projects").mkdir()
        (root / "proof").mkdir()
        output = root / "projects/0001.3mf"
        from harness.native_matrix import CANVAS_SCENARIOS, RECORDED_SCENARIOS, REPLAY_SOURCES, UIA_HYBRID_SCENARIOS, UIA_SAVE_SCENARIO, scenario_spec
        tab, disturbance = scenario_spec(actor, scenario)
        if scenario.startswith("uia_param_"):
            # 2026-11-22: param scenarios switch tabs themselves inside
            # run_ops (param_case_lib click_tab, OCR-based). The eager
            # pre-click by exact child caption times out for the Speed tab
            # (121abf7b/8946a225/968bfc6d/0dda1e61 + overhang/accel runs all
            # died here in gui_wait_timeout); skip it for the param family
            # only - every other scenario keeps the trusted initial-tab
            # contract.
            pass
        else:
            target = ui.wait(lambda: ui.named_child(tab), 15)
            ui.click_rect(target[1])
        if not probe_waits:
            ui.pause(2)
        else:
            ui.wait(lambda: ready_on_open(ui.app), 10)
            report["mix_wait_probe"]["initial_ready_at_ns"] = time.time_ns()
        setup = {"run_id": run_id, "scenario": scenario, "app_pid": ui.app.pid, "tab_clicked": tab}
        if disturbance == "overwrite":
            raw = (root / "input/fixture.3mf").read_bytes()
            with output.open("xb") as stream:
                stream.write(raw)
            setup["baseline_sha256"] = hashlib.sha256(raw).hexdigest()
        scope = {"run_id": run_id, "app_pid": ui.app.pid, "hwnd": ui.app.hwnd,
                 "output_path": str(output), "scenario": scenario,
                 "contract_sha256": report["contract_sha256"], "actor": actor}
        # A modal disables the canvas. Bind the enabled child before applying the disturbance.
        if bound_plan:
            scope["resolved_plan_sha256"] = report["resolved_plan_sha256"]
        binding = None
        if bound_plan or scenario in CANVAS_SCENARIOS | UIA_HYBRID_SCENARIOS:
            binding = bind_native_canvas(ui, scope, root, sut_sha)
        if disturbance == "save_dialog":
            ui._save_command()
            dialog = ui.wait(lambda: ui.eu.wait_save_dialog(ui.app.pid, timeout_s=.2), 10)
            if not ui.owned_dialog(dialog[3]):
                raise RuntimeError("native_initial_dialog_not_owned")
            setup["dialog_hwnd"] = scope["dialog_hwnd"] = dialog[3]
        window, capture = ui.identity()
        if not ui.wu.force_set_foreground(setup.get("dialog_hwnd", ui.app.hwnd)):
            raise RuntimeError("native_initial_foreground_failed")
        (root / "initial.png").write_bytes(_encode_capture(capture)[1])
        setup.update(initial_sha256=hashlib.sha256((root / "initial.png").read_bytes()).hexdigest(),
                     finished_at_ns=time.time_ns())
        atomic_json(root / "setup.json", setup)
        atomic_json(root / "scope.json", scope)
        if scenario == "canvas_probe":
            from harness.canvas_input import collect_window_evidence
            atomic_json(root / "canvas_diagnostic.json", collect_window_evidence(run_id, ui.app.pid, ui.app.hwnd))
            ui.close()
            report["app_closed"] = not ui.app.alive()
            report["diagnostic_only"] = True
            return 0 if report["app_closed"] else 1
        if actor == "script":
            from harness.native_script_baseline import edit_project
            report.update(actor="script", scenario=scenario, script_steps=[],
                          script_action_started_at_ns=time.time_ns())
            measured_start = time.monotonic_ns()
            try:
                if bound_plan:
                    from harness.native_script_baseline import move_x
                    report["move"] = move_x(ui, binding.hwnd, original_x=initial_transform[9],
                                             delta_mm=bound_plan["template"]["operations"][0]["delta_mm"])
                    report["script_steps"].append("edit")
                    ui.save_project()
                    report["script_steps"].append("save")
                elif scenario in RECORDED_SCENARIOS:
                    from harness.native_uia_replay import play
                    native.start()
                    report["recording_sha256"] = play(ui, run_id, str(output), scenario=scenario, report=report)
                    report["recorded_trace_sha256"] = hashlib.sha256((root / "native_trace.ndjson").read_bytes()).hexdigest()
                    report["script_steps"] = ["save"] if REPLAY_SOURCES.get(scenario) == UIA_SAVE_SCENARIO else ["edit", "save"]
                else:
                    if scenario != UIA_SAVE_SCENARIO:
                        census = REPO / "artifacts/native_mix_census_requests" / run_id
                        mix_census = census.is_file()
                        if mix_census:
                            census.unlink()
                        edit_project(ui, scenario, ui.app.hwnd if binding is None else binding.hwnd, mix_census=mix_census)
                        report["script_steps"].append("edit")
                    ui.save_project(prepared_dialog=setup.get("dialog_hwnd"))
                    report["script_steps"].append("save")
            finally:
                report["script_action_elapsed_ns"] = time.monotonic_ns() - measured_start
                report["script_action_finished_at_ns"] = time.time_ns()
            stopped = native.stop()
        else:
            native.start()
            if scenario == "authority_probe":
                from harness.native_authority_probe import run_probe
                atomic_json(root / "authority_probe.json", run_probe(root, run_id, ui.app.pid, ui.app.hwnd))
                native.stop()
                ui.close()
                report["app_closed"] = not ui.app.alive()
                report["diagnostic_only"] = True
                return 0 if report["app_closed"] else 1
            atomic_json(root / "ready.json", {"ready": True, "run_id": run_id,
                "window": window, "output_path": str(output), "contract_sha256": report["contract_sha256"]})
            while not (root / "host_done.json").exists():
                guard()
                if native.server.poll()[0] is not None:
                    raise RuntimeError("native_server_died")
                time.sleep(.1)
            stopped = native.stop()
            host = json.loads((root / "host_done.json").read_text())
            if not host.get("native_ok") or host.get("run_id") != run_id:
                raise RuntimeError("native_actor_failed")
        _, capture = ui.identity()
        (root / "agent_final.png").write_bytes(_encode_capture(capture)[1])
        old = ui.app
        ui.close()
        if old.popen.poll() != 0:
            raise RuntimeError("native_old_exit_not_zero")
        closed = time.time_ns()
        prove_project(ui, root, run_id, report["contract_sha256"], guard, sut_sha, stopped, old, closed,
                      probe_boot=probe_boot, probe_waits=probe_waits, report=report)
    except Exception as exc:
        report["error"] = type(exc).__name__+":"+str(exc)[:160]
    finally:
        try:
            native.stop()
        except Exception as exc:
            report["input_stop_error"] = type(exc).__name__
        if ui is not None:
            try:
                ui.close()
                report["app_closed"] = not ui.app.alive()
            except Exception as exc:
                report["cleanup_error"] = type(exc).__name__
        (root / "token").unlink(missing_ok=True)
        if video is not None:
            try:
                atomic_json(root / "desktop_video.json", video.finish())
            except Exception as exc:
                report["video_error"] = type(exc).__name__
        write_json_once(root / "native_worker.json", report)
    return 0 if not report["error"] and report["app_closed"] and not report.get("input_stop_error") else 1


if __name__ == "__main__":
    # The suite captures this process's stdout into native_worker.log. That
    # stream is block buffered, so every print without flush=True landed
    # only when the buffer filled - the log read out of order and could not
    # be followed as a sequence (queue19, 2026-11-23).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--actor", choices=("codex", "zcode", "script"), default="codex")
    from harness.native_matrix import SCENARIOS
    p.add_argument("--scenario", choices=tuple(SCENARIOS), default="base")
    a = p.parse_args()
    raise SystemExit(worker(a.run_id, a.actor, a.scenario))
