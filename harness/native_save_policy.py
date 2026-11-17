"""Data-only authority policy; no coordinates or business action sequence."""
from __future__ import annotations

import math
import re
from copy import deepcopy

NATIVE_TOOLS = frozenset({"Snapshot", "Screenshot", "Click", "Type", "Shortcut", "Wait", "ControlStatus"})
INPUT_TOOLS = frozenset({"Click", "Type", "Shortcut"})
SHORTCUTS = frozenset({"ctrl+s", "ctrl+shift+s", "enter", "tab", "shift+tab", "esc", "escape"})


def scoped_tool_schemas(tools, output_path):
    """Advertise the same narrow types accepted by the authority middleware.

    Upstream coordinate/string unions otherwise invite stringified locations.
    This edits transport metadata only, never the original MCP implementation.
    """
    if len(tools) != len(NATIVE_TOOLS) or {t["name"] for t in tools} != NATIVE_TOOLS:
        raise ValueError("native_toolset_changed")
    loc = {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1919},
           "minItems": 2, "maxItems": 2, "description": "Desktop [x,y] as two JSON integers. x<1920 and y<1080. Do not stringify."}
    numeric = {"type": "string", "pattern": r"^(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?$"}
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
    result = deepcopy(tools)
    for tool in result:
        properties, required = fields[tool["name"]]
        if not set(tool.get("inputSchema", {}).get("required", [])) <= set(required):
            raise ValueError("native_upstream_required_schema_changed")
        tool["inputSchema"] = {"type": "object", "properties": properties, "required": required,
                               "additionalProperties": False}
        if tool["name"] == "ControlStatus":
            tool["description"] = ("Read/release the original global control lease. Its disabled state is expected in this "
                "dedicated --no-control guest; per-call owned-window/input authority is enforced separately. "
                "This tool cannot enable or reconfigure authority.")
    return result


def validate_input(name, args, output_path):
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
        else:
            text = args.get("text")
            if (type(text) is not str or len(text) > 1024 or
                    not (text == output_path or re.fullmatch(r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?", text))):
                raise ValueError("native_type_text_rejected")
            if (set(args) - {"loc", "text", "clear", "caret_position", "press_enter"}
                    or any(type(args[k]) is not bool for k in ("clear", "press_enter") if k in args)
                    or args.get("caret_position", "idle") not in {"idle", "start", "end"}):
                raise ValueError("native_type_options_rejected")
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

    def check(self, name, args):
        validate_input(name, args, self.scope["output_path"])
        if (self.root / "input_revoked").exists() or (self.root / "control_cancel.json").exists():
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
        if name == "Type":
            if wu.window_class(target) != "Edit":
                raise ValueError("native_type_requires_owned_edit")
            if args["text"] == self.scope["output_path"]:
                caption = wu.window_title(foreground)
                if caption not in {"Save file as", "Save file as:"}:
                    raise ValueError("native_path_requires_save_dialog")
        return {"foreground_hwnd": foreground, "target_hwnd": target,
                "app_pid": self.scope["app_pid"]}
