"""Synthetic evidence challenges; no guest, GUI or model calls."""
from copy import deepcopy
import hashlib
import json

import pytest

from harness.canvas_input import binding_to_json, decide_type
from harness.native_canvas_verify import verify_canvas_trace
from harness.script_verify import _InvalidEvidence
from unit_tests.test_canvas_input import evidence, observed_binding, window, OUTPUT, RUN

CONTRACT = "c" * 64


@pytest.fixture
def case(evidence):
    bound = observed_binding(evidence)
    scope = dict(run_id=RUN, contract_sha256=CONTRACT, scenario="canvas_trial", app_pid=123,
        hwnd=10, output_path=OUTPUT, canvas_binding_json=binding_to_json(bound),
        canvas_approval_profile=bound.approval_profile, canvas_diagnostic_sha256=bound.diagnostic_sha256,
        canvas_sut_sha256=bound.sut_sha256)
    setup = dict(run_id=RUN, contract_sha256=CONTRACT, binding=json.loads(binding_to_json(bound)),
                 evidence=deepcopy(evidence), pfd_verified=False, internal_numeric_field_verified=False)
    current = deepcopy(evidence)
    current.update(captured_monotonic_ns=2_000_000_000, observation_finished_ns=2_000_001_000)
    trace = [dict(run_id=RUN, seq=1, tool="Click", error=None, dispatched=True,
                  arguments={"loc": [450, 100]}, window=dict(target_hwnd=30, app_pid=123, foreground_pid=123,
                    target_pid=123, click_finished_monotonic_ns=1_500_000_000)),
             dict(run_id=RUN, seq=2, tool="Type", error=None, dispatched=True,
                  arguments={"loc": [450, 100], "text": "145.50"})]
    data = dict(scope=scope, setup=setup, trace=trace, observations={2: current}, bound=bound)
    fill_compact(data, 2)
    return data


def fill_compact(data, seq):
    row = data["trace"][seq - 1]; obs = data["observations"][seq]
    checked = obs["observation_finished_ns"] + 100
    target = next(w for w in obs["windows"] if w["hwnd"] == obs["target_hwnd"])
    decision = decide_type("pilot_transform", row["arguments"]["text"], row["arguments"]["loc"], obs,
                          output_path=OUTPUT, now_ns=checked, binding=data["bound"])
    row["window"] = dict(**decision, foreground_hwnd=obs["foreground_hwnd"], focus_hwnd=obs["focus_hwnd"],
        process_created=obs["process_created"], captured_monotonic_ns=obs["captured_monotonic_ns"],
        target_class=target["class"], target_title=target["title"],
        canvas_diagnostic_sha256=data["bound"].diagnostic_sha256,
        canvas_profile=data["bound"].approval_profile, pfd_index=0,
        pfd_verified=False, internal_numeric_field_verified=False, guard_checked_monotonic_ns=checked,
        observation_file=f"canvas_input_{seq}.json")
    refresh_hash(data, seq)


def refresh_hash(data, seq=2):
    raw = json.dumps(data["observations"][seq]).encode()
    data["trace"][seq - 1]["window"]["observation_sha256"] = hashlib.sha256(raw).hexdigest()


def verify(data, reader=None):
    def read(name, limit):
        assert name.startswith("canvas_input_") and limit == 2_000_000
        return json.dumps(data["observations"][int(name.removeprefix("canvas_input_").removesuffix(".json"))]).encode()
    return verify_canvas_trace(data["trace"], data["scope"], data["setup"], run_id=RUN,
                               contract_sha256=CONTRACT, read_artifact=reader or read)


def test_independent_canvas_evidence_passes_without_claiming_gl_or_field(case):
    result = verify(case)
    assert result["canvas_numeric_count"] == 1 and result["native_edit_count"] == 0
    assert result["pfd_verified"] is False and result["internal_numeric_field_verified"] is False
    json.dumps(result)


def test_legitimate_sidebar_layout_change_passes(case):
    case["observations"][2]["windows"][2]["rect"] = [100, 50, 1800, 1000]
    case["observations"][2]["windows"][2]["client_rect"] = [0, 0, 1700, 950]
    refresh_hash(case)
    assert verify(case)["canvas_numeric_count"] == 1


@pytest.mark.parametrize("target,key,value", [
    ("scope", "run_id", "b" * 32), ("setup", "contract_sha256", "d" * 64),
    ("scope", "canvas_approval_profile", "old-profile"),
    ("scope", "canvas_diagnostic_sha256", "b" * 64), ("scope", "canvas_sut_sha256", "b" * 64),
    ("setup", "pfd_verified", True), ("setup", "internal_numeric_field_verified", True),
    ("scope", "scenario", "pilot_transform"),
])
def test_scope_or_setup_forgery_rejected(case, target, key, value):
    case[target][key] = value
    with pytest.raises(_InvalidEvidence): verify(case)


@pytest.mark.parametrize("key,value", [("window_class", "Other"), ("window_title", "Other"),
    ("process_created", 9999), ("mode", "pfd"), ("hwnd", 20)])
def test_binding_cannot_be_replaced_in_both_records(case, key, value):
    binding = json.loads(case["scope"]["canvas_binding_json"])
    binding[key] = value
    case["scope"]["canvas_binding_json"] = json.dumps(binding)
    case["setup"]["binding"] = binding
    with pytest.raises(_InvalidEvidence): verify(case)


@pytest.mark.parametrize("fault", ["foreign", "ctime", "focus", "foreground", "main_rect", "title", "class",
                                   "parent", "desktop", "session", "stale", "reverse_time", "missing_finished"])
def test_hashed_but_invalid_raw_window_evidence_rejected(case, fault):
    obs = case["observations"][2]
    if fault == "foreign": obs["windows"][2]["pid"] = 456
    if fault == "ctime": obs["process_created"] = 9877
    if fault == "focus": obs["focus_hwnd"] = 20
    if fault == "foreground": obs["foreground_hwnd"] = 20
    if fault == "main_rect": obs["windows"][0]["rect"][2] = 1919
    if fault in {"title", "class"}: obs["windows"][2][fault] = "Other"
    if fault == "parent": obs["windows"][2]["parent"] = 10
    if fault == "desktop": obs["input_desktop"] = "Winlogon"
    if fault == "session": obs["active_session_id"] = 2
    if fault == "stale": case["trace"][1]["window"]["guard_checked_monotonic_ns"] += 1_000_000_000
    if fault == "reverse_time": obs["observation_finished_ns"] = 1
    if fault == "missing_finished": del obs["observation_finished_ns"]
    refresh_hash(case)
    with pytest.raises(_InvalidEvidence): verify(case)


@pytest.mark.parametrize("key,value", [("route", "native_edit"), ("target_hwnd", 20),
    ("canvas_profile", "old"), ("pfd_verified", True), ("internal_numeric_field_verified", True),
    ("observation_file", "../canvas_input_2.json"), ("observation_sha256", "b" * 64)])
def test_compact_receipt_cannot_override_raw_evidence(case, key, value):
    case["trace"][1]["window"][key] = value
    with pytest.raises(_InvalidEvidence): verify(case)


@pytest.mark.parametrize("fault", ["wrong_loc", "wrong_target", "foreign_pid", "old", "future", "failed", "not_dispatched"])
def test_prior_click_must_be_successful_matching_and_recent(case, fault):
    click = case["trace"][0]
    if fault == "wrong_loc": click["arguments"]["loc"] = [451, 100]
    if fault == "wrong_target": click["window"]["target_hwnd"] = 20
    if fault == "foreign_pid": click["window"]["target_pid"] = 456
    if fault == "old":
        case["observations"][2].update(captured_monotonic_ns=40_000_000_000, observation_finished_ns=40_000_001_000)
        fill_compact(case, 2)
    if fault == "future": click["window"]["click_finished_monotonic_ns"] = 50_000_000_000
    if fault == "failed": click["error"] = "failed"
    if fault == "not_dispatched": click["dispatched"] = False
    with pytest.raises(_InvalidEvidence): verify(case)


def test_click_receipt_is_one_use(case):
    case["trace"].append(deepcopy(case["trace"][1])); case["trace"][2]["seq"] = 3
    case["observations"][3] = deepcopy(case["observations"][2])
    case["observations"][3].update(captured_monotonic_ns=3_000_000_000, observation_finished_ns=3_000_001_000)
    fill_compact(case, 3)
    with pytest.raises(_InvalidEvidence, match="recent_click"): verify(case)


@pytest.mark.parametrize("key,value", [("clear", True), ("press_enter", True), ("caret_position", "end")])
def test_canvas_options_remain_narrow(case, key, value):
    case["trace"][1]["arguments"][key] = value
    with pytest.raises(_InvalidEvidence): verify(case)


def append_save_edit(case):
    case["trace"].append(deepcopy(case["trace"][1])); row = case["trace"][-1]
    row["seq"] = 3; row["arguments"]["text"] = OUTPUT
    obs = deepcopy(case["observations"][2]); case["observations"][3] = obs
    obs.update(captured_monotonic_ns=3_000_000_000, observation_finished_ns=3_000_001_000,
               foreground_hwnd=40, focus_hwnd=50, target_hwnd=50)
    dialog = window(40, 0, cls="#32770", rect=[200, 50, 1600, 900])
    dialog.update(title="Save file as", root_hwnd=40)
    edit = window(50, 40, cls="Edit", rect=[300, 80, 800, 150]); edit["root_hwnd"] = 40
    obs["windows"] += [dialog, edit]; obs["windows"][0]["enabled"] = False
    fill_compact(case, 3)


def test_native_save_as_edit_remains_allowed(case):
    append_save_edit(case)
    assert verify(case)["native_edit_count"] == 1


def test_edit_only_does_not_prove_canvas_capability(case):
    append_save_edit(case)
    case["trace"][1]["error"] = "rejected"; case["trace"][1]["dispatched"] = False
    with pytest.raises(_InvalidEvidence, match="path_not_exercised"): verify(case)


def test_artifact_callback_failure_propagates_as_invalid_evidence(case):
    def read(name, limit): raise OSError("missing")
    with pytest.raises(_InvalidEvidence): verify(case, read)
