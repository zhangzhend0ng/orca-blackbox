"""Project challenge routing through a fake MCP client; no guest or model."""
import json
import time

import pytest

from tools import v3_layer_fault_probe as shared
from tools import v3_project_fault_probe as project
from unit_tests.test_v3_layer_fault_probe import Client, RUN


@pytest.mark.parametrize("fault,expected", [
    ("save_before_edit", ["observe", "save_project", "edit", "reopen_project", "slice", "export_gcode", "finish"]),
    ("missing_reopen", ["observe", "edit", "save_project", "observe", "slice", "export_gcode", "finish"]),
    ("missing_slice", ["observe", "edit", "save_project", "reopen_project", "observe", "export_gcode", "finish"]),
])
def test_project_faults_are_isolated_fixed_sources_without_inference(tmp_path, monkeypatch, fault, expected):
    monkeypatch.setattr(shared.host, "REPO", tmp_path)
    root = tmp_path / "artifacts/v3_host" / RUN
    root.mkdir(parents=True)
    client, model = Client(), project.ProjectFaultModel(fault, RUN)
    result = shared.host.control_loop(client, model, root, time.monotonic()+60, model.case_id)
    assert result["finished"] and [name for name, _args in client.calls] == expected
    assert model.source == "fault_probe_project_" + fault
    edit = next(args for name, args in client.calls if name == "edit")
    assert (edit["x"], edit["y"], edit["text"]) == (298, 764, "0.24")
    records = [json.loads(p.read_text()) for p in root.glob("model_*/summary.json")]
    assert len(records) == 6 and all(r["ai_trial"] is False and r["model_inference"] is False for r in records)
    assert not (root / "fault_injection_request.json").exists()


def test_project_probe_uses_project_contract_and_leaves_verdict_to_guest(tmp_path, monkeypatch):
    monkeypatch.setattr(shared.host, "REPO", tmp_path)
    root = tmp_path / "artifacts/v3_host" / RUN
    def host(run, guest, model, case):
        assert case == "m3g_export_3mf" and model.case_id == case
        root.mkdir(parents=True)
        (root / "host_run.json").write_text(json.dumps({"run_id": run, "model_source": model.source}))
        return {"finished": True}
    monkeypatch.setattr(shared.host, "run_host", host)
    value = project.run_probe(RUN, r"C:\coil\orca-blackbox-v3-r1", "save_before_edit")
    assert value["expected_release_verdict"] == "NON_GREEN" and value["observed_release_verdict"] is None
    assert value["cleanup_confirmed"] is None and value["ai_trial"] is False


@pytest.mark.parametrize("fault", ["export_collision", "wrong_parameter", "shell", "../path"])
def test_project_cannot_select_layer_faults_or_arbitrary_operations(fault):
    with pytest.raises(ValueError, match="unknown_fault"):
        project.ProjectFaultModel(fault, RUN)
