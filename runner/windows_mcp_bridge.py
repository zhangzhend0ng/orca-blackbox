"""Data-only PS Direct -> guest loopback HTTP transport for original Windows-MCP.

No GUI code or agent decisions run here. Input errors/ambiguous transport stop
the connection; input actions are never retried. This is an isolated probe.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from runner.agent_bridge import RelayMailbox, decode_json

TOOLS = frozenset({"Snapshot", "Screenshot", "Click", "Wait", "ControlStatus"})
ZCODE_INLINE_IMAGE_LIMIT = 200 * 1024
ZCODE_INLINE_TARGET = 180 * 1024
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
 }else{
  $task = if ($spec.require_suite_result) { Get-ScheduledTask suite -ErrorAction SilentlyContinue }
  if ($task -and $task.State -eq 'Ready' -and
      (Test-Path -LiteralPath 'C:\coil\run_suite.ps1') -and
      [IO.File]::ReadAllText('C:\coil\run_suite.ps1').Contains("--run-id '$run'")) {
   '{"suite_exited_without_result":true}'
  }else{'{"pending":true}'}
 }
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


def validate_request(request, tool_calls, *, goal_save=False, scenario="base"):
    if type(request) is not dict or request.get("jsonrpc") != "2.0":
        raise ValueError("invalid_mcp_request")
    method = request.get("method")
    if type(method) is not str or method not in {"initialize", "notifications/initialized", "tools/list", "tools/call", "ping"}:
        raise ValueError("method_rejected")
    if method == "tools/call":
        params = request.get("params")
        from harness.native_save_policy import native_tools
        allowed = native_tools(scenario) if goal_save else TOOLS
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


def authority_receipt(response, request, run_id, seq):
    """Only the authenticated guest response supplies an authority decision."""
    result = response.get("result", {})
    receipt = result.get("structuredContent", {}).get("authority")
    tool = request["params"]["name"]
    if (type(receipt) is not dict or receipt.get("protocol") != "native-authority-1"
            or receipt.get("run_id") != run_id or type(receipt.get("seq")) is not int
            or receipt["seq"] != seq or receipt.get("tool") != tool
            or receipt.get("decision") not in {"completed", "recoverable", "fatal"}
            or type(receipt.get("dispatched")) is not bool):
        raise ValueError("native_authority_receipt_missing_or_mismatched")
    completed = receipt["decision"] == "completed"
    if (completed and (receipt["dispatched"] is not True or result.get("isError", False) is not False)
            or not completed and result.get("isError") is not True
            or receipt["decision"] == "recoverable" and receipt["dispatched"] is not False):
        raise ValueError("native_authority_result_conflict")
    return receipt


def inline_canvas_observations(result, expected_size=(1920, 1080)):
    """Fit oversized frames under ZCode's inline limit at unchanged coordinates."""
    changes = []
    for item in result.get("content", []):
        if item.get("type") != "image":
            continue
        data = item["data"]
        if len(data) <= ZCODE_INLINE_IMAGE_LIMIT:
            continue
        from PIL import Image
        if len(data) > 3_000_000 or item["mimeType"] not in {"image/png", "image/jpeg"}:
            raise ValueError("native_observation_image_size_or_format")
        with Image.open(io.BytesIO(base64.b64decode(data, validate=True)), formats=["PNG", "JPEG"]) as source:
            if source.size != expected_size:
                raise ValueError("native_observation_image_geometry")
            frame = source.convert("RGB")
        for quality in (88, 78, 68, 52):
            out = io.BytesIO()
            frame.save(out, format="JPEG", optimize=True, quality=quality)
            encoded = base64.b64encode(out.getvalue()).decode("ascii")
            if len(encoded) <= ZCODE_INLINE_TARGET:
                changes.append({"before_base64": len(data), "after_base64": len(encoded), "mime_type": "image/jpeg"})
                item.update(data=encoded, mimeType="image/jpeg")
                break
        else:
            raise ValueError("native_observation_inline_limit")
    return changes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    p.add_argument("--goal-save", action="store_true")
    p.add_argument("--authority-log", type=Path)
    from harness.native_matrix import CANVAS_REPLACE_SCENARIOS, GENERALIZATION, SCENARIOS, UIA_HYBRID_SCENARIOS
    p.add_argument("--scenario", choices=tuple(SCENARIOS), default="base")
    args = p.parse_args()
    transport = GuestHTTP(args.guest_root, args.run_id, deadline=time.monotonic()+900, goal_save=args.goal_save)
    calls = 0
    terminal = False
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            break
        if len(raw) > 65536:
            raise ValueError("request_too_large")
        request = decode_json(raw)
        method = validate_request(request, calls, goal_save=args.goal_save, scenario=args.scenario)
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
            from harness.native_save_policy import native_tools
            names = {t["name"] for t in response.get("result", {}).get("tools", [])}
            if names != (native_tools(args.scenario) if args.goal_save else TOOLS):
                raise ValueError("server_toolset_changed")
            if args.goal_save:
                from harness.native_save_policy import scoped_tool_schemas
                output = str(Path(args.guest_root)/"artifacts/v3"/args.run_id/"artifacts/projects/0001.3mf")
                response["result"]["tools"] = scoped_tool_schemas(response["result"]["tools"], output, scenario=args.scenario)
        if method == "tools/call" and args.authority_log is not None:
            receipt = authority_receipt(response, request, args.run_id, calls)
            sidecar = {"request_id": request["id"], "authority": receipt}
            if (args.scenario in CANVAS_REPLACE_SCENARIOS | set(GENERALIZATION) | UIA_HYBRID_SCENARIOS
                    and receipt["decision"] == "completed"
                    and receipt["tool"] in {"Screenshot", "Snapshot"}):
                size = (1920, 1080)
                if args.scenario in UIA_HYBRID_SCENARIOS and receipt["tool"] == "Screenshot":
                    arguments = request["params"]["arguments"]
                    crop = arguments.get("region")
                    popup = False
                    if "region_name" in arguments:
                        structured = response["result"]["structuredContent"]
                        popup = structured.get("popup_observation") is True
                        if popup and ("crop_region" in structured or any(item.get("type") == "image"
                                                                         for item in response["result"].get("content", []))):
                            raise ValueError("native_observation_popup_image_conflict")
                        if not popup and structured.get("crop_region_name") != arguments["region_name"]:
                            raise ValueError("native_observation_crop_identity")
                        crop = structured.get("crop_region")
                    if not popup:
                        if (type(crop) is not list or len(crop) != 4 or any(type(side) is not int for side in crop)
                                or not (0 <= crop[0] < crop[2] <= 1920 and 0 <= crop[1] < crop[3] <= 1080)
                                or crop == [0, 0, 1920, 1080]):
                            raise ValueError("native_observation_image_geometry")
                        left, top, right, bottom = crop
                        size = (right - left, bottom - top)
                changes = inline_canvas_observations(response["result"], size)
                if changes:
                    sidecar["observation_transcode"] = changes
            # Written completely before forwarding this response. The agent has
            # no filesystem tool and cannot create its own authority receipts.
            with args.authority_log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(sidecar)+"\n")
                stream.flush()
            terminal = args.scenario.startswith("uia_") and receipt["decision"] == "fatal"
        print(json.dumps(response, separators=(",", ":")), flush=True)
        if terminal:
            return


if __name__ == "__main__":
    main()
