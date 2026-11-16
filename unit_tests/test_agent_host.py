"""Host loop end conditions with fake MCP and inference; no GUI/model calls."""
import base64
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from tools import v3_agent_host as host

PNG = b"\x89PNG\r\n\x1a\n" + b"test-data"


class Client:
    def __init__(self):
        self.calls = []

    def call(self, name, args):
        self.calls.append((name, args))
        meta = {"observation_id": f"obs_{len(self.calls)}", "width": 1186, "height": 792,
                "finished": name == "finish", "image_sha256": hashlib.sha256(PNG).hexdigest()}
        return {"isError": False, "content": [{"type": "text", "text": json.dumps(meta)},
             {"type": "image", "mimeType": "image/png", "data": base64.b64encode(PNG).decode()}]}


class Model:
    def __init__(self):
        self.index = 0

    def next_action(self, image, observation, history, remaining, output, deadline):
        assert image.exists() and len(history) == self.index
        tool = ("click", "click", "finish")[self.index]
        self.index += 1
        return {"tool": tool, "observation_id": observation["id"],
                "x": 244 if tool == "click" else None, "y": 49 if tool == "click" else None}


def test_loop_uses_model_decisions_and_finish_is_not_verdict(tmp_path):
    client = Client()
    result = host.control_loop(client, Model(), tmp_path, time.monotonic()+60)
    assert result["finished"] and result["model_calls"] == 3
    assert [c[0] for c in client.calls] == ["observe", "click", "click", "finish"]
    assert "verified_pass" not in result
    assert len(list(tmp_path.glob("action_*.json"))) == 3


def test_model_returning_after_deadline_cannot_click(tmp_path, monkeypatch):
    clock = [10.]
    monkeypatch.setattr(host.time, "monotonic", lambda: clock[0])
    class Late(Model):
        def next_action(self, *args):
            action = super().next_action(*args)
            clock[0] = 100.
            return action
    client = Client()
    with pytest.raises(TimeoutError):
        host.control_loop(client, Late(), tmp_path, 50.)
    assert [c[0] for c in client.calls] == ["observe"]


def test_mcp_expired_request_does_not_write(monkeypatch):
    client = host.McpClient.__new__(host.McpClient)
    client.deadline, client.ident = 0., 0
    class Unwritable:
        def write(self, _):
            pytest.fail("deadline must be checked before write")
    client.process = SimpleNamespace(stdin=Unwritable())
    with pytest.raises(TimeoutError):
        client.request("tools/call")


def test_close_failure_still_requests_cancel_and_writes_report(tmp_path, monkeypatch):
    from harness.agent_session import agent_contract
    from harness.run_verdict import contract_digest
    run = "a" * 32
    monkeypatch.setattr(host, "REPO", tmp_path)
    cancelled = []
    class Control:
        def __init__(self, *a, **kw):
            pass
        def wait_json(self, *a, **kw):
            return {"run_id": run, "case_id": "m1_minimal_loop",
                    "contract_sha256": contract_digest(agent_contract("m1_minimal_loop"))}
        def cancel(self):
            cancelled.append(True)
    class BrokenClient(Client):
        def __init__(self, *a):
            super().__init__()
        def initialize(self):
            pass
        def close(self):
            raise OSError("owned process wait failed")
    monkeypatch.setattr(host, "RelayMailbox", Control)
    monkeypatch.setattr(host, "McpClient", BrokenClient)
    with pytest.raises(RuntimeError, match="close_failed"):
        host.run_host(run, r"C:\coil\orca-blackbox-v3-r1", Model())
    report = json.loads((tmp_path / "artifacts/v3_host" / run / "host_run.json").read_text())
    assert cancelled and report["cancel_request_written"]
    assert report["finished"] is False and report["bridge_close_error"] == "OSError"


def test_bad_image_hash_is_not_forwarded_to_model(tmp_path):
    result = Client().call("observe", {})
    result["content"][1]["data"] = base64.b64encode(PNG+b"corrupt").decode()
    with pytest.raises(ValueError, match="image_hash"):
        host.unpack_observation(result, tmp_path, 1)
    assert not list(tmp_path.iterdir())


def test_chat_model_receipt_binds_input_hash_and_strict_action(tmp_path, monkeypatch):
    image = tmp_path / "observation.png"
    image.write_bytes(PNG)
    output = tmp_path / "model_0001"
    action = {"tool": "click", "observation_id": "obs_1", "x": 244, "y": 49}
    def publish(_):
        pending = output / "decision.pending"
        pending.write_text(json.dumps(action))
        pending.rename(output / "decision.json")
    monkeypatch.setattr(host.time, "sleep", publish)
    result = host.ChatDecisionModel().next_action(image, {"id": "obs_1", "window": {
        "width": 1186, "height": 792}}, [], 8, output, time.monotonic()+2)
    assert result == action
    request = json.loads((output / "request.json").read_text())
    assert request["image_sha256"] == hashlib.sha256(PNG).hexdigest()
    summary = json.loads((output / "summary.json").read_text())
    assert summary["source"] == "codex_chat" and summary["usage"] is None


def test_layer_host_routes_model_numeric_edit_and_path_free_exports(tmp_path):
    class LayerModel:
        index = 0
        def next_action(self, image, observation, history, remaining, output, deadline):
            tool = ("slice", "export_gcode", "edit", "slice", "export_gcode", "finish")[self.index]
            self.index += 1
            return {"tool": tool, "observation_id": observation["id"],
                    "x": 290 if tool == "edit" else None,
                    "y": 610 if tool == "edit" else None,
                    "text": "0.24" if tool == "edit" else None}
    client = Client()
    result = host.control_loop(client, LayerModel(), tmp_path, time.monotonic()+60,
                               case_id="m3d_param_reslice")
    assert result["finished"] and result["model_calls"] == 6
    assert [c[0] for c in client.calls] == [
        "observe", "slice", "export_gcode", "edit", "slice", "export_gcode", "finish"]
    assert client.calls[3][1]["text"] == "0.24"
    assert all(set(args) == {"observation_id"} for name, args in client.calls if name == "export_gcode")


def test_slice_wait_has_phase_headroom_without_extending_run_deadline():
    from unittest.mock import Mock
    client = host.McpClient.__new__(host.McpClient)
    client.request = Mock(return_value={})
    client.call("slice", {"observation_id": "obs_1"})
    assert client.request.call_args.kwargs["timeout_s"] == 230
