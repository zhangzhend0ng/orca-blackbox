"""Serialized dispatch accounting. A fatal refusal revokes this run durably."""
import json
import time

from .native_recovery import RecoveryGate, RecoveryViolation
from .native_save_policy import INPUT_TOOLS, NATIVE_TOOLS

PROTOCOL = "native-authority-1"
RECOVERY_SCENARIOS = frozenset({"recovery_owned_edit", "canvas_trial"})


def attach_authority(original, receipt):
    """Retain upstream outputSchema fields; add metadata without nesting them."""
    if original is not None and type(original) is not dict:
        raise ValueError("native_original_structured_result_schema")
    result = dict(original or {})
    if "authority" in result:
        raise ValueError("native_original_authority_collision")
    result["authority"] = receipt
    return result


def validate_scope(scope, manifest, contract, *, run_id, output_path):
    from .run_contract import validate_contract
    from .run_verdict import contract_digest
    from .native_save_session import native_spec
    digest = contract_digest(validate_contract(contract))
    actor, scenario = native_spec(digest)
    if (scope.get("run_id") != run_id or manifest.get("run_id") != run_id
            or scope.get("contract_sha256") != digest or manifest.get("contract_sha256") != digest
            or scope.get("actor") != actor or scope.get("scenario") != scenario
            or scope.get("output_path") != output_path
            or any(type(scope.get(k)) is not int or scope[k] <= 0 for k in ("app_pid", "hwnd"))):
        raise ValueError("native_scope_contract_mismatch")
    return scenario in RECOVERY_SCENARIOS


class AuthorityController:
    def __init__(self, guard, root, run_id, *, recovery_enabled=False):
        self.guard, self.root, self.run_id = guard, root, run_id
        self.gate = RecoveryGate(run_id, enabled=recovery_enabled)
        self.calls = 0

    def abort(self, code):
        # A write failure propagates and prevents dispatch, rather than
        # returning a harmless-looking tool result without a durable latch.
        self.gate.fatal = True
        (self.root / "input_revoked").touch(exist_ok=True)
        path = self.root / "authority_abort.json"
        if not path.exists():
            with path.open("x", encoding="utf-8") as stream:
                json.dump({"run_id": self.run_id, "error_code": code,
                           "at_ns": time.time_ns()}, stream)

    async def call(self, name, arguments, dispatch):
        self.calls += 1
        row = {"seq": self.calls, "tool": name if name in NATIVE_TOOLS else "rejected_tool",
               "arguments": {}, "run_id": self.run_id, "level": "INFO",
               "message": "native_tool_call", "started_at_ns": time.time_ns(),
               "error": None, "dispatched": False}
        payload, decision = None, "completed"
        self.guard.last_window, self.guard.arguments_validated = {}, False
        self.guard.last_canvas_evidence = None
        try:
            if self.gate.fatal:
                raise ValueError("native_authority_already_revoked")
            if self.calls > 40:
                raise ValueError("native_tool_budget")
            if name in INPUT_TOOLS:
                self.gate.before_input()
            row["window"] = self.guard.check(name, arguments)
            row["arguments"] = arguments
            if self.guard.last_canvas_evidence is not None:
                import hashlib
                raw = json.dumps(self.guard.last_canvas_evidence, sort_keys=True).encode("utf-8")
                filename = "canvas_input_"+str(self.calls)+".json"
                with (self.root / filename).open("xb") as stream:
                    stream.write(raw)
                row["window"].update(observation_file=filename, observation_sha256=hashlib.sha256(raw).hexdigest())
            # Recheck revocation immediately before calling the original tool.
            if (self.root / "input_revoked").exists() or (self.root / "control_cancel.json").exists():
                raise ValueError("native_input_revoked")
            row["dispatched"] = True
            payload = await dispatch()
            if type(getattr(payload, "is_error", None)) is not bool:
                raise ValueError("native_original_result_schema")
            if payload.is_error:
                raise ValueError("native_original_tool_failed")
            if name == "Click" and hasattr(self.guard, "record_click"):
                self.guard.record_click(arguments["loc"])
            if name in {"Snapshot", "Screenshot"}:
                self.gate.observed(self.calls)
        except Exception as exc:
            code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("native_") else "native_tool_failed"
            row.update(error=type(exc).__name__+":"+code[:120], error_code=code, level="ERROR")
            if self.guard.arguments_validated:
                row["arguments"] = arguments
            row["window"] = self.guard.last_window
            try:
                receipt = self.gate.reject(row)
                row["recovery"] = receipt
                decision = receipt["decision"]
            except RecoveryViolation:
                decision = "fatal"
            if decision == "fatal":
                self.abort(code)
        finally:
            row["finished_at_ns"] = time.time_ns()
            try:
                with (self.root / "native_trace.ndjson").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=True)+"\n")
            except OSError:
                self.abort("native_trace_write_failed")
                raise
        envelope = {"protocol": PROTOCOL, "run_id": self.run_id, "seq": self.calls,
                    "tool": row["tool"], "decision": decision, "dispatched": row["dispatched"]}
        if decision != "completed":
            envelope.update(error_code=row["error_code"], recovery=row.get("recovery"))
        return payload, envelope
