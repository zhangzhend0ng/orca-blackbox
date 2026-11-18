"""Synthetic acceptance and counterexamples for the held-out oracles."""
from decimal import Decimal
from pathlib import Path
import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pytest

from harness.agent_protocol import LAYER_FIXTURE
from harness.native_matrix import GENERALIZATION
from harness.pilot_infill_material import verify_business as verify_combo
from harness.pilot_scale_x import verify_business as verify_scale
from harness.pilot_top_layers import verify_business as verify_top
from harness.pilot_transform import _fixture_with_transform
from harness.project_3mf import _archive, _geometry
from tools.zcode_matrix import generalization_threshold
from unit_tests.test_agent_layer_verify import gcode
from unit_tests.test_pilot_infill import sliced
from unit_tests.test_pilot_material import saved
from unit_tests.test_pilot_transform import moves


@pytest.fixture
def fixture():
    return Path(LAYER_FIXTURE).read_bytes()


def change_settings(project, **changes):
    files = _archive(project, lambda: False)
    name = "Metadata/project_settings.config"
    settings = json.loads(files[name])
    settings.update(changes)
    files[name] = json.dumps(settings).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def test_top_shell_layers_requires_saved_setting_and_top_surface_extrusion(fixture):
    project = change_settings(fixture, top_shell_layers="5")
    raw = gcode().replace(b";Z:", b";TYPE:Top surface\n;Z:").replace(
        b"; CONFIG_BLOCK_END", b"; top_shell_layers = 5\n; CONFIG_BLOCK_END")
    assert verify_top(project, fixture, raw)["top_shell_layers"] == 5
    with pytest.raises(ValueError, match="pilot_target_setting_mismatch"):
        verify_top(fixture, fixture, raw)
    with pytest.raises(ValueError, match="top_gcode_setting"):
        verify_top(project, fixture, raw.replace(b"top_shell_layers = 5", b"top_shell_layers = 3"))
    with pytest.raises(ValueError, match="top_surface_no_extrusion"):
        verify_top(project, fixture, raw.replace(b";TYPE:Top surface", b";TYPE:Outer wall"))


def test_scale_requires_same_center_and_extrusion_in_scaled_x_bounds(fixture):
    entries = _archive(fixture, lambda: False)
    transform = list(_geometry(entries)[2])
    transform[0] = Decimal("1.5")
    previous_assembly = _fixture_with_transform(entries, tuple(transform))
    model_config = "Metadata/model_settings.config"
    metadata = ET.fromstring(entries[model_config])
    metadata.find("assemble/assemble_item").set("transform", " ".join(map(str, transform)))
    entries[model_config] = ET.tostring(metadata)
    project = _fixture_with_transform(entries, tuple(transform))
    old = moves(0)
    wide = old.replace(b"X122.4", b"X115.65").replace(b"X148.6", b"X155.35")
    assert verify_scale(project, fixture, wide)["dimensions_mm"] == ["40.5", "27", "27"]
    with pytest.raises(ValueError, match="project_assembly_transform"):
        verify_scale(previous_assembly, fixture, wide)
    with pytest.raises(ValueError, match="transform_gcode_footprint_too_small"):
        verify_scale(project, fixture, old)
    transform[9] += 1
    shifted = _fixture_with_transform(entries, tuple(transform))
    with pytest.raises(ValueError, match="project_physical_geometry_changed"):
        verify_scale(shifted, fixture, wide)


def test_combo_requires_both_targets_on_same_project_and_export(fixture):
    project = change_settings(saved(fixture, slot="3"), sparse_infill_density="30%")
    raw = sliced().replace(b"T0\n", b"T2\n", 1)
    assert verify_combo(project, fixture, raw)["object_tools"] == [2]
    with pytest.raises(ValueError, match="material_object_tool_not_T2"):
        verify_combo(project, fixture, sliced())
    with pytest.raises(ValueError, match="pilot_infill_target"):
        verify_combo(saved(fixture, slot="3"), fixture, raw)


def test_threshold_preserves_entire_frozen_denominator():
    slots = [{"scenario": scenario, "status": "pass"} for scenario in GENERALIZATION]
    assert len(slots) == 8 and generalization_threshold(slots)
    slots[2]["status"] = "fail"
    assert generalization_threshold(slots)
    slots[3]["status"] = "not_run"
    assert not generalization_threshold(slots)
