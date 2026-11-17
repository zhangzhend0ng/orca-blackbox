"""Data-only PS Direct -> guest loopback HTTP transport for original Windows-MCP.

No GUI code or agent decisions run here. Input errors/ambiguous transport stop
the connection; input actions are never retried. This is an isolated probe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from runner.agent_bridge import RelayMailbox, decode_json

TOOLS = frozenset({"Snapshot", "Screenshot", "Click", "Wait", "ControlStatus"})
GUEST_HTTP = r"""
param($sb,$run,$encoded)
$ErrorActionPreference='Stop'
$spec=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded))|ConvertFrom-Json
$root=Join-Path $sb ('artifacts\windows_mcp_runs\'+$run)
$probe=$root
while ($probe -and $probe.Length -ge $sb.Length) {
 if ((Test-Path -LiteralPath $probe) -and ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'link_rejected'}
 $probe=Split-Path $probe -Parent
}
if ($spec.op -eq 'ready') {
 $p=Join-Path $root 'ready.json'
 if(Test-Path -LiteralPath $p){[IO.File]::ReadAllText($p)}else{'{"ready":false}'}
 return
}
if ($spec.op -eq 'done') {
 [IO.File]::WriteAllText((Join-Path $root 'done'),'done')
 return '{"done":true}'
}
if ($spec.op -ne 'http') {throw 'op_rejected'}
$tokenPath=Join-Path $root 'token'
if ((Get-Item -LiteralPath $tokenPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'link_rejected'}
$token=[IO.File]::ReadAllText($tokenPath)
$headers=@{Authorization=('Bearer '+$token);Accept='application/json, text/event-stream';'MCP-Protocol-Version'='2025-06-18'}
$body=[Text.Encoding]::UTF8.GetBytes([string]$spec.body)
if($body.Length -gt 65536){throw 'request_too_large'}
# Use the canonical endpoint: PS 5 strips Authorization on a trailing-slash redirect.
$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18789/mcp' -MaximumRedirection 0 -Method Post -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 18
$text=[string]$r.Content
if($text.Length -gt 3800000){throw 'response_too_large'}
@{status=[int]$r.StatusCode;body=$text}|ConvertTo-Json -Compress
"""


class GuestHTTP(RelayMailbox):
    guest_io = GUEST_HTTP


def validate_request(request, tool_calls):
    if type(request) is not dict or request.get("jsonrpc") != "2.0":
        raise ValueError("invalid_mcp_request")
    method = request.get("method")
    if type(method) is not str or method not in {"initialize", "notifications/initialized", "tools/list", "tools/call", "ping"}:
        raise ValueError("method_rejected")
    if method == "tools/call":
        params = request.get("params")
        if (type(params) is not dict or type(params.get("name")) is not str or params.get("name") not in TOOLS
                or type(params.get("arguments", {})) is not dict or tool_calls >= 20):
            raise ValueError("tool_rejected_or_budget")
    return method


def response_json(body):
    if body.lstrip().startswith("{"):
        return decode_json(body)
    # Stateless MCP emits exactly one JSON-RPC result as an SSE data event.
    events = [line[5:].lstrip() for line in body.splitlines() if line.startswith("data:")]
    if len(events) != 1:
        raise ValueError("unsupported_sse_response")
    return decode_json(events[0])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    args = p.parse_args()
    transport = GuestHTTP(args.guest_root, args.run_id, deadline=time.monotonic()+600)
    calls = 0
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            break
        if len(raw) > 65536:
            raise ValueError("request_too_large")
        request = decode_json(raw)
        method = validate_request(request, calls)
        calls += method == "tools/call"
        result = transport.remote({"op": "http", "body": raw.decode("utf-8")})
        if "id" not in request:
            if result["status"] not in (200, 202, 204):
                raise ValueError("notification_rejected")
            continue
        response = response_json(result["body"])
        if response.get("jsonrpc") != "2.0" or response.get("id") != request["id"]:
            raise ValueError("response_identity")
        if method == "tools/list":
            names = {t["name"] for t in response.get("result", {}).get("tools", [])}
            if names != TOOLS:
                raise ValueError("server_toolset_changed")
        print(json.dumps(response, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
