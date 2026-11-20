"""One native Codex agent run, using only the original Windows-MCP UI tools.

Run after hv_go -WindowsMcpProbe. No JSON action policy, model-per-step wrapper,
or task-specific GUI tools. Local config applies to this process only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from runner.windows_mcp_bridge import GuestHTTP
from harness.agent_model import _child_environment, _DISABLED, default_codex_executable
from harness.win32_job import OwnedJobProcess


def native_calls(path):
    calls = []
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        if not line.startswith("{"):
            continue  # Native stderr shares the owned Job diagnostic log.
        event = json.loads(line)
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
            calls.append({"tool": item.get("tool"), "status": item.get("status"),
                          "arguments": item.get("arguments"), "error": item.get("error"),
                          "is_error": (item.get("result") or {}).get("isError", False)})
    return calls


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--goal-save", action="store_true")
    args = p.parse_args(argv)
    control = GuestHTTP(r"C:\coil\orca-blackbox-v3-r1", args.run_id,
                        deadline=time.monotonic()+1000, channel="control", goal_save=args.goal_save)
    root = REPO / "artifacts" / "windows_mcp_host" / args.run_id
    root.mkdir(parents=True, exist_ok=False)
    exe = default_codex_executable()
    report = {"run_id": args.run_id, "release_eligible": False,
              "codex_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "error": None}
    process = None
    prompt = ("Use only the windows_mcp MCP tools to operate the Snapmaker Orca application "
              "already open in the isolated Windows test guest. Inspect the live screen yourself. "
              "Select Preview, verify the visible selection, then return to Prepare and verify it. "
              "Do not modify settings, files, or other applications. Do not use shell/code/browser tools. "
              "Do not launch or close the application. Take fresh screenshots after each action. "
              "The tool coordinates are desktop screen pixels; read the returned screen geometry. "
              "If the UI tree does not expose custom-drawn tabs, use screenshot reasoning and Click. "
              "At the end release desktop control with ControlStatus(release=true), "
              "then briefly describe what you observed. Do not claim test pass; an independent observer decides.")
    if args.goal_save:
        output_path = r"C:\coil\orca-blackbox-v3-r1\artifacts\v3" + "\\" + args.run_id + r"\artifacts\projects\0001.3mf"
        prompt = ("Use only windows_mcp tools to achieve this goal in the already loaded Snapmaker Orca: "
                  "set regular Layer height to 0.24 mm, preserve First layer height 0.40 mm and the cube model, "
                  "and save the whole project as a 3MF at the exact absolute path " + output_path + ". "
                  "Do not switch printer/filament/process presets or change other settings. "
                  "Choose the UI route and coordinates yourself from fresh screenshots. "
                  "Use loc=[x,y] desktop pixels for Click and Type; label inputs are unavailable. "
                  "Type supports clear=true and press_enter=true. Only numeric strings and the full assigned save path are permitted. "
                  "Available shortcuts are ctrl+s, ctrl+shift+s, enter, tab, shift+tab, esc. "
                  "Only the owned application and its dialogs may receive input. Never open other apps. "
                  "Inspect the screen after changes and confirm the save completed through its UI. "
                  "Do not close, reopen, slice or export the application: independent post-run verification handles that. "
                  "Release ControlStatus(release=true) when done, then describe observations without claiming test pass.")
    (root / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [str(exe), "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--skip-git-repo-check", "-s", "read-only", "--json", "--color", "never",
               "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"']
    for feature in _DISABLED:
        command.extend(["--disable", feature])
    config = {"command": sys.executable,
              "args": ["-B", str(REPO / "runner/windows_mcp_bridge.py"), "--run-id", args.run_id],
              "startup_timeout_sec": 90, "tool_timeout_sec": 60, "required": True}
    if args.goal_save:
        config["args"].append("--goal-save")
    # Inline TOML table, with JSON string escaping for Windows paths.
    encoded = "{"+", ".join(key+"="+json.dumps(value) for key, value in config.items())+"}"
    # User-authorized reversible clicks in this isolated guest only. A native
    # noninteractive `never` approval policy otherwise rejects this write tool.
    # Keep this per-tool and per-process; do not grant shell/full host access.
    command.extend(["-c", "mcp_servers.windows_mcp="+encoded,
                    "-c", 'mcp_servers.windows_mcp.tools.Click.approval_mode="approve"', prompt])
    if args.goal_save:
        command[-1:-1] = ["-c", 'mcp_servers.windows_mcp.tools.Type.approval_mode="approve"',
                          "-c", 'mcp_servers.windows_mcp.tools.Shortcut.approval_mode="approve"']
    env, report["proxy_source"] = _child_environment()
    try:
        for _ in range(50):
            ready = control.remote({"op": "ready"})
            if ready.get("ready") is True:
                break
            time.sleep(2)
        else:
            raise TimeoutError("guest_not_ready")
        report["guest"] = ready
        if args.goal_save and ready.get("output_path") != output_path:
            raise ValueError("native_goal_path_mismatch")
        process = OwnedJobProcess.start(command, cwd=root, env=env, log_path=root / "codex.log")
        cutoff = time.monotonic()+(600 if args.goal_save else 480)
        while True:
            code, active = process.poll()
            if code is not None and active == 0:
                break
            if (root / "codex.log").stat().st_size > 32_000_000 or time.monotonic() >= cutoff:
                raise TimeoutError("codex_deadline_or_output_limit")
            time.sleep(.2)
        report["codex_exit"] = code
        if code:
            raise RuntimeError("codex_failed")
        calls = native_calls(root / "codex.log")
        report["native_tool_calls"] = calls
        if (not calls or any(c["status"] != "completed" or c["error"] or c["is_error"] for c in calls)):
            raise RuntimeError("native_tools_failed_or_unused")
        time.sleep(2)  # Allow two independent stable final-state captures.
    except Exception as exc:
        report["error"] = type(exc).__name__+":"+str(exc)[:160]
    finally:
        if process is not None:
            forced = process.poll()[1] != 0
            if forced:
                process.terminate()
            for _ in range(100):
                code, active = process.poll()
                if active == 0:
                    break
                time.sleep(.1)
            report["host_job"] = {"active_processes": active, "forced_termination": forced}
            if active == 0:
                process.close()
            else:
                report["error"] = "host_cleanup_unconfirmed"
        try:
            receipt = {"run_id": args.run_id, "native_ok": report["error"] is None,
                "host_active_processes": report.get("host_job", {}).get("active_processes", 0),
                "host_forced": report.get("host_job", {}).get("forced_termination", False),
                "tool_count": len(report.get("native_tool_calls", []))}
            report["done"] = control.remote({"op": "done", "receipt": receipt})
            if args.goal_save:
                cutoff = min(control.deadline, time.monotonic()+240)
                while time.monotonic() < cutoff:
                    result = control.remote({"op": "result"})
                    if result.get("pending") is not True:
                        report["guest_result"] = result
                        if result.get("verified_pass") is not True:
                            report["error"] = report["error"] or "native_independent_proof_failed"
                        break
                    time.sleep(2)
                else:
                    report["error"] = report["error"] or "native_result_timeout"
        except Exception as exc:
            report["done_error"] = type(exc).__name__
            if args.goal_save:
                report["error"] = report["error"] or "native_completion_unconfirmed"
        (root / "host.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 1 if report["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
