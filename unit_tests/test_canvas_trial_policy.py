"""Pure trial authority challenges; no desktop APIs or actual field input."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from harness.native_save_policy import InputGuard, validate_input, scoped_tool_schemas, NATIVE_TOOLS
from harness.native_diagnostic_recovery import COMMIT_SCENARIO
from harness.native_matrix import CANVAS_REPLACE_SCENARIO
from harness.canvas_input import binding_to_json
from unit_tests.test_canvas_input import evidence, observed_binding, OUTPUT, RUN
from unit_tests.test_canvas_approval import approved


@pytest.mark.parametrize("text", ["145.50", "999.9999", "0.0001"])
def test_trial_alone_gains_positive_three_digit_numeric(text):
    validate_input("Type", {"loc":[450,100], "text":text}, OUTPUT, "canvas_trial")
    if text.startswith("0."):
        return
    for scenario in ("base", "pilot_transform", "pilot_strength", "pilot_material3"):
        with pytest.raises(ValueError): validate_input("Type", {"loc":[450,100],"text":text}, OUTPUT, scenario)


@pytest.mark.parametrize("text", ["0", "0.0000", "1000", "-10", "145.5\n", "NaN", "01", "١٤٥"])
def test_trial_numeric_boundary_remains_closed(text):
    with pytest.raises(ValueError): validate_input("Type", {"loc":[450,100],"text":text}, OUTPUT, "canvas_trial")


@pytest.mark.parametrize("options", [{"clear":True},{"press_enter":True},{"caret_position":"start"},{"caret_position":"end"}])
def test_trial_minimal_options_are_enforced_in_schema_and_authority(options):
    jsonschema = pytest.importorskip("jsonschema")
    tools=[{"name":n,"inputSchema":{}} for n in NATIVE_TOOLS]
    schema=next(t["inputSchema"] for t in scoped_tool_schemas(tools,OUTPUT,"canvas_trial") if t["name"]=="Type")
    bad={"loc":[450,100],"text":"145.5",**options}
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(bad,schema)
    with pytest.raises(ValueError): validate_input("Type",bad,OUTPUT,"canvas_trial")
    # The assigned native SaveAs Edit retains its established options.
    good={**bad,"text":OUTPUT}
    jsonschema.validate(good,schema)
    validate_input("Type",good,OUTPUT,"canvas_trial")


@pytest.fixture
def trial(evidence, tmp_path, monkeypatch):
    binding=observed_binding(evidence);a=approved();clock=[1_000_000_010]
    scope={"run_id":RUN,"app_pid":123,"hwnd":10,"scenario":"canvas_trial","output_path":OUTPUT,
           "canvas_binding_json":binding_to_json(binding),"canvas_approval_profile":a.profile_id,
           "canvas_diagnostic_sha256":a.diagnostic_sha256,"canvas_sut_sha256":a.sut_sha256}
    guard=InputGuard(scope,tmp_path)
    def collect(*args):
        current=deepcopy(evidence);current["captured_monotonic_ns"]=clock[0]-10
        return current
    monkeypatch.setattr("harness.canvas_input.collect_window_evidence",collect)
    monkeypatch.setattr("time.monotonic_ns",lambda:clock[0])
    return guard,clock,evidence,tmp_path


def test_recent_click_token_is_same_target_single_use_and_not_a_field_proof(trial):
    guard,_,_,_=trial
    guard.last_window={"target_hwnd":30};guard.record_click([450,100])
    result=guard._canvas_trial_type({"loc":[450,100],"text":"145.5"})
    assert result["route"]=="canvas_numeric" and result["internal_numeric_field_verified"] is False
    assert "windows" not in result and guard.last_canvas_evidence["windows"]
    with pytest.raises(ValueError,match="^native_canvas_trial_recent_click_required$"):
        guard._canvas_trial_type({"loc":[450,100],"text":"145.5"})


@pytest.mark.parametrize("fault", ["absent","expired","wrong_loc","other_hwnd","changed_focus","revoked"])
def test_click_and_environment_failures_do_not_authorize_canvas_type(trial,fault):
    guard,clock,evidence,root=trial
    if fault!="absent":
        guard.last_window={"target_hwnd":20 if fault=="other_hwnd" else 30}
        guard.record_click([451,100] if fault=="wrong_loc" else [450,100])
    if fault=="expired":clock[0]+=30_000_000_001
    if fault=="changed_focus":evidence["focus_hwnd"]=20
    if fault=="revoked":(root/"input_revoked").touch()
    with pytest.raises(ValueError):guard._canvas_trial_type({"loc":[450,100],"text":"145.5"})


def test_actual_checked_in_diagnostic_bytes_match_the_approval():
    path=Path(__file__).resolve().parents[1]/"contracts/evidence/canvas-diagnostic-bb64.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest()==approved().diagnostic_sha256


@pytest.mark.parametrize("scenario,clear,text", [
    (COMMIT_SCENARIO, True, "0.24"), (CANVAS_REPLACE_SCENARIO, False, "145.5"),
])
def test_commit_options_match_advertised_type_schema(scenario, clear, text):
    jsonschema = pytest.importorskip("jsonschema")
    tools = [{"name": name, "inputSchema": {}} for name in NATIVE_TOOLS]
    schema = next(tool["inputSchema"] for tool in scoped_tool_schemas(tools, OUTPUT, scenario)
                  if tool["name"] == "Type")
    args = {"loc": [450, 100], "text": text, "clear": clear, "press_enter": True}
    jsonschema.validate(args, schema)
    validate_input("Type", args, OUTPUT, scenario)
    for bad in [dict(args, press_enter=False), dict(args, caret_position="start"), dict(args, clear=not clear)]:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)
        with pytest.raises(ValueError, match="native_numeric_type_options"):
            validate_input("Type", bad, OUTPUT, scenario)
    save = dict(args, text=OUTPUT, clear=True)
    jsonschema.validate(save, schema)
    validate_input("Type", save, OUTPUT, scenario)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(save, clear=False), schema)
    with pytest.raises(ValueError, match="native_save_path_requires_clear"):
        validate_input("Type", dict(save, clear=False), OUTPUT, scenario)


def test_replace_accepts_one_click_and_rechecks_before_each_key(trial):
    from tools.native_save_server import send_canvas_number

    guard, _, evidence, _ = trial
    guard.scope["scenario"] = CANVAS_REPLACE_SCENARIO
    args = {"loc": [450, 100], "text": "145.5", "press_enter": True}
    guard.last_window = {"target_hwnd": 30}
    guard.record_click(args["loc"], clicks=2)
    with pytest.raises(ValueError, match="recent_click"):
        guard._canvas_trial_type(args)
    guard.record_click(args["loc"])
    guard._canvas_trial_type(args)
    keys = []
    send_canvas_number(guard, args, lambda key, **_: keys.append(key))
    assert keys == [*"145.5", "{Enter}"]

    keys.clear()
    def lose_focus(key, **_):
        keys.append(key)
        evidence["focus_hwnd"] = 20

    with pytest.raises(ValueError, match="canvas_focus_or_foreground_changed"):
        send_canvas_number(guard, args, lose_focus)
    assert keys == ["1"]
