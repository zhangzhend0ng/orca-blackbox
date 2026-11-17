"""Slot-3 synthetic counterexamples; never GUI or physical-nozzle evidence."""
import hashlib
import json
from pathlib import Path

import pytest

from harness.agent_protocol import LAYER_FIXTURE
from harness.pilot_material3 import verify_business, _verify_logical_slot
from harness.script_verify import _InvalidEvidence
from unit_tests.test_agent_layer_verify import gcode
from unit_tests.test_pilot_material import saved


@pytest.fixture
def original():
    return (Path(__file__).resolve().parents[1]/LAYER_FIXTURE).read_bytes()


def tool2():
    return gcode().replace(b"T0\n", b"T2\n", 1)


def test_slot_three_and_actual_object_T2_are_both_required(original):
    raw = saved(original, slot="3")
    result = verify_business(raw, original, tool2())
    assert result["case_id"] == "pilot_material_slot3"
    assert result["object_filament_slot"] == 3 and result["object_tools"] == [2]
    assert result["layer_count"] == 68 and result["last_z"] == "27.2"
    assert result["project_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["physical_nozzle_mapping_verified"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("slot", ["1", "2", "0", "4"])
def test_previous_slot_two_or_other_saved_assignment_is_rejected(original, slot):
    with pytest.raises(_InvalidEvidence, match="project_object_tool"):
        verify_business(saved(original, slot=slot), original, tool2())


@pytest.mark.parametrize("raw", [gcode(), gcode().replace(b"T0\n", b"T1\n", 1),
    gcode().replace(b"G1 X10 E2", b"T2\nG1 X10 E2\nT0"), gcode()+b"; T2 in comment only\n",
    tool2().replace(b";Z:0.8", b"T1\n;Z:0.8", 1)],
    ids=["original-T0", "slot2-T1", "T2-only-purge", "T2-only-comment", "mixed-object-tools"])
def test_only_actual_T2_object_extrusion_proves_the_new_target(original, raw):
    with pytest.raises(_InvalidEvidence, match="material_object_tool_not_T2|gcode_multiple_object_tools"):
        verify_business(saved(original, slot="3"), original, raw)


def test_old_slot_two_result_cannot_pass_as_new_business(original):
    with pytest.raises(_InvalidEvidence):
        verify_business(saved(original, slot="2"), original, gcode().replace(b"T0\n", b"T1\n", 1))


def test_finite_helper_keeps_slot_two_distinct_for_future_shared_refactor(original):
    raw = saved(original, slot="2")
    result = _verify_logical_slot(raw, original, gcode().replace(b"T0\n", b"T1\n", 1),
                                  slot=2, cancelled=lambda: False)
    assert result["case_id"] == "pilot_material_slot2"
    assert result["object_filament_slot"] == 2 and result["object_tools"] == [1]


@pytest.mark.parametrize("key,value", [("wall_filament", "3"), ("wall_loops", "3"),
    ("filament_settings_id", ["changed"]*5), ("initial_layer_print_height", "0.3"),
    ("filament_maps", ["1", "2", "3"]), ("unregistered_setting", "1")])
def test_other_global_material_or_process_mutations_remain_rejected(original, key, value):
    with pytest.raises(_InvalidEvidence):
        verify_business(saved(original, slot="3", config=lambda c: c.update({key:value})), original, tool2())


def test_plate_mapping_is_not_permission_to_choose_a_different_physical_head(original):
    def change(root):
        root.find("plate/metadata[@key='filament_maps']").set("value", "1 1 3 1 1")
    with pytest.raises(_InvalidEvidence, match="material_plate_mapping_changed"):
        verify_business(saved(original, slot="3", model=change), original, tool2())


def test_layer_config_echo_cannot_hide_wrong_actual_schedule(original):
    wrong = gcode("0.24", echo="0.4").replace(b"T0\n", b"T2\n", 1)
    with pytest.raises(_InvalidEvidence, match="gcode_actual_layer_step_mismatch"):
        verify_business(saved(original, slot="3"), original, wrong)


def test_cancel_and_fixture_mismatch_fail_closed(original):
    raw = saved(original, slot="3")
    with pytest.raises(_InvalidEvidence, match="verification_cancelled"):
        verify_business(raw, original, tool2(), cancelled=lambda: True)
    with pytest.raises(_InvalidEvidence, match="material_fixture_identity"):
        verify_business(raw, original+b"modified", tool2())


@pytest.mark.parametrize("slot", [True, "3", 0, 1, 4, 99])
def test_private_helper_does_not_become_a_free_form_target_selector(original, slot):
    with pytest.raises(_InvalidEvidence, match="material_target_not_registered"):
        _verify_logical_slot(saved(original, slot="3"), original, tool2(), slot=slot, cancelled=lambda: False)
