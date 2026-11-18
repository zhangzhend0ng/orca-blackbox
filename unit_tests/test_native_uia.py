"""Pure UIA contract and evidence checks. No desktop calls."""
from copy import deepcopy
import sys
import time
from types import SimpleNamespace

import pytest

from harness.native_matrix import UIA_CANVAS_SCENARIO, UIA_LAYER_SCENARIO, UIA_SAVE_SCENARIO
from harness.native_save_policy import native_tools, scoped_tool_schemas, validate_input
from harness.native_uia import UiaSaveGuard, value_digest, verify_uia_save
from harness.native_uia_hybrid import UiaHybridGuard, verify_hybrid_trace

RUN = "a" * 32
OUTPUT = r"C:\owned\0001.3mf"
EDIT = {"control_type": "EditControl", "name": "File name:", "automation_id": "1001"}
SAVE = {"control_type": "ButtonControl", "name": "Save", "automation_id": "1"}


def test_save_scope_rejects_coordinates_screenshots_and_other_paths():
    jsonschema = pytest.importorskip("jsonschema")
    tools = [{"name": n, "inputSchema": {}} for n in native_tools(UIA_SAVE_SCENARIO)]
    schemas = {t["name"]: t["inputSchema"] for t in scoped_tool_schemas(tools, OUTPUT, UIA_SAVE_SCENARIO)}
    assert "Screenshot" not in schemas
    for name, args in (("Type", {"loc": [1, 2], "text": OUTPUT}),
                       ("Type", {"target": EDIT, "text": "other.3mf"}),
                       ("Click", {"target": {**SAVE, "hwnd": 5}}), ("Snapshot", {"use_vision": True})):
        with pytest.raises(ValueError):
            validate_input(name, args, OUTPUT, UIA_SAVE_SCENARIO)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(args, schemas[name])
    args = {"target": EDIT, "text": OUTPUT}
    jsonschema.validate(args, schemas["Type"])
    validate_input("Type", args, OUTPUT, UIA_SAVE_SCENARIO)


def fake_trace():
    controls = {"filename": {"target": EDIT, "hwnd": 11}, "save": {"target": SAVE, "hwnd": 12}}
    rows = [
        ("Snapshot", {}, {"route": "uia_tree", "controls": controls}),
        ("Type", {"target": EDIT, "text": OUTPUT}, {"route": "uia_value", "pattern": "ValuePattern",
            "target": EDIT, "target_hwnd": 11, "target_pid": 4, "target_class": "Edit",
            "readback_sha256": value_digest(OUTPUT), "native_edit_notified": True}),
        ("Click", {"target": SAVE}, {"route": "uia_invoke", "pattern": "InvokePattern",
            "target": SAVE, "target_hwnd": 12, "target_pid": 4, "target_class": "Button",
            "path_sha256": value_digest(OUTPUT)}),
        ("Snapshot", {}, {"route": "uia_tree", "dialog_closed": True, "foreground_hwnd": 20}),
    ]
    return deepcopy([dict(seq=i, run_id=RUN, tool=name, arguments=args, error=None, dispatched=True,
        window={"app_pid": 4, "foreground_pid": 4, "foreground_hwnd": 10, **details})
        for i, (name,args,details) in enumerate(rows, 1)])


@pytest.mark.parametrize("fault", [None, "changed_element", "no_readback", "foreign", "screen", "no_close"])
def test_save_trace_requires_the_observed_target_readback_and_invoke(fault):
    trace = fake_trace()
    if fault == "changed_element":
        trace[1]["window"]["target_hwnd"] = 99
    if fault == "no_readback":
        trace[1]["window"].pop("readback_sha256")
    if fault == "foreign":
        trace[2]["window"]["target_pid"] = 99
    if fault == "screen":
        trace[0]["tool"] = "Screenshot"
    if fault == "no_close":
        trace.pop()
    kwargs = dict(run_id=RUN, app_pid=4, dialog_hwnd=10, output_path=OUTPUT)
    if fault:
        with pytest.raises(ValueError):
            verify_uia_save(trace, **kwargs)
    else:
        assert verify_uia_save(trace, **kwargs)["screenshots"] == 0


def test_native_filename_edit_notification_stops_at_target_change(tmp_path, monkeypatch):
    record = {"hwnd": 11, "target": EDIT}
    current = dict(record)
    value = SimpleNamespace(Value=OUTPUT, IsReadOnly=False)
    edit = SimpleNamespace(GetValuePattern=lambda: value)
    messages = []

    def send(hwnd, message, wparam, lparam):
        messages.append((hwnd, message, wparam, lparam))
        if message == 0x0102:
            value.Value = value.Value[:-1]
            current["hwnd"] = 99

    guard = UiaSaveGuard({"app_pid": 4}, tmp_path, None)
    monkeypatch.setattr(guard, "owned_foreground", lambda: (SimpleNamespace(_send_msg=send), 10))
    monkeypatch.setattr(guard, "_dialog", lambda *_: None)
    monkeypatch.setattr(guard, "_controls", lambda *_: {"filename": (edit, current)})
    with pytest.raises(ValueError, match="native_uia_filename_target_changed"):
        guard._notify_filename_edit(edit, OUTPUT, record, 10)
    assert messages == [(11, 0x00B1, len(OUTPUT) - 1, len(OUTPUT)), (11, 0x0102, 8, 0)]


def test_hybrid_contract_rejects_whole_frames_and_path_by_location():
    with pytest.raises(ValueError, match="native_uia_crop_required"):
        validate_input("Screenshot", {}, OUTPUT, UIA_CANVAS_SCENARIO)
    with pytest.raises(ValueError, match="native_uia_canvas_arguments"):
        validate_input("Type", {"loc": [20, 30], "text": OUTPUT, "press_enter": True}, OUTPUT, UIA_CANVAS_SCENARIO)
    validate_input("Type", {"target": EDIT, "text": "0.24"}, OUTPUT, UIA_LAYER_SCENARIO)


def test_hybrid_schema_exposes_typed_properties_for_model_projection():
    jsonschema = pytest.importorskip("jsonschema")
    tools = [{"name": n, "inputSchema": {}} for n in native_tools(UIA_CANVAS_SCENARIO)]
    schemas = {t["name"]: t["inputSchema"] for t in scoped_tool_schemas(tools, OUTPUT, UIA_CANVAS_SCENARIO)}
    for name in ("Click", "Type"):
        assert schemas[name]["properties"]["loc"]["type"] == "array"
        assert schemas[name]["properties"]["target"]["type"] == "object"
    jsonschema.validate({"loc": [120, 480]}, schemas["Click"])
    jsonschema.validate({"target": SAVE}, schemas["Click"])
    jsonschema.validate({"target": EDIT, "text": OUTPUT}, schemas["Type"])
    jsonschema.validate({"loc": [120, 480], "text": "145.5", "press_enter": True}, schemas["Type"])
    jsonschema.validate({"region_name": "imgui_canvas"}, schemas["Screenshot"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"region_name": "desktop"}, schemas["Screenshot"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"loc": "[120,480]"}, schemas["Click"])


def test_drawn_canvas_click_uses_the_owned_input_guard(tmp_path, monkeypatch):
    scope = {"app_pid": 4, "hwnd": 20, "output_path": OUTPUT, "scenario": UIA_CANVAS_SCENARIO,
             "canvas_binding_json": '{"hwnd":21}'}
    guard = UiaHybridGuard(scope, tmp_path, None, None)
    api = SimpleNamespace(_window_pid=lambda _: 4, window_title=lambda _: "Orca",
                          window_from_screen_point=lambda *_: 21, window_class=lambda _: "wxGLCanvas")
    monkeypatch.setattr(guard, "owned_foreground", lambda: (api, 20))
    box = [100, 150, 900, 800]
    monkeypatch.setattr(guard, "_visual_route", lambda *_: ("imgui_canvas", box, box, 21))
    proof = guard.check("Click", {"loc": [120, 480]})
    assert proof["target_hwnd"] == 21 and proof["route"] == "local_visual"
    assert proof["visual_fallback"] == "imgui_canvas"


def test_named_crop_resolves_live_geometry_after_layout_changes(tmp_path, monkeypatch):
    scope = {"app_pid": 4, "hwnd": 20, "output_path": OUTPUT, "scenario": UIA_CANVAS_SCENARIO,
             "canvas_binding_json": '{"hwnd":21}'}
    guard = UiaHybridGuard(scope, tmp_path, None, None)
    api = SimpleNamespace(_window_pid=lambda _: 4, window_title=lambda _: "Orca")
    monkeypatch.setattr(guard, "owned_foreground", lambda: (api, 20))
    old, current = [400, 70, 1920, 1032], [460, 70, 1920, 1032]
    guard.visual_regions = {"imgui_canvas": old}
    guard.last_crop = ("imgui_canvas", old, old, time.monotonic_ns())
    guard._last_click = [500, 250]
    monkeypatch.setattr(guard, "_regions", lambda _: {"imgui_canvas": current})
    with pytest.raises(ValueError, match="native_uia_visual_region_not_observed"):
        guard.check("Screenshot", {"region": old})
    proof = guard.check("Screenshot", {"region_name": "imgui_canvas"})
    assert proof["visual_region"] == current and guard.capture_region() == current
    guard.complete_view()
    assert guard._last_click is None


def test_stale_crop_has_owned_predispatch_facts_and_foreign_target_stops(tmp_path, monkeypatch):
    scope = {"app_pid": 4, "hwnd": 20, "output_path": OUTPUT, "scenario": UIA_CANVAS_SCENARIO,
             "canvas_binding_json": '{"hwnd":21}'}
    guard = UiaHybridGuard(scope, tmp_path, None, lambda *_: None)
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(IsChild=lambda p, c: p == 20 and c == 21))
    api = SimpleNamespace(_window_pid=lambda _: 4, window_title=lambda _: "Orca",
                          window_from_screen_point=lambda *_: 21, window_class=lambda _: "wxGLCanvas")
    monkeypatch.setattr(guard, "owned_foreground", lambda: (api, 20))
    monkeypatch.setattr(guard, "_regions", lambda _: {"imgui_canvas": [400, 70, 1920, 1032]})
    guard._last_click = [500, 250]
    with pytest.raises(ValueError, match="native_uia_refresh_required"):
        guard.check("Type", {"loc": [500, 250], "text": "145.5", "press_enter": True})
    assert guard.last_window["refresh_reason"] == "stale_crop"
    assert guard.last_window["target_hwnd"] == 21 and guard.last_window["target_pid"] == 4
    assert guard._last_click is None
    api._window_pid = lambda hwnd: 4 if hwnd == 20 else 5
    with pytest.raises(ValueError, match="native_uia_drawn_target_not_owned"):
        guard.check("Click", {"loc": [500, 250]})
    assert "refresh_reason" not in guard.last_window


def test_owned_popup_is_read_only_and_requires_main_snapshot(tmp_path, monkeypatch):
    scope = {"app_pid": 4, "hwnd": 20, "output_path": OUTPUT, "scenario": UIA_CANVAS_SCENARIO,
             "canvas_binding_json": '{"hwnd":21}'}
    guard = UiaHybridGuard(scope, tmp_path, None, None)
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(
        GetAncestor=lambda hwnd, flag: 20 if hwnd == 30 and flag == 3 else 55,
        IsWindowVisible=lambda _: True))
    api = SimpleNamespace(_window_pid=lambda _: 4, window_title=lambda _: "Popup", window_class=lambda _: "wxWindow")
    monkeypatch.setattr(guard, "owned_foreground", lambda: (api, 30))
    assert guard.check("Snapshot", {})["route"] == "uia_popup"
    assert guard.perform("Snapshot", {})["popup"]["root_owner_hwnd"] == 20
    with pytest.raises(ValueError, match="native_uia_main_window_required"):
        guard.check("Click", {"loc": [500, 250]})
    monkeypatch.setattr(guard, "owned_foreground", lambda: (api, 20))
    with pytest.raises(ValueError, match="native_uia_main_observation_after_popup"):
        guard.check("Screenshot", {"region_name": "imgui_canvas"})
    monkeypatch.setattr(guard, "owned_foreground", lambda: (api, 31))
    with pytest.raises(ValueError, match="native_uia_popup_owner_unverified"):
        guard.check("Snapshot", {})


@pytest.mark.parametrize("box", [[2, 3, 40, 60], [0, 0, 1920, 1080]])
def test_hybrid_audits_crop_before_save_as(box):
    main = {"app_pid": 4, "foreground_pid": 4, "foreground_hwnd": 20}
    rows = [
        ("Snapshot", {}, {"route": "uia_tree", "visual_regions": {"wx_sidebar": [0, 0, 400, 900]},
                         "native_targets": []}),
        ("Screenshot", {"region": box}, {"visual_fallback": "wx_sidebar", "visual_region": box}),
    ]
    prefix = [dict(seq=i, tool=name, arguments=args, window={**main, **evidence},
                   run_id=RUN, dispatched=True, error=None)
              for i, (name, args, evidence) in enumerate(rows, 1)]
    suffix = fake_trace()
    for row in suffix:
        row["seq"] += len(prefix)
    suffix[0]["window"]["uia_save"] = True
    kwargs = dict(run_id=RUN, app_pid=4, main_hwnd=20, output_path=OUTPUT, scenario=UIA_LAYER_SCENARIO)
    if box[2] > 400:
        with pytest.raises(ValueError, match="native_uia_cropped_proof"):
            verify_hybrid_trace(prefix + suffix, **kwargs)
    else:
        assert verify_hybrid_trace(prefix + suffix, **kwargs)["cropped_visual_calls"] == 1
