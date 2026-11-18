"""Pure UIA contract and evidence checks. No desktop calls."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from harness.native_matrix import UIA_SAVE_SCENARIO
from harness.native_save_policy import native_tools, scoped_tool_schemas, validate_input
from harness.native_uia import UiaSaveGuard, value_digest, verify_uia_save

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
