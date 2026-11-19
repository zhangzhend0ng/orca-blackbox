"""Compile and replay bounded recordings from proven native runs."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .agent_protocol import LAYER_FIXTURE_SHA256, ProtocolError, valid_run_id
from .native_matrix import (REPLAY_SOURCES, UIA_CANVAS_SCENARIO, UIA_LAYER_SCENARIO, UIA_PROCESS_COMBO,
    UIA_MIX_RECIPES, UIA_MOVE_LAYER, UIA_PROCESS_SCENARIOS, UIA_QUALITY_ENUMS, UIA_REPLAY_CANVAS,
    UIA_REPLAY_ENUMS, UIA_REPLAY_MIX, UIA_REPLAY_MOVE_LAYER, UIA_REPLAY_PROCESS, UIA_REPLAY_SAVE,
    UIA_REPLAY_SCENARIO, UIA_SAVE_SCENARIO)
from .native_save_policy import PROCESS_POPUP, validate_input, validate_uia_selector
from .native_pairwise import CONFIG_CASES, PAIR_CASES, PAIR_ENUM_CASES, check_config_snapshot, check_live, compile_pair
from .native_uia import verify_uia_save
from .native_uia_hybrid import ENUM_READBACK_VALUES, contains, new_enum_readback, verify_hybrid_trace, within

RECORDING = Path(__file__).resolve().parents[1] / "contracts/replays/uia_layer.json"
OUTPUT = "$OUTPUT_3MF"
ORDER = ("Snapshot", "Type", "Snapshot", "Shortcut", "Snapshot", "Type", "Click", "Snapshot")
SAVE_ORDER = ("Snapshot", "Type", "Click", "Snapshot")
RECORDINGS = {UIA_REPLAY_SCENARIO: RECORDING, UIA_REPLAY_SAVE: RECORDING.with_name("uia_save.json"),
              UIA_REPLAY_CANVAS: RECORDING.with_name("uia_canvas.json"),
              UIA_REPLAY_PROCESS: RECORDING.with_name("uia_process.json"),
              UIA_REPLAY_MIX: RECORDING.with_name("uia_mix.json"),
              UIA_REPLAY_ENUMS: RECORDING.with_name("uia_enums.json"),
              UIA_REPLAY_MOVE_LAYER: RECORDING.with_name("uia_move_layer.json")}


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
    if scenario in {UIA_CANVAS_SCENARIO, UIA_MOVE_LAYER}:
        verify_canvas_steps(steps, UIA_REPLAY_MOVE_LAYER if scenario == UIA_MOVE_LAYER else UIA_REPLAY_CANVAS)
        return recipe
    if scenario in {UIA_PROCESS_COMBO, UIA_QUALITY_ENUMS}:
        verify_process_steps(steps, UIA_REPLAY_ENUMS if scenario == UIA_QUALITY_ENUMS else UIA_REPLAY_PROCESS)
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
    if type(steps) is not list or not (6 if scenario in CONFIG_CASES else 8) <= len(steps) <= 40:
        raise ValueError("replay_canvas_size")
    for step in steps:
        if type(step) is not dict or not {"tool", "arguments"} <= step.keys():
            raise ValueError("replay_step_schema")
        tool, args = step["tool"], step["arguments"]
        keys = {"tool", "arguments", "bounds"} if tool == "Screenshot" else {"tool", "arguments"}
        if scenario in PAIR_ENUM_CASES | {UIA_REPLAY_ENUMS} and tool == "Snapshot" and "process_value" in step:
            if step["process_value"] not in ENUM_READBACK_VALUES:
                raise ValueError("replay_process_value")
            keys.add("process_value")
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


def verify_process_steps(steps, scenario=UIA_REPLAY_PROCESS):
    verify_visual_steps(steps, scenario)
    enum_replay = scenario == UIA_REPLAY_ENUMS
    crops, values, menu_clicks = {}, [], 0
    snapshot_observed = needs_readback = needs_viewport_snapshot = False
    readbacks = set()
    for step in steps[:-5]:
        tool, args = step["tool"], step["arguments"]
        if needs_viewport_snapshot and tool not in {"Snapshot", "Wait"}:
            raise ValueError("replay_process_viewport_needs_snapshot")
        if tool == "Snapshot":
            snapshot_observed = True
            needs_viewport_snapshot = False
            if "process_value" in step:
                if not needs_readback or step["process_value"] in readbacks:
                    raise ValueError("replay_process_readback_order")
                readbacks.add(step["process_value"])
                needs_readback = False
        elif tool == "Screenshot":
            region = args["region_name"]
            if region not in {"wx_sidebar", PROCESS_POPUP}:
                raise ValueError("replay_process_region")
            crops[region] = step["bounds"]
            snapshot_observed = False
        elif tool == "Type":
            values.append(Decimal(args["text"]))
            crops.clear()
        elif tool == "Click":
            navigates = "process_group" in args
            if needs_readback and not navigates:
                raise ValueError("replay_process_readback_missing")
            if navigates:
                if not snapshot_observed:
                    raise ValueError("replay_process_viewport_unobserved")
                needs_viewport_snapshot = True
            point = args.get("loc")
            if point is not None:
                popup = crops.get(PROCESS_POPUP)
                if popup is not None:
                    if not contains(popup, point):
                        raise ValueError("replay_process_popup_unobserved")
                    menu_clicks += 1
                    needs_readback = enum_replay
                elif "wx_sidebar" not in crops or not contains(crops["wx_sidebar"], point):
                    raise ValueError("replay_process_sidebar_unobserved")
            crops.clear()
            snapshot_observed = False
    if needs_viewport_snapshot or (enum_replay and (needs_readback or readbacks != ENUM_READBACK_VALUES)):
        raise ValueError("replay_process_readback_missing")
    if enum_replay and any("process_value" in step for step in steps[-5:]):
        raise ValueError("replay_process_readback_order")
    expected_values, expected_clicks = ([], 2) if enum_replay else ([Decimal("0.3"), Decimal("30")], 1)
    if sorted(values) != expected_values or menu_clicks != expected_clicks:
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


def verify_canvas_steps(steps, scenario=UIA_REPLAY_CANVAS):
    verify_visual_steps(steps, scenario)
    numeric, layer = 0, 0
    canvas = sidebar = point = None
    for step in steps[:-5]:
        tool, args = step["tool"], step["arguments"]
        if tool == "Screenshot":
            if args["region_name"] == "imgui_canvas":
                canvas = step["bounds"]
            elif scenario == UIA_REPLAY_MOVE_LAYER and args["region_name"] == "wx_sidebar":
                sidebar = step["bounds"]
        elif tool == "Click":
            point = args.get("loc")
            if point is not None and not (canvas is not None and contains(canvas, point)):
                if sidebar is None or not contains(sidebar, point):
                    raise ValueError("replay_canvas_point_unobserved")
                point = None
            canvas = sidebar = None
        elif tool == "Type":
            if scenario == UIA_REPLAY_MOVE_LAYER and "target" in args and args["text"] == "0.24":
                layer += 1
            elif point is None or args.get("loc") != point or Decimal(args["text"]) != Decimal("145.5"):
                raise ValueError("replay_canvas_numeric_precondition")
            else:
                numeric += 1
            canvas = sidebar = point = None
    if numeric != 1 or layer != (scenario == UIA_REPLAY_MOVE_LAYER):
        raise ValueError("replay_canvas_numeric_count")


def read_recipe(scenario=UIA_REPLAY_SCENARIO):
    from .agent_protocol import read_json

    if scenario in PAIR_CASES:
        recipe = compile_pair(scenario)
    else:
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
        strict = scenario in {UIA_CANVAS_SCENARIO, UIA_PROCESS_COMBO, UIA_MIX_RECIPES, UIA_MOVE_LAYER, UIA_QUALITY_ENUMS}
        verify_hybrid_trace(trace, run_id=run_id, app_pid=app_pid, main_hwnd=main_hwnd,
                            output_path=output_path, scenario=scenario, named_crops_only=strict,
                            strict_crop_lifetime=strict or any("visual_crop_id" in row["window"] for row in trace),
                            allow_refresh=scenario in UIA_PROCESS_SCENARIOS | {UIA_MOVE_LAYER})
    actions = []
    save_started = False
    needs_readback = False
    readbacks = set()
    for row in trace:
        tool, args = row["tool"], dict(row["arguments"])
        if (tool == "ControlStatus" or row.get("error") or row["window"].get("route") == "uia_popup"
                or (tool == "Wait" and (scenario != UIA_QUALITY_ENUMS or save_started))
                or (scenario in {UIA_LAYER_SCENARIO, UIA_SAVE_SCENARIO} and tool in {"Snapshot", "Screenshot"})
                or (scenario in UIA_PROCESS_SCENARIOS and tool == "Screenshot" and args.get("region_name") == "imgui_canvas")):
            continue
        if tool == "Shortcut":
            save_started = True
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
        if scenario == UIA_QUALITY_ENUMS:
            if tool == "Click" and row["window"].get("route") == "process_popup_visual":
                needs_readback = True
            elif tool == "Snapshot" and needs_readback:
                value = new_enum_readback(row["window"].get("process_values", []), readbacks)
                if value is not None:
                    action["process_value"] = value
                    readbacks.add(value)
                    needs_readback = False
        actions.append(action)
    steps = actions
    snapshot = {"tool": "Snapshot", "arguments": {}}
    if scenario == UIA_LAYER_SCENARIO:
        if tuple(step["tool"] for step in actions) != ("Type", "Shortcut", "Type", "Click"):
            raise ValueError("replay_source_action_order")
        steps = [snapshot, actions[0], snapshot, actions[1], snapshot, actions[2], actions[3], snapshot]
    elif scenario == UIA_SAVE_SCENARIO:
        steps = [snapshot, *actions, snapshot]
    elif scenario in UIA_PROCESS_SCENARIOS | {UIA_MIX_RECIPES, UIA_MOVE_LAYER}:
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


def play(ui, run_id, output_path, *, scenario=UIA_REPLAY_SCENARIO, report=None):
    from .host_guard import in_guest
    from .native_authority_probe import loopback_client
    from runner.windows_mcp_bridge import authority_receipt

    if not in_guest():
        raise PermissionError("replay_guest_only")
    recipe, digest = read_recipe(scenario)
    enum_replay = scenario in PAIR_ENUM_CASES | {UIA_REPLAY_ENUMS}
    segments = {seq: segment for segment in recipe.get("segments", ())
                for seq in range(segment["first"], segment["last"] + 1)}
    request = loopback_client(ui.artifacts, "native-uia-replay")
    observations = None
    popup_open = False
    dialog_snapshot = len(recipe["steps"]) - 3
    for seq, (tool, args) in enumerate(executable_steps(recipe, output_path), 1):
        step = recipe["steps"][seq - 1]
        segment = segments.get(seq)
        if report is not None and (segments or scenario in CONFIG_CASES):
            report["replay_cursor"] = {"step": seq, "tool": tool,
                                       "operation": segment["operation"] if segment else
                                       "checkpoint" if seq in recipe.get("checkpoints", {}) else "save"}
        ui.guard()
        if seq == 2 and scenario == UIA_REPLAY_SCENARIO:
            values = [item.get("value") for item in observations["controls"] if item["target"] == args["target"]]
            if values not in (["0.4"], ["0.40"]):
                raise ProtocolError("replay_layer_precondition")
        if seq == dialog_snapshot and scenario != UIA_REPLAY_SAVE:
            ui.wait(lambda: ui.eu.wait_save_dialog(ui.app.pid, timeout_s=.2), 10)
        if seq == len(recipe["steps"]):
            ui.wait(lambda: ui.wu.user32.GetForegroundWindow() == ui.app.hwnd, 10)
        if enum_replay and tool == "Screenshot" and args["region_name"] == PROCESS_POPUP:
            ui.wait(lambda: ui.wu.user32.GetForegroundWindow() not in (0, ui.app.hwnd), 5)
        call = {"jsonrpc": "2.0", "id": seq, "method": "tools/call",
                "params": {"name": tool, "arguments": args}}
        response = request(call, timeout=25) if "process_group" in args else request(call)
        receipt = authority_receipt(response, call, run_id, seq)
        if receipt["decision"] != "completed":
            raise ProtocolError("replay_tool_refused:" + receipt["error_code"])
        structured = response["result"]["structuredContent"]
        if tool == "Snapshot":
            observations = json.loads(structured["result"])
            checkpoint = recipe.get("checkpoints", {}).get(seq)
            if checkpoint:
                check_config_snapshot(checkpoint, observations, live=True)
            if "process_value" in step and step["process_value"] not in observations.get("process_values", []):
                raise ProtocolError("replay_process_value_readback")
            if segment and seq in {segment["first"], segment["last"]}:
                check_live(segment, seq, observations, recipe["steps"])
        if tool == "Screenshot" and (structured.get("crop_region") != step["bounds"]
                                     or structured.get("crop_region_name") != args["region_name"]):
            raise ProtocolError("replay_canvas_layout_changed")
        if enum_replay and tool == "Screenshot" and args["region_name"] == PROCESS_POPUP:
            popup_open = True
        if tool == "Type" and "target" in args:
            returned = json.loads(structured["result"])
            if returned.get("value") != args["text"]:
                raise ProtocolError("replay_value_readback")
        if tool == "Click" and scenario == UIA_REPLAY_MIX:
            ui.pause(.25)
        elif tool in {"Click", "Type"} and "loc" in args:
            ui.pause(.6)  # Allow the draw loop to render before the next crop.
            if popup_open:
                ui.wait(lambda: ui.wu.user32.GetForegroundWindow() == ui.app.hwnd, 10)
                popup_open = False
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
    if scenario in (PAIR_CASES.keys() | {UIA_REPLAY_CANVAS, UIA_REPLAY_PROCESS, UIA_REPLAY_ENUMS, UIA_REPLAY_MOVE_LAYER}) and any(step.get("bounds") != row["window"].get("visual_region")
                                             for step, row in zip(recipe["steps"], trace)
                                             if step["tool"] == "Screenshot"):
        raise ValueError("replay_canvas_layout_receipt")
    if scenario in PAIR_ENUM_CASES | {UIA_REPLAY_ENUMS} and any(step["process_value"] not in row["window"].get("process_values", ())
                                            for step, row in zip(recipe["steps"], trace) if "process_value" in step):
        raise ValueError("replay_process_value_readback")
    for seq, checkpoint in recipe.get("checkpoints", {}).items():
        check_config_snapshot(checkpoint, trace[seq - 1]["window"], live=False)
    return verify_hybrid_trace(trace, run_id=run_id, app_pid=scope["app_pid"], main_hwnd=scope["hwnd"],
                               output_path=scope["output_path"], scenario=scope["scenario"],
                               named_crops_only=True, strict_crop_lifetime=True)
