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
CASES = ("m1_minimal_loop", "m3d_param_reslice", "m3g_export_3mf")


def verifier_type(case_id):
    if case_id == "m1_minimal_loop":
        return AgentTabVerifier
    if case_id == "m3d_param_reslice":
        from harness.agent_layer_verify import AgentLayerVerifier
        return AgentLayerVerifier
    from harness.agent_project_verify import AgentProjectVerifier
    return AgentProjectVerifier


def test_registered_intent_preserves_tabs_and_adds_only_fixed_business_cases():
    assert agent_session.registered_agent_cases() == CASES
    contract = agent_session.agent_contract("m1_minimal_loop")
    assert contract.executor == "agent_mcp" and contract.contract_version == "ai-tabs-1"
    assert [s.id for s in contract.steps] == ["boot", "preview", "prepare", "close"]
    assert contract.limits.timeout_s == 900 and contract.limits.max_actions == 12
    assert contract_digest(contract) == "4fe2d56332c5525524cceed2dccdc3a212995d742c98f828a86fcd15964c0901"
    with pytest.raises(ValueError, match="approved"):
        agent_session.agent_contract("../../arbitrary.py")


def test_layer_contract_binds_fixed_fixture_and_actual_slice_goal():
    from harness.agent_protocol import LAYER_FIXTURE_SHA256
    contract = agent_session.agent_contract("m3d_param_reslice")
    assert contract.contract_version == "ai-layer-1" and contract.executor == "agent_mcp"
    assert [s.id for s in contract.steps] == ["boot", "baseline", "edit", "reslice", "close"]
    assert LAYER_FIXTURE_SHA256 in contract.steps[0].goal
    assert "0.24" in contract.steps[2].goal and "0.40" in contract.steps[2].goal
    assert contract.limits.timeout_s == 900 and contract.limits.max_actions == 12
    assert contract_digest(contract) == "a84be6d0070374966f50ae053a41fe8779ed483f7863fd2055ce75ce99e81114"


def test_project_contract_is_one_save_reopen_slice_chain_with_fixed_limits():
    from harness.agent_protocol import LAYER_FIXTURE_SHA256
    contract = agent_session.agent_contract("m3g_export_3mf")
    assert contract.contract_version == "ai-project-1"
    assert [s.id for s in contract.steps] == ["boot", "edit", "save", "reopen", "slice", "export", "close"]
    assert LAYER_FIXTURE_SHA256 in contract.steps[0].goal
    assert "projects/0001.3mf" in contract.steps[2].goal
    assert "profile_reopen" in contract.steps[3].goal
    assert "exports/0001.gcode" in contract.steps[5].goal
    assert contract.limits.timeout_s == 900 and contract.limits.max_actions == 12
    assert contract.limits.max_retries == 0 and contract.limits.max_cost_usd == 0
    assert contract_digest(contract) == "85e34108df31cd0a79c8de86c7f2b4d6af3b3ecef3c5e5b8d1cdbb5f2c921bbd"


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


@pytest.mark.parametrize("case_id", CASES)
def test_composition_uses_fixed_ports_digest_and_shared_desktop(monkeypatch, tmp_path, case_id):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(agent_session, "SCRIPT_ROOT", tmp_path)
    dispatch = Mock(return_value={"mode": "agent_shadow"})
    monkeypatch.setattr(agent_session, "run_once", dispatch)
    agent_session.run_agent(case_id, tmp_path, RUN_ID)
    contract, executor, registry = dispatch.call_args.args
    assert type(executor) is AgentExecutor
    assert executor.contract_sha256 == contract_digest(contract)
    assert type(registry[contract_digest(contract)]) is verifier_type(case_id)
    options = dict(dispatch.call_args.kwargs)
    cancelled = options.pop("cancelled")
    assert callable(cancelled) and not cancelled()
    assert options == {"root": tmp_path, "run_id": RUN_ID,
                                         "desktop_id": "guest-console",
                                         "execution_mode": "guest_agent"}


@pytest.mark.parametrize("payload", [
    ('{"schema_version":1,"run_id":"' + RUN_ID + '","reason":"host_stopped"}').encode(), b'not JSON'])
def test_host_control_cancel_reaches_runtime_after_worker_exit(monkeypatch, tmp_path, payload):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(agent_session, "SCRIPT_ROOT", tmp_path)
    dispatch = Mock(return_value={"mode": "agent_shadow"})
    monkeypatch.setattr(agent_session, "run_once", dispatch)
    agent_session.run_agent("m3d_param_reslice", tmp_path, RUN_ID)
    cancelled = dispatch.call_args.kwargs["cancelled"]
    other = tmp_path / ("b" * 32) / "artifacts" / "control_cancel.json"
    other.parent.mkdir(parents=True)
    other.write_bytes(payload)
    assert not cancelled()
    current = tmp_path / RUN_ID / "artifacts" / "control_cancel.json"
    current.parent.mkdir(parents=True)
    current.write_bytes(payload)
    # Any control record stops the coordinator too; a dead worker is not
    # needed to parse it, and malformed input cannot defer owned Job cleanup.
    assert cancelled()


def test_real_agent_runtime_cannot_be_entered_on_host(monkeypatch, tmp_path):
    monkeypatch.setattr(host_guard, "in_guest", lambda: False)
    contract = agent_session.agent_contract("m1_minimal_loop")
    with pytest.raises(PermissionError, match="Hyper-V"):
        run_once(contract, AgentExecutor(contract_digest(contract)), {}, root=tmp_path,
                 run_id=RUN_ID, execution_mode="guest_agent")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("case_id", CASES)
def test_guest_agent_result_cannot_emit_release_green(monkeypatch, tmp_path, case_id):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    contract = agent_session.agent_contract(case_id)
    monkeypatch.setattr(AgentExecutor, "start", lambda _self, _ctx:
                        SyntheticHandle(ExecutionOutcome("completed")))
    checks = {name: CheckResult("pass", "test-only evidence", ("test-only",))
              for name in contract.required_checks}
    checker = verifier_type(case_id)
    monkeypatch.setattr(checker, "start", lambda _self, _snapshot:
                        SyntheticHandle(VerificationOutcome(checks, True, True)))
    result = run_once(contract, AgentExecutor(contract_digest(contract)),
                      {contract_digest(contract): checker()}, root=tmp_path,
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


@pytest.mark.parametrize("case_id,other", [(a, b) for a in CASES for b in CASES if a != b])
def test_verifier_cannot_cross_case_boundary(monkeypatch, tmp_path, case_id, other):
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    contract = agent_session.agent_contract(case_id)
    with pytest.raises(ValueError, match="unregistered agent verifier"):
        run_once(contract, AgentExecutor(contract_digest(contract)),
                 {contract_digest(contract): verifier_type(other)()}, root=tmp_path,
                 run_id=RUN_ID, execution_mode="guest_agent")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("case_id", CASES)
@pytest.mark.parametrize("mutation", ["goal", "budget"])
def test_matching_adapter_digest_cannot_authorize_changed_registered_contract(monkeypatch, tmp_path, case_id, mutation):
    from harness.run_contract import validate_contract
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    data = agent_session.agent_contract(case_id).to_dict()
    if mutation == "goal":
        data["steps"][0]["goal"] = "Accept a different fixture"
    else:
        data["limits"]["timeout_s"] = 901
    altered = validate_contract(data)
    start = Mock()
    monkeypatch.setattr(AgentExecutor, "start", start)
    with pytest.raises(ValueError, match="invalid fixed agent contract"):
        run_once(altered, AgentExecutor(contract_digest(altered)), {}, root=tmp_path,
                 run_id=RUN_ID, execution_mode="guest_agent")
    start.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_layer_contract_cannot_relabel_old_tab_version(monkeypatch, tmp_path):
    from harness.run_contract import validate_contract
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    data = agent_session.agent_contract("m3d_param_reslice").to_dict()
    data["contract_version"] = "ai-tabs-1"
    contract = validate_contract(data)
    with pytest.raises(ValueError, match="invalid fixed agent contract"):
        run_once(contract, AgentExecutor(contract_digest(contract)), {}, root=tmp_path,
                 run_id=RUN_ID, execution_mode="guest_agent")
    assert not list(tmp_path.iterdir())
