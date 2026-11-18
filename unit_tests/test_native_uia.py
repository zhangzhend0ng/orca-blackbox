"""Pure UIA contract and evidence checks. No desktop calls."""
from copy import deepcopy

import pytest

from harness.native_matrix import UIA_SAVE_SCENARIO
from harness.native_save_policy import native_tools, scoped_tool_schemas, validate_input
from harness.native_uia import value_digest, verify_uia_save

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
            "readback_sha256": value_digest(OUTPUT)}),
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
