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


def worker(run_id, actor="codex", scenario="base"):
    from harness import host_guard
    from harness.agent_protocol import valid_run_id, write_json_once
    from harness.agent_project_ui import ProjectUI
    from harness.agent_guest import _WindowsUI, _encode_capture
    from harness.native_save_session import native_contract, NATIVE_SUT_SHA256
    from harness.run_verdict import contract_digest
    from harness.win32_job import OwnedJobProcess
    valid_run_id(run_id)
    if not host_guard.in_guest():
        raise PermissionError("native worker requires guest")
    root = REPO / "artifacts/v3" / run_id / "artifacts"
    deadline = time.monotonic()+840
    def guard():
        if (time.monotonic() >= deadline or (root / "control_cancel.json").exists()
                or (root / "authority_abort.json").exists()):
            raise TimeoutError("native_worker_deadline_or_cancel")
    ui, server = None, None
    report = {"run_id": run_id, "error": None, "app_closed": False,
              "release_eligible": False, "contract_sha256": contract_digest(native_contract(actor, scenario))}
    def atomic_json(path, data):
        pending = path.with_name(path.name+".pending")
        write_json_once(pending, data)
        pending.rename(path)
    def stop_input():
        nonlocal server
        (root / "input_revoked").touch(exist_ok=True)
        if server is not None:
            server.terminate()  # Only the exact owned MCP server tree.
            cutoff = time.monotonic()+15
            while server.poll()[1] and time.monotonic() < cutoff:
                time.sleep(.1)
            if server.poll()[1]:
                raise RuntimeError("native_mcp_stop_unconfirmed")
            server.close()
            server = None
        return time.time_ns()
    try:
        from harness.launcher import default_exe
        sut_sha = hashlib.sha256(default_exe().read_bytes()).hexdigest()
        if sut_sha != NATIVE_SUT_SHA256:
            raise RuntimeError("native_frozen_sut_changed")
        ui = ProjectUI(root, guard)
        (root / "input/fixture.3mf").chmod(stat.S_IREAD)
        (root / "projects").mkdir()
        (root / "proof").mkdir()
        output = root / "projects/0001.3mf"
        from harness.native_matrix import CANVAS_SCENARIOS, UIA_HYBRID_SCENARIOS, scenario_spec
        tab, disturbance = scenario_spec(actor, scenario)
        target = ui.wait(lambda: ui.named_child(tab), 15)
        ui.click_rect(target[1])
        ui.pause(2)
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
        if scenario in CANVAS_SCENARIOS | UIA_HYBRID_SCENARIOS:
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
            atomic_json(root / "canvas_setup.json", {"run_id": run_id, "contract_sha256": report["contract_sha256"],
                "binding": json.loads(scope["canvas_binding_json"]), "evidence": evidence,
                "pfd_verified": False, "internal_numeric_field_verified": False})
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
        (root / "token").write_text(secrets.token_hex(32), encoding="ascii")
        (root / "config.toml").write_text("", encoding="utf-8")
        env = os.environ.copy()
        env.update(POSTHOG_API_KEY="", ANONYMIZED_TELEMETRY="false",
                   WINDOWS_MCP_AUTH_KEY=(root / "token").read_text(), PYTHONIOENCODING="utf-8")
        server = OwnedJobProcess.start([r"C:\coil\tools\windows-mcp-0.8.9\python.exe", "-B",
            str(REPO / "tools/native_save_server.py"), "--run-id", run_id],
            cwd=REPO, env=env, log_path=root / "server.log")
        for _ in range(60):
            guard()
            if server.poll()[0] is not None:
                raise RuntimeError("native_server_exited")
            try:
                socket.create_connection(("127.0.0.1", 18789), timeout=1).close()
                break
            except OSError:
                time.sleep(1)
        else:
            raise TimeoutError("native_server_not_ready")
        if scenario == "authority_probe":
            from harness.native_authority_probe import run_probe
            atomic_json(root / "authority_probe.json", run_probe(root, run_id, ui.app.pid, ui.app.hwnd))
            stop_input()
            ui.close()
            report["app_closed"] = not ui.app.alive()
            report["diagnostic_only"] = True
            return 0 if report["app_closed"] else 1
        atomic_json(root / "ready.json", {"ready": True, "run_id": run_id,
            "window": window, "output_path": str(output), "contract_sha256": report["contract_sha256"]})
        while not (root / "host_done.json").exists():
            guard()
            if server.poll()[0] is not None:
                raise RuntimeError("native_server_died")
            time.sleep(.1)
        stopped = stop_input()
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
        saved = ui._snapshot()
        with output.open("rb") as stream:
            raw = stream.read(16*1024*1024+1)
        if hashlib.sha256(raw).hexdigest() != saved["sha256"]:
            raise RuntimeError("native_saved_changed")
        frozen = root / "proof/0001.3mf"
        with frozen.open("xb") as stream:
            stream.write(raw)
        frozen.chmod(stat.S_IREAD)
        frozen_ns = time.time_ns()
        started = time.time_ns()
        base = _WindowsUI(root, model=frozen, profile_name="profile_reopen")
        ui.base, ui.app, ui.wu = base, base.app, base.winutil
        ui._close_requested = False
        ui.pause(12)
        ui.wu.user32.ShowWindow(ui.app.hwnd, 3)
        ui.pause(2)
        ui.slice()
        exported = ui.export_gcode()
        exported_ns = time.time_ns()
        (root / "proof_final.png").write_bytes(_encode_capture(ui.identity()[1])[1])
        ui.close()
        write_json_once(root / "proof.json", {"run_id": run_id,
            "sut_sha256": sut_sha,
            "contract_sha256": report["contract_sha256"], "output_path": str(output),
            "input_stopped_at_ns": stopped, "mcp_active_processes": 0,
            "old_pid": old.pid, "old_exit_code": old.popen.poll(), "old_closed_at_ns": closed,
            "frozen_at_ns": frozen_ns, "project_sha256": saved["sha256"],
            "reopen_started_at_ns": started, "reopened_pid": ui.app.pid,
            "reopened_closed": not ui.app.alive(), "reopened_exit_code": ui.app.popen.poll(), "exported_at_ns": exported_ns,
            "gcode_sha256": exported["sha256"]})
    except Exception as exc:
        report["error"] = type(exc).__name__+":"+str(exc)[:160]
    finally:
        try:
            stop_input()
        except Exception as exc:
            report["input_stop_error"] = type(exc).__name__
        if ui is not None:
            try:
                ui.close()
                report["app_closed"] = not ui.app.alive()
            except Exception as exc:
                report["cleanup_error"] = type(exc).__name__
        (root / "token").unlink(missing_ok=True)
        write_json_once(root / "native_worker.json", report)
    return 0 if not report["error"] and report["app_closed"] and not report.get("input_stop_error") else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--actor", choices=("codex", "zcode"), default="codex")
    from harness.native_matrix import SCENARIOS
    p.add_argument("--scenario", choices=tuple(SCENARIOS), default="base")
    a = p.parse_args()
    raise SystemExit(worker(a.run_id, a.actor, a.scenario))
