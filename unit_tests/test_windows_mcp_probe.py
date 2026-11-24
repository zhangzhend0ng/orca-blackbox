"""Probe transport boundaries, independent of Windows/UI/network."""
import base64
import io
import json
from types import SimpleNamespace

import pytest

from runner.windows_mcp_bridge import response_json, validate_request
from tools.windows_mcp_codex_probe import native_calls


@pytest.mark.parametrize("method", ["resources/read", "completion/complete", "exec"])
def test_unknown_mcp_methods_rejected(method):
    with pytest.raises(ValueError, match="method_rejected"):
        validate_request({"jsonrpc": "2.0", "method": method}, 0)


@pytest.mark.parametrize("name,calls", [("PowerShell", 0), ("Registry", 0), ("Click", 20)])
def test_disallowed_tools_and_exhausted_budget_stop(name, calls):
    with pytest.raises(ValueError, match="tool_rejected_or_budget"):
        validate_request({"jsonrpc": "2.0", "method": "tools/call",
                          "params": {"name": name, "arguments": {}}}, calls)


def test_sse_result_is_decoded_without_evaluating_text():
    assert response_json('event: message\ndata: {"id":1,"result":{}}\n\n') == {"id": 1, "result": {}}


def test_multiple_sse_events_are_not_silently_dropped():
    with pytest.raises(ValueError, match="unsupported_sse"):
        response_json('data: {}\n\ndata: {}\n\n')


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
def test_unicode_in_ui_text_does_not_split_sse_frame(separator):
    assert response_json('data: {"text":"a'+separator+'b"}\r\n\r\n') == {"text": "a"+separator+"b"}


@pytest.mark.parametrize("status,error", [("completed", None), ("failed", {"message": "Transport closed"})])
def test_native_tool_result_is_audited_independently_of_cli_exit(tmp_path, status, error):
    log = tmp_path / "codex.log"
    log.write_text('native diagnostic\n'+json.dumps({"type": "item.completed", "item": {
        "type": "mcp_tool_call", "tool": "Snapshot", "status": status,
        "arguments": {"use_vision": True}, "error": error, "result": None}})+'\n')
    calls = native_calls(log)
    assert calls[0]["status"] == status
    assert calls[0]["error"] == error


def test_uia_bridge_does_not_relay_queued_input_after_guest_fatal(tmp_path, monkeypatch, capsys):
    from runner import windows_mcp_bridge as bridge

    run_id = "a" * 32
    requests = [dict(jsonrpc="2.0", id=i, method="tools/call", params=dict(name=tool, arguments={}))
                for i, tool in ((1, "Click"), (2, "Type"))]
    sent = []

    def relay(spec):
        request = json.loads(spec["body"])
        sent.append(request)
        authority = dict(protocol="native-authority-1", run_id=run_id, seq=1,
                         tool="Click", decision="fatal", dispatched=False)
        return dict(status=200, body=json.dumps(dict(jsonrpc="2.0", id=request["id"],
                    result=dict(isError=True, structuredContent=dict(authority=authority)))))

    log = tmp_path / "authority.ndjson"
    monkeypatch.setattr(bridge, "GuestHTTP", lambda *args, **kwargs: SimpleNamespace(remote=relay))
    monkeypatch.setattr(bridge.sys, "argv", ["windows_mcp_bridge", "--run-id", run_id, "--goal-save",
                                             "--scenario", "uia_hybrid_canvas", "--authority-log", str(log)])
    lines = "".join(json.dumps(request) + "\n" for request in requests).encode()
    monkeypatch.setattr(bridge.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(lines)))

    bridge.main()

    assert sent == requests[:1]
    assert json.loads(capsys.readouterr().out)["id"] == 1
    assert json.loads(log.read_text())["authority"]["decision"] == "fatal"


def test_comparison_bridge_advertises_the_scoped_guest_toolset(monkeypatch, capsys):
    from harness.native_save_policy import native_tools
    from runner import windows_mcp_bridge as bridge

    scenario = "compare_265_quality"
    request = dict(jsonrpc="2.0", id=1, method="tools/list")
    tools = [{"name": name, "inputSchema": {"type": "object"}} for name in sorted(native_tools(scenario))]

    def relay(spec):
        assert json.loads(spec["body"]) == request
        return dict(status=200, body=json.dumps(dict(jsonrpc="2.0", id=1, result=dict(tools=tools))))

    monkeypatch.setattr(bridge, "GuestHTTP", lambda *args, **kwargs: SimpleNamespace(remote=relay))
    monkeypatch.setattr(bridge.sys, "argv", ["windows_mcp_bridge", "--run-id", "a" * 32, "--goal-save",
                                             "--scenario", scenario])
    monkeypatch.setattr(bridge.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode())))

    bridge.main()

    advertised = json.loads(capsys.readouterr().out)["result"]["tools"]
    assert {tool["name"] for tool in advertised} == native_tools(scenario)


@pytest.mark.parametrize("scenario, operation, tool, deadline, succeeds", [
    ("compare_276_quality", "ready", None, None, True),
    ("compare_276_quality", "result", None, None, True),
    ("compare_276_quality", "http", "Snapshot", None, True),
    ("compare_276_strength", "http", "Screenshot", None, True),
    ("compare_276_quality", "result", None, 50, False),
    ("compare_276_quality", "http", "Click", None, False),
    ("compare_276_quality", "http", "Type", None, False),
    ("compare_276_quality", "http", "Shortcut", None, False),
    ("compare_276_quality", "http", "ControlStatus", None, False),
    ("compare_276_quality", "done", None, None, False),
    ("compare_276_quality", "cancel", None, None, False),
    ("base", "ready", None, None, False),
    ("base", "http", "Snapshot", None, False),
])
def test_late_reply_for_comparison_observations_only(tmp_path, monkeypatch, scenario, operation,
                                                     tool, deadline, succeeds):
    from runner import agent_bridge, relay_run
    from runner.windows_mcp_bridge import GuestHTTP

    monkeypatch.setattr(agent_bridge, "REPO", tmp_path)
    transport = GuestHTTP(r"C:\coil\orca-blackbox-v3-r1", "a" * 32, deadline=100,
                          goal_save=True, scenario=scenario)
    spec = {"op": operation}
    if tool:
        spec["body"] = json.dumps({"method": "tools/call", "params": {"name": tool}})
    clock = 0
    launches = []
    response = transport.root / "0001.json"

    def sleep(seconds):
        nonlocal clock
        clock += seconds
        if clock >= 55 and not response.exists():
            data = base64.b64encode(b'{"received":true}').decode()
            response.write_text(json.dumps({"ok": True, "data_b64": data}))

    def launch(command, timeout_s):
        launches.append(command)
        sleep(2)
        return "123"

    monkeypatch.setattr(agent_bridge, "time", SimpleNamespace(monotonic=lambda: clock, sleep=sleep))
    monkeypatch.setattr(relay_run, "relay_transact", launch)
    if succeeds:
        assert transport.remote(spec, deadline=deadline) == {"received": True}
        assert 55 <= clock < 55.2
    else:
        with pytest.raises(TimeoutError, match="ps_direct_ambiguous_stop"):
            transport.remote(spec, deadline=deadline)
        assert clock == pytest.approx(deadline or 47, abs=.11)
    assert len(launches) == 1
