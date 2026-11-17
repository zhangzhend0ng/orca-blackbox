"""Guest-only original Windows-MCP compatibility probe; never a release GREEN.

Only hv_go starts this supervisor in INTERACTIVE. PS Direct only carries HTTP
data. Codex supplies native MCP calls; this worker independently records tabs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from harness import host_guard
from harness.agent_protocol import valid_run_id, write_json_once
from harness.win32_job import OwnedJobProcess

RUNTIME = Path(r"C:\coil\tools\windows-mcp-0.8.9\python.exe")
TOOLSET = "Snapshot,Screenshot,Click,Wait,ControlStatus"


def worker(root):
    from harness.agent_business_ui import BusinessUI
    from harness.agent_guest import _encode_capture
    from harness.agent_verify import _frame_state
    deadline = time.monotonic()+660
    def guard():
        if time.monotonic() >= deadline:
            raise TimeoutError("probe_deadline")
    ui, server = None, None
    report = {"release_eligible": False, "states": [], "error": None,
              "app_closed": False, "server_stopped": False}
    log = (root / "server.log").open("xb")
    try:
        ui = BusinessUI(root, guard)
        token = secrets.token_hex(32)
        (root / "token").write_text(token, encoding="ascii")
        (root / "config.toml").write_text("", encoding="utf-8")
        env = os.environ.copy()
        env.update(POSTHOG_API_KEY="", WINDOWS_MCP_AUTH_KEY=token,
                   WINDOWS_MCP_SCREENSHOT_SCALE="1.0", PYTHONIOENCODING="utf-8")
        server = subprocess.Popen([str(RUNTIME), "-m", "windows_mcp", "serve",
            "--transport", "streamable-http", "--host", "127.0.0.1", "--port", "18789",
            # Dedicated, idle-gated test VM only: original 0.8.9 ownership hooks
            # reject all inputs with CONTROL_UNAVAILABLE on this guest. Use its
            # supported explicit opt-out, never silently weaken a shared host.
            "--stateless-http", "--no-control", "--tools", TOOLSET, "--config", str(root / "config.toml")],
            cwd=root, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW)
        report["server_pid"] = server.pid
        report["desktop_ownership_hooks"] = False
        # HTTP readiness only; this does not execute UI tools.
        for _ in range(60):
            guard()
            if server.poll() is not None:
                raise RuntimeError("windows_mcp_server_exited")
            try:
                socket.create_connection(("127.0.0.1", 18789), timeout=1).close()
                break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("server_not_ready")
        window, _ = ui.identity()
        write_json_once(root / "ready.json", {"ready": True, "window": window,
                        "server_pid": server.pid, "driver_pid": os.getpid()})
        last, stable = None, 0
        while not (root / "done").exists():
            guard()
            if server.poll() is not None:
                raise RuntimeError("server_died")
            window, capture = ui.identity()
            bmp, png = _encode_capture(capture)
            try:
                state = _frame_state(bmp, window["width"], window["height"], lambda: False)
            except ValueError:
                state = "unknown"
            stable = stable+1 if state == last else 1
            last = state
            states = report["states"]
            if state != "unknown" and stable >= 2 and (not states or states[-1]["state"] != state):
                name = f"state_{len(states):02d}_{state}.bmp"
                (root / name).write_bytes(bmp)
                png_name = name.removesuffix('.bmp')+'.png'
                (root / png_name).write_bytes(png)
                states.append({"state": state, "at_ns": time.time_ns(), "file": name,
                               "sha256": hashlib.sha256(bmp).hexdigest(), "png": png_name,
                               "png_sha256": hashlib.sha256(png).hexdigest()})
            time.sleep(.5)
    except Exception as exc:
        report["error"] = type(exc).__name__+":"+str(exc)[:160]
    finally:
        if ui is not None:
            try:
                ui.close()
                report["app_closed"] = not ui.app.alive()
            except Exception as exc:
                report["cleanup_error"] = type(exc).__name__
        if server is not None:
            if server.poll() is None:
                server.terminate()  # Exact run-owned server, never the SUT.
            try:
                server.wait(timeout=8)
                report["server_stopped"] = True
            except subprocess.TimeoutExpired:
                report["cleanup_error"] = "server_exit_timeout"
        log.close()
        (root / "token").unlink(missing_ok=True)
        write_json_once(root / "worker.json", report)
    return 0 if not report["error"] and report["app_closed"] and report["server_stopped"] else 1


def supervise(root):
    root.mkdir(parents=True, exist_ok=False)
    job = OwnedJobProcess.start([sys.executable, "-B", str(Path(__file__).resolve()),
        "--run-id", root.name, "--worker"], cwd=REPO, log_path=root / "worker.log", env=os.environ.copy())
    forced, deadline = False, time.monotonic()+720
    try:
        while True:
            code, active = job.poll()
            if code is not None and active == 0:
                break
            if time.monotonic() >= deadline or code is not None:
                forced = True
                job.terminate()
                break
            time.sleep(.2)
    finally:
        # Any supervisor exception also closes its whole owned tree.
        if job.poll()[1]:
            forced = True
            job.terminate()
        for _ in range(100):
            code, active = job.poll()
            if active == 0:
                break
            time.sleep(.1)
        receipt = {"schema_version": 1, "run_id": root.name, "release_eligible": False,
                   "exit_code": code, "active_processes": active, "forced_termination": forced}
        write_json_once(root / "process.json", receipt)
        job.close()
    return 0 if code == 0 and active == 0 and not forced else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--worker", action="store_true")
    args = p.parse_args()
    valid_run_id(args.run_id)
    if not host_guard.in_guest():
        raise PermissionError("probe requires Hyper-V guest")
    root = REPO / "artifacts" / "windows_mcp_runs" / args.run_id
    return worker(root) if args.worker else supervise(root)


if __name__ == "__main__":
    raise SystemExit(main())
