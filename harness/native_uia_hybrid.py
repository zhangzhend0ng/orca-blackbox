"""Owned UIA targets with narrowly scoped visual fallback for Orca's drawn UI."""
import json
import time

from .agent_verify import _require
from .native_save_policy import validate_input, validate_uia_selector
from .native_uia import SAVE_DIALOG_TITLES, UiaSaveGuard, value_digest, verify_uia_save

OBSERVATION_LIMIT_NS = 30_000_000_000


def within(bounds, rect):
    return (bounds[0] <= rect[0] < rect[2] <= bounds[2]
            and bounds[1] <= rect[1] < rect[3] <= bounds[3])


def contains(rect, loc):
    return rect[0] <= loc[0] < rect[2] and rect[1] <= loc[1] < rect[3]


def selector_key(target):
    return target["control_type"], target["name"], target["automation_id"]


class UiaHybridGuard(UiaSaveGuard):
    def __init__(self, scope, root, control_from_handle, control_from_point):
        super().__init__(scope, root, control_from_handle)
        self.control_from_point = control_from_point
        self.native_targets = {}
        self.visual_regions = {}
        self.last_crop = None
        self.canvas_hwnd = json.loads(scope["canvas_binding_json"])["hwnd"]

    def _main_window(self, wu, hwnd):
        if hwnd != self.scope["hwnd"]:
            raise ValueError("native_uia_main_window_required")
        return dict(app_pid=self.scope["app_pid"], foreground_pid=wu._window_pid(hwnd),
                    foreground_hwnd=hwnd)

    def _regions(self, wu):
        from win32gui import IsChild

        main, canvas = self.scope["hwnd"], self.canvas_hwnd
        if (not IsChild(main, canvas) or wu.window_class(canvas) != "wxGLCanvas"
                or wu._window_pid(canvas) != self.scope["app_pid"]):
            raise ValueError("native_uia_visual_anchor_changed")
        left, top, right, bottom = wu.window_rect(canvas)
        scene = [left, top, right, bottom]
        if not within([0, 0, 1920, 1080], scene) or not 0 <= left <= 800:
            raise ValueError("native_uia_visual_anchor_geometry")
        regions = {"imgui_canvas": scene}
        if left > 0:
            regions["wx_sidebar"] = [0, top, left, bottom]
        return regions

    @staticmethod
    def _pattern(element):
        kind = element.ControlTypeName
        if kind == "EditControl":
            value = element.GetValuePattern()
            if value is not None and not value.IsReadOnly:
                return "ValuePattern", value
        elif kind in {"ButtonControl", "MenuItemControl"}:
            invoke = element.GetInvokePattern()
            if invoke is not None:
                return "InvokePattern", invoke
        elif kind == "TabItemControl":
            select = element.GetSelectionItemPattern()
            if select is not None:
                return "SelectionItemPattern", select
        return None, None

    def _native_controls(self, wu, hwnd):
        from win32gui import IsChild

        candidates, duplicates = {}, set()
        for element in self._elements(hwnd):
            kind = element.ControlTypeName
            if kind not in {"EditControl", "ButtonControl", "MenuItemControl", "TabItemControl"}:
                continue
            handle = element.NativeWindowHandle
            if (not handle or not IsChild(hwnd, handle) or wu._window_pid(handle) != self.scope["app_pid"]
                    or not element.IsEnabled or element.IsOffscreen):
                continue
            if kind == "EditControl" and (element.IsPassword or wu.window_class(handle) != "Edit"):
                continue
            target = {"control_type": kind, "name": element.Name or "", "automation_id": element.AutomationId or ""}
            if not (target["name"] or target["automation_id"]):
                continue
            validate_uia_selector(target, kind)
            pattern, implementation = self._pattern(element)
            if pattern is None:
                continue
            key = selector_key(target)
            if key in candidates:
                duplicates.add(key)
            candidates[key] = (element, implementation, dict(target=target, hwnd=handle, pattern=pattern))
        return {key: record for key, record in candidates.items() if key not in duplicates}

    def _find_native(self, wu, hwnd, args):
        key = selector_key(args["target"])
        item = self._native_controls(wu, hwnd).get(key)
        if item is None or item[2] != self.native_targets.get(key):
            raise ValueError("native_uia_target_not_observed")
        return item

    def _visual_route(self, wu, hwnd, name, args):
        self._main_window(wu, hwnd)
        live = self._regions(wu)
        if name == "Screenshot":
            region = args["region"]
            matches = [key for key, rect in live.items()
                       if self.visual_regions.get(key) == rect and within(rect, region)]
            if len(matches) != 1:
                raise ValueError("native_uia_visual_region_not_observed")
            return matches[0], region
        if self.last_crop is None:
            raise ValueError("native_uia_visual_observation_required")
        kind, region, stamp = self.last_crop
        if (kind not in live or not within(live[kind], region) or not contains(region, args["loc"])
                or time.monotonic_ns() - stamp > OBSERVATION_LIMIT_NS):
            raise ValueError("native_uia_visual_observation_stale")
        element = self.control_from_point(*args["loc"])
        if (element is not None and element.ProcessId == self.scope["app_pid"]
                and element.IsEnabled and self._pattern(element)[0] is not None):
            raise ValueError("native_uia_target_available")
        target = wu.window_from_screen_point(*args["loc"])
        expected_classes = {"wxPanel", "wxWindowNR", "wxWindow"} if kind == "wx_sidebar" else {"wxGLCanvas"}
        if (not target or wu._window_pid(target) != self.scope["app_pid"]
                or wu.window_class(target) not in expected_classes
                or kind == "imgui_canvas" and target != self.canvas_hwnd):
            raise ValueError("native_uia_drawn_target_required")
        return kind, region

    def check(self, name, args):
        self.last_canvas_evidence, self.last_window, self.arguments_validated = None, {}, False
        validate_input(name, args, self.scope["output_path"], self.scope["scenario"])
        self.arguments_validated = True
        if name in {"ControlStatus", "Wait"}:
            return super().check(name, args)
        wu, hwnd = self.owned_foreground()
        if name == "Snapshot" and wu.window_title(hwnd) in SAVE_DIALOG_TITLES:
            from win32gui import GetAncestor
            if GetAncestor(hwnd, 3) != self.scope["hwnd"]:
                raise ValueError("native_uia_save_dialog_not_owned")
            self.scope["dialog_hwnd"] = hwnd
        if "dialog_hwnd" in self.scope and (hwnd == self.scope["dialog_hwnd"] or self.invoked):
            if (name in {"Click", "Type"} and "target" not in args) or name in {"Screenshot", "Shortcut"}:
                raise ValueError("native_uia_dialog_route_required")
            self.last_crop = None
            self.last_window = super().check(name, args)
            self.last_window["uia_save"] = True
            return self.last_window
        self.last_window = self._main_window(wu, hwnd)
        if name == "Snapshot":
            self.last_window["route"] = "uia_tree"
        elif "target" in args:
            if name == "Type" and args["text"] == self.scope["output_path"]:
                raise ValueError("native_path_requires_save_dialog")
            _, _, record = self._find_native(wu, hwnd, args)
            self.last_window.update(route="uia_value" if name == "Type" else "uia_action",
                target_hwnd=record["hwnd"], target_pid=self.scope["app_pid"],
                target_class=wu.window_class(record["hwnd"]), target=record["target"], pattern=record["pattern"])
        elif name == "Screenshot" or "loc" in args:
            role, region = self._visual_route(wu, hwnd, name, args)
            if name == "Type" and role != "imgui_canvas":
                raise ValueError("native_uia_canvas_visual_type_required")
            if name != "Screenshot":
                self.last_window = super().check(name, args)
            self.last_window.setdefault("route", "local_visual")
            self.last_window.update(visual_fallback=role, visual_region=region)
        else:
            self.last_window = super().check(name, args)
            self.last_window["route"] = "owned_command"
        return self.last_window

    def complete_view(self, arguments):
        self.last_crop = (self.last_window["visual_fallback"], arguments["region"], time.monotonic_ns())

    def perform(self, name, arguments):
        if self.last_window.get("uia_save"):
            return super().perform(name, arguments)
        wu, hwnd = self.owned_foreground()
        self._main_window(wu, hwnd)
        if name == "Snapshot":
            controls = self._native_controls(wu, hwnd)
            self.visual_regions = self._regions(wu)
            self.native_targets = {key: item[2] for key, item in controls.items()}
            self.last_window.update(native_targets=list(self.native_targets.values()), visual_regions=self.visual_regions)
            visible = []
            for element, implementation, record in controls.values():
                bounds = element.BoundingRectangle
                observed = {"target": record["target"], "bounds": [bounds.left, bounds.top, bounds.right, bounds.bottom]}
                if record["pattern"] == "ValuePattern":
                    observed["value"] = implementation.Value
                visible.append(observed)
            return {"controls": visible, "visual_regions": self.visual_regions}
        element, pattern, record = self._find_native(wu, hwnd, arguments)
        if record["hwnd"] != self.last_window["target_hwnd"]:
            raise ValueError("native_uia_target_changed")
        self.check_revocation()
        if name == "Type":
            value = arguments["text"]
            if not pattern.SetValue(value) or self._value(element).Value != value:
                raise ValueError("native_uia_value_readback_mismatch")
            self.last_window["readback_sha256"] = value_digest(value)
            wu, hwnd = self.owned_foreground()
            self._main_window(wu, hwnd)
            _, _, current = self._find_native(wu, hwnd, arguments)
            if current != record:
                raise ValueError("native_uia_target_changed")
            self.check_revocation()
            wu.msg_text(record["hwnd"], "\r")
            self.last_window["commit_backend"] = "uia_target_native_enter"
            return {"value": value, "pattern": "ValuePattern", "commit": "Enter delivered to the observed Edit"}
        if record["pattern"] == "InvokePattern":
            success = pattern.Invoke()
        else:
            success = pattern.Select()
        if not success:
            raise ValueError("native_uia_action_failed")
        return {"target": record["target"], "pattern": record["pattern"]}


def verify_hybrid_trace(trace, *, run_id, app_pid, main_hwnd, output_path, scenario):
    regions, crop, targets = {}, None, []
    counts = dict(uia_tree_calls=0, uia_actions=0, cropped_visual_calls=0, visual_inputs=0)
    for index, row in enumerate(trace):
        window, args, name = row["window"], row["arguments"], row["tool"]
        _require(row["seq"] == index + 1 and row["run_id"] == run_id and row["dispatched"] is True
                 and row["error"] is None, "native_uia_hybrid_identity")
        validate_input(name, args, output_path, scenario)
        if window.get("uia_save"):
            _require(counts["uia_tree_calls"] and window["foreground_hwnd"] != main_hwnd,
                     "native_uia_hybrid_main_not_observed")
            save = verify_uia_save(trace[index:], run_id=run_id, app_pid=app_pid,
                dialog_hwnd=window["foreground_hwnd"], output_path=output_path, first_seq=index + 1)
            return {"save_as": save, **counts}
        if name in {"ControlStatus", "Wait"}:
            continue
        _require(window.get("app_pid") == window.get("foreground_pid") == app_pid
                 and window.get("foreground_hwnd") == main_hwnd, "native_uia_hybrid_main_identity")
        if name == "Snapshot":
            _require(not args and window.get("route") == "uia_tree", "native_uia_tree_required")
            regions, targets = window["visual_regions"], window["native_targets"]
            counts["uia_tree_calls"] += 1
        elif name == "Screenshot":
            kind = window.get("visual_fallback")
            box = window.get("visual_region")
            _require(kind in {"imgui_canvas", "wx_sidebar"} and kind in regions
                     and box == args["region"] and within(regions[kind], box), "native_uia_cropped_proof")
            crop = (kind, box)
            counts["cropped_visual_calls"] += 1
        elif "loc" in args:
            _require(crop is not None and crop == (window.get("visual_fallback"), window.get("visual_region"))
                     and contains(crop[1], args["loc"])
                     and window.get("target_pid") == app_pid
                     and (name != "Type" or (crop[0] == "imgui_canvas" and window.get("route") == "canvas_numeric")),
                     "native_uia_visual_input_proof")
            counts["visual_inputs"] += 1
        elif "target" in args:
            _require({"target": args["target"], "hwnd": window["target_hwnd"], "pattern": window["pattern"]}
                     in targets and window["target_pid"] == app_pid, "native_uia_target_binding")
            if name == "Type":
                _require(window.get("route") == "uia_value" and window.get("pattern") == "ValuePattern"
                         and window.get("commit_backend") == "uia_target_native_enter"
                         and window.get("readback_sha256") == value_digest(args["text"]), "native_uia_value_readback")
            else:
                _require(window.get("route") == "uia_action"
                         and window.get("pattern") in {"InvokePattern", "SelectionItemPattern"}, "native_uia_action_proof")
            counts["uia_actions"] += 1
        elif name == "Shortcut":
            _require(window.get("route") == "owned_command", "native_uia_owned_command")
    _require(False, "native_uia_save_trace_missing")
