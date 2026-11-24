"""Data-only authority policy; no coordinates or business action sequence."""
from __future__ import annotations

import ctypes
import math
import re
from copy import deepcopy
from ctypes import wintypes
from .agent_protocol import MAINTENANCE_TRIALS
from .native_diagnostic_recovery import COMMIT_SCENARIO
from .native_matrix import (CANVAS_REPLACE_SCENARIOS, CANVAS_SCENARIOS, SAVE_CLEAR_SCENARIOS, POPUP_BIND_SCENARIOS,
    UIA_ENUM_SCENARIOS, UIA_HYBRID_SCENARIOS, UIA_MIX_SCENARIOS, UIA_PROCESS_SCENARIOS, UIA_REPLAY_CANVAS, UIA_REPLAY_MIX, UIA_REPLAY_PROCESS, UIA_REPLAY_SAVE,
    UIA_REPLAY_SCENARIO, UIA_SAVE_SCENARIOS)
from .native_process_viewport import PROCESS_GROUPS

NATIVE_TOOLS = frozenset({"Snapshot", "Screenshot", "Click", "Type", "Shortcut", "Wait", "ControlStatus"})
INPUT_TOOLS = frozenset({"Click", "Type", "Shortcut"})
SHORTCUTS = frozenset({"ctrl+s", "ctrl+shift+s", "enter", "tab", "shift+tab", "esc", "escape"})
UIA_SAVE_TOOLS = frozenset({"Snapshot", "Click", "Type", "Wait", "ControlStatus"})
UIA_ACTION_TYPES = ("ButtonControl", "MenuItemControl", "TabItemControl")
UIA_VISUAL_REGIONS = ("wx_sidebar", "imgui_canvas")
PROCESS_POPUP = "wx_process_popup"
MIX_DIALOG, MIX_CHOICES = "wx_add_mix", "wx_mix_filaments"
MIX_ROLES = ("ratio", "gradient", "filament1", "filament3", "confirm")
EDIT_NUMBER = r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?"
CANVAS_NUMBER = r"(?:[1-9][0-9]{0,2}(?:\.[0-9]{1,4})?|0\.(?=[0-9]{0,3}[1-9])[0-9]{1,4})"
NATIVE_EDIT_OBSERVATION_SCENARIOS = frozenset(MAINTENANCE_TRIALS)


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT)]


def visible_native_edits(wu, children, focused, pid):
    """Return bounded, hit-tested Edit geometry without reading window text."""
    gui = wu.user32
    fields = []
    for hwnd in children:
        handle = wintypes.HWND(hwnd)
        if (wu._window_pid(hwnd) != pid or wu.window_class(hwnd) != "Edit"
                or not gui.IsWindowVisible(handle) or not gui.IsWindowEnabled(handle)):
            continue
        style = gui.GetWindowLongW(handle, -16)  # GWL_STYLE
        if not style or style & (0x20 | 0x800):  # invalid HWND, ES_PASSWORD or ES_READONLY
            continue
        left, top, right, bottom = wu.window_rect(hwnd)
        x1, y1, x2, y2 = max(0, left), max(0, top), min(1920, right), min(1080, bottom)
        if not (x1 < x2 and y1 < y2):
            continue
        loc = [(x1 + x2) // 2, (y1 + y2) // 2]
        if wu.window_from_screen_point(*loc) != hwnd:
            continue  # clipped by a viewport or covered by another control
        fields.append({"bounds": [x1, y1, x2, y2], "loc": loc, "focused": hwnd == focused})
    fields.sort(key=lambda row: (row["bounds"][1], row["bounds"][0]))
    return {"fields": fields[:48], "truncated": len(fields) > 48}


def edit_number(scenario):
    # The comparison only extends native numeric input for named case targets.
    if scenario in {"compare_276_quality", "compare_276_strength"}:
        return "(?:" + EDIT_NUMBER + "|500|700)"
    if scenario in {"compare_265_quality", "compare_265_strength"}:
        return "(?:" + EDIT_NUMBER + "|10%)"
    return EDIT_NUMBER


def native_tools(scenario):
    if scenario in UIA_MIX_SCENARIOS:
        # The pinned upstream server always retains ControlStatus.
        return NATIVE_TOOLS - {"Screenshot", "Wait"}
    if scenario == UIA_REPLAY_SCENARIO:
        return frozenset({"Snapshot", "Click", "Type", "Shortcut"})
    if scenario == UIA_REPLAY_SAVE:
        return frozenset({"Snapshot", "Click", "Type"})
    if scenario in {UIA_REPLAY_CANVAS, UIA_REPLAY_MIX, UIA_REPLAY_PROCESS}:
        return NATIVE_TOOLS - {"Wait", "ControlStatus"}
    return UIA_SAVE_TOOLS if scenario in UIA_SAVE_SCENARIOS else NATIVE_TOOLS


def visual_regions(scenario):
    if scenario in UIA_MIX_SCENARIOS:
        return ("wx_sidebar", MIX_DIALOG, MIX_CHOICES)
    return (*UIA_VISUAL_REGIONS, PROCESS_POPUP) if scenario in POPUP_BIND_SCENARIOS else UIA_VISUAL_REGIONS


def action_types(scenario):
    return (*UIA_ACTION_TYPES, "PaneControl") if scenario in UIA_MIX_SCENARIOS else UIA_ACTION_TYPES


def uia_selector_schema(control_type):
    return {"type": "object", "properties": {
        "control_type": {"const": control_type},
        "name": {"type": "string", "maxLength": 128},
        "automation_id": {"type": "string", "maxLength": 128},
    }, "required": ["control_type", "name", "automation_id"], "additionalProperties": False}


def validate_uia_selector(selector, control_type):
    if (type(selector) is not dict or set(selector) != {"control_type", "name", "automation_id"}
            or selector["control_type"] != control_type
            or any(type(selector[k]) is not str or len(selector[k]) > 128
                   or any(ord(c) < 32 for c in selector[k]) for k in ("name", "automation_id"))
            or not (selector["name"] or selector["automation_id"])):
        raise ValueError("native_uia_selector_invalid")


def uia_tool_schema(tool, output_path):
    schemas = {
        "Snapshot": ({}, [], "Read the owned Save As UIA controls and file-name value as text."),
        "Click": ({"target": uia_selector_schema("ButtonControl")}, ["target"],
                  "Invoke the Save button using its exact UIA target from Snapshot."),
        "Type": ({"target": uia_selector_schema("EditControl"), "text": {"const": output_path}},
                 ["target", "text"], "Set the exact assigned path on the file-name Edit via UIA and read it back."),
        "Wait": ({"duration": {"type": "integer", "minimum": 0, "maximum": 5}},
                 ["duration"], "Wait for at most five whole seconds."),
        "ControlStatus": ({"release": {"type": "boolean"}}, [], "Finish the isolated GUI session."),
    }
    properties, required, description = schemas[tool["name"]]
    tool.update(description=description, inputSchema={"type": "object", "properties": properties,
                "required": required, "additionalProperties": False})


def hybrid_tool_schema(tool, output_path, scenario):
    def exact(properties, required=None):
        return {"type": "object", "properties": properties,
                "required": list(properties) if required is None else required,
                "additionalProperties": False}

    def pixels(length):
        return {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1920},
                "minItems": length, "maxItems": length}

    name = tool["name"]
    if name in {"Wait", "ControlStatus"}:
        uia_tool_schema(tool, output_path)
        return
    snapshots = exact({})
    crop = exact({"region_name": {"type": "string", "enum": list(visual_regions(scenario))}})
    loc = {**pixels(2), "description": "Absolute desktop pixel pair as a JSON integer array. Example [120,480]."}
    action = uia_selector_schema("ButtonControl")
    action["properties"]["control_type"] = {"type": "string", "enum": list(action_types(scenario))}
    click = exact({"target": action, "loc": loc}, [])
    click["oneOf"] = [{"required": ["target"]}, {"required": ["loc"]}]
    if scenario in UIA_ENUM_SCENARIOS:
        click["properties"]["process_group"] = {"enum": list(PROCESS_GROUPS)}
        click["oneOf"].append({"required": ["process_group"]})
    if scenario in UIA_MIX_SCENARIOS:
        click = exact({"target": action, "mix_role": {"type": "string", "enum": list(MIX_ROLES)}}, [])
        click["oneOf"] = [{"required": ["target"]}, {"required": ["mix_role"]}]
    value = {"type": "string", "anyOf": [{"const": output_path}, {"pattern": "^" + EDIT_NUMBER + "$"}]}
    edit = exact({"target": uia_selector_schema("EditControl"), "text": value})
    if scenario in CANVAS_SCENARIOS:
        edit["required"] = ["text"]
        edit["properties"].update(loc=loc, press_enter={"type": "boolean", "const": True})
        edit["oneOf"] = [
            {"required": ["target"], "not": {"anyOf": [{"required": ["loc"]}, {"required": ["press_enter"]}]}},
            {"required": ["loc", "press_enter"], "not": {"required": ["target"]},
             "properties": {"text": {"pattern": "^" + CANVAS_NUMBER + "$"}}},
        ]
        value["anyOf"].append({"pattern": "^" + CANVAS_NUMBER + "$"})
    schemas = {
        "Snapshot": (snapshots, "Read the scoped UIA tree, values and anchored regions available for drawn UI."),
        "Screenshot": (crop, "Capture one named wx or ImGui area. The executor derives its live bounds and returns crop_region."),
        "Click": (click, ("Use an exact observed target or a listed Add Mix mix_role. The filament3 role is available only after observing it in the material popup."
                          if scenario in UIA_MIX_SCENARIOS else
                          "Invoke or select a native control using its exact Snapshot target. Use loc only for a drawn control in the latest crop; add the crop origin to the pixel coordinates.")),
        "Type": (edit, "Set an observed UIA Edit using its exact target and read back its value. On the approved ImGui route only, a same-location Click followed by numeric Type with press_enter=true commits the field."),
        "Shortcut": (exact({"shortcut": {"const": "ctrl+shift+s"}}), "Open Save As in the owned main application."),
    }
    tool["inputSchema"], tool["description"] = schemas[name]
    if name == "Click" and scenario in UIA_ENUM_SCENARIOS:
        tool["description"] += " To bring a Quality parameter group into view, pass only process_group from the latest Snapshot. Take a new Snapshot before navigating again. Observe the sidebar crop before using loc on a drawn combo."


def scoped_tool_schemas(tools, output_path, scenario="base"):
    """Advertise the same narrow types accepted by the authority middleware.

    Upstream coordinate/string unions otherwise invite stringified locations.
    This edits transport metadata only, never the original MCP implementation.
    """
    expected = native_tools(scenario)
    if len(tools) != len(expected) or {t["name"] for t in tools} != expected:
        raise ValueError("native_toolset_changed")
    if scenario in UIA_SAVE_SCENARIOS:
        result = deepcopy(tools)
        for tool in result:
            uia_tool_schema(tool, output_path)
        return result
    if scenario in UIA_HYBRID_SCENARIOS:
        result = deepcopy(tools)
        for tool in result:
            hybrid_tool_schema(tool, output_path, scenario)
        return result
    loc = {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1919},
           "minItems": 2, "maxItems": 2, "description": "Desktop [x,y] as two JSON integers. x<1920 and y<1080. Do not stringify."}
    numeric = {"type": "string", "pattern": "^" + edit_number(scenario) + "$"}
    if scenario in CANVAS_SCENARIOS:
        numeric = {"type": "string", "pattern": "^" + CANVAS_NUMBER + "$"}
    fields = {
        "Snapshot": ({"use_vision": {"type": "boolean"}, "use_annotation": {"type": "boolean"},
                      "use_dom": {"type": "boolean", "enum": [False]}}, []),
        "Screenshot": ({}, []),
        "Click": ({"loc": loc, "button": {"type": "string", "enum": ["left"]},
                   "clicks": {"type": "integer", "enum": [1, 2]}}, ["loc"]),
        "Type": ({"loc": loc, "text": {"anyOf": [numeric, {"type": "string", "enum": [output_path]}], "maxLength": 1024},
                  "clear": {"type": "boolean"}, "press_enter": {"type": "boolean"},
                  "caret_position": {"type": "string", "enum": ["idle", "start", "end"]}}, ["loc", "text"]),
        "Shortcut": ({"shortcut": {"type": "string", "enum": sorted(SHORTCUTS)}}, ["shortcut"]),
        "Wait": ({"duration": {"type": "integer", "minimum": 0, "maximum": 5}}, ["duration"]),
        "ControlStatus": ({"release": {"type": "boolean"}}, []),
    }
    descriptions = {
        "Snapshot": "Observe the isolated guest desktop and UI tree. Optional boolean use_vision/use_annotation; use_dom must remain false. No file output. Act with fresh desktop pixel coordinates, not element labels.",
        "Screenshot": "Capture the whole isolated guest desktop. This scoped tool takes no arguments; region, display and save_path are unavailable. Use the returned image to choose current desktop pixel coordinates.",
        "Click": "Left-click a current desktop pixel loc=[x,y] inside the owned application or its dialog. Optional clicks is 1 or 2. Element labels and other mouse buttons are unavailable.",
        "Type": "Type numeric text or the exact assigned project save path into an owned native Edit at loc=[x,y]. clear=true replaces existing text; otherwise text is appended. press_enter=true commits once after typing. Save paths are accepted only in the owned Save file as dialog. No arbitrary text or other paths.",
        "Shortcut": "Send only ctrl+s, ctrl+shift+s, enter, tab, shift+tab, esc or escape to the owned application/dialog. Other keyboard shortcuts are unavailable.",
        "Wait": "Wait for required integer duration in whole seconds from 0 to 5. Fractional durations and omitted duration are unavailable.",
        "ControlStatus": "Read/release the original global control lease. Its disabled state is expected in this dedicated --no-control guest; per-call owned-window/input authority is enforced separately. This tool cannot enable or reconfigure authority.",
    }
    if scenario in NATIVE_EDIT_OBSERVATION_SCENARIOS:
        descriptions["Snapshot"] += " Includes hit-tested writable native Edit bounds and focus when Orca owns the foreground."
        descriptions["Screenshot"] += " Includes writable native Edit locations as text alongside the image. Match each Edit to its row using the field bounds."
        descriptions["Type"] += " Match the field visually with its observed writable Edit and use that Edit's loc."
    if scenario == "canvas_trial":
        descriptions["Type"] = ("Type positive numeric text below 1000 (at most 4 decimals) into the explicitly bound canvas. Each numeric Type requires and consumes a successful Click at the same loc within 30 seconds. If another Type is necessary after inspecting the result, Click again first. Canvas Type requires clear=false, caret_position=idle and press_enter=false. Its own Click can alter selection. The exact assigned save path remains allowed only in native Save file as Edit, with normal Edit options. No other strings or paths.")
    elif scenario in CANVAS_REPLACE_SCENARIOS:
        fields["Click"][0]["clicks"] = {"type": "integer", "enum": [1]}
        descriptions["Click"] = ("Single left-click at loc=[x,y] inside the owned application or its dialog. "
                                 "This trial accepts one click at a time. Leave clicks unset or set clicks=1.")
        descriptions["Type"] = ("Type positive numeric text below 1000 (at most 4 decimals) into a newly activated canvas field. "
                                "Activate an inactive numeric field with exactly one left Click and then Type at that same loc "
                                "within 30 seconds. This consumes the Click, preserves the selection from activation, and "
                                "presses Enter once without clicking again. Set press_enter=true, clear=false, caret_position=idle. "
                                "Inspect the committed value. For the assigned path, use clear=true in the native Save As Edit.")
    elif scenario == COMMIT_SCENARIO:
        descriptions["Type"] += (" For numeric edits in this trial, send clear=true and press_enter=true together "
                                 "with idle caret to replace and commit in one operation. The assigned save path also requires clear=true.")
    elif scenario in SAVE_CLEAR_SCENARIOS:
        descriptions["Type"] += " The assigned save path requires clear=true."
    result = deepcopy(tools)
    for tool in result:
        properties, required = fields[tool["name"]]
        if not set(tool.get("inputSchema", {}).get("required", [])) <= set(required):
            raise ValueError("native_upstream_required_schema_changed")
        tool["inputSchema"] = {"type": "object", "properties": properties, "required": required,
                               "additionalProperties": False}
        if scenario in CANVAS_SCENARIOS | SAVE_CLEAR_SCENARIOS and tool["name"] == "Type":
            save_options = {"properties": {"text": {"const": output_path}}}
            if scenario in SAVE_CLEAR_SCENARIOS:
                save_options["properties"]["clear"] = {"const": True}
                save_options["required"] = ["clear"]
            numeric_options = {"properties": {"text": numeric}}
            if scenario in CANVAS_SCENARIOS | {COMMIT_SCENARIO}:
                numeric_options["properties"].update(clear={"enum": [scenario == COMMIT_SCENARIO]},
                    press_enter={"enum": [scenario != "canvas_trial"]}, caret_position={"enum": ["idle"]})
                if scenario != "canvas_trial":
                    numeric_options["required"] = ["press_enter"]
                if scenario == COMMIT_SCENARIO:
                    numeric_options["required"].append("clear")
            tool["inputSchema"]["anyOf"] = [save_options, numeric_options]
        tool["description"] = descriptions[tool["name"]]
    return result


def validate_input(name, args, output_path, scenario="base"):
    if type(name) is not str or name not in native_tools(scenario) or type(args) is not dict:
        raise ValueError("native_tool_rejected")
    if scenario in UIA_HYBRID_SCENARIOS:
        if name == "Snapshot" and args:
            raise ValueError("native_uia_snapshot_options")
        if name == "Click" and scenario in UIA_ENUM_SCENARIOS and set(args) == {"process_group"}:
            if args["process_group"] not in PROCESS_GROUPS:
                raise ValueError("native_process_group_rejected")
            return
        if name == "Click" and scenario in UIA_MIX_SCENARIOS:
            if set(args) == {"mix_role"} and args["mix_role"] in MIX_ROLES:
                return
            if set(args) != {"target"}:
                raise ValueError("native_mix_click_arguments")
        if name == "Screenshot":
            if set(args) == {"region_name"} and args["region_name"] in visual_regions(scenario):
                return
            box = args.get("region")
            if (set(args) != {"region"} or type(box) is not list or len(box) != 4
                    or any(type(value) is not int for value in box)
                    or not (0 <= box[0] < box[2] <= 1920 and 0 <= box[1] < box[3] <= 1080)):
                raise ValueError("native_uia_crop_required")
            return
        if name in {"Click", "Type"} and "target" in args:
            target = args["target"]
            kind = target.get("control_type") if type(target) is dict else None
            if name == "Type":
                if (set(args) != {"target", "text"} or kind != "EditControl" or type(args["text"]) is not str
                        or not (args["text"] == output_path or re.fullmatch(EDIT_NUMBER, args["text"]))):
                    raise ValueError("native_uia_edit_arguments")
            elif set(args) != {"target"} or kind not in action_types(scenario):
                raise ValueError("native_uia_action_arguments")
            validate_uia_selector(target, kind)
            return
        if name == "Click" and set(args) != {"loc"}:
            raise ValueError("native_uia_visual_click_arguments")
        if name == "Type" and (scenario not in CANVAS_SCENARIOS or set(args) != {"loc", "text", "press_enter"}
                               or args["text"] == output_path):
            raise ValueError("native_uia_canvas_arguments")
        if name == "Shortcut" and args != {"shortcut": "ctrl+shift+s"}:
            raise ValueError("native_uia_command_rejected")
    elif scenario in UIA_SAVE_SCENARIOS:
        if name == "Snapshot" and args:
            raise ValueError("native_uia_snapshot_options")
        if name in {"Click", "Type"}:
            required = {"target", "text"} if name == "Type" else {"target"}
            if set(args) != required or (name == "Type" and args["text"] != output_path):
                raise ValueError("native_uia_save_arguments")
            validate_uia_selector(args["target"], "EditControl" if name == "Type" else "ButtonControl")
            return
    if name in {"Snapshot", "Screenshot"}:
        if args.get("save_path") is not None or args.get("use_dom", False) is not False:
            raise ValueError("native_capture_write_or_dom_rejected")
        permitted = {"use_vision", "use_annotation", "use_dom"} if name == "Snapshot" else set()
        if set(args)-permitted or any(type(v) is not bool for v in args.values()):
            raise ValueError("native_capture_options_rejected")
    elif name in {"Click", "Type"}:
        loc = args.get("loc")
        if ("label" in args or type(loc) is not list or len(loc) != 2
                or any(type(x) is not int for x in loc)
                or not 0 <= loc[0] < 1920 or not 0 <= loc[1] < 1080):
            raise ValueError("native_screen_location_rejected")
        if name == "Click":
            if (args.get("button", "left") != "left" or type(args.get("clicks", 1)) is not int
                    or args.get("clicks", 1) not in {1, 2} or set(args) - {"loc", "button", "clicks"}):
                raise ValueError("native_click_rejected")
            if scenario in CANVAS_REPLACE_SCENARIOS and args.get("clicks", 1) != 1:
                raise ValueError("native_canvas_single_click_required")
        else:
            text = args.get("text")
            from .canvas_input import numeric_text_allowed
            numeric_ok = numeric_text_allowed("pilot_transform", text) if scenario in CANVAS_SCENARIOS else bool(
                type(text) is str and re.fullmatch(edit_number(scenario), text))
            if (type(text) is not str or len(text) > 1024 or not (text == output_path or numeric_ok)):
                raise ValueError("native_type_text_rejected")
            if (set(args) - {"loc", "text", "clear", "caret_position", "press_enter"}
                    or any(type(args[k]) is not bool for k in ("clear", "press_enter") if k in args)
                    or args.get("caret_position", "idle") not in {"idle", "start", "end"}):
                raise ValueError("native_type_options_rejected")
            if (scenario in SAVE_CLEAR_SCENARIOS
                    and text == output_path and args.get("clear") is not True):
                raise ValueError("native_save_path_requires_clear")
            if scenario in CANVAS_SCENARIOS | {COMMIT_SCENARIO} and text != output_path:
                if (args.get("clear", False) is not (scenario == COMMIT_SCENARIO)
                        or args.get("press_enter", False) is not (scenario != "canvas_trial")
                        or args.get("caret_position", "idle") != "idle"):
                    code = "canvas_trial_type_options" if scenario == "canvas_trial" else "native_numeric_type_options"
                    raise ValueError(code)
    elif name == "Shortcut":
        if (set(args) != {"shortcut"} or type(args["shortcut"]) is not str
                or args["shortcut"].lower() not in SHORTCUTS):
            raise ValueError("native_shortcut_rejected")
    elif name == "Wait":
        duration = args.get("duration")
        if (set(args) - {"duration"} or type(duration) not in (int, float)
                or not math.isfinite(duration) or not 0 <= duration <= 5 or duration != int(duration)):
            raise ValueError("native_wait_rejected")
    elif set(args) - {"release"} or ("release" in args and type(args["release"]) is not bool):
        raise ValueError("native_control_status_rejected")


class InputGuard:
    """Trusted guest check, executed in the same INTERACTIVE MCP process."""
    def __init__(self, scope, root):
        self.scope, self.root = scope, root
        self.last_window, self.arguments_validated = {}, False
        self.last_canvas_evidence = None
        self._last_click = None

    def record_click(self, loc, *, clicks=1):
        """Controller calls only after a successful original Click; not a field proof."""
        if self.scope.get("scenario") not in CANVAS_SCENARIOS:
            return
        import time
        if (type(loc) is not list or len(loc) != 2 or any(type(v) is not int for v in loc)
                or not 0 <= loc[0] < 1920 or not 0 <= loc[1] < 1080):
            raise ValueError("canvas_click_location")
        target = self.last_window.get("target_hwnd")
        if type(target) is not int or target <= 0:
            raise ValueError("canvas_click_target_missing")
        finished_ns = time.monotonic_ns()
        self._last_click = (tuple(loc), finished_ns, target, clicks)
        self.last_window["click_finished_monotonic_ns"] = finished_ns

    def observe_native_edits(self):
        try:
            wu, foreground = self.owned_foreground()
            gui = wu.user32
            foreground_handle = wintypes.HWND(foreground)
            thread_id = gui.GetWindowThreadProcessId(foreground_handle, None)
            info = _GuiThreadInfo(cbSize=ctypes.sizeof(_GuiThreadInfo))
            if not thread_id or not gui.GetGUIThreadInfo(wintypes.DWORD(thread_id), ctypes.byref(info)):
                return {"unavailable": True}
            children = []

            @wu.WNDENUMPROC
            def collect(hwnd, _lparam):
                children.append(hwnd)
                return True

            gui.EnumChildWindows(foreground_handle, collect, 0)
            result = visible_native_edits(wu, children, info.hwndFocus, self.scope["app_pid"])
            _, current = self.owned_foreground()
        except (ValueError, OSError):
            # A transient redraw can invalidate a child between enumeration and query.
            return {"unavailable": True}
        return result if current == foreground else {"unavailable": True}

    def _canvas_destination(self, args):
        import time
        from .canvas_approval import resolve_approval
        from .canvas_input import collect_window_evidence, load_canvas_binding, decide_type
        evidence = collect_window_evidence(self.scope["run_id"], self.scope["app_pid"], self.scope["hwnd"], args["loc"])
        approval = resolve_approval(self.scope["canvas_approval_profile"],
            diagnostic_sha256=self.scope["canvas_diagnostic_sha256"], sut_sha256=self.scope["canvas_sut_sha256"])
        binding = load_canvas_binding(self.scope["canvas_binding_json"], run_id=self.scope["run_id"],
            app_pid=self.scope["app_pid"], process_created=evidence["process_created"],
            main_hwnd=self.scope["hwnd"], approval=approval)
        checked_ns = time.monotonic_ns()
        decision = decide_type("pilot_transform", args["text"], args["loc"], evidence,
            output_path=self.scope["output_path"], now_ns=checked_ns, binding=binding)
        if any((self.root / flag).exists() for flag in ("input_revoked", "control_cancel.json", "authority_abort.json")):
            raise ValueError("native_input_revoked")
        return evidence, binding, checked_ns, decision

    def recheck_canvas_keys(self, args):
        """Recheck the fixed canvas destination without clicking or consuming another ticket."""
        _, _, _, decision = self._canvas_destination(args)
        if decision["route"] != "canvas_numeric":
            raise ValueError("native_canvas_destination_changed")

    def _canvas_trial_type(self, args):
        import time
        evidence, binding, checked_ns, decision = self._canvas_destination(args)
        self.last_canvas_evidence = evidence
        if decision["route"] == "canvas_numeric":
            click, self._last_click = self._last_click, None
            replace = self.scope["scenario"] in CANVAS_REPLACE_SCENARIOS
            if (args.get("clear", False) is not False or args.get("press_enter", False) is not replace
                    or args.get("caret_position", "idle") != "idle"):
                raise ValueError("canvas_trial_type_options")
            if (click is None or click[0] != tuple(args["loc"]) or click[2] != binding.hwnd
                    or (replace and click[3] != 1)
                    or not 0 <= time.monotonic_ns()-click[1] <= 30_000_000_000):
                raise ValueError("native_canvas_trial_recent_click_required")
        windows = {w["hwnd"]:w for w in evidence["windows"]}
        target = windows[evidence["target_hwnd"]]
        self.last_window.update(decision)
        self.last_window.update(foreground_hwnd=evidence["foreground_hwnd"], focus_hwnd=evidence["focus_hwnd"],
            process_created=evidence["process_created"], guard_checked_monotonic_ns=checked_ns,
            target_class=target["class"], target_title=target.get("title", ""),
            captured_monotonic_ns=evidence["captured_monotonic_ns"],
            canvas_diagnostic_sha256=binding.diagnostic_sha256, canvas_profile=binding.approval_profile,
            pfd_index=target.get("pixel_format", {}).get("index", 0),
            pfd_verified=False, internal_numeric_field_verified=False)
        return self.last_window

    def check(self, name, args):
        self.last_canvas_evidence, self.last_window, self.arguments_validated = None, {}, False
        validate_input(name, args, self.scope["output_path"], self.scope.get("scenario", "base"))
        if name == "Shortcut" and self.scope.get("scenario") in CANVAS_REPLACE_SCENARIOS:
            self._last_click = None
        self.arguments_validated = True
        self.check_revocation()
        if name not in INPUT_TOOLS:
            if name in {"Snapshot", "Screenshot"} and self.scope.get("scenario") in NATIVE_EDIT_OBSERVATION_SCENARIOS:
                return self.last_window
            return {}
        wu, foreground = self.owned_foreground()
        target = wu.window_from_screen_point(*args["loc"]) if "loc" in args else foreground
        if not target or wu._window_pid(target) != self.scope["app_pid"]:
            raise ValueError("native_target_not_owned")
        self.last_window = {"foreground_hwnd": foreground, "target_hwnd": target,
                            "app_pid": self.scope["app_pid"], "foreground_pid": wu._window_pid(foreground),
                            "target_pid": wu._window_pid(target), "target_class": wu.window_class(target)}
        if name == "Type" and self.scope.get("scenario") in CANVAS_SCENARIOS:
            return self._canvas_trial_type(args)
        if name == "Type":
            if wu.window_class(target) != "Edit":
                raise ValueError("native_type_requires_owned_edit")
            if args["text"] == self.scope["output_path"]:
                caption = wu.window_title(foreground)
                if caption not in {"Save file as", "Save file as:"}:
                    raise ValueError("native_path_requires_save_dialog")
        return self.last_window

    def check_revocation(self):
        if any((self.root / flag).exists() for flag in
               ("input_revoked", "control_cancel.json", "authority_abort.json")):
            raise ValueError("native_input_revoked")

    def owned_foreground(self):
        self.check_revocation()
        import ctypes as C
        from ctypes import wintypes as W
        from . import winutil as wu
        u, k = wu.user32, C.WinDLL("kernel32", use_last_error=True)
        k.WTSGetActiveConsoleSessionId.restype = W.DWORD
        k.ProcessIdToSessionId.argtypes = [W.DWORD, C.POINTER(W.DWORD)]
        session = W.DWORD()
        if (not k.ProcessIdToSessionId(self.scope["app_pid"], C.byref(session))
                or session.value != k.WTSGetActiveConsoleSessionId()
                or (u.GetSystemMetrics(0), u.GetSystemMetrics(1)) != (1920, 1080)):
            raise ValueError("native_interactive_session_changed")
        if (not u.IsWindow(self.scope["hwnd"]) or
                wu._window_pid(self.scope["hwnd"]) != self.scope["app_pid"]):
            raise ValueError("native_app_identity_changed")
        foreground = u.GetForegroundWindow()
        if not foreground or wu._window_pid(foreground) != self.scope["app_pid"]:
            raise ValueError("native_foreground_not_owned")
        return wu, foreground
