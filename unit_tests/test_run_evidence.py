import hashlib
import json

import pytest

from harness.run_evidence import RunEvidence


@pytest.fixture
def contract_data():
    return {"schema_version": 1, "case_id": "m0_boot_check", "contract_version": "1",
            "executor": "script", "required_checks": ["path", "business"],
            "steps": [{"id": "boot", "goal": "Launch from GUI"}],
            "limits": {"timeout_s": 120, "max_actions": 20,
                       "max_retries": 0, "max_cost_usd": 0}}


def test_create_freezes_contract_and_refuses_existing_run(tmp_path, contract_data):
    with RunEvidence.create(tmp_path, contract_data, run_id="run-one") as run:
        original = (run.run_dir / "contract.json").read_bytes()
        manifest = json.loads((run.run_dir / "manifest.json").read_text())
        assert manifest["contract_sha256"] == hashlib.sha256(original).hexdigest()
        assert manifest["started_at_ns"] > 0
        with pytest.raises(FileExistsError):
            RunEvidence.create(tmp_path, contract_data, run_id="run-one")
        assert (run.run_dir / "contract.json").read_bytes() == original


def test_events_append_chain_then_final_result_is_sealed(tmp_path, contract_data):
    with RunEvidence.create(tmp_path, contract_data) as run:
        run.append_event("step_started", step_id="boot")
        first = (run.run_dir / "events.ndjson").read_bytes()
        run.append_event("step_observed", status="unknown", evidence="shots/frame.png")
        lines = (run.run_dir / "events.ndjson").read_bytes().splitlines()
        assert lines[0] + b"\n" == first
        assert json.loads(lines[1])["previous_sha256"] == hashlib.sha256(lines[0]).hexdigest()
        assert [json.loads(line)["sequence"] for line in lines] == [0, 1]
        result = {"business": "unknown", "execution": "blocked"}
        out = run.finalize(result)
        assert json.loads(out.read_text()) == result
        with pytest.raises(ValueError, match="finalized"):
            run.finalize({"business": "pass"})
        with pytest.raises(ValueError, match="finalized"):
            run.append_event("changed")
        assert json.loads(out.read_text()) == result


@pytest.mark.parametrize("run_id", ["../outside", "/absolute", "..", "bad\\path", "bad:name"])
def test_run_identifiers_cannot_escape_root(tmp_path, contract_data, run_id):
    with pytest.raises(ValueError, match="identifier"):
        RunEvidence.create(tmp_path, contract_data, run_id=run_id)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("reference", ["../secret", "/absolute", "a/../secret", "C:/secret", "a\\b", "a//b", "a\nb"])
def test_event_references_cannot_escape_run(tmp_path, contract_data, reference):
    with RunEvidence.create(tmp_path, contract_data) as run:
        with pytest.raises(ValueError, match="reference"):
            run.append_event("observation", evidence=reference)
        assert (run.run_dir / "events.ndjson").read_bytes() == b""


def test_sensitive_and_nonfinite_result_is_rejected_without_sealing(tmp_path, contract_data):
    with RunEvidence.create(tmp_path, contract_data) as run:
        with pytest.raises(ValueError, match="sensitive"):
            run.finalize({"debug": {"access_token": "not logged"}})
        with pytest.raises(ValueError):
            run.finalize({"cost": float("nan")})
        assert not (run.run_dir / "result.json").exists()
        run.finalize({"business": "unknown"})


def test_existing_result_is_never_overwritten(tmp_path, contract_data):
    with RunEvidence.create(tmp_path, contract_data) as run:
        out = run.run_dir / "result.json"
        out.write_text('{"execution":"failed"}', encoding="utf-8")
        with pytest.raises(FileExistsError):
            run.finalize({"execution": "completed"})
        assert json.loads(out.read_text())["execution"] == "failed"


def test_metadata_has_allowlisted_fields_only(tmp_path, contract_data):
    with pytest.raises(ValueError, match="metadata"):
        RunEvidence.create(tmp_path, contract_data, metadata={"password": "sensitive"})
    assert list(tmp_path.iterdir()) == []
