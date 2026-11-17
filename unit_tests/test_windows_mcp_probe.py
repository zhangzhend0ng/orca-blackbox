"""Probe transport boundaries, independent of Windows/UI/network."""
import pytest

from runner.windows_mcp_bridge import response_json, validate_request


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
