"""Pure diagnostic protocol counterexamples, never GUI/model coverage."""
from copy import deepcopy
import json

import pytest

from harness.native_diagnostic_recovery import (DiagnosticOnceGate, ERROR_CODE, PROTOCOL,
                                                audit_diagnostic_trace, verify_diagnostic_calls)
from harness.native_recovery import RecoveryGate, RecoveryViolation

RUN = "a" * 32


def rejection(seq=1):
    return dict(run_id=RUN, seq=seq, tool="Type", error_code=ERROR_CODE, dispatched=False,
        error="ValueError:" + ERROR_CODE, guard_allowed=True, diagnostic_injection=True,
        arguments={"loc": [450, 100], "text": "0.24", "clear": True},
        window=dict(app_pid=123, foreground_pid=123, target_pid=123,
                    foreground_hwnd=10, target_hwnd=50, target_class="Edit"))


def success(seq, tool="Screenshot"):
    return dict(run_id=RUN, seq=seq, tool=tool, error=None, dispatched=True)


def turn():
    return dict(run_id=RUN, session_identity_sha256="b" * 64, session_create_count=1,
        session_send_count=1, turn_started_count=1, turn_completed_count=1, turn_failed_count=0)


def trace():
    row = rejection()
    row["recovery"] = DiagnosticOnceGate(RUN, enabled=True).reject(row)
    return [row, success(2), success(3, "Type")]


def audit(rows, receipt=None, *, enabled=True):
    return audit_diagnostic_trace(rows, RUN, enabled=enabled, turn_receipt=turn() if receipt is None else receipt)


def test_diagnostic_once_with_fresh_observation_is_mechanism_only():
    result = audit(trace())
    assert result == dict(protocol=PROTOCOL, injected_recoveries=1, natural_recoveries=0,
        recovery_complete=True, evidence_class="MECHANISM_ONLY", session_identity_sha256="b" * 64,
        same_turn_verified=True)
    assert "session_id" not in result
    json.dumps(result)


def test_real_edit_identity_is_preserved_and_production_gate_stays_fatal():
    row = rejection(); before = deepcopy(row)
    result = DiagnosticOnceGate(RUN, enabled=True).reject(row)
    assert row == before and row["window"]["target_class"] == "Edit"
    assert result["protocol"] == PROTOCOL and result["decision"] == "recoverable"
    assert RecoveryGate(RUN, enabled=True).reject(row)["decision"] == "fatal"
    assert DiagnosticOnceGate(RUN).reject(row)["decision"] == "fatal"


@pytest.mark.parametrize("code", ["native_type_requires_owned_edit", "native_foreground_not_owned",
    "native_target_not_owned", "native_input_revoked", "native_original_tool_failed", "unknown_error"])
def test_no_production_rejection_becomes_diagnostic_recoverable(code):
    row = rejection(); row["error_code"] = code
    assert DiagnosticOnceGate(RUN, enabled=True).reject(row)["decision"] == "fatal"


@pytest.mark.parametrize("key,value", [("guard_allowed", False), ("guard_allowed", 1),
    ("diagnostic_injection", False), ("diagnostic_injection", "true"), ("dispatched", True),
    ("tool", "Click")])
def test_required_truthful_flags_and_predispatch_type(key, value):
    row = rejection(); row[key] = value
    assert DiagnosticOnceGate(RUN, enabled=True).reject(row)["decision"] == "fatal"


@pytest.mark.parametrize("key", ["guard_allowed", "diagnostic_injection"])
def test_missing_injection_flag_is_fatal(key):
    row = rejection(); del row[key]
    assert DiagnosticOnceGate(RUN, enabled=True).reject(row)["decision"] == "fatal"


@pytest.mark.parametrize("key,value", [("target_class", "wxGLCanvas"), ("target_class", "edit"),
    ("target_pid", 999), ("app_pid", True), ("foreground_pid", 999), ("target_hwnd", 0)])
def test_truthful_owned_native_edit_is_required(key, value):
    row = rejection(); row["window"][key] = value
    assert DiagnosticOnceGate(RUN, enabled=True).reject(row)["decision"] == "fatal"


@pytest.mark.parametrize("text", [r"C:\owned\0001.3mf", "100", "1e2", "10\n", "NaN", "powershell", True])
def test_only_existing_numeric_scope_can_trigger(text):
    row = rejection(); row["arguments"]["text"] = text
    assert DiagnosticOnceGate(RUN, enabled=True).reject(row)["decision"] == "fatal"


def test_second_injection_after_observation_is_permanently_fatal():
    gate = DiagnosticOnceGate(RUN, enabled=True)
    assert gate.reject(rejection())["decision"] == "recoverable"
    gate.observed(2); gate.before_input()
    assert gate.reject(rejection(3))["decision"] == "fatal"
    with pytest.raises(RecoveryViolation): gate.observed(4)
    with pytest.raises(RecoveryViolation): gate.before_input()


def test_no_new_observation_disallows_further_input():
    gate = DiagnosticOnceGate(RUN, enabled=True); gate.reject(rejection())
    with pytest.raises(RecoveryViolation): gate.before_input()
    with pytest.raises(RecoveryViolation): gate.observed(2)


@pytest.mark.parametrize("mutation", ["bad_run", "unknown_dispatch", "nonserializable_flag"])
def test_malformed_rejection_revokes_gate(mutation):
    row = rejection()
    if mutation == "bad_run": row["run_id"] = "d" * 32
    if mutation == "unknown_dispatch": row["dispatched"] = None
    if mutation == "nonserializable_flag": row["diagnostic_injection"] = object()
    gate = DiagnosticOnceGate(RUN, enabled=True)
    with pytest.raises(RecoveryViolation): gate.reject(row)
    with pytest.raises(RecoveryViolation): gate.before_input()


@pytest.mark.parametrize("mutation", ["class", "text", "guard_flag", "injection_flag", "protocol", "digest"])
def test_receipt_binds_true_identity_arguments_and_flags(mutation):
    rows = trace()
    if mutation == "class": rows[0]["window"]["target_class"] = "wxGLCanvas"
    if mutation == "text": rows[0]["arguments"]["text"] = "0.28"
    if mutation == "guard_flag": rows[0]["guard_allowed"] = False
    if mutation == "injection_flag": rows[0]["diagnostic_injection"] = False
    if mutation == "protocol": rows[0]["recovery"]["protocol"] = "native-recovery-1"
    if mutation == "digest": rows[0]["recovery"]["facts_sha256"] = "0" * 64
    with pytest.raises(RecoveryViolation): audit(rows)


def test_exactly_one_injection_is_required():
    with pytest.raises(RecoveryViolation, match="not_exercised"): audit([success(1)])
    rows = trace(); second = rejection(4)
    second["recovery"] = DiagnosticOnceGate(RUN, enabled=True).reject(second)
    rows.append(second)
    with pytest.raises(RecoveryViolation): audit(rows)


@pytest.mark.parametrize("rows", [[], [success(1, "Unknown")]])
def test_missing_or_unknown_trace_rejected(rows):
    with pytest.raises(RecoveryViolation): audit(rows)


def test_unresolved_or_wait_only_recovery_rejected():
    rows = trace()
    with pytest.raises(RecoveryViolation): audit(rows[:1])
    rows[1]["tool"] = "Wait"
    with pytest.raises(RecoveryViolation): audit(rows)


def test_default_or_disabled_audit_cannot_accept_diagnostic():
    with pytest.raises(RecoveryViolation): audit(trace(), enabled=False)
    with pytest.raises(RecoveryViolation): audit_diagnostic_trace(trace(), RUN, turn_receipt=turn())


@pytest.mark.parametrize("key,value", [("session_create_count", 2), ("session_send_count", 2),
    ("turn_started_count", 0), ("turn_completed_count", 0), ("turn_failed_count", 1),
    ("session_send_count", True), ("run_id", "d" * 32), ("session_identity_sha256", "raw-session-id")])
def test_host_same_turn_receipt_cannot_claim_retry_as_recovery(key, value):
    receipt = turn(); receipt[key] = value
    with pytest.raises(RecoveryViolation): audit(trace(), receipt)


def test_guest_trace_alone_cannot_prove_same_turn():
    with pytest.raises(RecoveryViolation, match="turn_receipt_required"):
        audit_diagnostic_trace(trace(), RUN, enabled=True)


def test_success_cannot_hide_injection_or_unknown_dispatch():
    for mutation in ["injection", "dispatch", "receipt"]:
        rows = trace()
        if mutation == "injection": rows[1]["diagnostic_injection"] = True
        if mutation == "dispatch": rows[1]["dispatched"] = False
        if mutation == "receipt": rows[1]["recovery"] = rows[0]["recovery"]
        with pytest.raises(RecoveryViolation): audit(rows)


@pytest.mark.parametrize("fault", [None, "host_calls", "only_save_path", "wrong_pid"])
def test_corrected_edit_must_match_guest_trace_and_native_turn(fault):
    rows = trace()
    rows[2].update(arguments={"text": "0.240"}, window=rows[0]["window"].copy())
    receipt = turn()
    receipt["calls"] = [
        dict(seq=1, tool="Type", decision="recoverable", dispatched=False,
             facts_sha256=rows[0]["recovery"]["facts_sha256"]),
        dict(seq=2, tool="Screenshot", decision="completed", dispatched=True, facts_sha256=None),
        dict(seq=3, tool="Type", decision="completed", dispatched=True, facts_sha256=None),
    ]
    if fault == "host_calls":
        receipt["calls"][0]["facts_sha256"] = "0" * 64
    if fault == "only_save_path":
        rows[2]["arguments"]["text"] = "C:/owned.3mf"
    if fault == "wrong_pid":
        rows[2]["window"]["app_pid"] = 234
    audit(rows, receipt)
    if fault:
        with pytest.raises(RecoveryViolation):
            verify_diagnostic_calls(rows, receipt, 123)
    else:
        assert verify_diagnostic_calls(rows, receipt, 123) == dict(rejected_seq=1, observation_seq=2, corrected_seq=3)
