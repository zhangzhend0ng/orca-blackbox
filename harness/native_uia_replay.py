"""Compile and replay bounded recordings from proven native runs."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .agent_protocol import LAYER_FIXTURE_SHA256, ProtocolError, valid_run_id
from .native_matrix import (REPLAY_SOURCES, UIA_CANVAS_SCENARIO, UIA_LAYER_SCENARIO, UIA_PROCESS_COMBO,
    UIA_MIX_RECIPES, UIA_REPLAY_CANVAS, UIA_REPLAY_MIX, UIA_REPLAY_PROCESS, UIA_REPLAY_SAVE,
    UIA_REPLAY_SCENARIO, UIA_SAVE_SCENARIO)
from .native_save_policy import PROCESS_POPUP, validate_input, validate_uia_selector
from .native_uia import verify_uia_save
from .native_uia_hybrid import contains, verify_hybrid_trace, within

RECORDING = Path(__file__).resolve().parents[1] / "contracts/replays/uia_layer.json"
OUTPUT = "$OUTPUT_3MF"
ORDER = ("Snapshot", "Type", "Snapshot", "Shortcut", "Snapshot", "Type", "Click", "Snapshot")
SAVE_ORDER = ("Snapshot", "Type", "Click", "Snapshot")
RECORDINGS = {UIA_REPLAY_SCENARIO: RECORDING, UIA_REPLAY_SAVE: RECORDING.with_name("uia_save.json"),
              UIA_REPLAY_CANVAS: RECORDING.with_name("uia_canvas.json"),
              UIA_REPLAY_PROCESS: RECORDING.with_name("uia_process.json"),
              UIA_REPLAY_MIX: RECORDING.with_name("uia_mix.json")}


def fixture_digest(scenario):
    if scenario == UIA_MIX_RECIPES:
        from .pilot_mix_recipes import FIXTURE_SHA256
        return FIXTURE_SHA256
    return LAYER_FIXTURE_SHA256


def recipe_path(scenario):
    return RECORDINGS[scenario]


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
    scenario = recipe["scenario"]
    if (type(recipe["schema_version"]) is not int or recipe["schema_version"] != 1 or scenario not in REPLAY_SOURCES.values()
            or recipe["initial_tab"] != "Quality" or recipe["fixture_sha256"] != fixture_digest(scenario)):
        raise ValueError("replay_recipe_scope")
    steps = recipe["steps"]
    if scenario == UIA_CANVAS_SCENARIO:
        verify_canvas_steps(steps)
        return recipe
    if scenario == UIA_PROCESS_COMBO:
        verify_process_steps(steps)
        return recipe
    if scenario == UIA_MIX_RECIPES:
        verify_mix_steps(steps)
        return recipe
    order = SAVE_ORDER if scenario == UIA_SAVE_SCENARIO else ORDER
    if (type(steps) is not list or len(steps) != len(order)
            or any(type(step) is not dict or set(step) != {"tool", "arguments"} or type(step["arguments"]) is not dict
                   for step in steps)):
        raise ValueError("replay_step_schema")
    if tuple(step["tool"] for step in steps) != order:
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
            value = "0.24" if scenario == UIA_LAYER_SCENARIO and index == 1 else OUTPUT
            if set(args) != {"target", "text"} or args["text"] != value:
                raise ValueError("replay_value_arguments")
        else:
            validate_uia_selector(args.get("target"), "ButtonControl")
            if set(args) != {"target"}:
                raise ValueError("replay_invoke_arguments")
    return recipe


def verify_visual_steps(steps, scenario):
    if type(steps) is not list or not 8 <= len(steps) <= 40:
        raise ValueError("replay_canvas_size")
    for step in steps:
        if type(step) is not dict or not {"tool", "arguments"} <= step.keys():
            raise ValueError("replay_step_schema")
        tool, args = step["tool"], step["arguments"]
        keys = {"tool", "arguments", "bounds"} if tool == "Screenshot" else {"tool", "arguments"}
        if step.keys() != keys:
            raise ValueError("replay_step_schema")
        validate_input(tool, args, OUTPUT, scenario)
        if tool == "Screenshot":
            bounds = step["bounds"]
            if (set(args) != {"region_name"} or type(bounds) is not list or len(bounds) != 4
                    or any(type(x) is not int for x in bounds) or not within([0, 0, 1920, 1080], bounds)):
                raise ValueError("replay_canvas_observation")
    order = [step["tool"] for step in steps]
    if order[0] != "Snapshot" or order.count("Shortcut") != 1 or tuple(order[-5:]) != ("Shortcut", *SAVE_ORDER):
        raise ValueError("replay_canvas_save_order")
    if steps[-3]["arguments"]["text"] != OUTPUT or "target" not in steps[-2]["arguments"]:
        raise ValueError("replay_canvas_save_arguments")


def verify_process_steps(steps):
    verify_visual_steps(steps, UIA_REPLAY_PROCESS)
    crops, values, menu_clicks = {}, [], 0
    for step in steps[:-5]:
        tool, args = step["tool"], step["arguments"]
        if tool == "Screenshot":
            region = args["region_name"]
            if region not in {"wx_sidebar", PROCESS_POPUP}:
                raise ValueError("replay_process_region")
            crops[region] = step["bounds"]
        elif tool == "Type":
            values.append(Decimal(args["text"]))
            crops.clear()
        elif tool == "Click":
            point = args.get("loc")
            if point is not None:
                popup = crops.get(PROCESS_POPUP)
                if popup is not None:
                    if not contains(popup, point):
                        raise ValueError("replay_process_popup_unobserved")
                    menu_clicks += 1
                elif "wx_sidebar" not in crops or not contains(crops["wx_sidebar"], point):
                    raise ValueError("replay_process_sidebar_unobserved")
            crops.clear()
    if sorted(values) != [Decimal("0.3"), Decimal("30")] or menu_clicks != 1:
        raise ValueError("replay_process_edit_scope")


def verify_mix_steps(steps):
    from .native_mix_uia import OPEN_MIX

    verify_visual_steps(steps, UIA_REPLAY_MIX)
    if any(step["tool"] not in {"Snapshot", "Click"} for step in steps[:-5]):
        raise ValueError("replay_mix_edit_scope")
    if any(first["tool"] == second["tool"] for first, second in zip(steps[:-5], steps[1:-5])):
        raise ValueError("replay_mix_observation_required")
    actions = [step["arguments"] for step in steps[:-5] if step["tool"] == "Click"]
    expected = []
    for mode in ("ratio", "gradient"):
        expected.extend([{"target": OPEN_MIX}, *({"mix_role": role} for role in
                         (mode, "filament1", "filament3", "confirm"))])
    ratio_optional = expected[:1] + expected[2:]
    if actions not in (expected, ratio_optional) or steps[-6]["tool"] != "Snapshot":
        raise ValueError("replay_mix_edit_order")


def verify_canvas_steps(steps):
    verify_visual_steps(steps, UIA_REPLAY_CANVAS)
    numeric = 0
    canvas = point = None
    for step in steps[:-5]:
        tool, args = step["tool"], step["arguments"]
        if tool == "Screenshot" and args["region_name"] == "imgui_canvas":
            canvas = step["bounds"]
        elif tool == "Click":
            point = args.get("loc")
            if point is not None and (canvas is None or not contains(canvas, point)):
                raise ValueError("replay_canvas_point_unobserved")
            canvas = None
        elif tool == "Type":
            if point is None or args.get("loc") != point or Decimal(args["text"]) != Decimal("145.5"):
                raise ValueError("replay_canvas_numeric_precondition")
            numeric += 1
            canvas = point = None
    if numeric != 1:
        raise ValueError("replay_canvas_numeric_count")


def read_recipe(scenario=UIA_REPLAY_SCENARIO):
    from .agent_protocol import read_json

    recipe = verify_recipe(read_json(recipe_path(scenario)))
    if recipe["scenario"] != REPLAY_SOURCES[scenario]:
        raise ValueError("replay_recipe_scenario")
    canonical = json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return recipe, hashlib.sha256(canonical).hexdigest()


def compile_recipe(raw, *, run_id, source_sha, app_pid, main_hwnd, output_path,
                   scenario=UIA_LAYER_SCENARIO, dialog_hwnd=None):
    trace = [json.loads(line) for line in raw.splitlines()]
    if not 1 <= len(trace) <= 40:
        raise ValueError("replay_source_trace_size")
    if scenario == UIA_SAVE_SCENARIO:
        verify_uia_save(trace, run_id=run_id, app_pid=app_pid, dialog_hwnd=dialog_hwnd, output_path=output_path)
    else:
        strict = scenario in {UIA_CANVAS_SCENARIO, UIA_PROCESS_COMBO, UIA_MIX_RECIPES}
        verify_hybrid_trace(trace, run_id=run_id, app_pid=app_pid, main_hwnd=main_hwnd,
                            output_path=output_path, scenario=scenario, named_crops_only=strict,
                            strict_crop_lifetime=strict or any("visual_crop_id" in row["window"] for row in trace),
                            allow_refresh=scenario == UIA_PROCESS_COMBO)
    actions = []
    for row in trace:
        tool, args = row["tool"], dict(row["arguments"])
        if (tool in {"Wait", "ControlStatus"} or row.get("error") or row["window"].get("route") == "uia_popup"
                or (scenario in {UIA_LAYER_SCENARIO, UIA_SAVE_SCENARIO} and tool in {"Snapshot", "Screenshot"})
                or (scenario == UIA_PROCESS_COMBO and tool == "Screenshot" and args.get("region_name") == "imgui_canvas")):
            continue
        if args.get("text") == output_path:
            args["text"] = OUTPUT
        if scenario == UIA_MIX_RECIPES and row["window"].get("route") == "mix_property":
            args = {"mix_role": row["window"]["mix_control"]["role"]}
        if scenario == UIA_MIX_RECIPES and tool == "Snapshot" and actions and actions[-1]["tool"] == "Snapshot":
            continue
        if scenario == UIA_MIX_RECIPES and tool == "Shortcut" and row["window"].get("mix_closed_dialog"):
            actions.append({"tool": "Snapshot", "arguments": {}})
        action = {"tool": tool, "arguments": args}
        if tool == "Screenshot":
            action["bounds"] = row["window"]["visual_region"]
        actions.append(action)
    steps = actions
    snapshot = {"tool": "Snapshot", "arguments": {}}
    if scenario == UIA_LAYER_SCENARIO:
        if tuple(step["tool"] for step in actions) != ("Type", "Shortcut", "Type", "Click"):
            raise ValueError("replay_source_action_order")
        steps = [snapshot, actions[0], snapshot, actions[1], snapshot, actions[2], actions[3], snapshot]
    elif scenario == UIA_SAVE_SCENARIO:
        steps = [snapshot, *actions, snapshot]
    elif scenario in {UIA_PROCESS_COMBO, UIA_MIX_RECIPES}:
        shortcut_index = next(i for i, action in enumerate(actions) if action["tool"] == "Shortcut")
        saved = [action for action in actions[shortcut_index + 1:] if action["tool"] != "Snapshot"]
        steps = [*actions[:shortcut_index + 1], snapshot, *saved, snapshot]
    return verify_recipe({"schema_version": 1, "scenario": scenario, "initial_tab": "Quality",
                          "fixture_sha256": fixture_digest(scenario), "steps": steps,
                          "source": {"run_id": run_id, "source_sha": source_sha,
                                     "trace_sha256": hashlib.sha256(raw).hexdigest()}})


def executable_steps(recipe, output_path):
    for step in recipe["steps"]:
        args = dict(step["arguments"])
        if args.get("text") == OUTPUT:
            args["text"] = output_path
        yield step["tool"], args


def play(ui, run_id, output_path, *, scenario=UIA_REPLAY_SCENARIO):
    from .host_guard import in_guest
    from .native_authority_probe import loopback_client
    from runner.windows_mcp_bridge import authority_receipt

    if not in_guest():
        raise PermissionError("replay_guest_only")
    recipe, digest = read_recipe(scenario)
    request = loopback_client(ui.artifacts, "native-uia-replay")
    observations = None
    dialog_snapshot = len(recipe["steps"]) - 3
    for seq, (tool, args) in enumerate(executable_steps(recipe, output_path), 1):
        ui.guard()
        if seq == 2 and scenario == UIA_REPLAY_SCENARIO:
            values = [item.get("value") for item in observations["controls"] if item["target"] == args["target"]]
            if values not in (["0.4"], ["0.40"]):
                raise ProtocolError("replay_layer_precondition")
        if seq == dialog_snapshot and scenario != UIA_REPLAY_SAVE:
            ui.wait(lambda: ui.eu.wait_save_dialog(ui.app.pid, timeout_s=.2), 10)
        if seq == len(recipe["steps"]):
            ui.wait(lambda: ui.wu.user32.GetForegroundWindow() == ui.app.hwnd, 10)
        call = {"jsonrpc": "2.0", "id": seq, "method": "tools/call",
                "params": {"name": tool, "arguments": args}}
        response = request(call)
        receipt = authority_receipt(response, call, run_id, seq)
        if receipt["decision"] != "completed":
            raise ProtocolError("replay_tool_refused:" + receipt["error_code"])
        structured = response["result"]["structuredContent"]
        if tool == "Snapshot":
            observations = json.loads(structured["result"])
        if tool == "Screenshot" and (structured.get("crop_region") != recipe["steps"][seq - 1]["bounds"]
                                     or structured.get("crop_region_name") != args["region_name"]):
            raise ProtocolError("replay_canvas_layout_changed")
        if tool == "Type" and "target" in args:
            returned = json.loads(structured["result"])
            if returned.get("value") != args["text"]:
                raise ProtocolError("replay_value_readback")
        if tool == "Click" and scenario == UIA_REPLAY_MIX:
            ui.pause(.25)
        elif tool in {"Click", "Type"} and "loc" in args:
            ui.pause(.6)  # Allow the draw loop to render before the next crop.
    if observations.get("dialog_closed") is not True:
        raise ProtocolError("replay_dialog_not_closed")
    return digest


def verify_replay_trace(trace, run_id, scope, digest):
    scenario = scope["scenario"]
    recipe, expected = read_recipe(scenario)
    if expected != digest or [(r["tool"], r["arguments"]) for r in trace] != list(
            executable_steps(recipe, scope["output_path"])):
        raise ValueError("replay_receipt_recipe_mismatch")
    if scenario == UIA_REPLAY_SAVE:
        return verify_uia_save(trace, run_id=run_id, app_pid=scope["app_pid"], dialog_hwnd=scope["dialog_hwnd"],
                               output_path=scope["output_path"])
    if scenario in {UIA_REPLAY_CANVAS, UIA_REPLAY_PROCESS} and any(step.get("bounds") != row["window"].get("visual_region")
                                             for step, row in zip(recipe["steps"], trace)
                                             if step["tool"] == "Screenshot"):
        raise ValueError("replay_canvas_layout_receipt")
    return verify_hybrid_trace(trace, run_id=run_id, app_pid=scope["app_pid"], main_hwnd=scope["hwnd"],
                               output_path=scope["output_path"], scenario=scope["scenario"],
                               named_crops_only=True, strict_crop_lifetime=True)
