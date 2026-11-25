import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tools.replay_case_evidence import replay_receipt


EVIDENCE = Path(__file__).resolve().parents[1] / "docs/runs/evidence"
SAVE = EVIDENCE / "feishu-140-201-202-2026-11-25/row-201-hyperv"
CUT = EVIDENCE / "feishu-250-251-2026-11-25/row-250-hyperv"
PART = EVIDENCE / "feishu-249-2026-11-25"
IMPORT = EVIDENCE / "multi-244-254-2026-11-25/win11-test"


@pytest.mark.parametrize("directory,prefix", [
    (SAVE, "1216dc9e-run1"), (CUT, "a7a65272-run2"), (PART, "dcadf798-run1"),
    (IMPORT, "e7ba1cd2-run1"),
])
def test_archived_evidence_and_negative_controls(directory, prefix):
    report = replay_receipt(directory / f"{prefix}-receipt.json")
    assert report["offline_checks_passed"], report


def test_incomplete_reopen_preserves_valid_save_evidence():
    report = replay_receipt(SAVE / "054dd881-receipt.json")
    assert not report["offline_checks_passed"]
    checks = report["result"]["checks"]
    assert checks["world_triangles_translated_by_10_mm_along_x_only"]
    assert not checks["reopen_input_matches_saved_bytes_and_logged_sha256"]


def test_unmodified_baseline_cannot_stand_in_for_the_negative_export(tmp_path):
    prefix = "a7a65272-run1-"
    for name in ("receipt.json", "case.log", "object_artifacts.json", "negative-project.3mf",
                 "baseline.gcode", "negative.gcode"):
        shutil.copyfile(CUT / (prefix + name), tmp_path / (prefix + name))
    baseline = (tmp_path / (prefix + "baseline.gcode")).read_bytes()
    (tmp_path / (prefix + "negative.gcode")).write_bytes(baseline)
    receipt = tmp_path / (prefix + "receipt.json")
    report = replay_receipt(receipt)
    assert not report["offline_checks_passed"]
    assert "negative.gcode" in report["error"]

    # Simulate a collector which consistently recorded the wrong export.
    manifest = tmp_path / (prefix + "object_artifacts.json")
    entries = json.loads(manifest.read_text(encoding="utf-8-sig"))
    entry = next(entry for entry in entries if entry["part"] == "negative.gcode")
    entry.update(bytes=len(baseline), sha256=hashlib.sha256(baseline).hexdigest())
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    report = replay_receipt(receipt)
    assert not report["offline_checks_passed"]
    assert not report["result"]["checks"]["local_subtraction_with_retained_extrusion"]
