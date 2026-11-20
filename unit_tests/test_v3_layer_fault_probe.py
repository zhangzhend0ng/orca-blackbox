"""Fault controllers with fake MCP only; no VM, relay, model, or GUI calls."""
import base64
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from tools import v3_layer_fault_probe as probe

RUN = "a" * 32
PNG = b"\x89PNG\r\n\x1a\nfixture"


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.host, "REPO", tmp_path)
    path = tmp_path / "artifacts/v3_host" / RUN
    path.mkdir(parents=True)
    return path


class Client:
    def __init__(self, fail_export=False):
        self.calls, self.fail_export = [], fail_export
    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if self.fail_export and name == "export_gcode" and len(self.calls) > 3:
            return {"isError": True, "content": []}
        meta = {"observation_id": f"{RUN}_{len(self.calls):04d}", "width": 1920, "height": 1032,
                "finished": name == "finish", "image_sha256": hashlib.sha256(PNG).hexdigest()}
        return {"isError": False, "content": [{"type": "text", "text": json.dumps(meta)},
            {"type": "image", "mimeType": "image/png", "data": base64.b64encode(PNG).decode()}]}


def ack():
    return {"schema_version": 1, "run_id": RUN, "fault": "export_collision",
        "path": "exports/0002.gcode", "sha256": probe.COLLISION_SHA256,
        "size_bytes": len(probe.COLLISION_BYTES), "created_new": True}


def acknowledge_after_request(monkeypatch, root, value=None):
    original = probe._once
    def write(path, data):
        original(path, data)
        if path.name == "fault_injection_request.json":
            original(root / "fault_injection_ack.json", ack() if value is None else value)
    monkeypatch.setattr(probe, "_once", write)


@pytest.mark.parametrize("fault,y,sequence", [
    ("wrong_parameter", 794, ["observe", "slice", "export_gcode", "edit", "slice", "export_gcode", "finish"]),
    ("missing_reslice", 764, ["observe", "slice", "export_gcode", "edit", "observe", "export_gcode", "finish"]),
    ("export_collision", 764, ["observe", "slice", "export_gcode", "edit", "slice", "export_gcode", "finish"]),
])
def test_real_host_loop_uses_exact_fixed_challenge_and_labels_it_non_ai(root, monkeypatch, fault, y, sequence):
    if fault == "export_collision":
        acknowledge_after_request(monkeypatch, root)
    client, model = Client(), probe.FaultProbeModel(fault, RUN)
    result = probe.host.control_loop(client, model, root, time.monotonic()+60, probe.CASE)
    assert result["finished"] and [name for name, args in client.calls] == sequence
    edit = next(args for name, args in client.calls if name == "edit")
    assert edit == {"observation_id": f"{RUN}_0003", "x": 298, "y": y, "text": "0.24"}
    assert model.source == "fault_probe_" + fault
    assert "verified_pass" not in result and "cleanup_confirmed" not in result
    summaries = [json.loads(path.read_text()) for path in root.glob("model_*/summary.json")]
    assert summaries and all(row["ai_trial"] is False and row["model_inference"] is False for row in summaries)
    assert all(row["source"] == model.source for row in summaries)
    if fault == "export_collision":
        request = json.loads((root / "fault_injection_request.json").read_text())
        assert request["path"] == "exports/0002.gcode" and request["operation"] == "create_new"
        assert hashlib.sha256(request["content_ascii"].encode("ascii")).hexdigest() == request["sha256"]
        assert json.loads((root / "fault_injection_accepted.json").read_text()) == ack()


def test_missing_reslice_tool_error_stops_without_finish_retry_or_extra_input(root):
    client = Client(fail_export=True)
    with pytest.raises(ValueError, match="tool_failed"):
        probe.host.control_loop(client, probe.FaultProbeModel("missing_reslice", RUN), root,
                                time.monotonic()+60, probe.CASE)
    assert [name for name,args in client.calls] == ["observe", "slice", "export_gcode", "edit", "observe", "export_gcode"]


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"run_id": "b"*32}, {"fault": "missing_reslice"},
    {"path": "exports/0001.gcode"}, {"path": "../outside"}, {"sha256": "f"*64},
    {"size_bytes": True}, {"created_new": False}, {"extra": 1},
])
def test_wrong_or_coerced_collision_ack_never_reaches_second_export(root, monkeypatch, change):
    acknowledge_after_request(monkeypatch, root, {**ack(), **change})
    client = Client()
    with pytest.raises(ValueError, match="injection_ack_identity"):
        probe.host.control_loop(client, probe.FaultProbeModel("export_collision", RUN), root,
                                time.monotonic()+60, probe.CASE)
    assert [name for name,args in client.calls] == ["observe", "slice", "export_gcode", "edit", "slice"]
    assert not (root / "fault_injection_accepted.json").exists()


def test_collision_ack_timeout_is_bounded_and_does_not_publish_acceptance(root, monkeypatch):
    now = [0.]
    monkeypatch.setattr(probe, "time", SimpleNamespace(monotonic=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0]+seconds)))
    with pytest.raises(TimeoutError, match="injection_ack_deadline"):
        probe.FaultProbeModel("export_collision", RUN)._collision_ack(root, 999)
    assert 60 <= now[0] < 61
    assert not (root / "fault_injection_accepted.json").exists()


def test_collision_request_does_not_overwrite_a_prior_injection_record(root):
    path = root / "fault_injection_request.json"
    path.write_text("keep")
    with pytest.raises(FileExistsError):
        probe.FaultProbeModel("export_collision", RUN)._collision_ack(root, time.monotonic()+60)
    assert path.read_text() == "keep"


@pytest.mark.parametrize("fault,run", [("shell",RUN), ("wrong_parameter","../old"), (True,RUN)])
def test_only_registered_faults_and_fresh_run_ids_are_accepted(fault, run):
    with pytest.raises(ValueError):
        probe.FaultProbeModel(fault, run)


@pytest.mark.parametrize("window", [{"width": 1186, "height": 792}, {"width": 1920., "height": 1032}])
def test_uncalibrated_or_coerced_dimensions_cannot_trigger_input(root, window):
    with pytest.raises(ValueError, match="uncalibrated"):
        probe.FaultProbeModel("wrong_parameter", RUN).next_action(root / "observation_0001.png",
            {"id":"obs_1", "window":window}, [], 8, root / "model_0001", time.monotonic()+60)
    assert not (root / "model_0001").exists()


@pytest.mark.parametrize("ident", ["b"*32 + "_0001", RUN + "_0002", "obs_1"])
def test_observation_must_match_this_run_and_next_sequence_before_any_receipt(root, ident):
    with pytest.raises(ValueError, match="stale_observation"):
        probe.FaultProbeModel("wrong_parameter", RUN).next_action(root / "observation_0001.png",
            {"id":ident,"window":{"width":1920,"height":1032}}, [], 8,
            root / "model_0001", time.monotonic()+60)
    assert not list(root.iterdir())


def test_existing_run_is_not_modified_or_started(root, monkeypatch):
    monkeypatch.setattr(probe.host, "run_host", lambda *args: pytest.fail("old run must not start"))
    with pytest.raises(FileExistsError, match="new_run"):
        probe.run_probe(RUN, r"C:\coil\orca-blackbox-v3-r1", "wrong_parameter")
    assert not list(root.iterdir())


@pytest.mark.parametrize("fail", [False, True])
def test_probe_summary_does_not_claim_guest_verdict_or_cleanup(tmp_path, monkeypatch, fail):
    monkeypatch.setattr(probe.host, "REPO", tmp_path)
    root = tmp_path / "artifacts/v3_host" / RUN
    def run_host(run_id, guest_root, model, case_id):
        assert case_id == probe.CASE and model.source == "fault_probe_wrong_parameter"
        root.mkdir(parents=True)
        (root / "host_run.json").write_text(json.dumps({"run_id":RUN,"model_source":model.source}))
        if fail:
            raise ValueError("tool_failed")
        return {"finished": True}
    monkeypatch.setattr(probe.host, "run_host", run_host)
    if fail:
        with pytest.raises(ValueError, match="tool_failed"):
            probe.run_probe(RUN, r"C:\coil\orca-blackbox-v3-r1", "wrong_parameter")
    else:
        probe.run_probe(RUN, r"C:\coil\orca-blackbox-v3-r1", "wrong_parameter")
    result = json.loads((root / "fault_probe.json").read_text())
    assert result["ai_trial"] is False and result["expected_release_verdict"] == "NON_GREEN"
    assert result["observed_release_verdict"] is None and result["cleanup_confirmed"] is None
    assert result["disposition"] == "awaiting_independent_guest_evidence"
    assert result["host_finished"] is not fail


@pytest.mark.parametrize("argv", [
    ["--run-id",RUN,"--fault","shell"],
    ["--run-id",RUN,"--fault","wrong_parameter","--script","anything.ps1"],
])
def test_cli_rejects_unknown_faults_or_arbitrary_script_switch(monkeypatch, argv):
    monkeypatch.setattr(probe, "run_probe", lambda *args: pytest.fail("invalid CLI must not run"))
    with pytest.raises(SystemExit) as raised:
        probe.main(argv)
    assert raised.value.code == 2
