"""Guest-only negative MCP probe. Both attempts must be rejected pre-dispatch."""
import json


def verify_responses(responses, run_id):
    if type(responses) is not list or len(responses) != 2:
        raise ValueError("authority_probe_response_count")
    for seq, response in enumerate(responses, 1):
        result = response.get("result", {})
        receipt = result.get("structuredContent", {}).get("authority", {})
        if (result.get("isError") is not True or receipt.get("protocol") != "native-authority-1"
                or receipt.get("run_id") != run_id or receipt.get("seq") != seq
                or receipt.get("tool") != "Click" or receipt.get("decision") != "fatal"
                or receipt.get("dispatched") is not False):
            raise ValueError("authority_probe_not_rejected")
    if responses[0]["result"]["structuredContent"]["authority"].get("error_code") != "native_target_not_owned":
        raise ValueError("authority_probe_wrong_first_refusal")
    if responses[1]["result"]["structuredContent"]["authority"].get("error_code") != "native_authority_already_revoked":
        raise ValueError("authority_probe_stop_latch_not_proven")
    return {"fatal_latched": True, "subsequent_input_dispatched": False,
            "attempts": 2, "model_used": False, "business_verified": False}


def run_probe(root, run_id, app_pid, main_hwnd):
    from . import host_guard, winutil as wu
    from .canvas_input import collect_window_evidence
    if not host_guard.in_guest():
        raise PermissionError("authority_probe_guest_only")
    # Locate an actually foreign window by read-only hit testing; no guessed
    # location is ever dispatched to an original input tool in a passing probe.
    foreign = None
    for y in (1070, 1050, 5):
        for x in (10, 300, 960, 1800):
            hwnd = wu.window_from_screen_point(x, y)
            if hwnd and wu._window_pid(hwnd) != app_pid:
                foreign = [x, y]
                break
        if foreign is not None:
            break
    if foreign is None:
        raise ValueError("authority_probe_foreign_point_not_found")
    evidence = collect_window_evidence(run_id, app_pid, main_hwnd)
    main = next(w for w in evidence["windows"] if w["hwnd"] == main_hwnd)
    rect = main["rect"]
    owned = [(max(0, rect[0])+min(1919, rect[2]-1))//2,
             (max(0, rect[1])+min(1079, rect[3]-1))//2]
    request = loopback_client(root, "owned-authority-negative-probe")
    responses = [request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "Click", "arguments": {"loc": foreign}}})]
    if not (root / "input_revoked").exists() or not (root / "authority_abort.json").exists():
        raise ValueError("authority_probe_durable_latch_missing")
    if (wu._window_pid(wu.user32.GetForegroundWindow()) != app_pid
            or wu._window_pid(wu.window_from_screen_point(*owned)) != app_pid):
        raise ValueError("authority_probe_second_point_not_owned")
    responses.append(request({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "Click", "arguments": {"loc": owned}}}))
    summary = verify_responses(responses, run_id)
    return {"run_id": run_id, **summary, "foreign_loc": foreign, "owned_loc": owned,
            "responses": responses}


def loopback_client(root, name):
    from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
    from runner.windows_mcp_bridge import response_json

    headers = {"Authorization": "Bearer "+(root/"token").read_text(),
               "Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "MCP-Protocol-Version": "2025-06-18"}

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("native_loopback_redirect_rejected")

    opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(body, *, timeout=15):
        with opener.open(Request("http://127.0.0.1:18789/mcp", data=json.dumps(body).encode(),
                                 headers=headers), timeout=timeout) as response:
            reply = response_json(response.read(2_000_000).decode("utf-8"))
        if reply.get("jsonrpc") != "2.0" or reply.get("id") != body["id"]:
            raise ValueError("native_loopback_response_identity")
        return reply

    reply = request({"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": name, "version": "1"}}})
    if "result" not in reply:
        raise ValueError("native_loopback_initialization")
    return request
