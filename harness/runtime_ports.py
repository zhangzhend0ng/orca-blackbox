"""Nonblocking trusted-adapter contracts for the synthetic runtime only.

No DTO grants permissions. Adapters are trusted Python code: every port method
must return promptly; the coordinator cannot preempt a blocking Python callback.
Done means the operation is quiescent (no further writes). cancel only requests
stopping; cleanup confirmed=True attests all owned work is quiescent and cleaned.
Snapshot.execution is diagnostic context, never proof of the business outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .run_contract import CaseContract
from .run_verdict import CheckResult


@dataclass(frozen=True)
class Pending:
    pass


@dataclass(frozen=True)
class Done:
    value: Any


@dataclass(frozen=True)
class ExecutionContext:
    contract: CaseContract
    run_id: str
    artifact_dir: Path


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str


@dataclass(frozen=True)
class VerificationSnapshot:
    contract: CaseContract
    run_id: str
    artifact_dir: Path
    manifest: Mapping[str, Any]
    execution: ExecutionOutcome


@dataclass(frozen=True)
class VerificationOutcome:
    checks: Mapping[str, CheckResult]
    evidence_complete: bool
    execution_compliant: bool


@dataclass(frozen=True)
class CleanupOutcome:
    confirmed: bool


class CleanupHandle(Protocol):
    def poll(self) -> Pending | Done: ...


class OperationHandle(Protocol):
    def poll(self) -> Pending | Done: ...
    def cancel(self, reason: str) -> None: ...
    def start_cleanup(self) -> CleanupHandle: ...


class ExecutorPort(Protocol):
    synthetic: bool
    kind: str

    def start(self, context: ExecutionContext) -> OperationHandle: ...


class VerifierPort(Protocol):
    synthetic: bool

    def start(self, snapshot: VerificationSnapshot) -> OperationHandle: ...
