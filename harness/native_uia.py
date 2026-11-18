"""UIA-first Save As using the installed Windows-MCP UIA backend."""
import hashlib

from .agent_verify import _require
from .native_save_policy import InputGuard, validate_input, validate_uia_selector

SAVE_DIALOG_TITLES = {"Save file as", "Save file as:"}


def value_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class UiaSaveGuard(InputGuard):
    def __init__(self, scope, root, control_from_handle):
        super().__init__(scope, root)
        self.control_from_handle = control_from_handle
        self.observed = {}
        self.invoked = False
        self.written = None

    def _elements(self, hwnd):
        pid = self.scope["app_pid"]
        root = self.control_from_handle(hwnd)
        if root is None or root.ProcessId != pid or root.NativeWindowHandle != hwnd:
            raise ValueError("native_uia_dialog_identity")
        pending = [(root, 0)]
        count = 0
        while pending:
            element, depth = pending.pop()
            count += 1
            if count > 512:
                raise ValueError("native_uia_node_limit")
            if element.ProcessId != pid:
                continue
            if depth < 12:
                pending.extend((child, depth + 1) for child in element.GetChildren())
            yield element

    def _controls(self, wu, hwnd):
        from win32gui import IsChild

        pid = self.scope["app_pid"]
        controls = {}
        for element in self._elements(hwnd):
            kind = element.ControlTypeName
            if kind not in {"EditControl", "ButtonControl"}:
                continue
            name = element.Name or ""
            label = name.replace("&", "").strip().rstrip(":").casefold()
            role = "filename" if kind == "EditControl" and label == "file name" else (
                "save" if kind == "ButtonControl" and label == "save" else None)
            child = element.NativeWindowHandle
            if role is None or not child or not IsChild(hwnd, child) or wu._window_pid(child) != pid:
                continue
            if (wu.window_class(child) != {"filename": "Edit", "save": "Button"}[role]
                    or not element.IsEnabled or element.IsOffscreen):
                continue
            target = {"control_type": kind, "name": name, "automation_id": element.AutomationId or ""}
            validate_uia_selector(target, kind)
            if role in controls:
                raise ValueError("native_uia_ambiguous_control")
            controls[role] = element, {"target": target, "hwnd": child}
        return controls

    def _observe_after_invoke(self, wu, hwnd):
        from win32gui import GetAncestor, IsWindow, IsWindowVisible

        main = self.scope["hwnd"]
        dialog = self.scope["dialog_hwnd"]
        if hwnd != main and GetAncestor(hwnd, 3) != main:
            raise ValueError("native_uia_post_save_window_not_owned")
        closed = not (IsWindow(dialog) and IsWindowVisible(dialog))
        self.last_window["dialog_closed"] = closed
        if hwnd == main and closed:
            return {"dialog_closed": True}
        texts = []
        for node in self._elements(hwnd):
            if node.ControlTypeName == "TextControl" and node.Name and len(texts) < 8:
                texts.append(node.Name[:192])
        modal = {"title": wu.window_title(hwnd)[:128], "class": wu.window_class(hwnd), "text": texts}
        self.last_window["post_invoke_window"] = modal
        return {"dialog_closed": closed, "foreground_window": modal}

    def _dialog(self, hwnd, wu):
        if (hwnd != self.scope.get("dialog_hwnd") or wu.window_class(hwnd) != "#32770"
                or wu.window_title(hwnd) not in SAVE_DIALOG_TITLES):
            raise ValueError("native_uia_save_dialog_required")

    def _resolve(self, name, arguments, controls):
        role = "filename" if name == "Type" else "save"
        control, record = controls.get(role, (None, None))
        if record is None or record["target"] != arguments["target"] or record != self.observed.get(role):
            raise ValueError("native_uia_target_not_observed")
        return control, record

    def check(self, name, args):
        if name not in {"Snapshot", "Click", "Type"}:
            return super().check(name, args)
        self.last_canvas_evidence, self.last_window, self.arguments_validated = None, {}, False
        validate_input(name, args, self.scope["output_path"], self.scope["scenario"])
        self.arguments_validated = True
        wu, hwnd = self.owned_foreground()
        pid = self.scope["app_pid"]
        self.last_window = dict(route="uia_tree", app_pid=pid, foreground_hwnd=hwnd, foreground_pid=pid)
        if name == "Snapshot" and self.invoked and hwnd != self.scope.get("dialog_hwnd"):
            return self.last_window
        self._dialog(hwnd, wu)
        if name in {"Click", "Type"}:
            _, record = self._resolve(name, args, self._controls(wu, hwnd))
            self.last_window.update(target_hwnd=record["hwnd"], target_pid=pid,
                target_class=wu.window_class(record["hwnd"]), target=record["target"])
        return self.last_window

    @staticmethod
    def _value(element):
        pattern = element.GetValuePattern()
        if pattern is None or pattern.IsReadOnly:
            raise ValueError("native_uia_value_pattern_required")
        return pattern

    def perform(self, name, arguments):
        wu, hwnd = self.owned_foreground()
        if hwnd != self.last_window["foreground_hwnd"]:
            raise ValueError("native_uia_foreground_changed")
        if name == "Snapshot" and self.invoked and hwnd != self.scope.get("dialog_hwnd"):
            return self._observe_after_invoke(wu, hwnd)
        self._dialog(hwnd, wu)
        controls = self._controls(wu, hwnd)
        if name == "Snapshot":
            self.observed = {role: item[1] for role, item in controls.items()}
            self.last_window["controls"] = self.observed
            filename = controls.get("filename")
            result = {"window": wu.window_title(hwnd), "controls": {r: c["target"] for r, c in self.observed.items()}}
            if filename:
                result["file_name_value"] = self._value(filename[0]).Value
            return result
        element, record = self._resolve(name, arguments, controls)
        if record["hwnd"] != self.last_window["target_hwnd"]:
            raise ValueError("native_uia_target_changed")
        self.check_revocation()
        if name == "Type":
            pattern = self._value(element)
            self.last_window.update(route="uia_value", pattern="ValuePattern")
            if not pattern.SetValue(arguments["text"]):
                raise ValueError("native_uia_set_value_failed")
            readback = self._value(element).Value
            if readback != arguments["text"]:
                raise ValueError("native_uia_value_readback_mismatch")
            self.written = record
            self.last_window["readback_sha256"] = value_digest(readback)
            return {"target": record["target"], "value": readback, "pattern": "ValuePattern"}
        filename = controls.get("filename")
        if (filename is None or filename[1] != self.written
                or self._value(filename[0]).Value != self.scope["output_path"]):
            raise ValueError("native_uia_save_value_unconfirmed")
        invoke = element.GetInvokePattern()
        if invoke is None:
            raise ValueError("native_uia_invoke_pattern_required")
        self.last_window.update(route="uia_invoke", pattern="InvokePattern",
                                path_sha256=value_digest(self.scope["output_path"]))
        if not invoke.Invoke():
            raise ValueError("native_uia_invoke_failed")
        self.invoked = True
        return {"target": record["target"], "pattern": "InvokePattern", "invoked": True}


def verify_uia_save(trace, *, run_id, app_pid, dialog_hwnd, output_path):
    """Auditable UIA observation, exact-path read-back, then property-based Save."""
    observed, written, invoked, closed = None, False, False, False
    for seq, row in enumerate(trace, 1):
        name, args, evidence = row["tool"], row["arguments"], row.get("window", {})
        _require(row["seq"] == seq and row["run_id"] == run_id and row["dispatched"] is True
                 and row["error"] is None and name in {"Snapshot", "Type", "Click", "Wait", "ControlStatus"},
                 "native_uia_trace")
        if name in {"Wait", "ControlStatus"}:
            continue
        _require(evidence.get("app_pid") == evidence.get("foreground_pid") == app_pid, "native_uia_ownership")
        if name == "Snapshot":
            _require(args == {} and evidence.get("route") == "uia_tree", "native_uia_tree_required")
            if not invoked:
                _require(evidence.get("foreground_hwnd") == dialog_hwnd, "native_uia_dialog_binding")
                observed = evidence.get("controls")
            elif evidence.get("dialog_closed") is True and evidence["foreground_hwnd"] != dialog_hwnd:
                closed = True
            continue
        role, route, pattern, kind = (("filename", "uia_value", "ValuePattern", "EditControl") if name == "Type"
                                      else ("save", "uia_invoke", "InvokePattern", "ButtonControl"))
        validate_uia_selector(args.get("target"), kind)
        record = (observed or {}).get(role)
        _require(record == {"target": args["target"], "hwnd": evidence.get("target_hwnd")}
                 and args["target"] == evidence.get("target") and evidence.get("target_pid") == app_pid
                 and type(record["hwnd"]) is int and record["hwnd"] > 0 and args.keys() == (
                     {"target", "text"} if name == "Type" else {"target"})
                 and evidence.get("foreground_hwnd") == dialog_hwnd
                 and evidence.get("route") == route and evidence.get("pattern") == pattern and not invoked,
                 "native_uia_target_binding")
        if name == "Type":
            _require(args.get("text") == output_path and evidence.get("target_class") == "Edit"
                     and evidence.get("readback_sha256") == value_digest(output_path), "native_uia_value_readback")
            written = True
        else:
            _require(written and evidence.get("target_class") == "Button"
                     and evidence.get("path_sha256") == value_digest(output_path), "native_uia_save_order")
            invoked = True
    _require(invoked and closed, "native_uia_save_not_confirmed")
    return {"locator": "UIA properties", "value_pattern": True, "invoke_pattern": True,
            "screenshots": 0, "coordinate_inputs": 0}
