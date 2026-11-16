"""Fake process factory, no GUI/real subprocess."""
import os

import pytest

from harness import agent_executor as module
from harness.run_contract import validate_contract
from harness.run_verdict import contract_digest
from harness.runtime_ports import ExecutionContext


@pytest.fixture
def contract():
    return validate_contract({"schema_version": 1, "case_id": "m1_minimal_loop",
        "contract_version": "ai-tabs-1", "executor": "agent_mcp", "required_checks": ["path", "business"],
        "steps": [{"id": "tabs", "goal": "Switch tabs and return"}],
        "limits": {"timeout_s": 900, "max_actions": 12, "max_retries": 0, "max_cost_usd": 0}})


def test_guest_fixed_worker_argv_no_model_credentials(tmp_path, contract, monkeypatch):
    captured = {}
    process = object()
    def start(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return process
    monkeypatch.setattr(module.host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(module.OwnedJobProcess, "start", start)
    monkeypatch.setenv("TEST_MODEL_API_KEY", "dummy-test-only")
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    monkeypatch.setenv("PYTHONIOENCODING", "cp936")
    digest = contract_digest(contract)
    adapter = module.AgentExecutor(digest)
    handle = adapter.start(ExecutionContext(contract, "run1", tmp_path))
    assert handle.process is process
    assert captured["argv"] == [module.sys.executable, str(module.REPO / "harness/agent_guest.py"),
        "--artifact-dir", str(tmp_path), "--run-id", "run1", "--contract-sha256", digest]
    assert "TEST_MODEL_API_KEY" not in captured["env"]
    assert "ORCA_BB_ALLOW_HOST" not in captured["env"]
    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["log_path"] == tmp_path / "agent.log"


def test_host_cannot_run_worker_even_with_allow_host(tmp_path, contract, monkeypatch):
    monkeypatch.setattr(module.host_guard, "in_guest", lambda: False)
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    with pytest.raises(PermissionError):
        module.AgentExecutor(contract_digest(contract)).start(ExecutionContext(contract, "run1", tmp_path))


def test_wrong_contract_or_existing_output_never_starts(tmp_path, contract, monkeypatch):
    monkeypatch.setattr(module.host_guard, "in_guest", lambda: True)
    with pytest.raises(ValueError, match="exact"):
        module.AgentExecutor("0" * 64).start(ExecutionContext(contract, "run1", tmp_path))
    (tmp_path / "ready.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        module.AgentExecutor(contract_digest(contract)).start(ExecutionContext(contract, "run1", tmp_path))
