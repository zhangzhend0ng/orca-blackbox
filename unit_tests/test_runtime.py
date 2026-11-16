"""Complete synthetic lifecycle tests; no GUI, shell, network, or real sleep."""
import hashlib
import json

import pytest

from harness.run_verdict import contract_digest
from harness.runtime import run_once
from harness.runtime_smoke import (ARTIFACT, PAYLOAD, SyntheticExecutor,
                                   SyntheticHandle, SyntheticVerifier, run_smoke, smoke_contract)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def run(root, *, executor=None, verifier=None, desktop_id="test-desktop", **kwargs):
    contract = smoke_contract()
    clock = FakeClock()
    return run_once(contract, executor or SyntheticExecutor(),
                    {contract_digest(contract): verifier or SyntheticVerifier()},
                    root=root, desktop_id=desktop_id, clock=clock, sleep=clock.sleep,
                    **kwargs)


def lock_path(root, desktop_id="test-desktop"):
    return root / ".desktop_locks" / (hashlib.sha256(desktop_id.encode()).hexdigest() + ".lock")


def test_smoke_executes_real_chain_and_never_claims_release(tmp_path):
    output = run_smoke(tmp_path)
    result = output
    assert output["mode"] == "synthetic"
    assert output["gui_executed"] is False
    assert output["release_eligible"] is False
    assert result["verified_pass"] is True
    assert result["release_verdict"] != "GREEN"
    assert result["execution_status"] == "completed"
    with open(output["result_path"], encoding="utf-8") as stream:
        persisted = json.load(stream)
    assert all(output[key] == value for key, value in persisted.items())
    assert "GREEN" not in json.dumps(output)
    with open(output["manifest_path"], encoding="utf-8") as stream:
        manifest = json.load(stream)
    assert manifest["contract_sha256"] == contract_digest(smoke_contract())


def test_success_cleans_executor_and_verifier_and_releases_lock(tmp_path):
    executor, verifier = SyntheticExecutor(), SyntheticVerifier()
    output = run(tmp_path, executor=executor, verifier=verifier)
    assert output["verified_pass"]
    assert executor.handle.cleanup_started and verifier.handle.cleanup_started
    assert not lock_path(tmp_path).exists()


def test_executor_failure_cannot_be_healed_by_file_success(tmp_path):
    executor = SyntheticExecutor(outcome_status="failed")
    output = run(tmp_path, executor=executor)
    assert output["execution_status"] == "failed"
    assert output["verified_pass"] is False
    assert executor.handle.cleanup_started


@pytest.mark.parametrize("status", ["fail", "unknown"])
def test_independent_verifier_blocks_executor_claim(tmp_path, status):
    output = run(tmp_path, verifier=SyntheticVerifier(forced_status=status))
    assert output["execution_status"] == "completed"
    assert not output["verified_pass"]


def test_missing_artifact_is_not_a_verified_pass(tmp_path):
    output = run(tmp_path, executor=SyntheticExecutor(write_artifact=False))
    assert not output["verified_pass"]


def test_unregistered_verifier_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        run_once(smoke_contract(), SyntheticExecutor(), {}, root=tmp_path)


def test_unmatched_executor_kind_is_rejected(tmp_path):
    executor = SyntheticExecutor()
    executor.kind = "agent_mcp"
    with pytest.raises(ValueError):
        run(tmp_path, executor=executor)


def test_nonsynthetic_executor_is_rejected_without_starting(tmp_path):
    executor = SyntheticExecutor()
    executor.synthetic = False
    with pytest.raises(ValueError):
        run(tmp_path, executor=executor)
    assert executor.handle is None


def test_deadline_cancels_pending_executor_then_cleans(tmp_path):
    executor = SyntheticExecutor(pending_polls=10000)
    output = run(tmp_path, executor=executor)
    assert output["execution_status"] == "timeout"
    assert not output["verified_pass"]
    assert executor.handle.cancel_reasons
    assert executor.handle.cleanup_started


def test_verifier_deadline_cancels_verifier_then_cleans(tmp_path):
    verifier = SyntheticVerifier(pending_polls=10000)
    output = run(tmp_path, verifier=verifier, verify_timeout_s=1)
    assert not output["verified_pass"]
    assert verifier.handle.cancel_reasons
    assert verifier.handle.cleanup_started


def test_unconfirmed_cleanup_retains_desktop_lock(tmp_path):
    output = run(tmp_path, executor=SyntheticExecutor(cleanup_confirmed=False))
    assert not output["verified_pass"]
    assert lock_path(tmp_path).exists()
    with pytest.raises(FileExistsError):
        run(tmp_path)


def test_existing_desktop_lease_prevents_any_start(tmp_path):
    lease = lock_path(tmp_path)
    lease.parent.mkdir()
    lease.write_text("already owned", encoding="utf-8")
    executor = SyntheticExecutor()
    with pytest.raises(FileExistsError):
        run(tmp_path, executor=executor)
    assert executor.handle is None
    assert lease.read_text(encoding="utf-8") == "already owned"


def test_first_failure_remains_unchanged_after_new_success(tmp_path):
    first = run(tmp_path, verifier=SyntheticVerifier(forced_status="fail"))
    original = open(first["result_path"], "rb").read()
    second = run(tmp_path)
    assert not first["verified_pass"]
    assert second["verified_pass"]
    assert first["run_dir"] != second["run_dir"]
    assert open(first["result_path"], "rb").read() == original


def test_run_identifier_cannot_overwrite_prior_evidence(tmp_path):
    run(tmp_path, run_id="same-id")
    with pytest.raises(FileExistsError):
        run(tmp_path, run_id="same-id")


def test_verdict_dict_contains_only_standard_json_values():
    from harness.run_verdict import CheckResult, aggregate_result
    result = aggregate_result(smoke_contract(), "completed",
                              {"path": CheckResult("pass", evidence=("p",)),
                               "business": CheckResult("unknown")},
                              evidence_complete=False, execution_compliant=True).to_dict()
    assert isinstance(result["reasons"], list)
    assert isinstance(result["checks"]["path"]["evidence"], list)
    assert json.loads(json.dumps(result)) == result


def test_cancellation_is_recorded_and_executor_is_stopped(tmp_path):
    executor = SyntheticExecutor(pending_polls=10000)
    output = run(tmp_path, executor=executor, cancelled=lambda: True)
    assert output["execution_status"] == "cancelled"
    assert not output["verified_pass"]
    assert executor.handle.cancel_reasons and executor.handle.cleanup_started


def test_nonsynthetic_verifier_is_rejected_before_execution(tmp_path):
    executor, verifier = SyntheticExecutor(), SyntheticVerifier()
    verifier.synthetic = False
    with pytest.raises(ValueError):
        run(tmp_path, executor=executor, verifier=verifier)
    assert executor.handle is None


def test_partial_start_failure_preserves_error_evidence_and_quarantines(tmp_path):
    class BrokenExecutor(SyntheticExecutor):
        def start(self, context):
            (context.artifact_dir / "partial.txt").write_text("partial synthetic work", encoding="utf-8")
            raise RuntimeError("synthetic partial start")
    with pytest.raises(RuntimeError, match="synthetic partial start"):
        run(tmp_path, executor=BrokenExecutor(), run_id="partial-start")
    assert lock_path(tmp_path).exists()
    result = json.loads((tmp_path / "partial-start" / "result.json").read_text(encoding="utf-8"))
    assert not result["verified_pass"] and not result["cleanup_confirmed"]


def test_verifier_start_failure_prevents_destructive_executor_cleanup(tmp_path):
    class BrokenVerifier(SyntheticVerifier):
        def start(self, snapshot):
            raise RuntimeError("synthetic verifier start failed")
    executor = SyntheticExecutor()
    with pytest.raises(RuntimeError, match="synthetic verifier start failed"):
        run(tmp_path, executor=executor, verifier=BrokenVerifier())
    assert lock_path(tmp_path).exists()
    assert executor.handle.cancel_reasons
    assert not executor.handle.cleanup_started


def test_unconfirmed_verifier_cleanup_blocks_remaining_cleanup(tmp_path):
    executor, verifier = SyntheticExecutor(), SyntheticVerifier(cleanup_confirmed=False)
    output = run(tmp_path, executor=executor, verifier=verifier)
    assert not output["verified_pass"] and lock_path(tmp_path).exists()
    assert verifier.handle.cleanup_started
    assert not executor.handle.cleanup_started
    assert executor.handle.cancel_reasons


def test_executor_cannot_return_checker_verdict_instead_of_execution_facts(tmp_path):
    class DishonestExecutor(SyntheticExecutor):
        def start(self, context):
            self.handle = SyntheticHandle({"execution_status": "completed", "verified_pass": True})
            return self.handle
    with pytest.raises(TypeError, match="execution outcome"):
        run(tmp_path, executor=DishonestExecutor(), run_id="bad-outcome")
    result = json.loads((tmp_path / "bad-outcome" / "result.json").read_text(encoding="utf-8"))
    assert not result["verified_pass"]


def test_same_desktop_nested_dispatch_is_blocked(tmp_path):
    class NestedExecutor(SyntheticExecutor):
        def start(self, context):
            run(tmp_path)
            raise AssertionError("nested dispatch must not succeed")
    with pytest.raises(FileExistsError):
        run(tmp_path, executor=NestedExecutor())
    assert lock_path(tmp_path).exists()


def test_time_spent_starting_executor_counts_toward_case_deadline(tmp_path):
    clock = FakeClock()

    class SlowStart(SyntheticExecutor):
        def start(self, context):
            handle = super().start(context)
            clock.now += 3
            return handle

    executor, verifier = SlowStart(), SyntheticVerifier()
    contract = smoke_contract()
    output = run_once(contract, executor, {contract_digest(contract): verifier},
                      root=tmp_path, clock=clock, sleep=clock.sleep)
    assert output["execution_status"] == "timeout"
    assert not output["verified_pass"]
    assert verifier.calls == 0
    assert executor.handle.cleanup_started


def test_verification_uses_remaining_case_budget_not_a_fresh_timeout(tmp_path):
    clock = FakeClock()
    contract = smoke_contract()
    executor = SyntheticExecutor(pending_polls=150)
    verifier = SyntheticVerifier(pending_polls=100)
    output = run_once(contract, executor, {contract_digest(contract): verifier},
                      root=tmp_path, verify_timeout_s=30,
                      clock=clock, sleep=clock.sleep)
    assert output["execution_status"] == "completed"
    assert output["runtime_status"] == "verification_timeout"
    assert not output["verified_pass"]
    assert clock.now <= contract["limits"]["timeout_s"]
    assert verifier.handle.cancel_reasons

