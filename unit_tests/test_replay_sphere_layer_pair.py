import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime

from tools.replay_case_evidence import replay_receipt
from tools.replay_sphere_layer_pair import _plate_source


ROWS = Path(__file__).resolve().parents[1] / "docs/runs/evidence/win11-254-2026-11-25"
RED = "62678a05-run1-"


def test_complete_guest_sphere_uses_both_real_exports_and_edits():
    report = replay_receipt(ROWS / "1d2de6b4-run1-receipt.json")
    assert report["offline_checks_passed"], report
    result = report["result"]
    assert result["baseline"]["layer_count"] == result["target"]["layer_count"] == 100
    assert result["baseline"]["gcode_sha256"] != result["target"]["gcode_sha256"]
    assert result["preview_overlap"] >= 0.9


def test_original_red_retains_its_independent_baseline_and_failure():
    report = replay_receipt(ROWS / (RED + "receipt.json"))
    assert not report["offline_checks_passed"]
    assert "FAIL=1" in report["historical_summary"]
    result = report["result"]
    assert result["checks"]["baseline_schedule"]
    assert result["checks"]["off_target_project"]
    assert result["checks"]["four_edits_match_receipt_log"]
    assert not result["checks"]["target_schedule"]
    assert "filament_settings_id" in result["target_error"]


def copy_red(tmp_path):
    for path in ROWS.glob(RED + "*"):
        shutil.copyfile(path, tmp_path / path.name)


def update_manifest(directory, name, raw):
    path = directory / (RED + "object_artifacts.json")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    entry = next(entry for entry in manifest if entry["part"] == name)
    entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_target_substituted_for_off_target_is_rejected_even_with_new_manifest(tmp_path):
    copy_red(tmp_path)
    edited = (tmp_path / (RED + "sphere-edited.3mf")).read_bytes()
    (tmp_path / (RED + "off-target.3mf")).write_bytes(edited)
    receipt = tmp_path / (RED + "receipt.json")
    report = replay_receipt(receipt)
    assert not report["offline_checks_passed"]
    assert "off-target.3mf" in report["error"]

    update_manifest(tmp_path, "off-target.3mf", edited)
    result = replay_receipt(receipt)["result"]
    assert result["checks"]["four_edits_match_receipt_log"]
    assert not result["checks"]["off_target_project"]


def test_lost_field_action_cannot_be_replaced_by_correct_disk_values(tmp_path):
    copy_red(tmp_path)
    path = tmp_path / (RED + "analysis.json")
    analysis = json.loads(path.read_text(encoding="utf-8-sig"))
    analysis["edits"].pop(0)
    raw = json.dumps(analysis).encode()
    path.write_bytes(raw)
    update_manifest(tmp_path, "analysis.json", raw)
    result = replay_receipt(tmp_path / (RED + "receipt.json"))["result"]
    assert result["checks"]["off_target_project"]
    assert not result["checks"]["four_edits_match_receipt_log"]


def test_private_plate_binds_the_slice_process_path_time_and_both_artifacts():
    timestamp = "2026-11-25T12:00:04+00:00"
    ns = round(datetime.fromisoformat(timestamp).timestamp() * 1e9)
    log = (f"[m7x249] started target_reopen_slice_export at {timestamp}\n"
           "[launcher] pid=137 hwnd=0x55\n[m7] target slice: True\n"
           "[m7x249] finished target_reopen_slice_export in 12.125s\n")
    record = {"pid": 137, "plate": r"snapmaker_orca_model\session\app#137#run\Metadata\.137.0.gcode",
              "slice_started_ns": ns + 1_000_000, "modified_ns": ns + 2_000_000,
              "project_sha256": "project", "sha256": "export"}
    assert _plate_source("target", log, record, "project", "export", True)
    assert not _plate_source("target", log, None, "project", "export", False)
    for changes in ({"pid": 138}, {"plate": "C:/temp/" + record["plate"]},
                    {"plate": record["plate"].replace("#137#", "#16#")},
                    {"modified_ns": ns}, {"modified_ns": ns + 60_000_000_000},
                    {"sha256": "other-export"}, {"project_sha256": "other-project"}):
        assert not _plate_source("target", log, {**record, **changes}, "project", "export", True)
