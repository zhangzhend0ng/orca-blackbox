"""Synthetic coordination plus fixed guest-only script and agent shadow adapters.

Registry and adapters belong to the trusted application, never contract JSON.
Deadlines bound cooperative poll loops; adapters must obey the nonblocking port
contract. Failed cleanup quarantines the desktop lock for operator inspection.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import time
from types import MappingProxyType
from typing import Callable, Mapping
import uuid

from .run_contract import CaseContract, validate_contract
from .run_evidence import RunEvidence
from .run_verdict import (CHECK_NAMES, EXECUTION_STATUSES, CheckResult,
                          aggregate_result, contract_digest)
from .runtime_ports import (CleanupOutcome, Done, ExecutionContext, ExecutionOutcome,
                            ExecutorPort, Pending, VerificationOutcome,
                            VerificationSnapshot, VerifierPort)


class _Deadline(Exception):
    pass


class _Cancelled(Exception):
    pass


def run_once(contract: CaseContract | dict, executor: ExecutorPort,
             verifier_registry: Mapping[str, VerifierPort], *, root: Path,
             desktop_id: str = "synthetic", run_id: str | None = None,
             execution_mode: str = "synthetic",
             verify_timeout_s: float = 30, cleanup_timeout_s: float = 10,
             clock: Callable[[], float] = time.monotonic,
             sleep: Callable[[float], None] = time.sleep,
             cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Execute one trusted adapter; finalize once, never emit release GREEN.

    Returns persisted result fields plus paths. Adapter exceptions are recorded then
    re-raised after cleanup. No runtime retry, promotion, shell or model API.
    Explicit guest modes accept only their fixed script or registered agent cases;
    default synthetic mode cannot launch either real adapter.
    A partial start without a returned handle quarantines the shared desktop.
    Desktop exclusion covers dispatchers sharing the same canonical evidence root.
    """
    frozen = validate_contract(contract.to_dict() if isinstance(contract, CaseContract) else contract)
    if execution_mode not in {"synthetic", "guest_script", "guest_agent", "guest_native"}:
        raise ValueError("runtime: unsupported execution mode")
    synthetic = execution_mode == "synthetic"
    if not synthetic:
        from . import host_guard
        if not host_guard.in_guest():
            raise PermissionError("runtime: real execution requires a Hyper-V guest")
        if execution_mode == "guest_script":
            from .script_executor import ScriptExecutor
            expected_type, expected_case = ScriptExecutor, "m0_boot_check"
        elif execution_mode == "guest_native":
            from .native_save_session import NativeSaveExecutor, native_actor
            expected_type, expected_case = NativeSaveExecutor, "m3g_export_3mf"
            native_actor(contract_digest(frozen))
            if type(run_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", run_id):
                raise ValueError("runtime: invalid native save contract/run identity")
        else:
            from .agent_executor import AgentExecutor
            from .agent_protocol import agent_profile
            from .agent_session import agent_contract
            profile = agent_profile(frozen.case_id)
            expected_type, expected_case = AgentExecutor, frozen.case_id
            if (type(run_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", run_id)
                    or frozen.contract_version != profile["contract_version"]
                    or contract_digest(frozen) != contract_digest(agent_contract(frozen.case_id))):
                raise ValueError("runtime: invalid fixed agent contract/run identity")
        if (type(executor) is not expected_type or frozen.case_id != expected_case
                or executor.contract_sha256 != contract_digest(frozen)):
            raise ValueError("runtime: unregistered real adapter")
    if getattr(executor, "synthetic", None) is not synthetic or executor.kind != frozen.executor:
        raise ValueError("runtime: executor mode/kind must match contract")
    verifier = verifier_registry.get(contract_digest(frozen))
    if verifier is None or getattr(verifier, "synthetic", None) is not synthetic:
        raise ValueError("runtime: no verifier registered for this exact contract and mode")
    if execution_mode == "guest_agent":
        if frozen.case_id == "m1_minimal_loop":
            from .agent_verify import AgentTabVerifier
            expected_verifier = AgentTabVerifier
        elif frozen.case_id == "m3d_param_reslice":
            from .agent_layer_verify import AgentLayerVerifier
            expected_verifier = AgentLayerVerifier
        elif frozen.case_id == "m3g_export_3mf":
            from .agent_project_verify import AgentProjectVerifier
            expected_verifier = AgentProjectVerifier
        else:
            raise ValueError("runtime: unregistered agent case")
        if type(verifier) is not expected_verifier:
            raise ValueError("runtime: unregistered agent verifier")
    if execution_mode == "guest_native":
        from .native_save_session import NativeSaveVerifier
        if type(verifier) is not NativeSaveVerifier:
            raise ValueError("runtime: unregistered native verifier")
    for budget in (verify_timeout_s, cleanup_timeout_s):
        if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 3600:
            raise ValueError("runtime: invalid phase budget")
    if type(desktop_id) is not str or not 1 <= len(desktop_id) <= 256:
        raise ValueError("runtime: invalid desktop identifier")
    root = Path(root).resolve(strict=True)
    lock_dir = root / ".desktop_locks"
    lock_dir.mkdir(exist_ok=True)
    lease = lock_dir / (hashlib.sha256(desktop_id.encode("utf-8")).hexdigest() + ".lock")
    ident = run_id if run_id is not None else uuid.uuid4().hex
    if type(ident) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", ident):
        raise ValueError("runtime: invalid run identifier")
    # Exclusive create also prevents nested dispatch on the same desktop.
    with lease.open("x", encoding="utf-8") as stream:
        stream.write(ident)
    writer = None
    handles = []
    primary = None
    cleanup_errors = []
    cleanup_confirmed = True
    execution = ExecutionOutcome("blocked")
    verification = VerificationOutcome({}, False, False)
    runtime_status = "starting"
    start_in_progress = False

    def wait(handle, seconds: float, *, observe_cancel: bool = True, deadline=None):
        deadline = min(clock() + seconds, deadline) if deadline is not None else clock() + seconds
        while True:
            if observe_cancel and cancelled():
                raise _Cancelled()
            if clock() >= deadline:
                raise _Deadline()
            polled = handle.poll()
            if isinstance(polled, Done):
                if clock() >= deadline:
                    raise _Deadline()
                return polled.value
            if not isinstance(polled, Pending):
                raise TypeError("runtime: poll must return Pending or Done")
            sleep(min(0.01, max(0, deadline - clock())))

    def request_cancel(handle, reason: str):
        try:
            handle.cancel(reason)
        except BaseException as exc:
            cleanup_errors.append(exc)

    try:
        writer = RunEvidence.create(root, frozen, run_id=ident)
        artifacts = writer.run_dir / "artifacts"
        artifacts.mkdir()
        writer.append_event("runtime_started", status=execution_mode)
        runtime_status = "executing"
        case_deadline = clock() + frozen.limits.timeout_s
        start_in_progress = True
        handle = executor.start(ExecutionContext(frozen, writer.run_id, artifacts))
        handles.append(handle)
        start_in_progress = False
        try:
            outcome = wait(handle, frozen.limits.timeout_s, deadline=case_deadline)
            if not isinstance(outcome, ExecutionOutcome) or outcome.status not in EXECUTION_STATUSES:
                raise TypeError("runtime: invalid execution outcome")
            execution = outcome
        except _Deadline:
            execution = ExecutionOutcome("timeout")
            request_cancel(handle, "execution_timeout")
        except _Cancelled:
            execution = ExecutionOutcome("cancelled")
            request_cancel(handle, "cancelled")
        writer.append_event("execution_finished", status=execution.status)
        if execution.status == "completed":
            runtime_status = "verifying"
            writer.append_event("verification_started")
            snapshot = VerificationSnapshot(frozen, writer.run_id, artifacts,
                                            MappingProxyType(dict(writer.manifest)), execution)
            start_in_progress = True
            verification_deadline = min(case_deadline, clock() + verify_timeout_s)
            checker = verifier.start(snapshot)
            handles.append(checker)
            start_in_progress = False
            try:
                verification = wait(checker, verify_timeout_s, deadline=verification_deadline)
                if (not isinstance(verification, VerificationOutcome)
                        or type(verification.evidence_complete) is not bool
                        or type(verification.execution_compliant) is not bool
                        or not isinstance(verification.checks, Mapping)
                        or any(k not in CHECK_NAMES or not isinstance(v, CheckResult)
                               for k, v in verification.checks.items())):
                    raise TypeError("runtime: invalid verification outcome")
            except _Deadline:
                verification = VerificationOutcome({}, False, False)
                runtime_status = "verification_timeout"
                request_cancel(checker, "verification_timeout")
            except _Cancelled:
                verification = VerificationOutcome({}, False, False)
                execution = ExecutionOutcome("cancelled")
                runtime_status = "cancelled"
                request_cancel(checker, "cancelled")
            writer.append_event("verification_finished", status=(
                "completed" if runtime_status == "verifying" else runtime_status))
        if runtime_status in {"executing", "verifying"}:
            runtime_status = "completed" if execution.status == "completed" else execution.status
    except BaseException as exc:
        primary = exc
        execution = ExecutionOutcome("failed")
        runtime_status = "adapter_error"
        verification = VerificationOutcome({}, False, False)
    finally:
        if start_in_progress:
            cleanup_confirmed = False  # A partial start without a handle is unconfirmed.
        safe_to_clean = not start_in_progress
        for index, handle in enumerate(reversed(handles)):
            if not safe_to_clean:
                try:
                    handle.cancel("desktop_quarantined")
                except BaseException as exc:
                    cleanup_errors.append(exc)
                continue
            if primary is not None:
                try:
                    handle.cancel("adapter_error")
                except BaseException as exc:
                    cleanup_errors.append(exc)
                    cleanup_confirmed = False
            try:
                writer.append_event("cleanup_started", step_id=f"operation_{index}")
                cleanup_deadline = clock() + cleanup_timeout_s
                outcome = wait(handle.start_cleanup(), cleanup_timeout_s, observe_cancel=False,
                               deadline=cleanup_deadline)
                if not isinstance(outcome, CleanupOutcome) or outcome.confirmed is not True:
                    cleanup_confirmed = False
                    safe_to_clean = False
                writer.append_event("cleanup_finished", step_id=f"operation_{index}",
                                    status="confirmed" if safe_to_clean else "unconfirmed")
            except BaseException as exc:
                cleanup_confirmed = False
                safe_to_clean = False
                cleanup_errors.append(exc)
                try:
                    writer.append_event("cleanup_finished", step_id=f"operation_{index}", status="error")
                except BaseException as recording_error:
                    cleanup_errors.append(recording_error)
        try:
            if writer is not None:
                if not cleanup_confirmed or runtime_status != "completed":
                    verification = VerificationOutcome(verification.checks, False, False)
                verdict = aggregate_result(frozen, execution.status, verification.checks,
                                           evidence_complete=verification.evidence_complete,
                                           execution_compliant=verification.execution_compliant)
                result = verdict.to_dict()
                result.update(mode=("synthetic" if synthetic else
                                    "agent_shadow" if execution_mode in {"guest_agent", "guest_native"} else "script_shadow"),
                              release_verdict="SYNTHETIC" if synthetic else (
                                  "SHADOW" if verdict.verified_pass else "NON_GREEN"),
                              release_eligible=False, runtime_status=runtime_status,
                              cleanup_confirmed=cleanup_confirmed)
                if synthetic:
                    result["gui_executed"] = False
                else:
                    result["gui_execution_requested"] = True
                writer.append_event("runtime_finished", status=runtime_status)
                result_path = writer.finalize(result)
                output = {**result, "run_id": writer.run_id, "run_dir": str(writer.run_dir),
                          "manifest_path": str(writer.run_dir / "manifest.json"),
                          "result_path": str(result_path)}
        except BaseException as exc:
            if primary is None:
                primary = exc
            else:
                primary.add_note("runtime: result persistence also failed")
        finally:
            if writer is not None:
                try:
                    writer.close()
                except BaseException as exc:
                    if primary is None:
                        primary = exc
                    else:
                        primary.add_note("runtime: evidence close also failed")
    if primary is not None:
        if cleanup_errors:
            primary.add_note("runtime: cleanup also failed; desktop remains quarantined")
        raise primary
    if cleanup_errors:
        raise cleanup_errors[0]
    if cleanup_confirmed:
        if lease.read_text(encoding="utf-8") != ident:
            raise RuntimeError("runtime: desktop lock ownership changed")
        lease.unlink()  # Only release after result persistence and writer.close succeed.
    return output
