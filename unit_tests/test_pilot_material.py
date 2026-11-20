"""Synthetic material oracle challenges: these tests do not operate Orca."""
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest

from harness.agent_protocol import LAYER_FIXTURE
from harness.pilot_material import verify_business
from harness.script_verify import _InvalidEvidence
from unit_tests.test_agent_layer_verify import gcode


@pytest.fixture
def fixture_bytes():
    return (Path(__file__).resolve().parents[1] / LAYER_FIXTURE).read_bytes()


def saved(fixture, *, slot="2", config=None, model=None, reverse=False):
    with zipfile.ZipFile(io.BytesIO(fixture)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    settings = ET.fromstring(files["Metadata/model_settings.config"])
    settings.find("object/metadata[@key='extruder']").set("value", slot)
    if model:
        model(settings)
    files["Metadata/model_settings.config"] = ET.tostring(settings)
    if config:
        values = json.loads(files["Metadata/project_settings.config"])
        config(values)
        files["Metadata/project_settings.config"] = json.dumps(values).encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files, reverse=reverse):
            archive.writestr(name, files[name])
    return result.getvalue()


def tool1():
    return gcode().replace(b"T0\n", b"T1\n", 1)


@pytest.mark.parametrize("reverse", [False, True], ids=["zip-order-a", "zip-order-b"])
def test_saved_slot_two_requires_actual_object_T1_and_preserves_original_hash(fixture_bytes, reverse):
    project = saved(fixture_bytes, reverse=reverse)
    result = verify_business(project, fixture_bytes, tool1())
    assert result["object_tools"] == [1] and result["layer_count"] == 68
    assert result["project_sha256"] == hashlib.sha256(project).hexdigest()
    assert result["physical_nozzle_mapping_verified"] is False
    json.dumps(result, allow_nan=False)


def test_observed_serialization_migrations_preserve_semantics(fixture_bytes):
    def migrate(c):
        c["outer_wall_speed"] = [c["outer_wall_speed"]]
        c["printer_settings_id"] += "(fixture.3mf)"
        c["print_settings_id"] += "(fixture.3mf)"
        c["filament_settings_id"] = [v + "(fixture.3mf)" for v in c["filament_settings_id"]]
        c["filament_ids"][0] = ""
        c["version"] = "2.4.0"
        c["project_schema_version"] = "1"
        c["filament_grouping_mode"] = "standard"
    assert verify_business(saved(fixture_bytes, config=migrate), fixture_bytes, tool1())["object_filament_slot"] == 2


@pytest.mark.parametrize("slot", ["1", "3", "0"], ids=["unchanged-slot", "wrong-slot", "inherit-slot"])
def test_wrong_saved_assignment_is_rejected_even_with_T1_gcode(fixture_bytes, slot):
    with pytest.raises(_InvalidEvidence, match="project_object_tool"):
        verify_business(saved(fixture_bytes, slot=slot), fixture_bytes, tool1())


@pytest.mark.parametrize("raw", [gcode(), gcode().replace(b"G1 X10 E2", b"T1\nG1 X10 E2\nT0"),
    gcode() + b"; fake tool T1\n", tool1().replace(b";Z:0.8", b"T0\n;Z:0.8", 1)],
    ids=["old-object-T0", "T1-only-purge", "T1-only-comment", "mixed-object-tools"])
def test_tool_markers_outside_object_extrusion_cannot_prove_assignment(fixture_bytes, raw):
    with pytest.raises(_InvalidEvidence, match="material_object_tool_not_T1|gcode_multiple_object_tools"):
        verify_business(saved(fixture_bytes), fixture_bytes, raw)


@pytest.mark.parametrize("key,value", [("sparse_infill_density", "99%"), ("nozzle_diameter", ["0.4"] * 4),
    ("filament_type", ["PETG"] * 5), ("wall_filament", "2"), ("outer_wall_speed", ["121"]),
    ("filament_flow_step_size", ["2"] * 5), ("unregistered_setting", "1")])
def test_other_global_settings_and_unknown_migrations_are_rejected(fixture_bytes, key, value):
    with pytest.raises(_InvalidEvidence, match="material_|pilot_unrelated_setting_changed|pilot_config_unknown_addition|project_slicing_scope"):
        verify_business(saved(fixture_bytes, config=lambda c: c.update({key: value})), fixture_bytes, tool1())


def test_plate_mapping_change_is_not_mistaken_for_object_assignment(fixture_bytes):
    def change(root):
        root.find("plate/metadata[@key='filament_maps']").set("value", "1 2 1 1 1")
    with pytest.raises(_InvalidEvidence, match="material_plate_mapping_changed"):
        verify_business(saved(fixture_bytes, model=change), fixture_bytes, tool1())


def test_duplicate_plate_mapping_cannot_select_a_convenient_value(fixture_bytes):
    def change(root):
        ET.SubElement(root.find("plate"), "metadata", key="filament_maps", value="1 2 1 1 1")
    with pytest.raises(_InvalidEvidence, match="material_duplicate_mapping"):
        verify_business(saved(fixture_bytes, model=change), fixture_bytes, tool1())


def test_part_override_cannot_hide_a_second_assignment(fixture_bytes):
    def change(root):
        ET.SubElement(root.find("object/part"), "metadata", key="extruder", value="1")
    with pytest.raises(_InvalidEvidence, match="project_object_override"):
        verify_business(saved(fixture_bytes, model=change), fixture_bytes, tool1())


@pytest.mark.parametrize("raw", [b"", b"not zip", b"PK\x03\x04bad"], ids=["empty", "text", "truncated"])
def test_malformed_project_raises_evidence_error(fixture_bytes, raw):
    with pytest.raises(_InvalidEvidence):
        verify_business(raw, fixture_bytes, tool1())


def test_wrong_fixture_and_cancel_fail_closed(fixture_bytes):
    project = saved(fixture_bytes)
    with pytest.raises(_InvalidEvidence, match="material_fixture_identity"):
        verify_business(project, fixture_bytes + b"changed", tool1())
    with pytest.raises(_InvalidEvidence, match="verification_cancelled"):
        verify_business(project, fixture_bytes, tool1(), cancelled=lambda: True)


def test_false_layer_echo_does_not_replace_actual_object_schedule(fixture_bytes):
    wrong = gcode("0.24", echo="0.4").replace(b"T0\n", b"T1\n", 1)
    with pytest.raises(_InvalidEvidence, match="gcode_actual_layer_step_mismatch"):
        verify_business(saved(fixture_bytes), fixture_bytes, wrong)


def test_cancellation_is_checked_during_processing(fixture_bytes):
    checks = 0
    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 8
    with pytest.raises(_InvalidEvidence, match="verification_cancelled"):
        verify_business(saved(fixture_bytes), fixture_bytes, tool1(), cancelled=cancelled)
    assert checks == 8


def test_first_layer_setting_must_remain_unchanged(fixture_bytes):
    with pytest.raises(_InvalidEvidence, match="project_layer_config"):
        verify_business(saved(fixture_bytes, config=lambda c: c.update(initial_layer_print_height="0.3")),
                        fixture_bytes, tool1())
