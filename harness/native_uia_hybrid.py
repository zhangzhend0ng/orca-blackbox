"""Owned UIA targets with narrowly scoped visual fallback for Orca's drawn UI."""
import json
import time
from dataclasses import dataclass

from .agent_verify import _require
from .native_matrix import UIA_DISTURBANCE_SCENARIO
from .native_save_policy import INPUT_TOOLS, InputGuard, UIA_VISUAL_REGIONS, validate_input, validate_uia_selector
from .native_uia import SAVE_DIALOG_TITLES, UiaSaveGuard, value_digest, verify_uia_save

OBSERVATION_LIMIT_NS = 30_000_000_000
UIA_REFRESH_ACTIONS = {
    "EditControl": ("Type", "ValuePattern"),
    "ButtonControl": ("Click", "InvokePattern"),
    "MenuItemControl": ("Click", "InvokePattern"),
    "TabItemControl": ("Click", "SelectionItemPattern"),
}


def within(bounds, rect):
    return (bounds[0] <= rect[0] < rect[2] <= bounds[2]
            and bounds[1] <= rect[1] < rect[3] <= bounds[3])


def contains(rect, loc):
    return rect[0] <= loc[0] < rect[2] and rect[1] <= loc[1] < rect[3]


def selector_key(target):
    return target["control_type"], target["name"], target["automation_id"]


@dataclass(frozen=True)
class VisualCrop:
    crop_id: int
    region: list[int]
    anchor: list[int]
    taken_at_ns: int


class UiaHybridGuard(UiaSaveGuard):
    def __init__(self, scope, root, control_from_handle, control_from_point):
        super().__init__(scope, root, control_from_handle)
        self.control_from_point = control_from_point
        self.native_targets = {}
        self.visual_regions = {}
        self.crops = {}
        self.crop_id = 0
        self.canvas_click_crop = None
        self.needs_main_snapshot = False
        self.needs_uia_snapshot = False
        self.canvas_hwnd = json.loads(scope["canvas_binding_json"])["hwnd"]
        self.prepared_dialog = scope.get("dialog_hwnd") if scope["scenario"] == UIA_DISTURBANCE_SCENARIO else None
        self.allow_cancel = self.prepared_dialog is not None
        self.cancel_invoked = False

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
        desktop = [0, 0, 1920, 1080]
        if not within(desktop, scene) or scene == desktop or not 0 <= left <= 800:
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

    def _popup(self, wu, hwnd):
        from win32gui import GetAncestor, IsWindowVisible

        main = self.scope["hwnd"]
        pid = wu._window_pid(hwnd)
        if hwnd == main or pid != self.scope["app_pid"]:
            raise ValueError("native_uia_popup_owner_unverified")
        root_owner = GetAncestor(hwnd, 3)
        proof = {"hwnd": hwnd, "root_owner_hwnd": root_owner,
                 "class": wu.window_class(hwnd), "name": wu.window_title(hwnd)}
        if root_owner != main or not IsWindowVisible(hwnd):
            self.last_window.update(app_pid=self.scope["app_pid"], foreground_pid=pid,
                                    foreground_hwnd=hwnd, unapproved_popup=proof)
            raise ValueError("native_uia_popup_owner_unverified")
        return proof

    def _clear_visual(self):
        self.crops.clear()
        self.canvas_click_crop = self._last_click = None

    def _discard_changed_crops(self, regions):
        self.crops = {role: crop for role, crop in self.crops.items() if regions.get(role) == crop.anchor}
        if self.canvas_click_crop is not None and regions.get("imgui_canvas") != self.canvas_click_crop[1].anchor:
            self.canvas_click_crop = self._last_click = None

    def _refresh_visual(self, target, target_class, reason, hint):
        self.last_window.update(target_hwnd=target, target_pid=self.scope["app_pid"], target_class=target_class,
                                refresh_reason=reason, refresh_hint=hint)
        self._clear_visual()
        self.native_targets, self.visual_regions = {}, {}
        self.needs_uia_snapshot = reason == "uia_target_available"
        raise ValueError("native_uia_refresh_required")

    def _visual_route(self, wu, hwnd, name, args):
        self._main_window(wu, hwnd)
        live = self._regions(wu)
        if name == "Screenshot":
            named = args["region_name"]
            if named not in live:
                raise ValueError("native_uia_visual_region_not_observed")
            return named, live[named], live[named], None, None
        from win32gui import IsChild

        matches = [kind for kind, box in live.items() if contains(box, args["loc"])]
        if len(matches) != 1:
            raise ValueError("native_uia_drawn_target_required")
        kind = matches[0]
        if name == "Type" and kind != "imgui_canvas":
            raise ValueError("native_uia_canvas_visual_type_required")
        target = wu.window_from_screen_point(*args["loc"])
        if not target or wu._window_pid(target) != self.scope["app_pid"] or not IsChild(hwnd, target):
            raise ValueError("native_uia_drawn_target_not_owned")
        target_class = wu.window_class(target)
        element = self.control_from_point(*args["loc"])
        if element is not None and element.ProcessId != self.scope["app_pid"]:
            raise ValueError("native_uia_drawn_target_not_owned")
        pattern = self._pattern(element)[0] if element is not None and element.IsEnabled else None
        if pattern is not None:
            selector = {"control_type": element.ControlTypeName, "name": element.Name or "",
                        "automation_id": element.AutomationId or ""}
            record = self._native_controls(wu, hwnd).get(selector_key(selector))
            if record is not None and element.NativeWindowHandle == target and record[2]["hwnd"] == target:
                tool, expected_pattern = UIA_REFRESH_ACTIONS[selector["control_type"]]
                if pattern == expected_pattern == record[2]["pattern"]:
                    self._refresh_visual(target, target_class, "uia_target_available",
                                         {"tool": tool, "target": record[2]["target"], "pattern": pattern})
            raise ValueError("native_uia_target_available")
        expected_classes = {"wxPanel", "wxWindowNR", "wxWindow", "wxDataView"} if kind == "wx_sidebar" else {"wxGLCanvas"}
        if target_class not in expected_classes or kind == "imgui_canvas" and target != self.canvas_hwnd:
            raise ValueError("native_uia_drawn_target_required")
        if name == "Type":
            click = self.canvas_click_crop
            crop = click[1] if click is not None and click[0] == tuple(args["loc"]) else None
        else:
            crop = self.crops.get(kind)
        if (crop is None or crop.anchor != live[kind] or not contains(crop.region, args["loc"])
                or not 0 <= time.monotonic_ns() - crop.taken_at_ns <= OBSERVATION_LIMIT_NS):
            self._refresh_visual(target, target_class, "stale_crop", {"region_name": kind})
        return kind, crop.region, live[kind], target, crop

    def check(self, name, args):
        self.last_canvas_evidence, self.last_window, self.arguments_validated = None, {}, False
        validate_input(name, args, self.scope["output_path"], self.scope["scenario"])
        if name == "Screenshot" and set(args) != {"region_name"}:
            raise ValueError("native_uia_named_crop_required")
        self.arguments_validated = True
        if name in {"ControlStatus", "Wait"}:
            return super().check(name, args)
        wu, hwnd = self.owned_foreground()
        if self.needs_uia_snapshot and name in INPUT_TOOLS:
            raise ValueError("native_uia_snapshot_required_for_target_hint")
        if self.prepared_dialog is not None and self.allow_cancel:
            if not self.cancel_invoked:
                self._dialog(hwnd, wu)
                self.last_window = dict(route="uia_tree", prepared_dialog=True, app_pid=self.scope["app_pid"],
                    foreground_pid=self.scope["app_pid"], foreground_hwnd=hwnd)
                if name == "Click" and "target" in args:
                    _, record = self._prepared_cancel(wu, hwnd, args)
                    self.last_window.update(route="uia_cancel", target=record["target"], target_hwnd=record["hwnd"],
                                            target_pid=self.scope["app_pid"], pattern="InvokePattern")
                elif name != "Snapshot":
                    raise ValueError("native_uia_prepared_dialog_requires_cancel")
                return self.last_window
            from win32gui import IsWindowVisible
            if name != "Snapshot" or hwnd != self.scope["hwnd"] or IsWindowVisible(self.prepared_dialog):
                raise ValueError("native_uia_prepared_dialog_closure_required")
            self.allow_cancel = False
            self.last_window["prepared_dialog_closed"] = True
        if name == "Snapshot" and wu.window_title(hwnd) in SAVE_DIALOG_TITLES:
            from win32gui import GetAncestor
            if GetAncestor(hwnd, 3) != self.scope["hwnd"]:
                raise ValueError("native_uia_save_dialog_not_owned")
            self.scope["dialog_hwnd"] = hwnd
        if "dialog_hwnd" in self.scope and (hwnd == self.scope["dialog_hwnd"] or self.invoked):
            if (name in {"Click", "Type"} and "target" not in args) or name in {"Screenshot", "Shortcut"}:
                raise ValueError("native_uia_dialog_route_required")
            self._clear_visual()
            self.last_window = super().check(name, args)
            self.last_window["uia_save"] = True
            return self.last_window
        named_observation = name == "Screenshot" and "region_name" in args
        if (name == "Snapshot" or named_observation) and hwnd != self.scope["hwnd"]:
            popup = self._popup(wu, hwnd)
            self._clear_visual()
            self.native_targets, self.visual_regions = {}, {}
            self.needs_main_snapshot = True
            self.last_window.update(route="uia_popup", app_pid=self.scope["app_pid"],
                foreground_hwnd=hwnd, foreground_pid=wu._window_pid(hwnd), popup=popup)
            return self.last_window
        self.last_window.update(self._main_window(wu, hwnd))
        if self.needs_main_snapshot and name != "Snapshot":
            raise ValueError("native_uia_main_observation_after_popup")
        if name == "Snapshot":
            self.last_window["route"] = "uia_tree"
        elif "target" in args:
            self._clear_visual()
            if name == "Type" and args["text"] == self.scope["output_path"]:
                raise ValueError("native_path_requires_save_dialog")
            _, _, record = self._find_native(wu, hwnd, args)
            self.last_window.update(route="uia_value" if name == "Type" else "uia_action",
                target_hwnd=record["hwnd"], target_pid=self.scope["app_pid"],
                target_class=wu.window_class(record["hwnd"]), target=record["target"], pattern=record["pattern"])
        elif name == "Screenshot" or "loc" in args:
            role, region, anchor, target, crop = self._visual_route(wu, hwnd, name, args)
            if name != "Screenshot":
                self.last_window = InputGuard.check(self, name, args)
                if self.last_window["foreground_hwnd"] != hwnd or self.last_window["target_hwnd"] != target:
                    raise ValueError("native_uia_visual_target_changed")
                self.last_window["visual_crop_id"] = crop.crop_id
                # Mutations consume all visual observations. The InputGuard only
                # records a real click after successful Windows-MCP dispatch.
                self._clear_visual()
                if name == "Click" and role == "imgui_canvas":
                    self.canvas_click_crop = (tuple(args["loc"]), crop)
            self.last_window.setdefault("route", "local_visual")
            self.last_window.update(visual_fallback=role, visual_region=region, visual_anchor_region=anchor)
            if "region_name" in args:
                self.last_window["visual_region_name"] = args["region_name"]
        else:
            self.last_window = super().check(name, args)
            self._clear_visual()
            self.last_window["route"] = "owned_command"
        return self.last_window

    def capture_region(self):
        wu, hwnd = self.owned_foreground()
        self._main_window(wu, hwnd)
        role = self.last_window["visual_fallback"]
        live = self._regions(wu)
        self._discard_changed_crops(live)
        if live.get(role) != self.last_window["visual_anchor_region"]:
            raise ValueError("native_uia_visual_anchor_changed")
        self.last_window["visual_live_regions"] = live
        return self.last_window["visual_region"]

    def complete_view(self):
        region = self.capture_region()
        role = self.last_window["visual_fallback"]
        anchor = self.last_window["visual_anchor_region"]
        self.crop_id += 1
        self.crops[role] = VisualCrop(self.crop_id, region, anchor, time.monotonic_ns())
        self.last_window["visual_crop_id"] = self.crop_id

    def _prepared_cancel(self, wu, hwnd, arguments):
        element, record = self._controls(wu, hwnd).get("cancel", (None, None))
        if record is None or record != self.observed.get("cancel") or arguments["target"] != record["target"]:
            raise ValueError("native_uia_prepared_cancel_target_not_observed")
        return element, record

    def perform(self, name, arguments):
        if self.last_window.get("prepared_dialog"):
            if name == "Snapshot":
                return super().perform(name, arguments)
            wu, hwnd = self.owned_foreground()
            self._dialog(hwnd, wu)
            element, record = self._prepared_cancel(wu, hwnd, arguments)
            if record["hwnd"] != self.last_window["target_hwnd"]:
                raise ValueError("native_uia_target_changed")
            self.check_revocation()
            invoke = element.GetInvokePattern()
            if invoke is None or not invoke.Invoke():
                raise ValueError("native_uia_prepared_cancel_failed")
            self.cancel_invoked = True
            return {"target": record["target"], "pattern": "InvokePattern", "invoked": True}
        if self.last_window.get("uia_save"):
            return super().perform(name, arguments)
        wu, hwnd = self.owned_foreground()
        if self.last_window.get("route") == "uia_popup":
            popup = self._popup(wu, hwnd)
            if popup != self.last_window["popup"]:
                raise ValueError("native_uia_popup_changed")
            return {"popup": popup, "controls": [], "visual_regions": {},
                    "state": "Owned popup is read-only. Wait for it to close, then Snapshot the main window."}
        self._main_window(wu, hwnd)
        if name == "Snapshot":
            controls = self._native_controls(wu, hwnd)
            self.visual_regions = self._regions(wu)
            self._discard_changed_crops(self.visual_regions)
            self.native_targets = {key: item[2] for key, item in controls.items()}
            self.needs_main_snapshot = False
            self.needs_uia_snapshot = False
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


def verify_hybrid_trace(trace, *, run_id, app_pid, main_hwnd, output_path, scenario, prepared_dialog=None,
                        allow_refresh=False, strict_crop_lifetime=False, named_crops_only=False):
    regions, crop, targets = {}, None, []
    crops, canvas_click = {}, None
    popup_open = pending_uia_snapshot = False
    counts = dict(uia_tree_calls=0, uia_actions=0, cropped_visual_calls=0, visual_inputs=0)
    cancel, cancelled, closed = None, False, prepared_dialog is None
    _require((scenario == UIA_DISTURBANCE_SCENARIO) == (prepared_dialog is not None), "native_uia_prepared_dialog_contract")
    for index, row in enumerate(trace):
        window, args, name = row["window"], row["arguments"], row["tool"]
        _require(row["seq"] == index + 1 and row["run_id"] == run_id, "native_uia_hybrid_identity")
        validate_input(name, args, output_path, scenario)
        _require(not named_crops_only or name != "Screenshot" or set(args) == {"region_name"},
                 "native_uia_named_crop_required")
        if allow_refresh and row.get("error_code") == "native_uia_refresh_required":
            _require(closed and not popup_open and name in {"Click", "Type"} and "loc" in args
                     and not pending_uia_snapshot
                     and row["dispatched"] is False and (row.get("recovery") or {}).get("decision") == "recoverable"
                     and window.get("app_pid") == window.get("foreground_pid") == window.get("target_pid") == app_pid
                     and window.get("foreground_hwnd") == main_hwnd and window.get("target_hwnd", 0) > 0
                     and window.get("refresh_reason") in {"stale_crop", "uia_target_available"},
                     "native_uia_refresh_binding")
            hint = window.get("refresh_hint")
            if hint is not None:
                _require(type(hint) is dict, "native_uia_refresh_hint")
                if window["refresh_reason"] == "uia_target_available":
                    target = hint.get("target")
                    kind = target.get("control_type") if type(target) is dict else None
                    _require(set(hint) == {"tool", "target", "pattern"} and type(kind) is str
                             and UIA_REFRESH_ACTIONS.get(kind) == (hint["tool"], hint["pattern"]),
                             "native_uia_refresh_hint")
                    validate_uia_selector(target, kind)
                    pending_uia_snapshot = True
                else:
                    _require(set(hint) == {"region_name"} and hint["region_name"] in UIA_VISUAL_REGIONS,
                             "native_uia_refresh_hint")
            regions, crop, targets = {}, None, []
            crops.clear()
            canvas_click = None
            continue
        _require(row["dispatched"] is True and row["error"] is None, "native_uia_hybrid_identity")
        _require(not pending_uia_snapshot or name not in INPUT_TOOLS, "native_uia_snapshot_required_for_target_hint")
        if window.get("prepared_dialog"):
            _require(not closed and not cancelled and window.get("foreground_hwnd") == prepared_dialog
                     and window.get("app_pid") == window.get("foreground_pid") == app_pid,
                     "native_uia_prepared_dialog_binding")
            if name == "Snapshot":
                cancel = window["controls"]["cancel"]
            else:
                _require(name == "Click" and window.get("route") == "uia_cancel" and window.get("pattern") == "InvokePattern"
                         and window.get("target_pid") == app_pid and cancel == {"target": args["target"], "hwnd": window["target_hwnd"]},
                         "native_uia_prepared_cancel_proof")
                cancelled = True
            continue
        if window.get("prepared_dialog_closed"):
            _require(not closed and cancelled and name == "Snapshot" and window["foreground_hwnd"] == main_hwnd,
                     "native_uia_prepared_dialog_closure_proof")
            closed = True
        if name in {"ControlStatus", "Wait"}:
            continue
        _require(closed, "native_uia_prepared_dialog_not_closed")
        if window.get("uia_save"):
            _require(not pending_uia_snapshot and counts["uia_tree_calls"] and window["foreground_hwnd"] != main_hwnd,
                     "native_uia_hybrid_main_not_observed")
            save = verify_uia_save(trace[index:], run_id=run_id, app_pid=app_pid,
                dialog_hwnd=window["foreground_hwnd"], output_path=output_path, first_seq=index + 1)
            return {"save_as": save, **counts}
        if window.get("route") == "uia_popup":
            popup, hwnd = window["popup"], window["foreground_hwnd"]
            observation = (name == "Snapshot" and not args) or (name == "Screenshot" and "region_name" in args)
            _require(observation and type(hwnd) is int and hwnd > 0 and hwnd != main_hwnd
                     and window.get("app_pid") == window.get("foreground_pid") == app_pid
                     and popup.get("hwnd") == hwnd and popup.get("root_owner_hwnd") == main_hwnd
                     and type(popup.get("class")) is str and popup["class"], "native_uia_popup_binding")
            regions, crop, targets = {}, None, []
            crops.clear()
            canvas_click = None
            popup_open = True
            continue
        _require(window.get("app_pid") == window.get("foreground_pid") == app_pid
                 and window.get("foreground_hwnd") == main_hwnd, "native_uia_hybrid_main_identity")
        _require(not popup_open or name == "Snapshot", "native_uia_main_observation_after_popup")
        if name == "Snapshot":
            _require(not args and window.get("route") == "uia_tree", "native_uia_tree_required")
            regions, targets = window["visual_regions"], window["native_targets"]
            if strict_crop_lifetime:
                crops = {role: record for role, record in crops.items() if regions.get(role) == record[3]}
                if canvas_click is not None and regions.get("imgui_canvas") != canvas_click[1][3]:
                    canvas_click = None
            popup_open = False
            pending_uia_snapshot = False
            counts["uia_tree_calls"] += 1
        elif name == "Screenshot":
            kind = window.get("visual_fallback")
            box = window.get("visual_region")
            if "region_name" in args:
                _require(kind == args["region_name"] == window.get("visual_region_name")
                         and type(box) is list and len(box) == 4 and all(type(side) is int for side in box)
                         and box == window.get("visual_anchor_region") and within([0, 0, 1920, 1080], box)
                         and (box[0] == 0 < box[2] <= 800 if kind == "wx_sidebar" else box[0] <= 800)
                         and box != [0, 0, 1920, 1080], "native_uia_named_cropped_proof")
            else:
                _require(kind in UIA_VISUAL_REGIONS and kind in regions and box == args["region"]
                         and within(regions[kind], box), "native_uia_cropped_proof")
            if strict_crop_lifetime:
                live = window.get("visual_live_regions")
                anchor = window.get("visual_anchor_region")
                crop_id = window.get("visual_crop_id")
                _require(type(crop_id) is int and crop_id == counts["cropped_visual_calls"] + 1
                         and type(live) is dict and live.get(kind) == anchor and isinstance(anchor, list)
                         and within(anchor, box), "native_uia_crop_lifetime_proof")
                crops = {role: record for role, record in crops.items() if live.get(role) == record[3]}
                if canvas_click is not None and live.get("imgui_canvas") != canvas_click[1][3]:
                    canvas_click = None
                crops[kind] = (kind, crop_id, box, anchor)
            else:
                crop = (kind, box)
            counts["cropped_visual_calls"] += 1
        elif "loc" in args:
            kind = window.get("visual_fallback")
            if strict_crop_lifetime:
                if name == "Type":
                    _require(canvas_click is not None and canvas_click[0] == args["loc"], "native_uia_visual_click_proof")
                    expected = canvas_click[1]
                else:
                    expected = crops.get(kind)
                _require(expected == (kind, window.get("visual_crop_id"), window.get("visual_region"),
                                      window.get("visual_anchor_region")), "native_uia_crop_lifetime_proof")
                crop = (expected[0], expected[2])
                crops.clear()
                canvas_click = (args["loc"], expected) if name == "Click" and kind == "imgui_canvas" else None
            _require(crop is not None and crop == (window.get("visual_fallback"), window.get("visual_region"))
                     and contains(crop[1], args["loc"])
                     and window.get("target_pid") == app_pid
                     and (name != "Type" or (crop[0] == "imgui_canvas" and window.get("route") == "canvas_numeric")),
                     "native_uia_visual_input_proof")
            counts["visual_inputs"] += 1
        elif "target" in args:
            crops.clear()
            canvas_click = None
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
            crops.clear()
            canvas_click = None
    _require(False, "native_uia_save_trace_missing")
