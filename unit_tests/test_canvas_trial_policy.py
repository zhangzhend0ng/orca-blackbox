"""Pure trial authority challenges; no desktop APIs or actual field input."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from harness.native_save_policy import InputGuard, validate_input, scoped_tool_schemas, NATIVE_TOOLS
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
    with pytest.raises(ValueError,match="recent_click"): guard._canvas_trial_type({"loc":[450,100],"text":"145.5"})


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
