"""Two fixed guest AI capabilities; model credentials stay on the host."""
from pathlib import Path
import re

from . import host_guard
from .run_contract import validate_contract
from .run_verdict import contract_digest
from .runtime import run_once
from .script_session import SCRIPT_ROOT


def registered_agent_cases() -> tuple[str, ...]:
    return ("m1_minimal_loop", "m3d_param_reslice")


def agent_contract(case_id: str):
    if type(case_id) is not str or case_id not in registered_agent_cases():
        raise ValueError("agent: case has not been approved for this adapter")
    from cases import CASES
    if not CASES.get(case_id, {}).get("enabled"):
        raise ValueError("agent: case is not enabled in cases.py")
    from .agent_protocol import agent_profile
    if case_id == "m1_minimal_loop":
        steps = [{"id": "boot", "goal": "Observe stable Prepare in a fresh guest session"},
                  {"id": "preview", "goal": "Use model-selected click to reach stable Preview"},
                  {"id": "prepare", "goal": "Use model-selected click to return to stable Prepare"},
                  {"id": "close", "goal": "Close and confirm the owned Job is empty"}]
    else:
        from .agent_protocol import LAYER_FIXTURE_SHA256
        steps = [{"id": "boot", "goal": "Load the fixed single-material 27 mm cube; fixture sha256=" + LAYER_FIXTURE_SHA256},
                 {"id": "baseline", "goal": "GUI slice and export baseline with layer height 0.40 mm"},
                 {"id": "edit", "goal": "Use screenshot-selected native Edit to change layer height to 0.24 mm; preserve first layer 0.40 mm"},
                 {"id": "reslice", "goal": "GUI reslice and export modified G-code; prove actual object extrusion layer spacing"},
                 {"id": "close", "goal": "Close and confirm the owned Job is empty"}]
    return validate_contract({
        "schema_version": 1, "case_id": case_id,
        "contract_version": agent_profile(case_id)["contract_version"],
        "executor": "agent_mcp", "required_checks": ["path", "business"],
        "steps": steps,
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
    if case_id == "m1_minimal_loop":
        from .agent_verify import AgentTabVerifier
        verifier = AgentTabVerifier()
    else:
        from .agent_layer_verify import AgentLayerVerifier
        verifier = AgentLayerVerifier()
    root.mkdir(parents=True, exist_ok=True)
    digest = contract_digest(contract)
    return run_once(contract, AgentExecutor(digest), {digest: verifier},
                    root=root, run_id=run_id, desktop_id="guest-console",
                    execution_mode="guest_agent")
