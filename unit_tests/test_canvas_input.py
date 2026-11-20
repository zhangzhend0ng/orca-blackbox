"""Synthetic window evidence only; never query the host desktop."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json

import pytest

from harness.canvas_input import (CanvasInputRejected, bind_canvas, collect_window_evidence,
                                  decide_type, numeric_text_allowed)

OUTPUT = r"C:\owned\projects\0001.3mf"
RUN = "a" * 32


def window(hwnd, parent, *, cls="SyntheticCanvas", rect=None, opengl=False):
    return {"hwnd": hwnd, "pid": 123, "thread_id": 55, "class": cls, "title": "",
            "parent": parent, "root_hwnd": 10, "is_main_child": hwnd != 10,
            "exists": True, "visible": True, "enabled": True, "dpi": 96,
            "rect": rect or [300, 50, 1800, 1000], "client_rect": [0, 0, 1500, 950],
            "pixel_format": {"index": 7 if opengl else 0, "describe_count": 20 if opengl else 0,
                             "flags": 0x25 if opengl else 0}}


@pytest.fixture
def evidence():
    return {"schema_version": 1, "run_id": RUN, "app_pid": 123, "process_created": 9876,
            "main_hwnd": 10, "session_id": 1, "active_session_id": 1,
            "thread_desktop": "SyntheticDesktop", "input_desktop": "SyntheticDesktop",
            "foreground_hwnd": 10, "focus_hwnd": 30, "target_hwnd": 30,
            "loc": [450, 100], "screen": [1920, 1080], "complete": True,
            "captured_monotonic_ns": 1_000_000_000,
            "windows": [window(10, 0, cls="Main", rect=[0, 0, 1920, 1040]),
                        window(20, 10, cls="Container"), window(30, 20, opengl=True)]}


def binding(e):
    return bind_canvas(e, 30, approved_class="SyntheticCanvas", diagnostic_id="reviewed-test-only")


def decide(e, b=None, text="145.50", scenario="pilot_transform", **kwargs):
    return decide_type(scenario, text, e["loc"], e, output_path=OUTPUT,
                       now_ns=1_000_000_010, binding=b, **kwargs)


def test_explicit_binding_and_current_focus_allow_transform_numeric(evidence):
    bound = binding(evidence)
    assert decide(evidence, bound)["route"] == "canvas_numeric"
    json.dumps(decide(evidence, bound))
    with pytest.raises(FrozenInstanceError):
        bound.hwnd = 99


def test_legal_canvas_layout_change_does_not_pin_sidebar_width(evidence):
    bound = binding(evidence)
    current = deepcopy(evidence)
    current["windows"][2]["rect"] = [100, 50, 1800, 1000]
    current["windows"][2]["client_rect"] = [0, 0, 1700, 950]
    current["loc"] = [150, 100]
    assert decide(current, bound, text="10")["route"] == "canvas_numeric"


@pytest.mark.parametrize("text", ["1", "10", "145.50", "999.9999", "0.0001"])
def test_transform_numeric_whitelist(text):
    assert numeric_text_allowed("pilot_transform", text)


@pytest.mark.parametrize("text", ["0", "0.0000", "1000", "-10", "+10", "1e2", "NaN", "01", "10\n", "10;calc", "١٤٥", True, 145])
def test_invalid_transform_numeric_text_is_rejected(text):
    assert not numeric_text_allowed("pilot_transform", text)


@pytest.mark.parametrize("scenario", ["base", "quality_a", "pilot_strength", "pilot_material"])
def test_other_scenarios_do_not_gain_three_digit_or_canvas_input(evidence, scenario):
    assert numeric_text_allowed(scenario, "99.9999")
    assert numeric_text_allowed(scenario, "0")
    assert not numeric_text_allowed(scenario, "145.50")
    with pytest.raises(CanvasInputRejected, match="binding_required"):
        decide(evidence, binding(evidence), text="10", scenario=scenario)


@pytest.mark.parametrize("fault,expected", [
    ("no_binding", "binding_required"), ("wrong_run", "run_binding"),
    ("pid_reused", "run_binding"), ("focus_other", "focus_or_foreground"),
    ("foreground_other", "focus_or_foreground"), ("foreign_pid", "not_owned"),
    ("changed_class", "window_binding"), ("changed_parent", "window_binding"),
    ("changed_parent_class", "window_binding"), ("changed_thread", "window_binding"),
    ("main_moved", "window_binding"), ("dpi", "geometry"),
    ("outside_main", "outside_main"), ("not_child", "window_binding"),
    ("lost_gl", "opengl_unproven"), ("lost_draw_flag", "opengl_unproven"),
    ("unavailable_pfd", "opengl_unproven"), ("session", "session"),
    ("desktop_locked", "input_desktop"), ("incomplete", "incomplete"),
    ("hidden", "not_owned"), ("disabled", "not_owned"), ("target_elsewhere", "target_rect"),
])
def test_current_evidence_changes_fail_closed(evidence, fault, expected):
    bound = binding(evidence)
    row = evidence["windows"][2]
    if fault == "no_binding": bound = None
    elif fault == "wrong_run": evidence["run_id"] = "b" * 32
    elif fault == "pid_reused": evidence["process_created"] += 1
    elif fault == "focus_other": evidence["focus_hwnd"] = 20
    elif fault == "foreground_other": evidence["foreground_hwnd"] = 20
    elif fault == "foreign_pid": row["pid"] = 999
    elif fault == "changed_class": row["class"] = "Other"
    elif fault == "changed_parent": row["parent"] = 10
    elif fault == "changed_parent_class": evidence["windows"][1]["class"] = "Other"
    elif fault == "changed_thread": row["thread_id"] += 1
    elif fault == "main_moved": evidence["windows"][0]["rect"][2] = 1919
    elif fault == "dpi": row["dpi"] = 120
    elif fault == "outside_main": row["rect"][2] = 2000
    elif fault == "not_child": row["is_main_child"] = False
    elif fault == "lost_gl": row["pixel_format"]["flags"] = 0x4
    elif fault == "lost_draw_flag": row["pixel_format"]["flags"] = 0x20
    elif fault == "unavailable_pfd": row["pixel_format"]["describe_count"] = 0
    elif fault == "session": evidence["active_session_id"] = 2
    elif fault == "desktop_locked": evidence["input_desktop"] = "Winlogon"
    elif fault == "incomplete": evidence["complete"] = False
    elif fault == "hidden": row["visible"] = False
    elif fault == "disabled": row["enabled"] = False
    elif fault == "target_elsewhere": evidence["loc"] = [250, 100]
    with pytest.raises(CanvasInputRejected, match=expected):
        decide(evidence, bound)


@pytest.mark.parametrize("approved", [None, "", "Guess", "Edit"])
def test_class_approval_is_explicit_and_exact(evidence, approved):
    with pytest.raises(CanvasInputRejected):
        bind_canvas(evidence, 30, approved_class=approved, diagnostic_id="d")


def test_plain_owned_nonedit_cannot_be_bound_without_gl_evidence(evidence):
    with pytest.raises(CanvasInputRejected, match="opengl_unproven"):
        bind_canvas(evidence, 20, approved_class="Container", diagnostic_id="d")


def test_binding_does_not_require_setup_to_focus_canvas(evidence):
    evidence["focus_hwnd"] = 20
    assert binding(evidence).hwnd == 30


def test_revocation_stale_observation_and_mismatched_hit_test_are_rejected(evidence):
    bound = binding(evidence)
    with pytest.raises(CanvasInputRejected, match="revoked"):
        decide(evidence, bound, revoked=True)
    with pytest.raises(CanvasInputRejected, match="stale"):
        decide_type("pilot_transform", "10", evidence["loc"], evidence, output_path=OUTPUT,
                    binding=bound, now_ns=2_000_000_001)
    with pytest.raises(CanvasInputRejected, match="location"):
        decide_type("pilot_transform", "10", [451, 100], evidence, output_path=OUTPUT,
                    binding=bound, now_ns=1_000_000_010)


def test_path_requires_native_save_as_edit_even_when_canvas_is_bound(evidence):
    with pytest.raises(CanvasInputRejected, match="binding_required"):
        decide(evidence, binding(evidence), text=OUTPUT)
    dialog = window(40, 0, cls="#32770", rect=[200, 50, 1600, 900])
    dialog["title"], dialog["root_hwnd"] = "Save file as", 40
    edit = window(50, 40, cls="Edit", rect=[300, 80, 800, 150])
    edit["root_hwnd"] = 40
    evidence["windows"] += [dialog, edit]
    evidence["windows"][0]["enabled"] = False  # Modal dialogs disable the main window.
    evidence.update(foreground_hwnd=40, focus_hwnd=50, target_hwnd=50)
    assert decide(evidence, text=OUTPUT)["route"] == "native_edit"
    dialog["title"] = "Open file"
    with pytest.raises(CanvasInputRejected, match="save_edit"):
        decide(evidence, text=OUTPUT)


def test_guest_gate_precedes_any_win32_call(monkeypatch):
    from harness import host_guard
    monkeypatch.setattr(host_guard, "in_guest", lambda: False)
    with pytest.raises(CanvasInputRejected, match="guest_only"):
        collect_window_evidence(RUN, 123, 10)


def observed_binding(e):
    from unit_tests.test_canvas_approval import approved
    a = approved()
    e["windows"][2].update({"class": a.window_class, "title": a.window_title,
                           "pixel_format": {"index": 0, "describe_count": 0, "flags": 0}})
    return bind_canvas(e, 30, approved_class=a.window_class, diagnostic_id=a.diagnostic_run_id, approval=a)


def test_parent_becoming_disabled_is_rejected_before_canvas_admission(evidence):
    b = binding(evidence)
    evidence["windows"][1]["enabled"] = False
    with pytest.raises(CanvasInputRejected, match="not_owned"):
        decide(evidence, b)
    with pytest.raises(CanvasInputRejected, match="not_owned"):
        binding(evidence)


def test_observed_mode_is_explicit_and_does_not_claim_pfd(evidence):
    from unit_tests.test_canvas_approval import approved
    b = observed_binding(evidence)
    assert decide(evidence, b)["approval_mode"] == "observed_wxglcanvas"
    assert evidence["windows"][2]["pixel_format"]["index"] == 0
    a = approved()
    with pytest.raises(CanvasInputRejected, match="opengl_unproven"):
        bind_canvas(evidence, 30, approved_class=a.window_class, diagnostic_id=a.diagnostic_run_id)


@pytest.mark.parametrize("key,value", [("class", "OtherCanvas"), ("title", "Other")])
def test_observed_class_or_title_drift_is_rejected(evidence, key, value):
    b = observed_binding(evidence)
    evidence["windows"][2][key] = value
    with pytest.raises(CanvasInputRejected): decide(evidence, b)


def test_observed_binding_cannot_be_given_a_different_review_id(evidence):
    from unit_tests.test_canvas_approval import approved
    a = approved(); observed_binding(evidence)
    with pytest.raises(CanvasInputRejected, match="observed_identity"):
        bind_canvas(evidence, 30, approved_class=a.window_class, diagnostic_id="other", approval=a)


def test_multiple_visible_observed_candidates_cannot_be_chosen_implicitly(evidence):
    from unit_tests.test_canvas_approval import approved
    a = approved(); observed_binding(evidence)
    other = deepcopy(evidence["windows"][2]); other["hwnd"] = 31
    evidence["windows"].append(other)
    with pytest.raises(CanvasInputRejected, match="candidate_ambiguous"):
        bind_canvas(evidence, 30, approved_class=a.window_class, diagnostic_id=a.diagnostic_run_id, approval=a)


def test_approval_does_not_unblock_transform_or_allow_save_path_to_canvas(evidence):
    from harness.native_pilots import require_pilot_ready
    b = observed_binding(evidence)
    with pytest.raises(RuntimeError, match="capability_blocked"): require_pilot_ready("pilot_transform")
    with pytest.raises(CanvasInputRejected): decide(evidence, b, text=OUTPUT)
    with pytest.raises(CanvasInputRejected): decide(evidence, b, scenario="pilot_material", text="10")


@pytest.mark.parametrize("observed", [False, True])
def test_binding_json_roundtrip_requires_independent_expected_scope(evidence, observed):
    from harness.canvas_input import binding_to_json, load_canvas_binding
    from unit_tests.test_canvas_approval import approved
    b = observed_binding(evidence) if observed else binding(evidence)
    raw = binding_to_json(b)
    a = approved() if observed else None
    got = load_canvas_binding(raw, run_id=RUN, app_pid=123, process_created=9876, main_hwnd=10, approval=a)
    assert got == b and type(got.parent_chain) is tuple and type(got.parent_chain[0]) is tuple
    assert decide(evidence, got)["route"] == "canvas_numeric"
    with pytest.raises(CanvasInputRejected, match="scope"):
        load_canvas_binding(raw, run_id="b"*32, app_pid=123, process_created=9876, main_hwnd=10, approval=a)


def test_observed_binding_json_needs_independent_approval(evidence):
    from harness.canvas_input import binding_to_json, load_canvas_binding
    raw = binding_to_json(observed_binding(evidence))
    with pytest.raises(CanvasInputRejected, match="approval_required"):
        load_canvas_binding(raw, run_id=RUN, app_pid=123, process_created=9876, main_hwnd=10)


@pytest.mark.parametrize("fault", ["extra", "missing", "bool_pid", "ctime", "broken_chain", "duplicate_chain",
                                 "float_rect", "bad_mode", "unknown_profile", "bool_version"])
def test_binding_json_cannot_change_identity_or_provenance(evidence, fault):
    from harness.canvas_input import binding_to_json, load_canvas_binding
    from unit_tests.test_canvas_approval import approved
    data = json.loads(binding_to_json(observed_binding(evidence)))
    if fault == "extra": data["surprise"] = 1
    elif fault == "missing": data.pop("desktop")
    elif fault == "bool_pid": data["app_pid"] = True
    elif fault == "ctime": data["process_created"] += 1
    elif fault == "broken_chain": data["parent_chain"][0][1] = 10
    elif fault == "duplicate_chain": data["parent_chain"].append(data["parent_chain"][0])
    elif fault == "float_rect": data["main_rect"][0] = 0.0
    elif fault == "bad_mode": data["mode"] = "automatic"
    elif fault == "unknown_profile": data["approval_profile"] = "any"
    elif fault == "bool_version": data["approval_version"] = True
    with pytest.raises(CanvasInputRejected):
        load_canvas_binding(json.dumps(data), run_id=RUN, app_pid=123, process_created=9876, main_hwnd=10, approval=approved())


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'NaN', b'{"x":Infinity}', b'{', b'0'*17000, b'\xff'])
def test_malformed_binding_json_is_rejected(raw):
    from harness.canvas_input import load_canvas_binding
    with pytest.raises(CanvasInputRejected):
        load_canvas_binding(raw, run_id=RUN, app_pid=123, process_created=9876, main_hwnd=10)
