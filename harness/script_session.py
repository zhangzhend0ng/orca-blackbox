"""Trusted composition root for the first guest Script integration.

This allowlist is a capability subset of cases.py, not another full case list.
Only m0 bootstrap is approved here; no model, arbitrary command or release gate.
"""
from pathlib import Path

from . import host_guard
from .run_contract import validate_contract
from .run_verdict import contract_digest
from .runtime import run_once

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "v3"


def registered_script_cases() -> tuple[str, ...]:
    return ("m0_boot_check",)


def script_contract(case_id: str):
    if type(case_id) is not str or case_id not in registered_script_cases():
        raise ValueError("script: case has not been approved for this adapter")
    from cases import CASES
    if not CASES.get(case_id, {}).get("enabled"):
        raise ValueError("script: case is not enabled in cases.py")
    return validate_contract({
        "schema_version": 1, "case_id": case_id, "contract_version": "1",
        "executor": "script", "required_checks": ["path", "business"],
        "steps": [
            {"id": "boot", "goal": "Launch the guest app with an exclusive new profile"},
            {"id": "capture", "goal": "Capture three complete nonconstant BMP frames"},
            {"id": "close", "goal": "Close the app and confirm the owned Job is empty"},
        ],
        "limits": {"timeout_s": 240, "max_actions": 20,
                   "max_retries": 0, "max_cost_usd": 0},
    })


def run_script(case_id: str, root: Path) -> dict:
    # The opt-out environment variable deliberately does not bypass this gate.
    if not host_guard.in_guest():
        raise ValueError("script: guest execution required")
    contract = script_contract(case_id)
    root = Path(root).resolve()
    if root != SCRIPT_ROOT.resolve():
        raise ValueError("script: use the canonical guest evidence root")
    from .script_executor import ScriptExecutor
    from .script_verify import M0ScriptVerifier
    root.mkdir(parents=True, exist_ok=True)
    digest = contract_digest(contract)
    return run_once(contract, ScriptExecutor(digest),
                    {digest: M0ScriptVerifier()}, root=root,
                    desktop_id="guest-console", execution_mode="guest_script")
