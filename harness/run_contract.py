"""Version-one data-only contracts. Validation never launches a GUI or a shell."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

MAX_CONTRACT_BYTES = 65536
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class ContractError(ValueError):
    """The supplied contract cannot be used; errors omit input payloads."""


def _fields(value: Any, fields: set[str], where: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ContractError(f"{where}: incorrect fields")
    return value


def _identifier(value: Any, where: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ContractError(f"{where}: invalid identifier")
    return value


def _integer(value: Any, minimum: int, maximum: int, where: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(f"{where}: invalid integer range")
    return value


@dataclass(frozen=True)
class Step:
    id: str
    goal: str


@dataclass(frozen=True)
class Limits:
    timeout_s: int
    max_actions: int
    max_retries: int
    max_cost_usd: float


@dataclass(frozen=True)
class CaseContract:
    schema_version: int
    case_id: str
    contract_version: str
    executor: str
    required_checks: tuple[str, ...]
    steps: tuple[Step, ...]
    limits: Limits

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "contract_version": self.contract_version,
            "executor": self.executor,
            "required_checks": list(self.required_checks),
            "steps": [{"id": step.id, "goal": step.goal} for step in self.steps],
            "limits": {"timeout_s": self.limits.timeout_s,
                       "max_actions": self.limits.max_actions,
                       "max_retries": self.limits.max_retries,
                       "max_cost_usd": self.limits.max_cost_usd},
        }


def validate_contract(value: Any) -> CaseContract:
    """Reject unknown fields/types; return an immutable, independent snapshot."""
    d = _fields(value, {"schema_version", "case_id", "contract_version", "executor",
                        "required_checks", "steps", "limits"}, "contract")
    _integer(d["schema_version"], 1, 1, "schema_version")
    case_id = _identifier(d["case_id"], "case_id")
    version = _identifier(d["contract_version"], "contract_version")
    if type(d["executor"]) is not str or d["executor"] not in {"script", "agent_mcp", "midscene"}:
        raise ContractError("executor: unsupported executor")
    checks = d["required_checks"]
    if (type(checks) is not list or not 1 <= len(checks) <= 3
            or any(type(x) is not str or x not in {"path", "business", "visual"} for x in checks)
            or len(set(checks)) != len(checks)):
        raise ContractError("required_checks: invalid or duplicate checks")
    if type(d["steps"]) is not list or not 1 <= len(d["steps"]) <= 1000:
        raise ContractError("steps: expected 1 to 1000 steps")
    steps = []
    for raw in d["steps"]:
        s = _fields(raw, {"id", "goal"}, "step")
        sid = _identifier(s["id"], "step.id")
        goal = s["goal"]
        if (type(goal) is not str or not goal.strip() or len(goal) > 2048
                or any(ord(ch) < 32 and ch not in "\n\t" for ch in goal)):
            raise ContractError("step.goal: invalid text")
        steps.append(Step(sid, goal))
    if len({s.id for s in steps}) != len(steps):
        raise ContractError("steps: duplicate identifiers")
    lim = _fields(d["limits"], {"timeout_s", "max_actions", "max_retries", "max_cost_usd"}, "limits")
    timeout = _integer(lim["timeout_s"], 1, 3600, "limits.timeout_s")
    actions = _integer(lim["max_actions"], 1, 10000, "limits.max_actions")
    retries = _integer(lim["max_retries"], 0, 3, "limits.max_retries")
    cost = lim["max_cost_usd"]
    if type(cost) not in (int, float) or not 0 <= cost <= 10000 or not math.isfinite(cost):
        raise ContractError("limits.max_cost_usd: invalid finite cost")
    return CaseContract(1, case_id, version, d["executor"], tuple(checks), tuple(steps),
                        Limits(timeout, actions, retries, float(cost)))


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("JSON: duplicate field")
        result[key] = value
    return result


def load_contract(path: str | Path) -> CaseContract:
    """Read bounded UTF-8 JSON, rejecting duplicate fields and nonfinite numbers."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_CONTRACT_BYTES + 1)
        if len(raw) > MAX_CONTRACT_BYTES:
            raise ContractError("contract: input exceeds size limit")
        def reject_constant(_value: str) -> None:
            raise ContractError("JSON: nonfinite number")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=reject_constant)
        return validate_contract(value)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("contract: invalid JSON document") from exc
