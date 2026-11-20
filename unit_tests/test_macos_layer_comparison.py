"""Plate receipts must bind real slicer output to the expected GUI process."""
import hashlib

import pytest

from runner.macos_project_copy import verify_plate
from unit_tests.test_agent_layer_verify import gcode


def receipt_for(raw):
    return {"pid": 42, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
            "project_sha256": "a" * 64, "source": "open_process_plate",
            "export_enabled_before": False, "export_enabled_after": True}


@pytest.mark.parametrize("name,height,count", [("baseline", "0.4", 68), ("edited", "0.24", 112)])
def test_verified_plate_uses_physical_layers_and_names_its_source(tmp_path, name, height, count):
    raw = gcode(height)
    (tmp_path / (name + ".gcode")).write_bytes(raw)
    result = verify_plate(tmp_path, name, receipt_for(raw), 42, "a" * 64, height, count)
    assert (result["layer_count"], result["first_z"], result["origin"]) == (count, "0.4", "gui_plate_temporary")


@pytest.mark.parametrize("changed", [{"pid": 43}, {"sha256": "0" * 64}, {"size": 0},
                                     {"project_sha256": "b" * 64}, {"export_enabled_before": True}])
def test_foreign_or_stale_plate_is_rejected(tmp_path, changed):
    raw = gcode("0.24")
    (tmp_path / "edited.gcode").write_bytes(raw)
    receipt = {**receipt_for(raw), **changed}
    with pytest.raises(ValueError, match="lineage or transfer"):
        verify_plate(tmp_path, "edited", receipt, 42, "a" * 64, "0.24", 112)


def test_unchanged_baseline_cannot_be_used_as_edited_plate(tmp_path):
    raw = gcode("0.4")
    (tmp_path / "edited.gcode").write_bytes(raw)
    with pytest.raises(ValueError, match="gcode_layer_height_mismatch"):
        verify_plate(tmp_path, "edited", receipt_for(raw), 42, "a" * 64, "0.24", 112)
