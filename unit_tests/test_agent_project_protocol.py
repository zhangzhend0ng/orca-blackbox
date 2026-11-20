"""Project capability authority checks, without GUI or worker startup."""
import pytest

from harness.agent_protocol import PROJECT_CASE, ProtocolError, agent_profile, validate_request


def request(method, arguments=None, observation="run_0001", seq=2):
    return {"schema_version": 1, "run_id": "run", "seq": seq, "method": method,
            "arguments": {} if arguments is None else arguments, "observation_id": observation}


@pytest.mark.parametrize("method", ["save_project", "reopen_project"])
def test_project_tools_are_registered_only_for_project_case(method):
    value = request(method)
    assert validate_request(value, run_id="run", expected_seq=2, observation_id="run_0001",
                            case_id=PROJECT_CASE) == value
    assert agent_profile(PROJECT_CASE)["contract_version"] == "ai-project-1"
    for legacy in ("m1_minimal_loop", "m3d_param_reslice"):
        with pytest.raises(ProtocolError, match="unknown_tool"):
            validate_request(value, run_id="run", expected_seq=2, observation_id="run_0001", case_id=legacy)


@pytest.mark.parametrize("method", ["save_project", "reopen_project"])
@pytest.mark.parametrize("arguments", [{"path": "../user.3mf"}, {"profile": "real-user"}, {"force": True}])
def test_model_cannot_supply_paths_profiles_or_overwrite_authority(method, arguments):
    with pytest.raises(ProtocolError, match="invalid_arguments"):
        validate_request(request(method, arguments), run_id="run", expected_seq=2,
                         observation_id="run_0001", case_id=PROJECT_CASE)


@pytest.mark.parametrize("method", ["save_project", "reopen_project"])
def test_project_tools_cannot_start_without_observation_or_replay_old_one(method):
    with pytest.raises(ProtocolError, match="observe_first"):
        validate_request(request(method, observation=None, seq=1), run_id="run", expected_seq=1,
                         observation_id=None, case_id=PROJECT_CASE)
    with pytest.raises(ProtocolError, match="stale_observation"):
        validate_request(request(method), run_id="run", expected_seq=2,
                         observation_id="run_0002", case_id=PROJECT_CASE)


def test_profile_copy_does_not_mutate_registered_capabilities():
    profile = agent_profile(PROJECT_CASE)
    profile["tools"] = ("shell",)
    profile["contract_version"] = "anything"
    assert "shell" not in agent_profile(PROJECT_CASE)["tools"]
    assert agent_profile(PROJECT_CASE)["contract_version"] == "ai-project-1"
