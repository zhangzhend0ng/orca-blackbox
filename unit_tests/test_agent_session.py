"""Guest composition and runtime guards; all execution ports are simulated."""
from unittest.mock import Mock

import pytest

from harness import agent_session, host_guard
from harness.agent_executor import AgentExecutor
from harness.agent_verify import AgentTabVerifier
from harness.run_verdict import CheckResult, contract_digest
from harness.runtime import run_once
from harness.runtime_ports import ExecutionOutcome, VerificationOutcome
from harness.runtime_smoke import SyntheticHandle

RUN_ID = "a" * 32


def test_registered_intent_is_tabs_only():
    assert agent_session.registered_agent_cases() == ("m1_minimal_loop",)
    contract = agent_session.agent_contract("m1_minimal_loop")
    assert contract.executor == "agent_mcp" and contract.contract_version == "ai-tabs-1"
    assert [s.id for s in contract.steps] == ["boot", "preview", "prepare", "close"]
    assert contract.limits.timeout_s == 900 and contract.limits.max_actions == 12
    with pytest.raises(ValueError, match="approved"):
        agent_session.agent_contract("../../arbitrary.py")


def test_host_override_cannot_start_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: False)
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    launch = Mock()
    monkeypatch.setattr(agent_session, "run_once", launch)
    with pytest.raises(ValueError, match="guest execution required"):
        agent_session.run_agent("m1_minimal_loop", tmp_path / "new", RUN_ID)
    launch.assert_not_called()
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("run_id", [None, "", "a" * 31, "A" * 32, "../run", 123])
def test_run_identity_is_required_before_any_files(monkeypatch, tmp_path, run_id):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    with pytest.raises(ValueError, match="32-hex"):
        agent_session.run_agent("m1_minimal_loop", tmp_path, run_id)
    assert not list(tmp_path.iterdir())


def test_agent_root_cannot_split_desktop_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(agent_session, "SCRIPT_ROOT", tmp_path / "canonical")
    with pytest.raises(ValueError, match="canonical"):
        agent_session.run_agent("m1_minimal_loop", tmp_path / "other", RUN_ID)
    assert not (tmp_path / "other").exists()


def test_composition_uses_fixed_ports_digest_and_shared_desktop(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(agent_session, "SCRIPT_ROOT", tmp_path)
    dispatch = Mock(return_value={"mode": "agent_shadow"})
    monkeypatch.setattr(agent_session, "run_once", dispatch)
    agent_session.run_agent("m1_minimal_loop", tmp_path, RUN_ID)
    contract, executor, registry = dispatch.call_args.args
    assert type(executor) is AgentExecutor
    assert executor.contract_sha256 == contract_digest(contract)
    assert type(registry[contract_digest(contract)]) is AgentTabVerifier
    assert dispatch.call_args.kwargs == {"root": tmp_path, "run_id": RUN_ID,
                                         "desktop_id": "guest-console",
                                         "execution_mode": "guest_agent"}


def test_real_agent_runtime_cannot_be_entered_on_host(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: False)
    contract = agent_session.agent_contract("m1_minimal_loop")
    with pytest.raises(PermissionError, match="Hyper-V"):
        run_once(contract, AgentExecutor(contract_digest(contract)), {}, root=tmp_path,
                 run_id=RUN_ID, execution_mode="guest_agent")
    assert not list(tmp_path.iterdir())


def test_guest_agent_result_cannot_emit_release_green(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    contract = agent_session.agent_contract("m1_minimal_loop")
    monkeypatch.setattr(AgentExecutor, "start", lambda _self, _ctx:
                        SyntheticHandle(ExecutionOutcome("completed")))
    checks = {name: CheckResult("pass", "test-only evidence", ("test-only",))
              for name in contract.required_checks}
    monkeypatch.setattr(AgentTabVerifier, "start", lambda _self, _snapshot:
                        SyntheticHandle(VerificationOutcome(checks, True, True)))
    result = run_once(contract, AgentExecutor(contract_digest(contract)),
                      {contract_digest(contract): AgentTabVerifier()}, root=tmp_path,
                      run_id=RUN_ID, execution_mode="guest_agent")
    assert result["mode"] == "agent_shadow"
    assert result["release_verdict"] == "SHADOW" and not result["release_eligible"]
    assert result["gui_execution_requested"] is True


def test_agent_runtime_rejects_unregistered_verifier(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    contract = agent_session.agent_contract("m1_minimal_loop")
    verifier = Mock(synthetic=False)
    with pytest.raises(ValueError, match="unregistered agent verifier"):
        run_once(contract, AgentExecutor(contract_digest(contract)),
                 {contract_digest(contract): verifier}, root=tmp_path, run_id=RUN_ID,
                 execution_mode="guest_agent")
    assert not list(tmp_path.iterdir())
