"""Build-report evidence binding, using generated project and G-code artifacts only."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from tools import gui_build_report as report
from unit_tests.test_agent_layer_verify import gcode
from unit_tests.test_agent_project_verify import project_bytes


CANDIDATE = "layer-pilot-test"
DIGEST = "f" * 64
FIXTURE = (report.ROOT / report.LAYER_FIXTURE).read_bytes()


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def archive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def mac_run(folder, control=False):
    height = "0.32" if control else "0.24"

    def settings(members):
        key = "Metadata/project_settings.config"
        config = json.loads(members[key])
        config["layer_height"] = height
        members[key] = json.dumps(config).encode()

    saved = archive(folder / "layer-024-copy.3mf", project_bytes(FIXTURE, settings))
    guest = {"run_id": folder.name, "ok": True, "cleanup_verified": True, "saved_sha256": saved,
             "source_before": report.LAYER_FIXTURE_SHA256, "source_after": report.LAYER_FIXTURE_SHA256,
             "sut": {"build": "1", "version": "2.4.1", "executable_sha256": DIGEST},
             "phases": {p: {"pid": i, "layers": [height if p == "reopen" else "0.4", "0.4"]}
                        for i, p in enumerate(("baseline", "edit", "reopen"), 1)}, "slice_receipts": {}}
    result = {"candidate": CANDIDATE, "run_id": folder.name, "test_kind": "layer_comparison",
              "verdict": "SHADOW", "guest": guest, "slices": {}}
    for name, phase, step in (("baseline", "baseline", "0.4"), ("edited", "reopen", height)):
        raw = gcode(step)
        filename = f"{name}.gcode"
        sha = archive(folder / filename, raw)
        guest["slice_receipts"][name] = {"sha256": sha, "size": len(raw), "phase": phase, "source": "open_process_plate",
                                         "pid": guest["phases"][phase]["pid"],
                                         "project_sha256": saved if name == "edited" else report.LAYER_FIXTURE_SHA256,
                                         "export_enabled_before": False, "export_enabled_after": True}
        if name == "baseline" or not control:
            result["slices"][name] = {**report.analyze_gcode(raw, layer_height=step),
                                      "artifact": filename, "origin": "gui_plate_temporary"}
    if control:
        result.update(test_kind="wrong_layer_control", verdict="NON_GREEN", failure_stage="verify.saved_project",
                      error="project_layer_config")
    return put(folder / "result.json", result)


def win_run(folder, baseline=False):
    run_id = folder.name
    put(folder / "binding.json", {"run_id": run_id, "candidate_id": CANDIDATE, "sut_version": "2.4.1",
                                  "sut_sha256": DIGEST, "fixture_sha256": report.LAYER_FIXTURE_SHA256,
                                  "post_verified_at": "2026-11-20T12:32:00Z"})
    put(folder / "manifest.json", {"case_id": "m3g_export_3mf", "run_id": run_id, "started_at": "2026-11-20",
                                   "contract_sha256": DIGEST})
    put(folder / "setup.json", {"run_id": run_id, "app_pid": 1,
                                "scenario": "uia_replay_save" if baseline else "uia_replay_layer"})
    project = archive(folder / "projects/0001.3mf", FIXTURE if baseline else project_bytes(FIXTURE))
    sliced = archive(folder / "exports/0001.gcode", gcode("0.4" if baseline else "0.24"))
    put(folder / "proof.json", {"old_pid": 1, "reopened_pid": 2, "reopened_closed": True, "run_id": run_id,
                                "contract_sha256": DIGEST, "sut_sha256": DIGEST,
                                "project_sha256": project, "gcode_sha256": sliced})
    return put(folder / "result.json", {"verified_pass": True, "release_verdict": "SHADOW", "cleanup_confirmed": True})


def summary(**paths):
    args = {"candidate": CANDIDATE, "windows": None, "windows_baseline": None, "macos": None,
            "negative_control": None, "historical_windows": [], "historical_macos": []}
    return report.build_report(SimpleNamespace(**{**args, **paths}))


def test_two_independent_windows_runs_and_mac_control(tmp_path):
    mac = mac_run(tmp_path / "mac")
    control = mac_run(tmp_path / "control", control=True)
    edited = win_run(tmp_path / "win-edited")
    baseline = win_run(tmp_path / "win-baseline", True)
    got = summary(macos=mac, windows=edited, windows_baseline=baseline, negative_control=control)
    assert got["status"] == "SHADOW" and got["version_comparison"] == "SAME_VERSION"
    for row in got["platforms"].values():
        assert [row["slices"][p]["layer_count"] for p in ("baseline", "edited")] == [68, 112]
    assert got["platforms"]["windows"]["baseline_run"]["baseline_input"] == "unmodified_settings_saved_copy"
    assert got["negative_control"]["status"] == "EXPECTED_FAILURE"
    assert got["negative_control"]["observed_rejected_slice"]["layer_height"] == "0.32"
    assert "edited" not in got["negative_control"]["slices"]


def test_history_and_missing_baseline_do_not_fill_current_slots(tmp_path):
    mac = mac_run(tmp_path / "mac")
    got = summary(historical_macos=[mac], windows=win_run(tmp_path / "edited"))
    assert got["status"] == "INCOMPLETE"
    assert got["platforms"]["macos"]["status"] == "NOT_RUN" and got["historical"][0]["scope"] == "historical"
    assert got["platforms"]["windows"]["missing"] == ["baseline_slice"]


@pytest.mark.parametrize("interrupted", ["baseline", "edited"])
def test_missing_windows_postcheck_keeps_current_pair_incomplete(tmp_path, interrupted):
    edited = win_run(tmp_path / "edited")
    baseline = win_run(tmp_path / "baseline", True)
    path = tmp_path / interrupted / "binding.json"
    binding = report.read_json(path)
    del binding["post_verified_at"]
    put(path, binding)
    row = summary(windows=edited, windows_baseline=baseline)["platforms"]["windows"]
    assert row["status"] == "INCOMPLETE"
    assert "post_verified_at" in (row["baseline_run"] if interrupted == "baseline" else row)["missing"]
    history = report.platform_row("windows", tmp_path / interrupted / "result.json", "historical",
                                  CANDIDATE, baseline=interrupted == "baseline")
    assert "post_verified_at" not in history["missing"] and history["slices"]


@pytest.mark.parametrize("source", ["binding.json", "attempt.json"])
def test_blocked_windows_attempt_rejects_wrong_scenario(tmp_path, source):
    edited = win_run(tmp_path / "edited")
    attempt = {"candidate_id": CANDIDATE, "run_id": "edited", "verdict": "BLOCKED",
               "error": "identity unavailable", "failure_stage": "guest.host_guard",
               "scenario": "uia_replay_layer"}
    put(edited.parent / "attempt.json", attempt)
    path = edited.parent / source
    data = report.read_json(path)
    data["scenario"] = "uia_replay_save"
    put(path, data)
    row = summary(windows=edited)["platforms"]["windows"]
    assert row["status"] == "INVALID_EVIDENCE" and "scenario" in row["error"]


@pytest.mark.parametrize("damage", ["source", "plate_origin", "transition", "candidate", "file"])
def test_mismatched_mac_evidence_is_rejected(tmp_path, damage):
    path = mac_run(tmp_path)
    data = report.read_json(path)
    receipt = data["guest"]["slice_receipts"]["edited"]
    if damage == "source":
        receipt["project_sha256"] = DIGEST
    elif damage == "plate_origin":
        receipt["source"] = "previous_run"
    elif damage == "transition":
        receipt["export_enabled_before"] = True
    elif damage == "candidate":
        data["candidate"] = "other-request"
    else:
        (tmp_path / "edited.gcode").unlink()
    put(path, data)
    assert summary(macos=path)["platforms"]["macos"]["status"] == "INVALID_EVIDENCE"


def test_unrelated_control_failure_cannot_pass(tmp_path):
    path = mac_run(tmp_path, control=True)
    data = report.read_json(path)
    data.update(failure_stage="transport", error="SSH timeout")
    put(path, data)
    assert summary(negative_control=path)["negative_control"]["status"] == "INVALID_EVIDENCE"


@pytest.mark.parametrize("change", ["same_run", "different_sut", "different_fixture", "no_positive"])
def test_wrong_layer_control_needs_a_matching_positive(tmp_path, change):
    mac = mac_run(tmp_path / "mac")
    control = mac_run(tmp_path / "control", control=True)
    data = report.read_json(control)
    if change == "same_run":
        data["run_id"] = data["guest"]["run_id"] = "mac"
    elif change == "different_sut":
        data["guest"]["sut"]["executable_sha256"] = "9" * 64
    elif change == "different_fixture":
        data["guest"]["source_before"] = "9" * 64
    else:
        mac = None
    put(control, data)
    row = summary(macos=mac, negative_control=control)["negative_control"]
    assert row["status"] == ("UNPAIRED_CONTROL" if change == "no_positive" else "INVALID_EVIDENCE")


def test_windows_preflight_block_keeps_identity_and_error(tmp_path):
    put(tmp_path / "binding.json", {"candidate_id": CANDIDATE, "run_id": "failed", "sut_version": "2.4.0",
                                    "sut_sha256": DIGEST, "fixture_sha256": report.LAYER_FIXTURE_SHA256})
    path = put(tmp_path / "attempt.json", {"candidate_id": CANDIDATE, "run_id": "failed", "verdict": "BLOCKED",
                                           "failure_stage": "guest.host_guard", "error": "guest identity unavailable"})
    (tmp_path / "runner_startup_failure.log").write_text("host_guard refused")
    got = summary(windows=path, macos=mac_run(tmp_path / "mac"))
    row = got["platforms"]["windows"]
    assert got["status"] == "NON_GREEN" and got["version_comparison"] == "DIFFERENT_VERSIONS"
    assert row["status"] == "BLOCKED" and row["failure_stage"] == "guest.host_guard"
    assert row["sut"]["version"] == "2.4.0" and row["gui_started"] is False


@pytest.mark.parametrize("component", ["sut_sha256", "dll_sha256"])
def test_windows_supplemental_run_must_match_build(tmp_path, component):
    edited = win_run(tmp_path / "edited")
    baseline = win_run(tmp_path / "baseline", True)
    for filename in (("binding.json", "proof.json") if component == "sut_sha256" else ("binding.json",)):
        path = baseline.parent / filename
        data = report.read_json(path)
        data[component] = "1" * 64
        put(path, data)
    got = summary(windows=edited, windows_baseline=baseline)
    assert got["platforms"]["windows"]["failure_stage"] == "report.bind_windows_pair"
