"""Compile and replay the semantic portion of a proven UIA layer-height run."""
import hashlib
import json
from pathlib import Path

from .agent_protocol import LAYER_FIXTURE_SHA256, ProtocolError, valid_run_id
from .native_matrix import UIA_LAYER_SCENARIO
from .native_save_policy import validate_uia_selector
from .native_uia_hybrid import verify_hybrid_trace

RECORDING = Path(__file__).resolve().parents[1] / "contracts/replays/uia_layer.json"
OUTPUT = "$OUTPUT_3MF"
ORDER = ("Snapshot", "Type", "Snapshot", "Shortcut", "Snapshot", "Type", "Click", "Snapshot")


def verify_recipe(recipe):
    if type(recipe) is not dict or set(recipe) != {"schema_version", "scenario", "initial_tab", "fixture_sha256", "source", "steps"}:
        raise ValueError("replay_recipe_schema")
    source = recipe["source"]
    if type(source) is not dict or set(source) != {"run_id", "source_sha", "trace_sha256"}:
        raise ValueError("replay_source_schema")
    valid_run_id(source["run_id"])
    for key in ("source_sha", "trace_sha256"):
        size = 40 if key == "source_sha" else 64
        if type(source[key]) is not str or len(source[key]) != size or any(c not in "0123456789abcdef" for c in source[key]):
            raise ValueError("replay_source_digest")
    if (type(recipe["schema_version"]) is not int or recipe["schema_version"] != 1 or recipe["scenario"] != UIA_LAYER_SCENARIO
            or recipe["initial_tab"] != "Quality" or recipe["fixture_sha256"] != LAYER_FIXTURE_SHA256):
        raise ValueError("replay_recipe_scope")
    steps = recipe["steps"]
    if (type(steps) is not list or len(steps) != len(ORDER)
            or any(type(step) is not dict or set(step) != {"tool", "arguments"} or type(step["arguments"]) is not dict
                   for step in steps)):
        raise ValueError("replay_step_schema")
    if tuple(step["tool"] for step in steps) != ORDER:
        raise ValueError("replay_tool_order")
    for index, step in enumerate(steps):
        tool, args = step["tool"], step["arguments"]
        if tool == "Snapshot":
            if args != {}:
                raise ValueError("replay_snapshot_arguments")
        elif tool == "Shortcut":
            if args != {"shortcut": "ctrl+shift+s"}:
                raise ValueError("replay_shortcut_arguments")
        elif tool == "Type":
            validate_uia_selector(args.get("target"), "EditControl")
            if set(args) != {"target", "text"} or args["text"] != ("0.24" if index == 1 else OUTPUT):
                raise ValueError("replay_value_arguments")
        else:
            validate_uia_selector(args.get("target"), "ButtonControl")
            if set(args) != {"target"}:
                raise ValueError("replay_invoke_arguments")
    return recipe


def read_recipe():
    from .agent_protocol import read_json

    recipe = verify_recipe(read_json(RECORDING))
    canonical = json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return recipe, hashlib.sha256(canonical).hexdigest()


def compile_recipe(raw, *, run_id, source_sha, app_pid, main_hwnd, output_path):
    trace = [json.loads(line) for line in raw.splitlines()]
    if not 1 <= len(trace) <= 40:
        raise ValueError("replay_source_trace_size")
    verify_hybrid_trace(trace, run_id=run_id, app_pid=app_pid, main_hwnd=main_hwnd,
                        output_path=output_path, scenario=UIA_LAYER_SCENARIO,
                        strict_crop_lifetime=any("visual_crop_id" in row["window"] for row in trace))
    actions = []
    for row in trace:
        tool, args = row["tool"], dict(row["arguments"])
        if tool in {"Snapshot", "Screenshot", "Wait", "ControlStatus"}:
            continue
        if args.get("text") == output_path:
            args["text"] = OUTPUT
        actions.append({"tool": tool, "arguments": args})
    if tuple(step["tool"] for step in actions) != ("Type", "Shortcut", "Type", "Click"):
        raise ValueError("replay_source_action_order")
    snapshot = {"tool": "Snapshot", "arguments": {}}
    steps = [snapshot, actions[0], snapshot, actions[1], snapshot, actions[2], actions[3], snapshot]
    return verify_recipe({"schema_version": 1, "scenario": UIA_LAYER_SCENARIO, "initial_tab": "Quality",
                          "fixture_sha256": LAYER_FIXTURE_SHA256, "steps": steps,
                          "source": {"run_id": run_id, "source_sha": source_sha,
                                     "trace_sha256": hashlib.sha256(raw).hexdigest()}})


def executable_steps(recipe, output_path):
    for step in recipe["steps"]:
        args = dict(step["arguments"])
        if args.get("text") == OUTPUT:
            args["text"] = output_path
        yield step["tool"], args


def play(ui, run_id, output_path):
    from .host_guard import in_guest
    from .native_authority_probe import loopback_client
    from runner.windows_mcp_bridge import authority_receipt

    if not in_guest():
        raise PermissionError("replay_guest_only")
    recipe, digest = read_recipe()
    request = loopback_client(ui.artifacts, "native-uia-replay")
    observations = None
    for seq, (tool, args) in enumerate(executable_steps(recipe, output_path), 1):
        ui.guard()
        if seq == 2:
            values = [item.get("value") for item in observations["controls"] if item["target"] == args["target"]]
            if values not in (["0.4"], ["0.40"]):
                raise ProtocolError("replay_layer_precondition")
        if seq == 5:
            ui.wait(lambda: ui.eu.wait_save_dialog(ui.app.pid, timeout_s=.2), 10)
        if seq == 8:
            ui.wait(lambda: ui.wu.user32.GetForegroundWindow() == ui.app.hwnd, 10)
        call = {"jsonrpc": "2.0", "id": seq, "method": "tools/call",
                "params": {"name": tool, "arguments": args}}
        response = request(call)
        receipt = authority_receipt(response, call, run_id, seq)
        if receipt["decision"] != "completed":
            raise ProtocolError("replay_tool_refused:" + receipt["error_code"])
        if tool == "Snapshot":
            observations = json.loads(response["result"]["structuredContent"]["result"])
        if tool == "Type":
            returned = json.loads(response["result"]["structuredContent"]["result"])
            if returned.get("value") != args["text"]:
                raise ProtocolError("replay_value_readback")
    if observations.get("dialog_closed") is not True:
        raise ProtocolError("replay_dialog_not_closed")
    return digest


def verify_replay_trace(trace, run_id, scope, digest):
    recipe, expected = read_recipe()
    if expected != digest or [(r["tool"], r["arguments"]) for r in trace] != list(
            executable_steps(recipe, scope["output_path"])):
        raise ValueError("replay_receipt_recipe_mismatch")
    return verify_hybrid_trace(trace, run_id=run_id, app_pid=scope["app_pid"], main_hwnd=scope["hwnd"],
                               output_path=scope["output_path"], scenario=scope["scenario"],
                               named_crops_only=True, strict_crop_lifetime=True)
