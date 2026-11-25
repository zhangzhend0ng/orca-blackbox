from pathlib import Path
import re

import pytest

from tools.verify_surface_flow_paths import _config_delta, verify


EVIDENCE = Path(__file__).resolve().parents[1] / "docs/runs/evidence/mac-262-2026-11-25"


def test_unrelated_travel_speed_rejects_an_otherwise_verified_real_plate(tmp_path):
    baseline = EVIDENCE / "cb5ac024-baseline.gcode"
    target = EVIDENCE / "cb5ac024-edited.gcode"
    original = verify(baseline, target)
    assert original["pass"]

    modified, count = re.subn(r"^; travel_speed = (\d+(?:\.\d+)?)(?=,|$)",
                              lambda m: f"; travel_speed = {float(m[1]) + 1}",
                              target.read_text(encoding="utf-8-sig"), flags=re.M)
    assert count == 1
    negative = tmp_path / "travel-speed.gcode"
    negative.write_text(modified, encoding="utf-8")
    rejected = verify(baseline, negative)
    assert rejected["pass"] is False
    assert rejected["effective_config"]["unexpected_changes"] == ["travel_speed"]
    assert rejected["feature_extrusion"] == original["feature_extrusion"]


@pytest.mark.parametrize("key,before,after", [
    ("wipe_tower_x", ["1", "2"], ["3", "2"]),
    ("different_settings_to_system", ["mixed_filament_definitions;;;;;;"],
     ["top_solid_infill_flow_ratio;mixed_filament_definitions;travel_speed;;;;;;"]),
])
def test_effective_config_preserves_all_occurrences_and_unrelated_dirty_flags(key, before, after):
    assert _config_delta({key: before}, {key: after})["unexpected_changes"] == [key]
