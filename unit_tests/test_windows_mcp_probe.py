"""Probe transport boundaries, independent of Windows/UI/network."""
import pytest
import json

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
