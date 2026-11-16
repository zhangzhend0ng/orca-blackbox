"""MCP/scoped dispatch checks use pure data; no relay or GUI."""
import base64
import hashlib
import io
import json

import pytest

from runner import agent_bridge
from runner.agent_bridge import ScopedTools, decode_json, serve, validate_identity

RUN = "a" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"test-data"


class Mailbox:
    def __init__(self):
        self.requests = []

    def call(self, r):
        self.requests.append(r)
        return {"schema_version": 1, "run_id": RUN, "seq": r["seq"], "tool": r["method"],
                "is_error": False, "error_code": None, "finished": r["method"] == "finish",
                "observation": {"id": RUN + f'_{r["seq"]:04d}',
                    "image": {"path": f'frames/{r["seq"]:04d}.png', "size_bytes": len(PNG),
                              "sha256": hashlib.sha256(PNG).hexdigest()},
                    "window": {"width": 1186, "height": 792}}}

    def image(self, _):
        return PNG


def test_tools_bind_latest_observation_and_never_expose_paths():
    backend = Mailbox()
    tools = ScopedTools(backend, RUN)
    first = tools.call("observe", {})
    meta = json.loads(first["content"][0]["text"])
    assert "path" not in meta
    tools.call("click", {"observation_id": meta["observation_id"], "x": 230, "y": 48})
    tools.call("finish", {})
    assert backend.requests[0]["observation_id"] is None
    assert backend.requests[-1]["observation_id"] == RUN + "_0002"
    assert backend.requests[1]["arguments"] == {"x": 230, "y": 48}
    assert base64.b64decode(first["content"][1]["data"]) == PNG
    with pytest.raises(ValueError):
        tools.call("observe", {})


@pytest.mark.parametrize("changes", [{"x": 313}, {"x": True}, {"y": 30},
                                      {"observation_id": "stale"}, {"extra": "file"}])
def test_bad_click_has_no_transport_side_effect(changes):
    backend = Mailbox()
    tools = ScopedTools(backend, RUN)
    tools.call("observe", {})
    arguments = {"observation_id": RUN + "_0001", "x": 244, "y": 49, **changes}
    with pytest.raises(ValueError):
        tools.call("click", arguments)
    assert len(backend.requests) == 1


def test_ambiguous_dispatch_is_consumed_not_replayed():
    class Broken(Mailbox):
        def call(self, r):
            super().call(r)
            raise TimeoutError("lost reply")
    backend = Broken()
    tools = ScopedTools(backend, RUN)
    with pytest.raises(TimeoutError):
        tools.call("observe", {})
    assert tools.seq == 1


def test_tool_budget_stops_before_transport():
    backend = Mailbox()
    tools = ScopedTools(backend, RUN)
    for _ in range(12):
        tools.call("observe", {})
    with pytest.raises(ValueError):
        tools.call("observe", {})
    assert len(backend.requests) == 12


def wire(*requests):
    return io.StringIO("".join(json.dumps(x)+"\n" for x in requests))


def test_mcp_initialization_negotiates_supported_version_then_tools():
    source = wire({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "unknown-future"}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                  {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "observe", "arguments": {}}})
    output = io.StringIO()
    serve(ScopedTools(Mailbox(), RUN), source, output)
    replies = [json.loads(x) for x in output.getvalue().splitlines()]
    assert len(replies) == 3
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert {t["name"] for t in replies[1]["result"]["tools"]} == {"observe", "click", "finish"}
    assert not replies[2]["result"]["isError"]


def test_mcp_cannot_dispatch_before_initialized():
    backend = Mailbox()
    output = io.StringIO()
    serve(ScopedTools(backend, RUN), wire({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "observe", "arguments": {}}}), output)
    assert "error" in json.loads(output.getvalue())
    assert not backend.requests


@pytest.mark.parametrize("guest,run", [(r"C:\coil\elsewhere", RUN),
                                       (r"C:\coil\orca-blackbox-v3-r1\..\other", RUN),
                                       (r"C:\coil\orca-blackbox", "../run")])
def test_remote_checkout_identity_rejects_escape(guest, run):
    with pytest.raises(ValueError):
        validate_identity(guest, run)


def test_json_duplicate_and_nonfinite_rejected():
    for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
        with pytest.raises(ValueError):
            decode_json(raw)


def test_detached_response_uses_base64_not_remoting_string_metadata(tmp_path, monkeypatch):
    import time
    from runner import relay_run
    monkeypatch.setattr(agent_bridge, "REPO", tmp_path)
    mailbox = agent_bridge.RelayMailbox(r"C:\coil\orca-blackbox-v3-r1", RUN,
                                        deadline=time.monotonic()+10)
    def launch(_cmd, timeout_s):
        script = (mailbox.root / "0001.ps1").read_text()
        assert "data_b64=" in script
        # PSDirect strings have PSComputerName/RunspaceId metadata. The
        # detached child encodes the plain string before JSON serialization.
        payload = base64.b64encode(b'{"exists":false}').decode()
        (mailbox.root / "0001.json").write_text(json.dumps({"ok": True, "data_b64": payload}))
        return "12345"
    monkeypatch.setattr(relay_run, "relay_transact", launch)
    assert mailbox.remote({"op": "json", "path": "ready.json"}) == {"exists": False}


def test_layer_capability_dispatches_only_registered_business_arguments():
    backend = Mailbox()
    tools = ScopedTools(backend, RUN, "m3d_param_reslice")
    assert {t["name"] for t in tools.tool_definitions} == {
        "observe", "click", "edit", "slice", "export_gcode", "finish"}
    tools.call("observe", {})
    for tool in ("slice", "export_gcode", "edit", "slice", "export_gcode"):
        args = {"observation_id": tools.observation_id}
        if tool == "edit":
            args.update(x=290, y=610, text="0.24")
        tools.call(tool, args)
    tools.call("finish", {})
    assert backend.requests[3]["arguments"] == {"x": 290, "y": 610, "text": "0.24"}
    assert [r["method"] for r in backend.requests] == [
        "observe", "slice", "export_gcode", "edit", "slice", "export_gcode", "finish"]


@pytest.mark.parametrize("name,args", [
    ("export_gcode", {"path": "C:/outside.gcode"}),
    ("edit", {"x": 290, "y": 610, "text": "0.24; command"}),
    ("edit", {"x": True, "y": 610, "text": "0.24"}),
])
def test_layer_invalid_input_never_reaches_transport(name, args):
    backend = Mailbox()
    tools = ScopedTools(backend, RUN, "m3d_param_reslice")
    tools.call("observe", {})
    with pytest.raises(ValueError):
        tools.call(name, {"observation_id": tools.observation_id, **args})
    assert len(backend.requests) == 1


def test_third_slice_is_rejected_before_dispatch():
    backend = Mailbox()
    tools = ScopedTools(backend, RUN, "m3d_param_reslice")
    tools.call("observe", {})
    for _ in range(2):
        tools.call("slice", {"observation_id": tools.observation_id})
    with pytest.raises(ValueError, match="budget"):
        tools.call("slice", {"observation_id": tools.observation_id})
    assert len(backend.requests) == 3


def test_tab_capability_cannot_invoke_business_tools():
    backend = Mailbox()
    tools = ScopedTools(backend, RUN)
    tools.call("observe", {})
    with pytest.raises(ValueError):
        tools.call("edit", {"observation_id": tools.observation_id, "x": 290, "y": 610, "text": "0.24"})
    assert len(backend.requests) == 1
