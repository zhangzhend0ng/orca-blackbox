"""Host-only controlled AI loop. GUI runs separately through hv_go -V3.

The model returns data, not code. A real stdio MCP client calls only the scoped
bridge. This host has no GUI driver; the guest captures and checks its own run.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from runner.agent_bridge import MAX_IMAGE_BYTES, RelayMailbox, decode_json, validate_identity


class McpClient:
    def __init__(self, guest_root, run_id, root, deadline, case_id="m1_minimal_loop"):
        self.deadline, self.ident = deadline, 0
        self.case_id = case_id
        self.errors = (root / "bridge_stderr.log").open("xb")
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(REPO / "runner" / "agent_bridge.py"),
             "--guest-root", guest_root, "--run-id", run_id, "--deadline", str(deadline), "--case", case_id],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.incoming = queue.Queue(maxsize=2)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(4_000_001)
                if not line or len(line) > 4_000_000 or not line.endswith(b"\n"):
                    self.incoming.put(None, timeout=1)
                    return
                self.incoming.put(line, timeout=1)
        except (OSError, ValueError, queue.Full):
            return

    def request(self, method, params=None, *, timeout_s=90):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("host_deadline")
        self.ident += 1
        request = {"jsonrpc": "2.0", "id": self.ident, "method": method}
        if params is not None:
            request["params"] = params
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        self.process.stdin.flush()
        remaining = min(timeout_s, self.deadline-time.monotonic())
        if remaining <= 0:
            raise TimeoutError("host_deadline")
        try:
            line = self.incoming.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("mcp_response_timeout") from exc
        if line is None:
            raise RuntimeError("mcp_bridge_stopped")
        response = decode_json(line)
        if (type(response) is not dict or response.get("jsonrpc") != "2.0"
                or response.get("id") != self.ident or "error" in response):
            raise RuntimeError("mcp_response_rejected")
        return response["result"]

    def initialize(self):
        result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "orca-v3-host", "version": "1"}})
        if result.get("protocolVersion") != "2025-06-18":
            raise ValueError("mcp_protocol_version")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("host_deadline")
        self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        self.process.stdin.flush()
        listed = self.request("tools/list")
        from harness.agent_protocol import agent_profile
        if {tool["name"] for tool in listed["tools"]} != set(agent_profile(self.case_id)["tools"]):
            raise ValueError("mcp_tools_changed")

    def call(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments},
                            timeout_s=230 if name == "slice" else 120 if name == "export_gcode" else 90)

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=3)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=3)
        finally:
            self.errors.close()


def unpack_observation(result, root: Path, index: int):
    if type(result) is not dict or result.get("isError") is not False:
        raise ValueError("tool_failed")
    content = result.get("content")
    if type(content) is not list or len(content) != 2:
        raise ValueError("observation_content")
    text, picture = content
    if text.get("type") != "text" or picture.get("type") != "image" or picture.get("mimeType") != "image/png":
        raise ValueError("observation_content")
    meta = decode_json(text["text"])
    if (type(meta) is not dict or set(meta) != {"observation_id", "width", "height", "finished", "image_sha256"}
            or type(meta["observation_id"]) is not str or not 1 <= len(meta["observation_id"]) <= 128
            or type(meta["width"]) is not int or not 313 <= meta["width"] <= 8192
            or type(meta["height"]) is not int or not 68 <= meta["height"] <= 8192
            or type(meta["finished"]) is not bool):
        raise ValueError("observation_metadata")
    if type(picture["data"]) is not str or len(picture["data"]) > 4*((MAX_IMAGE_BYTES+2)//3):
        raise ValueError("observation_image_size")
    raw = base64.b64decode(picture["data"], validate=True)
    if hashlib.sha256(raw).hexdigest() != meta["image_sha256"] or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("observation_image_hash")
    path = root / f"observation_{index:04d}.png"
    with path.open("xb") as f:
        f.write(raw)
    return meta, path


def control_loop(client, model, root, deadline, case_id="m1_minimal_loop"):
    """Initial observe is mechanical. All subsequent tool choices come from model."""
    history, calls = [], 0
    if time.monotonic() >= deadline:
        raise TimeoutError("host_deadline")
    result = client.call("observe", {})
    for index in range(1, 10):
        if time.monotonic() >= deadline:
            raise TimeoutError("host_deadline")
        observation, image = unpack_observation(result, root, index)
        if observation["finished"]:
            return {"finished": True, "model_calls": calls, "actions": history}
        if calls >= 8:
            raise RuntimeError("model_call_budget")
        calls += 1
        action = model.next_action(image, {"id": observation["observation_id"],
            "window": {"width": observation["width"], "height": observation["height"]}},
            history, 8-calls+1, root / f"model_{calls:04d}", deadline)
        if time.monotonic() >= deadline:
            raise TimeoutError("host_deadline")
        # The model module validates the schema. Revalidate at the tool boundary.
        from harness.agent_model import _action
        action = _action(action, observation["observation_id"], observation["width"],
                         observation["height"], case_id=case_id)
        tool = action["tool"]
        if tool in {"click", "edit"}:
            args = {"observation_id": action["observation_id"], "x": action["x"], "y": action["y"]}
            if tool == "edit":
                args["text"] = action["text"]
        elif tool in {"slice", "export_gcode"}:
            args = {"observation_id": action["observation_id"]}
        elif tool in {"observe", "finish"} and action["x"] is None and action["y"] is None:
            args = {}
        else:
            raise ValueError("model_action_tool")
        history.append(dict(action))
        with (root / f"action_{calls:04d}.json").open("x", encoding="utf-8") as f:
            json.dump(action, f)
        result = client.call(tool, args)
    raise RuntimeError("host_loop_limit")


class ChatDecisionModel:
    """Active Codex chat supplies observations/decisions through exclusive files.

    This is an explicit external model port, not evidence that CLI inference
    works. No GUI input or user confirmation is required by this provider.
    """
    source = "codex_chat"

    def __init__(self, case_id="m1_minimal_loop"):
        from harness.agent_protocol import agent_profile
        agent_profile(case_id)
        self.case_id = case_id

    def next_action(self, image, observation, history, remaining_calls, output_dir, deadline):
        from harness.agent_model import _action
        output_dir.mkdir(exist_ok=False)
        with (output_dir / "request.json").open("x", encoding="utf-8") as f:
            json.dump({"source": self.source, "image": str(image.resolve()),
                       "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                       "run_id": image.parent.name,
                       "observation": observation, "history": history,
                       "remaining_calls": remaining_calls, "created_at_ns": time.time_ns()}, f)
        print(json.dumps({"awaiting_model": self.source, "request": str((output_dir / 'request.json').resolve())}), flush=True)
        decision = output_dir / "decision.json"
        while time.monotonic() < deadline:
            if decision.exists():
                with decision.open("rb") as f:
                    raw = f.read(4097)
                if len(raw) > 4096:
                    raise ValueError("chat_decision_size")
                action = _action(decode_json(raw), observation["id"],
                                 observation["window"]["width"], observation["window"]["height"],
                                 case_id=self.case_id)
                with (output_dir / "summary.json").open("x", encoding="utf-8") as f:
                    json.dump({"source": self.source, "action": action, "usage": None,
                               "dollar_cost": None, "received_at_ns": time.time_ns()}, f)
                return action
            time.sleep(.1)
        raise TimeoutError("chat_decision_deadline")


def run_host(run_id, guest_root, model, case_id="m1_minimal_loop"):
    validate_identity(guest_root, run_id)
    from harness.agent_session import agent_contract
    from harness.run_verdict import contract_digest
    digest = contract_digest(agent_contract(case_id))
    if getattr(model, "case_id", case_id) != case_id:
        raise ValueError("model_task_mismatch")
    root = REPO / "artifacts" / "v3_host" / run_id
    root.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic()+600
    control = RelayMailbox(guest_root, run_id, deadline=deadline, channel="control")
    client, completed = None, False
    report = {"schema_version": 1, "run_id": run_id, "model_source": getattr(model, "source", "codex_cli"),
              "case_id": case_id,
              "finished": False, "release_eligible": False, "dollar_cost": None, "started_at_ns": time.time_ns()}
    try:
        ready = control.wait_json("ready.json", seconds=120)
        if (ready.get("run_id") != run_id or ready.get("case_id") != case_id
                or ready.get("contract_sha256") != digest):
            raise ValueError("guest_ready_identity")
        client = McpClient(guest_root, run_id, root, deadline, case_id)
        client.initialize()
        result = control_loop(client, model, root, deadline, case_id)
        report.update(result)
        completed = True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        report.update(finished=False, error_type=type(exc).__name__)
        raise
    finally:
        close_error = None
        if client is not None:
            try:
                client.close()
            except BaseException as exc:
                close_error = exc
                completed = False
                report.update(finished=False, bridge_close_error=type(exc).__name__)
        if not completed:
            # Separate trusted control, never an additional model tool. The guest
            # may already be done; lack of acknowledgement stays explicit.
            control.deadline = time.monotonic()+30
            try:
                control.cancel()
                report["cancel_request_written"] = True
            except (OSError, ValueError, RuntimeError):
                report["cancel_request_written"] = False
        report["finished_at_ns"] = time.time_ns()
        with (root / "host_run.json").open("x", encoding="utf-8") as f:
            json.dump(report, f, sort_keys=True, allow_nan=False)
            f.write("\n")
        if close_error is not None and sys.exc_info()[0] is None:
            raise RuntimeError("bridge_close_failed") from close_error
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    p.add_argument("--model-source", choices=("codex_cli", "codex_chat"), default="codex_cli")
    p.add_argument("--case", default="m1_minimal_loop")
    p.add_argument("--codex", type=Path, help="Explicit native Codex; otherwise prefer the installed desktop native")
    args = p.parse_args()
    from harness.agent_model import CodexModel, default_codex_executable
    model = ChatDecisionModel(args.case) if args.model_source == "codex_chat" else CodexModel(
        args.codex or default_codex_executable(), case_id=args.case)
    report = run_host(args.run_id, args.guest_root, model, args.case)
    print(json.dumps({"run_id": report["run_id"], "finished": report["finished"],
                      "model_calls": report["model_calls"], "release_eligible": False}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "host_stopped", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2)
