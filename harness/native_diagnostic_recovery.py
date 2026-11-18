"""One controlled pre-dispatch refusal, isolated from production recovery.

Integration contract (the pure module cannot authenticate its caller):
* A separately registered diagnostic contract/hash enables this gate. Default
  is disabled; production RecoveryGate and its whitelist remain unchanged.
* After the real guard permits a native Edit numeric Type, the authority may
  inject EXACTLY ONCE before calling the original dispatch function. Preserve
  the real Edit class, arguments and identity, and set both explicit flags.
* Guest persists fatal revocation before returning; host still binds every
  receipt to its original call. No wrapper retry or second session/send.
* Audit needs trusted host lifecycle counts, not model prose. Artifact reading,
  native-tool call matching and independent saved-project/G-code checks remain
  the parent verifier's responsibility.

A passing audit proves a controlled recovery mechanism only. It cannot prove
natural non-Edit recovery, autonomous fault diagnosis or generalization. No GUI,
file writes, agent loop, dispatch, retries or GREEN verdict live in this module.
"""
import hashlib
import json
import re
from decimal import Decimal

from .native_recovery import (RecoveryGate, RecoveryViolation, INPUT_TOOLS,
                              OBSERVATION_TOOLS, TOOLS, _check, _facts, _positive)

PROTOCOL = "native-diagnostic-recovery-1"
ERROR_CODE = "native_diagnostic_injected_pre_dispatch"
SCENARIO = "recovery_diagnostic_once"
COMMIT_SCENARIO = "recovery_diagnostic_commit"
DIAGNOSTIC_SCENARIOS = frozenset({SCENARIO, COMMIT_SCENARIO})


def _owned_edit_numeric(row):
    args, window = row.get("arguments"), row.get("window")
    if type(args) is not dict or type(window) is not dict:
        return False
    text = args.get("text")
    if type(text) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?", text):
        return False
    pids = [window.get(k) for k in ("app_pid", "foreground_pid", "target_pid")]
    return (all(_positive(v) for v in pids) and len(set(pids)) == 1
            and all(_positive(window.get(k)) for k in ("foreground_hwnd", "target_hwnd"))
            and window.get("target_class") == "Edit")


def _diagnostic_facts(row):
    # Base digest binds the unaltered real Edit window and original arguments.
    payload = dict(base_facts_sha256=_facts(row), guard_allowed=row.get("guard_allowed"),
                   diagnostic_injection=row.get("diagnostic_injection"))
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError) as exc:
        raise RecoveryViolation("diagnostic_rejection_not_serializable") from exc
    _check(len(raw) <= 16384, "diagnostic_rejection_size")
    return hashlib.sha256(raw).hexdigest()


class DiagnosticOnceGate(RecoveryGate):
    """Default-off, one-shot diagnostic authority; no production-code aliasing."""

    def should_inject(self, row):
        return (self.enabled and self.recoveries == 0 and not self.fatal
                and self.pending_seq is None and row["tool"] == "Type"
                and _owned_edit_numeric(row))

    def reject(self, row):
        try:
            _check(type(row) is dict and row.get("run_id") == self.run_id, "diagnostic_rejection_run")
            digest = _diagnostic_facts(row)
            _check(row["seq"] > self.last_seq, "diagnostic_sequence_not_increasing")
        except RecoveryViolation:
            self.fatal = True
            raise
        self.last_seq = row["seq"]
        allowed = (self.should_inject(row) and row["error_code"] == ERROR_CODE
                   and row["dispatched"] is False and row.get("guard_allowed") is True
                   and row.get("diagnostic_injection") is True)
        if allowed:
            self.recoveries = 1
            self.pending_seq = row["seq"]
        else:
            self.fatal = True
        return dict(protocol=PROTOCOL, run_id=self.run_id, seq=row["seq"], tool=row["tool"],
            error_code=row["error_code"], dispatch_state="dispatched" if row["dispatched"] else "not_dispatched",
            decision="recoverable" if allowed else "fatal", requires_observation=allowed,
            budget_used=self.recoveries, facts_sha256=digest)

    def audit_state(self):
        _check(not self.fatal and self.pending_seq is None, "diagnostic_unresolved_or_fatal")
        _check(self.recoveries == 1, "diagnostic_not_exercised")
        return dict(protocol=PROTOCOL, injected_recoveries=1, natural_recoveries=0,
                    recovery_complete=True, evidence_class="MECHANISM_ONLY")


def _single_turn(receipt):
    _check(type(receipt) is dict, "diagnostic_turn_receipt_required")
    _check(type(receipt.get("session_identity_sha256")) is str
           and re.fullmatch(r"[0-9a-f]{64}", receipt["session_identity_sha256"]),
           "diagnostic_session_identity")
    for key, value in dict(session_create_count=1, session_send_count=1, turn_started_count=1,
                           turn_completed_count=1, turn_failed_count=0).items():
        _check(type(receipt.get(key)) is int and receipt[key] == value, "diagnostic_single_turn_required")


def audit_diagnostic_trace(trace, run_id, *, enabled=False, turn_receipt=None):
    """Recompute exactly one injected refusal plus new observation in one turn.

    turn_receipt is independently produced by the host protocol driver; a guest
    trace cannot establish how many session/send calls the host made. The root
    verifier must bind this receipt to this run and to the trace/call identities.
    """
    _single_turn(turn_receipt)
    _check(turn_receipt.get("run_id") == run_id, "diagnostic_turn_run")
    _check(type(trace) is list and 1 <= len(trace) <= 40, "diagnostic_trace_budget")
    gate = DiagnosticOnceGate(run_id, enabled=enabled)
    for seq, row in enumerate(trace, 1):
        _check(type(row) is dict and row.get("run_id") == run_id and _positive(row.get("seq"))
               and row["seq"] == seq, "diagnostic_trace_identity_or_sequence")
        _check(type(row.get("tool")) is str and row["tool"] in TOOLS
               and "error" in row and type(row.get("dispatched")) is bool, "diagnostic_trace_schema")
        if row["tool"] in INPUT_TOOLS:
            gate.before_input()
        if row["error"] is not None:
            _check(type(row["error"]) is str and bool(row["error"]), "diagnostic_trace_error")
            receipt = gate.reject(row)
            _check(row.get("recovery") == receipt, "diagnostic_receipt_mismatch")
            _check(receipt["decision"] == "recoverable", "diagnostic_fatal_rejection")
        else:
            _check(row["dispatched"] is True and row.get("recovery") is None
                   and row.get("error_code") is None
                   and (row.get("diagnostic_injection") is None or row.get("diagnostic_injection") is False),
                   "diagnostic_success_evidence")
            if row["tool"] in OBSERVATION_TOOLS:
                gate.observed(seq)
    result = gate.audit_state()
    result.update(session_identity_sha256=turn_receipt["session_identity_sha256"], same_turn_verified=True)
    return result


def verify_diagnostic_calls(trace, turn_receipt, app_pid, *, require_commit=False):
    """Bind host call receipts to audited guest rows and prove a later numeric edit."""
    expected = [dict(seq=row["seq"], tool=row["tool"], dispatched=row["dispatched"],
                     decision="completed" if row["error"] is None else "recoverable",
                     facts_sha256=(row.get("recovery") or {}).get("facts_sha256")) for row in trace]
    calls = turn_receipt.get("calls")
    _check(type(calls) is list and len(calls) == len(expected)
           and all(type(call) is dict and type(call.get("seq")) is int
                   and type(call.get("dispatched")) is bool for call in calls)
           and calls == expected, "diagnostic_host_calls_mismatch")
    refusal = next(row for row in trace if row["error"] is not None)
    _check(refusal["window"]["app_pid"] == app_pid, "diagnostic_refusal_app_mismatch")
    after = trace[refusal["seq"]:]
    observation = next(row for row in after if row["tool"] in OBSERVATION_TOOLS)
    fixed = next((row for row in trace[observation["seq"]:] if row["tool"] == "Type"
                  and _owned_edit_numeric(row) and row["window"]["app_pid"] == app_pid
                  and Decimal(row["arguments"]["text"]) == Decimal(refusal["arguments"]["text"])), None)
    _check(fixed is not None, "diagnostic_corrected_numeric_type_missing")
    if require_commit:
        for attempt in (refusal, fixed):
            args = attempt["arguments"]
            _check(args.get("clear") is True and args.get("press_enter") is True
                   and args.get("caret_position", "idle") == "idle", "native_diagnostic_commit_options")
    return dict(rejected_seq=refusal["seq"], observation_seq=observation["seq"], corrected_seq=fixed["seq"])
