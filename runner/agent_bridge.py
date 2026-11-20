"""Run-scoped MCP stdio bridge to an INTERACTIVE guest mailbox.

PS Direct only ferries bounded data; it never launches GUI. Each transaction
runs in a detached, hidden relay child so a wedged session cannot own the relay.
No retry of a write/click: ambiguous transport failure stops this client.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parents[1]
MAX_IMAGE_BYTES = 2_900_000  # Base64 plus metadata fits the 4 MB MCP frame cap.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TOOLS = [
    {"name": "observe", "description": "Observe the assigned app; no input.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "click", "description": "Click a tab using current screenshot client pixels.",
     "inputSchema": {"type": "object", "properties": {
         "observation_id": {"type": "string", "maxLength": 128},
         "x": {"type": "integer", "minimum": 40, "maximum": 312},
         "y": {"type": "integer", "minimum": 31, "maximum": 67}},
         "required": ["observation_id", "x", "y"], "additionalProperties": False}},
    {"name": "finish", "description": "End execution; independent checks decide success.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

_OBS_ID_SCHEMA = {"type": "string", "maxLength": 128}
LAYER_TOOLS = [*TOOLS,
    {"name": "edit", "description": "Edit the owned visible numeric GUI Edit at client pixels and commit.",
     "inputSchema": {"type": "object", "properties": {
         "observation_id": _OBS_ID_SCHEMA, "x": {"type": "integer", "minimum": 0, "maximum": 4095},
         "y": {"type": "integer", "minimum": 0, "maximum": 2159},
         "text": {"type": "string", "maxLength": 7, "pattern": r"^(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?$"}},
         "required": ["observation_id", "x", "y", "text"], "additionalProperties": False}},
    *[{"name": name, "description": description,
       "inputSchema": {"type": "object", "properties": {"observation_id": _OBS_ID_SCHEMA},
                       "required": ["observation_id"], "additionalProperties": False}}
      for name, description in (
          ("slice", "Click the owned GUI Slice button once, then wait up to 180 seconds."),
          ("export_gcode", "Export through the owned GUI dialog to a new fixed run output; no supplied path."))],
]
PROJECT_TOOLS = [*LAYER_TOOLS,
    *[{"name": name, "description": description,
       "inputSchema": {"type": "object", "properties": {"observation_id": _OBS_ID_SCHEMA},
                       "required": ["observation_id"], "additionalProperties": False}}
      for name, description in (
          ("save_project", "Save the current project through its GUI to the new fixed run-owned 3mf; no supplied path."),
          ("reopen_project", "Confirm the old app exits, then reopen that saved project with a new isolated profile."))],
]


def decode_json(raw):
    if not isinstance(raw, (str, bytes)) or len(raw) > 4_000_000:
        raise ValueError("invalid_json_size")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate_json_field")
            result[k] = v
        return result
    def invalid(_):
        raise ValueError("invalid_json_number")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("invalid_json") from exc


def validate_identity(guest_root: str, run_id: str):
    if not re.fullmatch(r"C:\\coil\\orca-blackbox(?:-v3-r[0-9]+)?", guest_root):
        raise ValueError("invalid_guest_checkout")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid_run_id")


# Fixed code: dynamic values are a base64 JSON payload and validated paths only.
_GUEST_IO = r"""
param($sb, $run, $encoded)
$ErrorActionPreference = 'Stop'
$spec = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json
$root = Join-Path $sb ('artifacts\v3\' + $run + '\artifacts')
if (-not (Test-Path -LiteralPath $root)) { return '{"exists":false}' }
$relative = [string]$spec.path
if ($relative -notmatch '^(ready\.json|control_cancel\.json|mailbox/(request|response)_[0-9]{4}\.json|frames/[0-9]{4}\.png)$') { throw 'path_rejected' }
$target = Join-Path $root ($relative -replace '/', '\')
$probe = $root
foreach ($part in ($relative -split '/')) {
  if ((Test-Path -LiteralPath $probe) -and ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'link_rejected' }
  $probe = Join-Path $probe $part
}
if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'link_rejected' }
if ($spec.op -eq 'write') {
  if ($relative -notmatch '^(mailbox/request_[0-9]{4}\.json|control_cancel\.json)$') { throw 'write_rejected' }
  $bytes = [Convert]::FromBase64String([string]$spec.payload)
  if ($bytes.Length -gt 8192) { throw 'request_too_large' }
  $tmp = $target + '.pending'
  $f = [IO.File]::Open($tmp, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
  try { $f.Write($bytes,0,$bytes.Length); $f.Flush() } finally { $f.Dispose() }
  [IO.File]::Move($tmp,$target)
  return '{"written":true}'
}
if (-not (Test-Path -LiteralPath $target)) { return '{"exists":false}' }
$info = Get-Item -LiteralPath $target
if ($info.Length -gt 4000000) { throw 'file_too_large' }
if ($spec.op -eq 'json') {
  if ($relative -notmatch '\.json$' -or $info.Length -gt 65536) { throw 'json_rejected' }
  return (@{exists=$true; text=[IO.File]::ReadAllText($target)} | ConvertTo-Json -Compress)
}
if ($spec.op -ne 'chunk' -or $relative -notmatch '^frames/[0-9]{4}\.png$') { throw 'read_rejected' }
$offset = [long]$spec.offset
if ($offset -lt 0 -or $offset -gt $info.Length) { throw 'offset_rejected' }
$f = [IO.File]::OpenRead($target)
try {
  [void]$f.Seek($offset,[IO.SeekOrigin]::Begin)
  $buffer = New-Object byte[] 196608
  $n = $f.Read($buffer,0,$buffer.Length)
  return (@{exists=$true; length=$info.Length; offset=$offset; payload=[Convert]::ToBase64String($buffer,0,$n)} | ConvertTo-Json -Compress)
} finally { $f.Dispose() }
"""


class RelayMailbox:
    guest_io = _GUEST_IO

    def __init__(self, guest_root: str, run_id: str, *, deadline: float, channel="transport"):
        validate_identity(guest_root, run_id)
        if channel not in {"transport", "control"}:
            raise ValueError("invalid_transport_channel")
        self.guest_root, self.run_id, self.deadline = guest_root, run_id, deadline
        self.root = REPO / "artifacts" / "v3_host" / run_id / channel
        self.root.mkdir(parents=True, exist_ok=False)
        self.index = 0

    def remote(self, spec: dict) -> dict:
        from runner.relay_run import relay_transact
        if time.monotonic() >= self.deadline:
            raise TimeoutError("host_deadline")
        self.index += 1
        script = self.root / f"{self.index:04d}.ps1"
        output = self.root / f"{self.index:04d}.json"
        payload = base64.b64encode(json.dumps(spec, separators=(",", ":")).encode()).decode()
        # All interpolated paths are generated below REPO or strictly allowlisted.
        def quoted(p):
            return "'" + str(p).replace("'", "''") + "'"
        code = ("$ErrorActionPreference='Stop'\n$stage='common'\ntry {\n. " + quoted(REPO / "runner" / "_common.ps1")
                + "\n$stage='invoke'\n$data=Invoke-Command -VMName $vm -Credential $cred -ErrorAction Stop -ScriptBlock {\n"
                + self.guest_io + "\n} -ArgumentList " + quoted(self.guest_root) + "," + quoted(self.run_id)
                + "," + quoted(payload) + "\n$wire=@{ok=$true; data_b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$data))}|ConvertTo-Json -Depth 8 -Compress\n"
                + "} catch { $wire=@{ok=$false;error='ps_direct_failed';stage=$stage;error_type=$_.Exception.GetType().Name;category=$_.CategoryInfo.Category.ToString();error_id=$_.FullyQualifiedErrorId}|ConvertTo-Json -Compress }\n"
                + "[IO.File]::WriteAllText(" + quoted(output) + ",$wire,(New-Object Text.UTF8Encoding($false)))\n")
        with script.open("x", encoding="utf-8") as f:
            f.write(code)
        command = ("Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList "
                   + "@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',"
                   + quoted(script) + ") | Select-Object -ExpandProperty Id")
        launched = relay_transact(command, timeout_s=min(15, max(1, self.deadline-time.monotonic())))
        if not launched or not launched.strip().isdigit():
            raise RuntimeError("relay_launch_unconfirmed")
        cutoff = min(self.deadline, time.monotonic() + 25)
        while not output.exists():
            if time.monotonic() >= cutoff:
                raise TimeoutError("ps_direct_ambiguous_stop")
            time.sleep(.1)
        # The file can briefly exist before the child completes its short write.
        while True:
            try:
                outer = decode_json(output.read_bytes())
                break
            except (ValueError, OSError):
                if time.monotonic() >= cutoff:
                    raise TimeoutError("ps_direct_incomplete_stop")
                time.sleep(.05)
        if type(outer) is not dict or outer.get("ok") is not True or type(outer.get("data_b64")) is not str:
            raise RuntimeError("ps_direct_failed")
        return decode_json(base64.b64decode(outer["data_b64"], validate=True))

    def wait_json(self, relative: str, seconds=45) -> dict:
        cutoff = min(self.deadline, time.monotonic() + seconds)
        while time.monotonic() < cutoff:
            value = self.remote({"op": "json", "path": relative})
            if value.get("exists") is True:
                return decode_json(value["text"])
            time.sleep(.1)
        raise TimeoutError("guest_reply_missing_stop")

    def call(self, request: dict) -> dict:
        seq = request["seq"]
        raw = json.dumps(request, separators=(",", ":")).encode()
        out = self.remote({"op": "write", "path": f"mailbox/request_{seq:04d}.json",
                           "payload": base64.b64encode(raw).decode()})
        if out.get("written") is not True:
            raise RuntimeError("guest_write_unconfirmed_stop")
        method = request["method"]
        timeout = (210 if method in {"slice", "reopen_project"} else
                   150 if method == "save_project" else 90 if method == "export_gcode" else 45)
        return self.wait_json(f"mailbox/response_{seq:04d}.json", seconds=timeout)

    def cancel(self):
        raw = json.dumps({"schema_version": 1, "run_id": self.run_id,
                          "reason": "host_stopped"}).encode()
        out = self.remote({"op": "write", "path": "control_cancel.json",
                           "payload": base64.b64encode(raw).decode()})
        if out.get("written") is not True:
            raise RuntimeError("guest_cancel_unconfirmed")

    def image(self, ref: dict) -> bytes:
        path, length, digest = ref.get("path"), ref.get("size_bytes"), ref.get("sha256")
        if (type(path) is not str or not re.fullmatch(r"frames/[0-9]{4}\.png", path)
                or type(length) is not int or not 1 <= length <= MAX_IMAGE_BYTES
                or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid_guest_image_ref")
        chunks, offset = [], 0
        while offset < length:
            response = self.remote({"op": "chunk", "path": path, "offset": offset})
            if response.get("offset") != offset or response.get("length") != length:
                raise ValueError("image_transport_identity")
            chunk = base64.b64decode(response["payload"], validate=True)
            if not 1 <= len(chunk) <= min(196608, length-offset):
                raise ValueError("image_transport_length")
            chunks.append(chunk)
            offset += len(chunk)
        raw = b"".join(chunks)
        if hashlib.sha256(raw).hexdigest() != digest or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("image_transport_hash")
        return raw


class ScopedTools:
    def __init__(self, mailbox, run_id, case_id="m1_minimal_loop", *, initial_identity=None):
        from harness.agent_protocol import agent_profile
        profile = agent_profile(case_id)
        self.mailbox, self.run_id = mailbox, run_id
        self.case_id = case_id
        self.tool_definitions = [t for t in PROJECT_TOOLS if t["name"] in profile["tools"]]
        self.seq, self.clicks, self.observation_id = 0, 0, None
        self.special_counts = {"edit": 0, "slice": 0, "export_gcode": 0}
        self.special_limit = 2
        self.window_identity = None
        self.window_geometry = None
        if case_id == "m3g_export_3mf":
            if (type(initial_identity) is not dict or set(initial_identity) != {"pid", "hwnd"}
                    or any(type(v) is not int or v <= 0 for v in initial_identity.values())):
                raise ValueError("project_initial_identity")
            self.window_identity = dict(initial_identity)
            self.special_counts.update(save_project=0, reopen_project=0)
            self.special_limit = 1
        self.finished = False

    def call(self, name, args):
        from harness.agent_protocol import validate_request
        if self.finished or self.seq >= 12 or type(args) is not dict:
            raise ValueError("tool_budget_or_state")
        if name in {"observe", "finish"}:
            if args:
                raise ValueError("tool_arguments")
            arguments = {}
        elif name == "click":
            if (set(args) != {"observation_id", "x", "y"} or self.clicks >= 6
                    or args["observation_id"] != self.observation_id or self.observation_id is None
                    or type(args["x"]) is not int or not 40 <= args["x"] <= 312
                    or type(args["y"]) is not int or not 31 <= args["y"] <= 67):
                raise ValueError("click_arguments_or_budget")
            arguments = {"x": args["x"], "y": args["y"]}
        elif name in self.special_counts and self.case_id in {"m3d_param_reslice", "m3g_export_3mf"}:
            fields = {"observation_id", "x", "y", "text"} if name == "edit" else {"observation_id"}
            if (set(args) != fields or args["observation_id"] != self.observation_id
                    or self.observation_id is None or self.special_counts[name] >= self.special_limit):
                raise ValueError("business_tool_arguments_or_budget")
            arguments = {key: args[key] for key in ("x", "y", "text")} if name == "edit" else {}
        else:
            raise ValueError("unregistered_tool")
        if self.seq == 0 and name != "observe":
            raise ValueError("initial_observation_required")
        request = {"schema_version": 1, "run_id": self.run_id, "seq": self.seq + 1,
                   "method": name, "arguments": arguments, "observation_id": self.observation_id}
        validate_request(request, run_id=self.run_id, expected_seq=self.seq + 1,
                         observation_id=self.observation_id, case_id=self.case_id)
        self.seq += 1  # consumed before transport; never re-execute ambiguous input.
        if name == "click":
            self.clicks += 1
        elif name in self.special_counts:
            self.special_counts[name] += 1
        response = self.mailbox.call(request)
        if (type(response) is not dict or response.get("schema_version") != 1
                or response.get("run_id") != self.run_id or response.get("seq") != self.seq
                or response.get("tool") != name or response.get("is_error") is not False
                or response.get("error_code") is not None or response.get("finished") is not (name == "finish")):
            raise ValueError("guest_response_rejected_stop")
        obs = response["observation"]
        if self.case_id == "m3g_export_3mf":
            self._project_observation(response, name)
        if type(obs["id"]) is not str or not 1 <= len(obs["id"]) <= 128:
            raise ValueError("observation_identity")
        self.observation_id = obs["id"]
        self.finished = name == "finish"
        image = self.mailbox.image(obs["image"])
        text = {"observation_id": obs["id"], "width": obs["window"]["width"],
                "height": obs["window"]["height"], "finished": self.finished,
                "image_sha256": obs["image"]["sha256"]}
        return {"content": [{"type": "text", "text": json.dumps(text)},
                            {"type": "image", "mimeType": "image/png",
                             "data": base64.b64encode(image).decode()}], "isError": False}

    def _project_observation(self, response, name):
        if (type(response.get("schema_version")) is not int or type(response.get("seq")) is not int
                or set(response) != {"schema_version", "run_id", "seq", "tool", "is_error", "error_code", "observation", "finished"}):
            raise ValueError("project_response_schema")
        obs = response["observation"]
        if (type(obs) is not dict or set(obs) != {"id", "window", "frames", "image"}
                or obs["id"] != f"{self.run_id}_{self.seq:04d}"):
            raise ValueError("project_observation_identity")
        window = obs["window"]
        if (type(window) is not dict or set(window) != {"pid", "hwnd", "width", "height", "dpi"}
                or any(type(v) is not int or v <= 0 for v in window.values())
                or window["dpi"] != 96 or not 313 <= window["width"] <= 4096
                or not 68 <= window["height"] <= 2160):
            raise ValueError("project_window_identity")
        current = {k: window[k] for k in ("pid", "hwnd")}
        geometry = tuple(window[k] for k in ("width", "height", "dpi"))
        if name != "reopen_project" and current != self.window_identity:
            raise ValueError("project_unexpected_window_change")
        if self.window_geometry is not None and geometry != self.window_geometry:
            raise ValueError("project_unexpected_geometry_change")
        if name == "reopen_project":
            self.window_identity = current
        self.window_geometry = geometry


def serve(tools, source, output):
    initialized, ready = False, False
    for _ in range(24):
        line = source.readline(16385)
        if not line:
            return
        if len(line) > 16384 or not line.endswith("\n"):
            raise ValueError("mcp_frame_limit")
        request = decode_json(line)
        if type(request) is not dict or request.get("jsonrpc") != "2.0":
            raise ValueError("invalid_mcp_request")
        if "id" not in request:
            if request.get("method") != "notifications/initialized" or not initialized or ready:
                raise ValueError("invalid_mcp_notification")
            ready = True
            continue
        ident = request["id"]
        if type(ident) not in (int, str) or len(str(ident)) > 64:
            raise ValueError("invalid_mcp_id")
        method = request.get("method")
        try:
            if method == "initialize":
                params = request.get("params")
                if initialized or type(params) is not dict or type(params.get("protocolVersion")) is not str:
                    raise ValueError("invalid_mcp_initialize")
                initialized = True
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "orca-v3-scoped", "version": "1"}}
            elif method == "tools/list" and ready:
                result = {"tools": tools.tool_definitions}
            elif method == "ping":
                result = {}
            elif method == "tools/call" and ready:
                params = request.get("params")
                if type(params) is not dict or set(params) != {"name", "arguments"}:
                    raise ValueError("invalid_mcp_params")
                result = tools.call(params["name"], params["arguments"])
            else:
                raise ValueError("unknown_mcp_method")
            response = {"jsonrpc": "2.0", "id": ident, "result": result}
        except (ValueError, RuntimeError, OSError, KeyError, TypeError):
            # Stop on first ambiguous tool failure; never issue subsequent input.
            response = {"jsonrpc": "2.0", "id": ident, "error": {
                "code": -32603, "message": "scoped_bridge_stopped"}}
            output.write(json.dumps(response) + "\n")
            output.flush()
            return
        output.write(json.dumps(response, separators=(",", ":")) + "\n")
        output.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--case", default="m1_minimal_loop")
    args = parser.parse_args()
    from harness.agent_protocol import agent_profile
    agent_profile(args.case)
    deadline = time.monotonic()+600
    if args.deadline is not None:
        if not math.isfinite(args.deadline):
            raise ValueError("invalid_host_deadline")
        deadline = min(deadline, args.deadline)
    mailbox = RelayMailbox(args.guest_root, args.run_id, deadline=deadline)
    initial = None
    if args.case == "m3g_export_3mf":
        from harness.agent_session import agent_contract
        from harness.run_verdict import contract_digest
        ready = mailbox.wait_json("ready.json")
        if (ready.get("run_id") != args.run_id or ready.get("case_id") != args.case
                or ready.get("contract_sha256") != contract_digest(agent_contract(args.case))):
            raise ValueError("project_ready_identity")
        initial = {"pid": ready.get("app_pid"), "hwnd": ready.get("hwnd")}
    serve(ScopedTools(mailbox, args.run_id, args.case, initial_identity=initial), sys.stdin, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError):
        print("scoped_bridge_failed", file=sys.stderr)
        raise SystemExit(2)
