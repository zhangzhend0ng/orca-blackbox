"""Data-only authority policy; no coordinates or business action sequence."""
from __future__ import annotations

import math
import re
from copy import deepcopy
from .native_diagnostic_recovery import COMMIT_SCENARIO
from .native_matrix import CANVAS_REPLACE_SCENARIO, CANVAS_SCENARIOS

NATIVE_TOOLS = frozenset({"Snapshot", "Screenshot", "Click", "Type", "Shortcut", "Wait", "ControlStatus"})
INPUT_TOOLS = frozenset({"Click", "Type", "Shortcut"})
SHORTCUTS = frozenset({"ctrl+s", "ctrl+shift+s", "enter", "tab", "shift+tab", "esc", "escape"})


def scoped_tool_schemas(tools, output_path, scenario="base"):
    """Advertise the same narrow types accepted by the authority middleware.

    Upstream coordinate/string unions otherwise invite stringified locations.
    This edits transport metadata only, never the original MCP implementation.
    """
    if len(tools) != len(NATIVE_TOOLS) or {t["name"] for t in tools} != NATIVE_TOOLS:
        raise ValueError("native_toolset_changed")
    loc = {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1919},
           "minItems": 2, "maxItems": 2, "description": "Desktop [x,y] as two JSON integers. x<1920 and y<1080. Do not stringify."}
    numeric = {"type": "string", "pattern": r"^(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?$"}
    if scenario in CANVAS_SCENARIOS:
        numeric = {"type": "string", "pattern": r"^(?:[1-9][0-9]{0,2}(?:\.[0-9]{1,4})?|0\.(?=[0-9]{0,3}[1-9])[0-9]{1,4})$"}
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
    if scenario == "canvas_trial":
        descriptions["Type"] = ("Type positive numeric text below 1000 (at most 4 decimals) into the explicitly bound canvas. Each numeric Type requires and consumes a successful Click at the same loc within 30 seconds. If another Type is necessary after inspecting the result, Click again first. Canvas Type requires clear=false, caret_position=idle and press_enter=false. Its own Click can alter selection. The exact assigned save path remains allowed only in native Save file as Edit, with normal Edit options. No other strings or paths.")
    elif scenario == CANVAS_REPLACE_SCENARIO:
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
    result = deepcopy(tools)
    for tool in result:
        properties, required = fields[tool["name"]]
        if not set(tool.get("inputSchema", {}).get("required", [])) <= set(required):
            raise ValueError("native_upstream_required_schema_changed")
        tool["inputSchema"] = {"type": "object", "properties": properties, "required": required,
                               "additionalProperties": False}
        if scenario in CANVAS_SCENARIOS | {COMMIT_SCENARIO} and tool["name"] == "Type":
            save_options = {"properties": {"text": {"const": output_path}}}
            if scenario in {CANVAS_REPLACE_SCENARIO, COMMIT_SCENARIO}:
                save_options["properties"]["clear"] = {"const": True}
                save_options["required"] = ["clear"]
            numeric_options = {"properties": {"text": numeric, "clear": {"enum": [scenario == COMMIT_SCENARIO]},
                               "press_enter": {"enum": [scenario != "canvas_trial"]},
                               "caret_position": {"enum": ["idle"]}}}
            if scenario != "canvas_trial":
                numeric_options["required"] = ["press_enter"]
            if scenario == COMMIT_SCENARIO:
                numeric_options["required"].append("clear")
            tool["inputSchema"]["anyOf"] = [save_options, numeric_options]
        tool["description"] = descriptions[tool["name"]]
    return result


def validate_input(name, args, output_path, scenario="base"):
    if type(name) is not str or name not in NATIVE_TOOLS or type(args) is not dict:
        raise ValueError("native_tool_rejected")
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
            if scenario == CANVAS_REPLACE_SCENARIO and args.get("clicks", 1) != 1:
                raise ValueError("native_canvas_single_click_required")
        else:
            text = args.get("text")
            from .canvas_input import numeric_text_allowed
            numeric_ok = numeric_text_allowed("pilot_transform", text) if scenario in CANVAS_SCENARIOS else bool(
                type(text) is str and re.fullmatch(r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?", text))
            if (type(text) is not str or len(text) > 1024 or not (text == output_path or numeric_ok)):
                raise ValueError("native_type_text_rejected")
            if (set(args) - {"loc", "text", "clear", "caret_position", "press_enter"}
                    or any(type(args[k]) is not bool for k in ("clear", "press_enter") if k in args)
                    or args.get("caret_position", "idle") not in {"idle", "start", "end"}):
                raise ValueError("native_type_options_rejected")
            if (scenario in {CANVAS_REPLACE_SCENARIO, COMMIT_SCENARIO}
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
            replace = self.scope["scenario"] == CANVAS_REPLACE_SCENARIO
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
        if name == "Shortcut" and self.scope.get("scenario") == CANVAS_REPLACE_SCENARIO:
            self._last_click = None
        self.arguments_validated = True
        if (self.root / "input_revoked").exists() or (self.root / "control_cancel.json").exists() or (self.root / "authority_abort.json").exists():
            raise ValueError("native_input_revoked")
        if name not in INPUT_TOOLS:
            return {}
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
