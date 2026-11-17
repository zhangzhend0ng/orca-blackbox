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
$root=if($spec.goal_save){Join-Path $sb ('artifacts\v3\'+$run+'\artifacts')}else{Join-Path $sb ('artifacts\windows_mcp_runs\'+$run)}
$probe=$root
while ($probe -and $probe.Length -ge $sb.Length) {
 if ((Test-Path -LiteralPath $probe) -and ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'link_rejected'}
 $probe=Split-Path $probe -Parent
}
if ($spec.op -eq 'ready') {
 $p=Join-Path $root 'ready.json'
 if(Test-Path -LiteralPath $p){
  $r=[IO.File]::ReadAllText($p)|ConvertFrom-Json
  if($spec.goal_save){
   $parent=Split-Path $root -Parent
   $m=[IO.File]::ReadAllText((Join-Path $parent 'manifest.json'))|ConvertFrom-Json
   $c=[IO.File]::ReadAllText((Join-Path $parent 'contract.json'))|ConvertFrom-Json
   $now=([DateTime]::UtcNow.Ticks-621355968000000000)*100
   $remaining=[Math]::Max(0,([double]$m.started_at_ns/1e9)+[double]$c.limits.timeout_s-([double]$now/1e9))
   $r|Add-Member -NotePropertyName remaining_s -NotePropertyValue $remaining
  }
  $r|ConvertTo-Json -Depth 8 -Compress
 }else{'{"ready":false}'}
 return
}
if($spec.op -eq 'cancel' -and $spec.goal_save){
 $file=Join-Path $root 'control_cancel.json'
 $now=([DateTime]::UtcNow.Ticks-621355968000000000)*100
 $body=@{reason='host_stop';revoked_at_ns=$now;run_id=$run}|ConvertTo-Json -Compress
 $f=[IO.File]::Open($file,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$bytes=[Text.Encoding]::UTF8.GetBytes($body);$f.Write($bytes,0,$bytes.Length);$f.Flush()}finally{$f.Dispose()}
 @{cancelled=$true;revoked_at_ns=$now}|ConvertTo-Json -Compress
 return
}
if ($spec.op -eq 'done') {
 if($spec.goal_save){
  $file=Join-Path $root 'host_done.json'
  if(Test-Path -LiteralPath $file){throw 'done_already_written'}
  $tmp=$file+'.pending'
  $bytes=[Text.Encoding]::UTF8.GetBytes(($spec.receipt|ConvertTo-Json -Depth 8 -Compress))
  $f=[IO.File]::Open($tmp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{$f.Write($bytes,0,$bytes.Length);$f.Flush()}finally{$f.Dispose()}
  [IO.File]::Move($tmp,$file)
  return '{"done":true}'
 }
 [IO.File]::WriteAllText((Join-Path $root 'done'),'done')
 return '{"done":true}'
}
if($spec.op -eq 'result' -and $spec.goal_save){
 $p=Join-Path (Split-Path $root -Parent) 'result.json'
 if(Test-Path -LiteralPath $p){
  try{$value=[IO.File]::ReadAllText($p);$value|ConvertFrom-Json -ErrorAction Stop|Out-Null;$value}catch{'{"pending":true}'}
 }else{'{"pending":true}'}
 return
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
$utf8=New-Object Text.UTF8Encoding($false,$true)
$text=$utf8.GetString($r.RawContentStream.ToArray())
if($text.Length -gt 3800000){throw 'response_too_large'}
@{status=[int]$r.StatusCode;body=$text}|ConvertTo-Json -Compress
"""


class GuestHTTP(RelayMailbox):
    guest_io = GUEST_HTTP

    def __init__(self, *args, goal_save=False, **kwargs):
        self.goal_save = goal_save
        super().__init__(*args, **kwargs)

    def remote(self, spec):
        return super().remote({**spec, "goal_save": self.goal_save})


def validate_request(request, tool_calls, *, goal_save=False):
    if type(request) is not dict or request.get("jsonrpc") != "2.0":
        raise ValueError("invalid_mcp_request")
    method = request.get("method")
    if type(method) is not str or method not in {"initialize", "notifications/initialized", "tools/list", "tools/call", "ping"}:
        raise ValueError("method_rejected")
    if method == "tools/call":
        params = request.get("params")
        from harness.native_save_policy import NATIVE_TOOLS
        allowed = NATIVE_TOOLS if goal_save else TOOLS
        if (type(params) is not dict or type(params.get("name")) is not str or params.get("name") not in allowed
                or type(params.get("arguments", {})) is not dict or tool_calls >= (40 if goal_save else 20)):
            raise ValueError("tool_rejected_or_budget")
    return method


def response_json(body):
    if body.lstrip().startswith("{"):
        return decode_json(body)
    # Stateless MCP emits exactly one JSON-RPC result as an SSE data event.
    # SSE is framed by ASCII LF. str.splitlines also splits legal JSON U+0085,
    # U+2028/U+2029 inside strings and can truncate a real UI tree response.
    events = [line[5:].lstrip(" ").rstrip("\r") for line in body.split("\n") if line.startswith("data:")]
    if len(events) != 1:
        raise ValueError("unsupported_sse_response")
    return decode_json(events[0])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    p.add_argument("--goal-save", action="store_true")
    args = p.parse_args()
    transport = GuestHTTP(args.guest_root, args.run_id, deadline=time.monotonic()+900, goal_save=args.goal_save)
    calls = 0
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            break
        if len(raw) > 65536:
            raise ValueError("request_too_large")
        request = decode_json(raw)
        method = validate_request(request, calls, goal_save=args.goal_save)
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
            from harness.native_save_policy import NATIVE_TOOLS
            names = {t["name"] for t in response.get("result", {}).get("tools", [])}
            if names != (NATIVE_TOOLS if args.goal_save else TOOLS):
                raise ValueError("server_toolset_changed")
            if args.goal_save:
                from harness.native_save_policy import scoped_tool_schemas
                output = str(Path(args.guest_root)/"artifacts/v3"/args.run_id/"artifacts/projects/0001.3mf")
                response["result"]["tools"] = scoped_tool_schemas(response["result"]["tools"], output)
        print(json.dumps(response, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
