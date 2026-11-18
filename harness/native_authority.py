"""Serialized dispatch accounting. A fatal refusal revokes this run durably."""
import base64
import hashlib
import json
import time

from .native_recovery import RecoveryGate, RecoveryViolation
from .native_diagnostic_recovery import DiagnosticOnceGate, ERROR_CODE
from .native_matrix import CANVAS_SCENARIOS, GENERALIZATION
from .native_save_policy import INPUT_TOOLS, NATIVE_TOOLS

PROTOCOL = "native-authority-1"
RECOVERY_SCENARIOS = CANVAS_SCENARIOS | set(GENERALIZATION) | {"recovery_owned_edit"}


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
    def __init__(self, guard, root, run_id, *, recovery_enabled=False, diagnostic_enabled=False,
                 canvas_dispatch=None, record_edit_frames=False):
        self.guard, self.root, self.run_id = guard, root, run_id
        if diagnostic_enabled and recovery_enabled:
            raise ValueError("native_recovery_contract_conflict")
        self.gate = (DiagnosticOnceGate(run_id, enabled=True) if diagnostic_enabled
                     else RecoveryGate(run_id, enabled=recovery_enabled))
        self.calls = 0
        self.canvas_dispatch = canvas_dispatch
        self.record_edit_frames = record_edit_frames
        self.last_type = None
        self.edit_frames = 0

    def _record_edit_frame(self, row, payload):
        if not self.record_edit_frames or self.last_type is None or self.edit_frames >= 4:
            return
        row["observed_type_seq"], self.last_type = self.last_type, None
        images = [item for item in payload.content if item.type == "image" and item.mimeType == "image/png"]
        if len(images) != 1 or len(images[0].data) > 512_000:
            row["edit_frame_status"] = "image_missing_or_large"
            return
        try:
            raw = base64.b64decode(images[0].data, validate=True)
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("not_png")
            name = f"native_observation_{self.calls}.png"
            with (self.root / name).open("xb") as stream:
                stream.write(raw)
        except (OSError, ValueError):
            row["edit_frame_status"] = "invalid_or_write_failed"
            return
        row.update(edit_frame_file=name, edit_frame_sha256=hashlib.sha256(raw).hexdigest())
        self.edit_frames += 1

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
        if name == "Type":
            self.last_type = self.calls
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
                raw = json.dumps(self.guard.last_canvas_evidence, sort_keys=True).encode("utf-8")
                filename = "canvas_input_"+str(self.calls)+".json"
                with (self.root / filename).open("xb") as stream:
                    stream.write(raw)
                row["window"].update(observation_file=filename, observation_sha256=hashlib.sha256(raw).hexdigest())
            # Recheck revocation immediately before calling the original tool.
            if (self.root / "input_revoked").exists() or (self.root / "control_cancel.json").exists():
                raise ValueError("native_input_revoked")
            if isinstance(self.gate, DiagnosticOnceGate) and self.gate.should_inject(row):
                row.update(guard_allowed=True, diagnostic_injection=True)
                raise ValueError(ERROR_CODE)
            row["dispatched"] = True
            if name == "Type" and self.canvas_dispatch is not None and row["window"].get("route") == "canvas_numeric":
                row["window"]["input_backend"] = "focused_keys_no_click"
                payload = self.canvas_dispatch(arguments)
            else:
                payload = await dispatch()
            if type(getattr(payload, "is_error", None)) is not bool:
                raise ValueError("native_original_result_schema")
            if payload.is_error:
                raise ValueError("native_original_tool_failed")
            if name == "Click" and "loc" in arguments and hasattr(self.guard, "record_click"):
                self.guard.record_click(arguments["loc"], clicks=arguments.get("clicks", 1))
            if name in {"Snapshot", "Screenshot"}:
                self.gate.observed(self.calls)
            if name == "Screenshot" and self.record_edit_frames:
                self._record_edit_frame(row, payload)
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
