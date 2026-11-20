"""Pure unit challenges for false passes; no GUI or host-guard override."""
import pytest

from harness.run_verdict import CheckResult, Promotion, aggregate_result, contract_digest


@pytest.fixture
def contract():
    return {"schema_version": 1, "case_id": "case1", "contract_version": "1",
            "executor": "script", "required_checks": ["path", "business"],
            "steps": [{"id": "change", "goal": "Change via GUI"}],
            "limits": {"timeout_s": 120, "max_actions": 20,
                       "max_retries": 0, "max_cost_usd": 0}}


@pytest.fixture
def checks():
    return {name: CheckResult("pass", evidence=(f"checker:{name}:1",))
            for name in ("path", "business")}


def verdict(contract, checks, **kwargs):
    return aggregate_result(contract, "completed", checks, evidence_complete=True,
                            execution_compliant=True, **kwargs)


def test_script_requires_independent_checks(contract, checks):
    result = verdict(contract, checks)
    assert result.verified_pass and result.release_verdict == "GREEN"


@pytest.mark.parametrize("status", ["fail", "unknown", "not_applicable"])
def test_required_check_cannot_be_waived(contract, checks, status):
    checks["path"] = CheckResult(status)
    assert not verdict(contract, checks).verified_pass


def test_missing_check_and_missing_evidence_block(contract, checks):
    checks.pop("business")
    assert "business_unknown" in verdict(contract, checks).reasons
    checks["business"] = CheckResult("pass")
    assert "business_evidence_missing" in verdict(contract, checks).reasons


def test_optional_failure_is_not_averaged_away(contract, checks):
    checks["visual"] = CheckResult("fail", "wrong layout")
    assert not verdict(contract, checks).verified_pass


@pytest.mark.parametrize("status", ["failed", "blocked", "timeout", "cancelled"])
def test_execution_failure_cannot_become_pass(contract, checks, status):
    assert not aggregate_result(contract, status, checks, evidence_complete=True,
                                execution_compliant=True).verified_pass


@pytest.mark.parametrize("field", ["evidence_complete", "execution_compliant"])
def test_missing_evidence_or_path_violation_blocks(contract, checks, field):
    flags = {"evidence_complete": True, "execution_compliant": True}
    flags[field] = False
    assert not aggregate_result(contract, "completed", checks, **flags).verified_pass


def test_hidden_recovery_blocks_but_recorded_recovery_stays_visible(contract, checks):
    assert not verdict(contract, checks, recovery_used=True).verified_pass
    result = verdict(contract, checks, recovery_used=True, recovery_recorded=True)
    assert result.verified_pass and result.recovery_used


@pytest.mark.parametrize("executor", ["agent_mcp", "midscene"])
def test_ai_defaults_shadow_and_promotion_is_contract_bound(contract, checks, executor):
    contract["executor"] = executor
    assert verdict(contract, checks).release_verdict == "SHADOW"
    promotion = Promotion(contract_digest(contract), "review:123")
    assert verdict(contract, checks, promotion=promotion).release_verdict == "GREEN"
    contract["contract_version"] = "2"
    assert verdict(contract, checks, promotion=promotion).release_verdict == "SHADOW"


@pytest.mark.parametrize("bad", ["pass", "skip", "GREEN", True])
def test_invalid_execution_status_rejected(contract, checks, bad):
    with pytest.raises(ValueError, match="execution status"):
        aggregate_result(contract, bad, checks, evidence_complete=True, execution_compliant=True)


def test_model_dictionary_cannot_supply_a_promotion(contract, checks):
    with pytest.raises(ValueError, match="trusted registry"):
        verdict(contract, checks, promotion={"approved": True})


def test_truthy_string_is_not_boolean_evidence(contract, checks):
    with pytest.raises(ValueError, match="boolean"):
        aggregate_result(contract, "completed", checks, evidence_complete="true",
                         execution_compliant=True)


@pytest.mark.parametrize("required", [[], ["path", "path"], ["new_check"], "path", [True]])
def test_invalid_required_checks_rejected(contract, checks, required):
    contract["required_checks"] = required
    with pytest.raises(ValueError, match="required_checks"):
        verdict(contract, checks)


def test_raw_model_result_is_rejected(contract):
    with pytest.raises(ValueError, match="checker results"):
        verdict(contract, {"business": {"status": "pass"}})


def test_incomplete_contract_cannot_produce_green(checks):
    with pytest.raises(ValueError, match="incorrect fields"):
        verdict({"executor": "script", "required_checks": ["path", "business"]}, checks)


def test_promotion_digest_matches_saved_contract_snapshot(contract, tmp_path):
    from harness.run_evidence import RunEvidence
    from harness.run_contract import validate_contract
    import hashlib
    with RunEvidence.create(tmp_path, contract) as run:
        raw = (run.run_dir / "contract.json").read_bytes()
        assert raw.endswith(b"\n")
        assert run.manifest["contract_sha256"] == hashlib.sha256(raw).hexdigest()
        assert contract_digest(contract) == run.manifest["contract_sha256"]
        assert contract_digest(validate_contract(contract)) == run.manifest["contract_sha256"]
