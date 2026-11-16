"""Independent, fail-closed result aggregation; never trust agent self-report.

Call from the trusted scheduler/checker, not an executor-facing tool. Promotion
records must come from an approved registry; constructing one is not approval.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Mapping

from .run_contract import CaseContract, validate_contract

CHECK_NAMES = frozenset({"path", "business", "visual"})
CHECK_STATUSES = frozenset({"pass", "fail", "unknown", "not_applicable"})
EXECUTION_STATUSES = frozenset({"completed", "failed", "blocked", "timeout", "cancelled"})


@dataclass(frozen=True)
class CheckResult:
    status: str
    detail: str = ""
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or self.status not in CHECK_STATUSES:
            raise ValueError("invalid check status")
        if not isinstance(self.detail, str) or len(self.detail) > 4096:
            raise ValueError("check detail must be a bounded string")
        if (not isinstance(self.evidence, tuple) or len(self.evidence) > 100
                or any(not isinstance(x, str) or not x or len(x) > 2048
                       for x in self.evidence)):
            raise ValueError("check evidence must be a bounded tuple of references")


def contract_digest(contract: Mapping | CaseContract) -> str:
    """Digest exactly the validated contract snapshot, without version guessing."""
    snapshot = validate_contract(contract.to_dict() if isinstance(contract, CaseContract)
                                 else dict(contract)).to_dict()
    data = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Promotion:
    """Trusted registry entry scoped to an exact contract, never model output."""
    contract_sha256: str
    approval_id: str

    def __post_init__(self) -> None:
        if (not isinstance(self.contract_sha256, str)
                or len(self.contract_sha256) != 64
                or any(x not in "0123456789abcdef" for x in self.contract_sha256)):
            raise ValueError("invalid promotion contract digest")
        if (not isinstance(self.approval_id, str) or not self.approval_id.strip()
                or len(self.approval_id) > 256):
            raise ValueError("invalid promotion approval reference")


@dataclass(frozen=True)
class VerdictResult:
    verified_pass: bool
    release_verdict: str
    mode: str
    execution_status: str
    checks: dict[str, CheckResult]
    reasons: tuple[str, ...]
    recovery_used: bool

    def to_dict(self) -> dict:
        return asdict(self)


def aggregate_result(contract: Mapping | CaseContract, execution_status: str,
                     checks: Mapping[str, CheckResult], *, evidence_complete: bool,
                     execution_compliant: bool, recovery_used: bool = False,
                     recovery_recorded: bool = False,
                     promotion: Promotion | None = None) -> VerdictResult:
    """Validate checker inputs, preserving failures and unknowns.

    The caller supplies a validated, frozen contract. Evidence references must
    be independently produced. This function does not authenticate evidence or
    promotion records and is deliberately not exposed to the operating agent.
    """
    if not isinstance(contract, (Mapping, CaseContract)):
        raise ValueError("contract must be a validated mapping")
    contract = validate_contract(contract.to_dict() if isinstance(contract, CaseContract)
                                 else dict(contract)).to_dict()
    executor = contract.get("executor")
    required = contract.get("required_checks")
    if executor not in ("script", "agent_mcp", "midscene"):
        raise ValueError("invalid executor")
    if (not isinstance(required, (list, tuple)) or not required
            or any(not isinstance(x, str) or x not in CHECK_NAMES for x in required)
            or len(set(required)) != len(required)):
        raise ValueError("invalid required_checks")
    if not isinstance(execution_status, str) or execution_status not in EXECUTION_STATUSES:
        raise ValueError("invalid execution status")
    for name, value in (("evidence_complete", evidence_complete),
                        ("execution_compliant", execution_compliant),
                        ("recovery_used", recovery_used),
                        ("recovery_recorded", recovery_recorded)):
        if type(value) is not bool:
            raise ValueError(f"{name} must be a boolean")
    if not isinstance(checks, Mapping) or any(
            name not in CHECK_NAMES or not isinstance(result, CheckResult)
            for name, result in checks.items()):
        raise ValueError("invalid checker results")
    if promotion is not None and not isinstance(promotion, Promotion):
        raise ValueError("promotion must come from the trusted registry")

    reasons = []
    if execution_status != "completed":
        reasons.append("execution_not_completed")
    if not evidence_complete:
        reasons.append("evidence_incomplete")
    if not execution_compliant:
        reasons.append("execution_noncompliant")
    if recovery_used and not recovery_recorded:
        reasons.append("recovery_not_recorded")
    results = dict(checks)
    for name in sorted(CHECK_NAMES):
        result = results.setdefault(name, CheckResult("unknown", "not checked"))
        if name in required and result.status != "pass":
            reasons.append(f"{name}_{result.status}")
        elif result.status == "fail":
            reasons.append(f"{name}_fail")
        if name in required and result.status == "pass" and not result.evidence:
            reasons.append(f"{name}_evidence_missing")
    verified = not reasons
    promoted = promotion is not None and promotion.contract_sha256 == contract_digest(contract)
    mode = "script" if executor == "script" else ("promoted" if promoted else "shadow")
    release = "GREEN" if verified and mode != "shadow" else ("SHADOW" if verified else "NON_GREEN")
    return VerdictResult(verified, release, mode, execution_status, results,
                         tuple(reasons), recovery_used)
