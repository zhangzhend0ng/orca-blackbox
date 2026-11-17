"""Data-only authority policy; no coordinates or business action sequence."""
from __future__ import annotations

import math
import re

NATIVE_TOOLS = frozenset({"Snapshot", "Screenshot", "Click", "Type", "Shortcut", "Wait", "ControlStatus"})
INPUT_TOOLS = frozenset({"Click", "Type", "Shortcut"})
SHORTCUTS = frozenset({"ctrl+s", "ctrl+shift+s", "enter", "tab", "shift+tab", "esc", "escape"})


def validate_input(name, args, output_path):
    if type(name) is not str or name not in NATIVE_TOOLS or type(args) is not dict:
        raise ValueError("native_tool_rejected")
    if name in {"Snapshot", "Screenshot"}:
        if args.get("save_path") is not None or args.get("use_dom", False) is not False:
            raise ValueError("native_capture_write_or_dom_rejected")
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
        duration = args.get("duration", 1)
        if (set(args) - {"duration"} or type(duration) not in (int, float)
                or not math.isfinite(duration) or not 0 <= duration <= 5):
            raise ValueError("native_wait_rejected")
    elif set(args) - {"release"} or ("release" in args and type(args["release"]) is not bool):
        raise ValueError("native_control_status_rejected")


class InputGuard:
    """Trusted guest check, executed in the same INTERACTIVE MCP process."""
    def __init__(self, scope, root):
        self.scope, self.root = scope, root

    def check(self, name, args):
        validate_input(name, args, self.scope["output_path"])
        if (self.root / "input_revoked").exists():
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
