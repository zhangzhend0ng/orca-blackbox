"""Pure bounded recovery protocol. Guest authority owns the persistent stop latch.

Recovery is limited to a proven owned input refused before dispatch. No retries,
next-action planning, GUI calls or file writes here.
"""
import hashlib
import json
import re

PROTOCOL = "native-recovery-1"
MAX_RECOVERIES = 2
UIA_REFRESH_ERROR = "native_uia_refresh_required"
INPUT_TOOLS = frozenset({"Click", "Type", "Shortcut"})
OBSERVATION_TOOLS = frozenset({"Snapshot", "Screenshot"})
TOOLS = INPUT_TOOLS | OBSERVATION_TOOLS | {"Wait", "ControlStatus"}


class RecoveryViolation(ValueError):
    pass


def _positive(value):
    return type(value) is int and value > 0


def _check(condition, reason):
    if not condition:
        raise RecoveryViolation(reason)


def _owned_numeric(row):
    args, window = row.get("arguments"), row.get("window")
    if type(args) is not dict or type(window) is not dict:
        return False
    text = args.get("text")
    if type(text) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,4})?", text):
        return False
    pids = [window.get(k) for k in ("app_pid", "foreground_pid", "target_pid")]
    return (all(_positive(x) for x in pids) and len(set(pids)) == 1
            and all(_positive(window.get(k)) for k in ("foreground_hwnd", "target_hwnd"))
            and type(window.get("target_class")) is str
            and 1 <= len(window["target_class"]) <= 256 and window["target_class"] != "Edit")


def _owned_uia_refresh(row):
    args, window = row.get("arguments"), row.get("window")
    if row["tool"] not in {"Click", "Type"} or type(args) is not dict or type(window) is not dict:
        return False
    loc = args.get("loc")
    if (type(loc) is not list or len(loc) != 2 or any(type(x) is not int for x in loc)
            or not (0 <= loc[0] < 1920 and 0 <= loc[1] < 1080)):
        return False
    pids = [window.get(key) for key in ("app_pid", "foreground_pid", "target_pid")]
    return (all(_positive(pid) for pid in pids) and len(set(pids)) == 1
            and all(_positive(window.get(key)) for key in ("foreground_hwnd", "target_hwnd"))
            and type(window.get("target_class")) is str and 1 <= len(window["target_class"]) <= 256
            and window.get("refresh_reason") in ("stale_crop", "uia_target_available"))


def _facts(row):
    _check(type(row) is dict and _positive(row.get("seq")), "recovery_rejection_schema")
    _check(type(row.get("tool")) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", row["tool"]),
           "recovery_rejection_tool")
    _check(type(row.get("error_code")) is str
           and re.fullmatch(r"[a-z][a-z0-9_]{0,127}", row["error_code"]), "recovery_rejection_code")
    _check(type(row.get("dispatched")) is bool, "recovery_dispatch_unknown")
    # A digest binds the decision to the original trusted evidence. The model
    # sees only the code and decision; raw denied arguments need not be echoed.
    facts = {k: row.get(k) for k in ("seq", "tool", "error_code", "dispatched", "arguments", "window")}
    try:
        raw = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise RecoveryViolation("recovery_rejection_not_serializable") from exc
    _check(len(raw) <= 16384, "recovery_rejection_size")
    return hashlib.sha256(raw).hexdigest()


class RecoveryGate:
    def __init__(self, run_id, *, enabled=False, uia_refresh_enabled=False):
        _check(type(run_id) is str and re.fullmatch(r"[0-9a-f]{32}", run_id), "recovery_run_id")
        _check(type(enabled) is bool, "recovery_enabled_type")
        _check(type(uia_refresh_enabled) is bool and not (enabled and uia_refresh_enabled), "recovery_mode_conflict")
        self.run_id, self.enabled, self.uia_refresh_enabled = run_id, enabled, uia_refresh_enabled
        self.recoveries, self.pending_seq, self.fatal = 0, None, False
        self.last_seq = 0

    def reject(self, row):
        """Classify a trusted authority rejection; fatal state can never reset."""
        try:
            _check(type(row) is dict and row.get("run_id") == self.run_id, "recovery_rejection_run")
            digest = _facts(row)
            _check(row["seq"] > self.last_seq, "recovery_sequence_not_increasing")
        except RecoveryViolation:
            self.fatal = True
            raise
        self.last_seq = row["seq"]
        eligible = (self.enabled and row["tool"] == "Type"
                    and row["error_code"] == "native_type_requires_owned_edit" and _owned_numeric(row))
        eligible_uia = (self.uia_refresh_enabled and row["error_code"] == UIA_REFRESH_ERROR and _owned_uia_refresh(row))
        allowed = (not self.fatal and self.pending_seq is None and self.recoveries < MAX_RECOVERIES
                   and row["dispatched"] is False and (eligible or eligible_uia))
        if allowed:
            self.recoveries += 1
            self.pending_seq = row["seq"]
        else:
            self.fatal = True
        return {"protocol": PROTOCOL, "run_id": self.run_id, "seq": row["seq"],
                "tool": row["tool"], "error_code": row["error_code"],
                "dispatch_state": "dispatched" if row["dispatched"] else "not_dispatched",
                "decision": "recoverable" if allowed else "fatal",
                "requires_observation": bool(allowed), "budget_used": self.recoveries,
                "facts_sha256": digest}

    def before_input(self):
        if self.fatal or self.pending_seq is not None:
            self.fatal = True
            raise RecoveryViolation("recovery_input_requires_live_authority_and_new_observation")

    def observed(self, seq):
        """Only call after a successful fresh Snapshot/Screenshot completes."""
        if self.fatal or not _positive(seq) or seq <= self.last_seq:
            self.fatal = True
            raise RecoveryViolation("recovery_observation_invalid_or_after_fatal")
        self.last_seq = seq
        self.pending_seq = None

    def audit_state(self):
        _check(not self.fatal and self.pending_seq is None, "recovery_unresolved_or_fatal")
        return {"protocol": PROTOCOL, "recoveries": self.recoveries,
                "first_attempt_success": self.recoveries == 0, "recovery_complete": True}


def audit_trace(trace, run_id, *, enabled=False, uia_refresh_enabled=False):
    """Rebuild decisions from trusted guest rows, never actor-declared success.

    New protocol rows require seq/tool/error/dispatched; denied rows additionally
    require error_code and the exact recovery receipt. No legacy silent upgrade.
    """
    _check(type(trace) is list and 1 <= len(trace) <= 40, "recovery_trace_budget")
    gate = RecoveryGate(run_id, enabled=enabled, uia_refresh_enabled=uia_refresh_enabled)
    previous = 0
    for row in trace:
        _check(type(row) is dict and row.get("run_id") == run_id
               and _positive(row.get("seq")) and row["seq"] == previous + 1,
               "recovery_trace_identity_or_sequence")
        previous = row["seq"]
        _check(type(row.get("tool")) is str and row["tool"] in TOOLS
               and "error" in row and type(row.get("dispatched")) is bool,
               "recovery_trace_schema")
        if row["tool"] in INPUT_TOOLS:
            gate.before_input()
        if row["error"] is not None:
            _check(type(row["error"]) is str and bool(row["error"]), "recovery_trace_error")
            receipt = gate.reject(row)
            _check(row.get("recovery") == receipt, "recovery_receipt_mismatch")
            _check(receipt["decision"] == "recoverable", "recovery_fatal_rejection")
        else:
            _check(row["dispatched"] is True and row.get("recovery") is None
                   and row.get("error_code") is None, "recovery_success_evidence")
            if row["tool"] in OBSERVATION_TOOLS:
                gate.observed(row["seq"])
    return gate.audit_state()
