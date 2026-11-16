"""Fixed guest AI tab-loop capability; model credentials stay on the host."""
from pathlib import Path
import re

from . import host_guard
from .run_contract import validate_contract
from .run_verdict import contract_digest
from .runtime import run_once
from .script_session import SCRIPT_ROOT


def registered_agent_cases() -> tuple[str, ...]:
    return ("m1_minimal_loop",)


def agent_contract(case_id: str):
    if type(case_id) is not str or case_id not in registered_agent_cases():
        raise ValueError("agent: case has not been approved for this adapter")
    from cases import CASES
    if not CASES.get(case_id, {}).get("enabled"):
        raise ValueError("agent: case is not enabled in cases.py")
    return validate_contract({
        "schema_version": 1, "case_id": case_id, "contract_version": "ai-tabs-1",
        "executor": "agent_mcp", "required_checks": ["path", "business"],
        "steps": [{"id": "boot", "goal": "Observe stable Prepare in a fresh guest session"},
                  {"id": "preview", "goal": "Use model-selected click to reach stable Preview"},
                  {"id": "prepare", "goal": "Use model-selected click to return to stable Prepare"},
                  {"id": "close", "goal": "Close and confirm the owned Job is empty"}],
        # Zero means no metered API is used here, NOT a measured free model run.
        # Host ChatGPT quota is bounded by calls/time; USD enforcement is unavailable.
        "limits": {"timeout_s": 900, "max_actions": 12,
                   "max_retries": 0, "max_cost_usd": 0},
    })


def run_agent(case_id: str, root: Path, run_id: str) -> dict:
    if not host_guard.in_guest():
        raise ValueError("agent: guest execution required")
    if type(run_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("agent: host-supplied 32-hex run identifier required")
    contract = agent_contract(case_id)
    root = Path(root).resolve()
    if root != SCRIPT_ROOT.resolve():
        raise ValueError("agent: use the canonical guest evidence root")
    from .agent_executor import AgentExecutor
    from .agent_verify import AgentTabVerifier
    root.mkdir(parents=True, exist_ok=True)
    digest = contract_digest(contract)
    return run_once(contract, AgentExecutor(digest), {digest: AgentTabVerifier()},
                    root=root, run_id=run_id, desktop_id="guest-console",
                    execution_mode="guest_agent")
