"""Synthetic authority receipts only; no native agent or GUI execution."""
from copy import deepcopy

import pytest

from harness.native_recovery import RecoveryGate, RecoveryViolation, audit_trace

RUN = "a" * 32


def denial(seq=1):
    return {"run_id": RUN, "seq": seq, "tool": "Type",
            "error": "ValueError:native_type_requires_owned_edit",
            "error_code": "native_type_requires_owned_edit", "dispatched": False,
            "arguments": {"text": "10", "loc": [400, 200]},
            "window": {"app_pid": 20, "foreground_pid": 20, "target_pid": 20,
                       "foreground_hwnd": 30, "target_hwnd": 40, "target_class": "Canvas"}}


def success(seq, tool):
    return {"run_id": RUN, "seq": seq, "tool": tool, "error": None, "dispatched": True}


def trace_with_recovery():
    row = denial()
    row["recovery"] = RecoveryGate(RUN, enabled=True).reject(row)
    return [row, success(2, "Screenshot"), success(3, "Click")]


def test_owned_numeric_predispatch_rejection_can_recover_after_fresh_observation():
    gate = RecoveryGate(RUN, enabled=True)
    receipt = gate.reject(denial())
    assert receipt["decision"] == "recoverable" and receipt["dispatch_state"] == "not_dispatched"
    gate.observed(2)
    gate.before_input()
    assert gate.audit_state() == {"protocol": "native-recovery-1", "recoveries": 1,
                                  "first_attempt_success": False, "recovery_complete": True}
    assert audit_trace(trace_with_recovery(), RUN, enabled=True)["recoveries"] == 1


def test_default_legacy_contract_never_recovers():
    assert RecoveryGate(RUN).reject(denial())["decision"] == "fatal"
    with pytest.raises(RecoveryViolation):
        audit_trace(trace_with_recovery(), RUN)


@pytest.mark.parametrize("code", ["native_target_not_owned", "native_foreground_not_owned",
    "native_app_identity_changed", "native_interactive_session_changed", "native_input_revoked",
    "native_tool_budget", "native_wait_rejected", "native_screen_location_rejected",
    "native_type_options_rejected", "native_tool_failed", "unknown_error"])
def test_every_other_rejection_is_terminal(code):
    row = denial()
    row["error_code"] = code
    gate = RecoveryGate(RUN, enabled=True)
    assert gate.reject(row)["decision"] == "fatal"
    with pytest.raises(RecoveryViolation): gate.observed(2)
    with pytest.raises(RecoveryViolation): gate.before_input()
    with pytest.raises(RecoveryViolation): gate.audit_state()
    assert gate.reject(denial(3))["decision"] == "fatal"


@pytest.mark.parametrize("fault", ["dispatched", "unknown_dispatch", "foreign_target", "foreign_foreground",
    "pid_bool", "missing_window", "missing_arguments", "path", "shell", "invalid_number",
    "already_edit", "missing_target_class", "wrong_tool"])
def test_owned_numeric_and_no_dispatch_require_complete_evidence(fault):
    row = denial()
    if fault == "dispatched": row["dispatched"] = True
    elif fault == "unknown_dispatch": row.pop("dispatched")
    elif fault == "foreign_target": row["window"]["target_pid"] = 999
    elif fault == "foreign_foreground": row["window"]["foreground_pid"] = 999
    elif fault == "pid_bool": row["window"]["target_pid"] = True
    elif fault == "missing_window": row.pop("window")
    elif fault == "missing_arguments": row.pop("arguments")
    elif fault == "path": row["arguments"]["text"] = r"C:\owned\0001.3mf"
    elif fault == "shell": row["arguments"]["text"] = "powershell"
    elif fault == "invalid_number": row["arguments"]["text"] = "10\n"
    elif fault == "already_edit": row["window"]["target_class"] = "Edit"
    elif fault == "missing_target_class": row["window"].pop("target_class")
    elif fault == "wrong_tool": row["tool"] = "Click"
    gate = RecoveryGate(RUN, enabled=True)
    if fault == "unknown_dispatch":
        with pytest.raises(RecoveryViolation, match="dispatch_unknown"): gate.reject(row)
    else:
        assert gate.reject(row)["decision"] == "fatal"
    assert gate.fatal


def test_two_recoveries_consume_budget_and_third_is_fatal():
    gate, trace = RecoveryGate(RUN, enabled=True), []
    for seq in (1, 3):
        row = denial(seq)
        row["recovery"] = gate.reject(row)
        trace += [row, success(seq+1, "Snapshot")]
        gate.observed(seq+1)
    assert audit_trace(trace, RUN, enabled=True)["recoveries"] == 2
    assert gate.reject(denial(5))["decision"] == "fatal"
    assert gate.recoveries == 2


def test_no_input_before_new_screenshot_and_wait_is_not_observation():
    gate = RecoveryGate(RUN, enabled=True)
    gate.reject(denial())
    with pytest.raises(RecoveryViolation): gate.before_input()
    with pytest.raises(RecoveryViolation): gate.observed(2)  # Fatal cannot reset.
    trace = trace_with_recovery()
    trace[1]["tool"] = "Wait"
    with pytest.raises(RecoveryViolation, match="new_observation"):
        audit_trace(trace, RUN, enabled=True)


@pytest.mark.parametrize("seq", [1, 0, True, -1])
def test_old_or_invalid_observation_cannot_clear_pending_rejection(seq):
    gate = RecoveryGate(RUN, enabled=True)
    gate.reject(denial())
    with pytest.raises(RecoveryViolation, match="observation_invalid"):
        gate.observed(seq)


@pytest.mark.parametrize("fault", ["receipt_missing", "receipt_fake_success", "receipt_wrong_run",
    "receipt_wrong_seq", "receipt_digest", "changed_numeric", "changed_error_code",
    "changed_owner", "sequence_gap", "other_run", "no_new_observation", "disguised_failure"])
def test_independent_audit_rejects_tampered_or_incomplete_evidence(fault):
    trace = deepcopy(trace_with_recovery())
    first = trace[0]
    if fault == "receipt_missing": first.pop("recovery")
    elif fault == "receipt_fake_success": first["recovery"]["decision"] = "success"
    elif fault == "receipt_wrong_run": first["recovery"]["run_id"] = "b" * 32
    elif fault == "receipt_wrong_seq": first["recovery"]["seq"] = 2
    elif fault == "receipt_digest": first["recovery"]["facts_sha256"] = "0" * 64
    elif fault == "changed_numeric": first["arguments"]["text"] = "20"
    elif fault == "changed_error_code": first["error_code"] = "native_foreground_not_owned"
    elif fault == "changed_owner": first["window"]["target_pid"] = 99
    elif fault == "sequence_gap": trace[1]["seq"] = 4
    elif fault == "other_run": trace[1]["run_id"] = "b" * 32
    elif fault == "no_new_observation": trace = trace[:1]
    elif fault == "disguised_failure": first["error"] = None
    with pytest.raises(RecoveryViolation): audit_trace(trace, RUN, enabled=True)


def test_clean_new_protocol_trace_is_first_attempt_success():
    result = audit_trace([success(1, "Snapshot"), success(2, "Type")], RUN)
    assert result["first_attempt_success"] and result["recoveries"] == 0


def test_unknown_dispatch_success_and_over_budget_trace_are_rejected():
    row = success(1, "Type")
    row["dispatched"] = False
    with pytest.raises(RecoveryViolation, match="success_evidence"):
        audit_trace([row], RUN)
    with pytest.raises(RecoveryViolation, match="trace_budget"):
        audit_trace([success(i, "Screenshot") for i in range(1, 42)], RUN)


def test_malformed_rejection_permanently_latches_gate():
    gate = RecoveryGate(RUN, enabled=True)
    with pytest.raises(RecoveryViolation): gate.reject({"seq": True})
    assert gate.fatal
    with pytest.raises(RecoveryViolation): gate.before_input()


def test_wrong_run_cannot_borrow_a_live_gate():
    gate = RecoveryGate(RUN, enabled=True)
    row = denial()
    row["run_id"] = "b" * 32
    with pytest.raises(RecoveryViolation, match="rejection_run"): gate.reject(row)
    assert gate.fatal


def test_unknown_tool_success_is_not_accepted_by_the_auditor():
    with pytest.raises(RecoveryViolation, match="trace_schema"):
        audit_trace([success(1, "PowerShell")], RUN, enabled=True)
