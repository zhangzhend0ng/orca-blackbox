import pytest

from harness import pilot_param_276_speed_limits
from harness.param_comparison import _export, _fan_effect, _flow_effect
from harness.pilot_common import inspect_preserved_settings
from harness.script_verify import _InvalidEvidence


def test_export_binds_config_and_reads_modal_relative_extrusion():
    data = b"""M83
T0
G1 X0 Y0
;Z:0.45
;TYPE:Outer wall
G1 F6000
G1 X10 E.5
; CONFIG_BLOCK_START
; machine_max_speed_x = 500,200
; CONFIG_BLOCK_END
"""
    wanted = {"machine_max_speed_x": "500,200"}
    layers, moves = _export(data, wanted, lambda: False)
    assert layers == [.45]
    assert moves == [((.45, "Outer wall", 0, 0, 10, 0), 100, None, .5)]
    with pytest.raises(_InvalidEvidence, match="comparison_export_key:machine_max_speed_x"):
        _export(data.replace(b"; machine_max_speed_x = 500,200\n", b""), wanted, lambda: False)


def test_fan_requires_overhang_context_and_reports_ordinary_surface_changes():
    wall = (.45, "Overhang wall", 0, 0, 1, 0)
    surface = (.45, "Top surface", 0, 0, 1, 0)
    before = [(wall, 50, 255, .04), (surface, 80, 255, .04)]
    after = [(wall, 10, 204, .04), (surface, 90, 255, .04)]
    result = _fan_effect(before, after)
    assert result["overhang_80pct_matches"] == 1
    assert result["ordinary_surface_feed_changes"] == 1
    assert result["ordinary_surface_fan_changes"] == 0
    assert _fan_effect(before, [(wall, 10, 255, .04), after[1]])["fan_effect"] == "not_observed"


def test_volumetric_effect_requires_flow_change_and_unchanged_path():
    path = (.45, "Outer wall", 0, 0, 10, 0)
    before = [(path, 160, 0, .307)]
    after = [(path, 203, 0, .307)]
    result = _flow_effect(before, after, .25, 1.75)
    assert result["outer_wall_peak_mm3_s"] == pytest.approx(15, abs=.02)
    assert result["near_feishu_178_mm_s"] is False
    with pytest.raises(_InvalidEvidence, match="comparison_outer_wall_volumetric_cap"):
        _flow_effect(before, before, .25, 1.75)
    with pytest.raises(_InvalidEvidence, match="comparison_outer_wall_paths_changed"):
        _flow_effect(before, [((.45, "Outer wall", 0, 0, 11, 0), 203, 0, .307)], .25, 1.75)


@pytest.mark.parametrize("key, vector", [
    ("filament_max_volumetric_speed", ["12", "18", "15", "15", "15"]),
    ("filament_max_volumetric_speed", ["15", "18", "15", "15", "15"]),
    ("machine_max_speed_x", ["500", "500"]),
])
def test_saved_slots_and_alternate_machine_mode_are_preserved(key, vector):
    process = pilot_param_276_speed_limits.VALUES
    original = {**process, "filament_max_volumetric_speed": ["12", "15", "15", "15", "15"],
                "machine_max_speed_x": ["500", "200"]}
    changes = {**process, "filament_max_volumetric_speed": (0, "15"), "machine_max_speed_x": (0, "500")}
    correct = {**original, "filament_max_volumetric_speed": ["15"] * 5}
    inspect_preserved_settings(correct, original, allowed_changes=changes)
    with pytest.raises(_InvalidEvidence, match="param_slot_value_or_preservation:" + key):
        inspect_preserved_settings({**correct, key: vector}, original, allowed_changes=changes)
