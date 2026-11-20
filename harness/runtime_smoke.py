"""Synthetic runtime adapters. No GUI, models, shell, or release evidence.

The fixed content is deliberately a simulation marker, not gcode. These ports
exercise the same lifecycle as future adapters without claiming GUI validation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_check import check_artifact
from .run_contract import validate_contract
from .run_verdict import CheckResult, contract_digest
from .runtime import run_once
from .runtime_ports import (CleanupOutcome, Done, ExecutionOutcome, Pending,
                            VerificationOutcome)

PAYLOAD = b"ORCA_BLACKBOX_SYNTHETIC_ONLY\nGUI_EXECUTED=false\nEND_SYNTHETIC\n"
ARTIFACT = "synthetic-output.txt"


def smoke_contract() -> dict:
    return {"schema_version": 1, "case_id": "synthetic_runtime_smoke",
            "contract_version": "1", "executor": "script",
            "required_checks": ["path", "business"],
            "steps": [{"id": "synthetic_write", "goal": "Write fixed simulation marker; no GUI"}],
            "limits": {"timeout_s": 2, "max_actions": 1,
                       "max_retries": 0, "max_cost_usd": 0}}


class SyntheticHandle:
    """Deterministic nonblocking test handle, including cancellation and cleanup."""
    def __init__(self, value: Any, *, pending_polls: int = 0,
                 cleanup_confirmed: bool = True, cleanup_pending_polls: int = 0):
        self.value = value
        self.pending_polls = pending_polls
        self.cleanup_confirmed = cleanup_confirmed
        self.cleanup_pending_polls = cleanup_pending_polls
        self.cancel_reasons: list[str] = []
        self.cleanup_started = False

    def poll(self):
        if self.pending_polls:
            self.pending_polls -= 1
            return Pending()
        return Done(self.value)

    def cancel(self, reason: str) -> None:
        self.cancel_reasons.append(reason)

    def start_cleanup(self):
        self.cleanup_started = True
        return SyntheticHandle(CleanupOutcome(self.cleanup_confirmed),
                               pending_polls=self.cleanup_pending_polls)


class SyntheticExecutor:
    """Writes only the fixed synthetic artifact; reports execution facts only."""
    synthetic = True
    kind = "script"

    def __init__(self, *, outcome_status: str = "completed", pending_polls: int = 0,
                 cleanup_confirmed: bool = True, write_artifact: bool = True):
        self.outcome_status = outcome_status
        self.pending_polls = pending_polls
        self.cleanup_confirmed = cleanup_confirmed
        self.write_artifact = write_artifact
        self.handle: SyntheticHandle | None = None

    def start(self, context):
        if self.write_artifact:
            with (context.artifact_dir / ARTIFACT).open("xb") as stream:
                stream.write(PAYLOAD)
        self.handle = SyntheticHandle(ExecutionOutcome(self.outcome_status),
                                      pending_polls=self.pending_polls,
                                      cleanup_confirmed=self.cleanup_confirmed)
        return self.handle


class SyntheticVerifier:
    """Independently reads the fixed file; no executor-supplied pass fields."""
    synthetic = True

    def __init__(self, *, forced_status: str | None = None, pending_polls: int = 0,
                 cleanup_confirmed: bool = True):
        self.forced_status = forced_status
        self.pending_polls = pending_polls
        self.cleanup_confirmed = cleanup_confirmed
        self.handle: SyntheticHandle | None = None
        self.calls = 0

    def start(self, snapshot):
        self.calls += 1
        import hashlib
        artifact = check_artifact(snapshot.artifact_dir, ARTIFACT,
                                  started_at_ns=snapshot.manifest["started_at_ns"],
                                  expected_size=len(PAYLOAD),
                                  expected_sha256=hashlib.sha256(PAYLOAD).hexdigest(),
                                  required_suffix=b"END_SYNTHETIC\n")
        status = self.forced_status or artifact.status
        checks = {name: CheckResult(status, "synthetic file marker only; no GUI proof",
                                    artifact.evidence if status == "pass" else ())
                  for name in ("path", "business")}
        self.handle = SyntheticHandle(
            VerificationOutcome(checks, artifact.status == "pass", True),
            pending_polls=self.pending_polls, cleanup_confirmed=self.cleanup_confirmed)
        return self.handle


def run_smoke(root: Path) -> dict:
    """Execute the actual orchestrator using only fixed synthetic ports."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    contract = validate_contract(smoke_contract())
    result = run_once(contract, SyntheticExecutor(),
                      {contract_digest(contract): SyntheticVerifier()}, root=root,
                      desktop_id="synthetic-smoke")
    return {**result,
            "artifact_path": str(Path(result["run_dir"]) / "artifacts" / ARTIFACT),
            "mode": "synthetic", "gui_executed": False, "release_eligible": False}
