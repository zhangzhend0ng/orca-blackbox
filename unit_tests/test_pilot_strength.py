"""Pure malformed/incorrect artifact challenges; no GUI coverage."""
import io
import json
from pathlib import Path
import zipfile

import pytest

from harness.agent_protocol import LAYER_FIXTURE
from harness.pilot_strength import verify_business
from unit_tests.test_agent_layer_verify import gcode


@pytest.fixture
def fixture():
    return Path(LAYER_FIXTURE).read_bytes()


def saved(fixture, **changes):
    with zipfile.ZipFile(io.BytesIO(fixture)) as archive:
        files = {i.filename: archive.read(i) for i in archive.infolist()}
    config = json.loads(files["Metadata/project_settings.config"])
    config["wall_loops"] = "3"
    config["different_settings_to_system"][0] += ";wall_loops"
    config.update(changes)
    files["Metadata/project_settings.config"] = json.dumps(config).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return output.getvalue()


def sliced(**kwargs):
    return gcode(**kwargs).replace(b"; CONFIG_BLOCK_END", b"; wall_loops = 3\n; CONFIG_BLOCK_END")


def test_correct_saved_intent_and_actual_object_extrusion_are_accepted(fixture):
    before = fixture[:]
    result = verify_business(saved(fixture), fixture, sliced())
    assert result["wall_loops"] == 3 and result["gcode"]["layer_count"] == 68
    assert result["project"]["geometry_unchanged"] is True
    assert result["physical_wall_count_verified"] is False
    assert fixture == before


def test_known_serializer_alias_and_one_element_vector_keep_same_meaning(fixture):
    with zipfile.ZipFile(io.BytesIO(fixture)) as z:
        original = json.loads(z.read("Metadata/project_settings.config"))
    raw = saved(fixture, bridge_speed=[original["bridge_speed"]], version="2.4.0",
                print_settings_id=original["print_settings_id"]+"(fixture.3mf)", project_schema_version="1")
    assert verify_business(raw, fixture, sliced())["other_fixture_settings_preserved"]


@pytest.mark.parametrize("changes,reason", [
    ({"wall_loops": "2"}, "pilot_wall_loops_target"),
    ({"wall_loops": 3}, "pilot_wall_loops_target"),
    ({"sparse_infill_density": "95%"}, "unrelated_setting"),
    ({"bridge_speed": ["999"]}, "unrelated_setting"),
    ({"layer_height": "0.24"}, "project_layer_config"),
    ({"unexpected_setting": "1"}, "pilot_config_unknown_addition"),
    ({"project_schema_version": "99"}, "pilot_config_unknown_addition"),
])
def test_old_wrong_or_extra_project_changes_are_rejected(fixture, changes, reason):
    with pytest.raises(ValueError, match=reason):
        verify_business(saved(fixture, **changes), fixture, sliced())


@pytest.mark.parametrize("raw,reason", [
    (gcode(), "gcode_wall_loops"),
    (sliced().replace(b"wall_loops = 3", b"wall_loops = 2"), "gcode_wall_loops"),
    (sliced(positive=False), "missing_object_extrusion"),
    (sliced(layer="0.24"), "layer_height_mismatch"),
    (gcode()+b"; wall_loops = 3\n", "gcode_wall_loops"),
    (sliced().replace(b"; wall_loops = 3", b"; wall_loops = 3\n; wall_loops = 2"), "gcode_wall_loops"),
])
def test_config_echo_without_matching_real_slice_cannot_pass(fixture, raw, reason):
    with pytest.raises(ValueError, match=reason):
        verify_business(saved(fixture), fixture, raw)


def test_different_fixture_is_not_a_valid_reference(fixture):
    with pytest.raises(ValueError, match="fixture_identity"):
        verify_business(saved(fixture), fixture+b"changed", sliced())
