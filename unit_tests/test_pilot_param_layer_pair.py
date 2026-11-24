"""Synthetic checks for the Feishu #254 layer-pair oracle (settings scope only).

The G-code schedule half needs real sliced output and is proven on the
guest; these tests pin the change-scope whitelist and the value gates."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.script_verify import _InvalidEvidence
from harness.pilot_common import LAYER_PAIR, inspect_preserved_settings


def _settings(**overrides):
    base = {"layer_height": "0.4", "initial_layer_print_height": "0.4", "wall_loops": "2"}
    base.update(overrides)
    return base


def test_layer_pair_scope_accepts_exactly_the_two_changes():
    actual = _settings(layer_height="0.2", initial_layer_print_height="0.25")
    inspect_preserved_settings(actual, _settings(), allowed_changes=LAYER_PAIR)


def test_layer_pair_scope_rejects_an_extra_changed_key():
    actual = _settings(layer_height="0.2", initial_layer_print_height="0.25", wall_loops="3")
    with pytest.raises(_InvalidEvidence) as err:
        inspect_preserved_settings(actual, _settings(), allowed_changes=LAYER_PAIR)
    assert "pilot_unrelated_setting_changed" in str(err.value)


def test_layer_pair_scope_rejects_wrong_target_value():
    actual = _settings(layer_height="0.2", initial_layer_print_height="0.3")
    with pytest.raises(_InvalidEvidence):
        inspect_preserved_settings(actual, _settings(), allowed_changes=LAYER_PAIR)


def test_layer_pair_values_are_the_registered_combination():
    assert LAYER_PAIR == {"layer_height": "0.2", "initial_layer_print_height": "0.25"}


# ---- the G-code half: layer count and top Z belong to the fixture --------------------
#
# verify_business on the real fixture files (their settings are the preservation
# check's own input), a project that differs in the pair only, and an export whose
# object prints one extruding move per Z. The fixtures' own schedules are measured
# in GUI runs; these tests hold the rule on synthetic exports.
import io
from decimal import Decimal
import zipfile

from harness import pilot_param_layer_pair as pilot
from harness.agent_protocol import FIXTURE_SUFFIXES, LAYER_FIXTURE
from harness.project_3mf import SETTINGS_MEMBER

REPO = Path(__file__).resolve().parents[1]
CUBE, STD = pilot.LAYER_FIXTURE_SHA256, pilot.STD_FIXTURE_SHA256
SPHERE = pilot.MODEL_FIXTURES["_sphere"][1]
CYLINDER = pilot.MODEL_FIXTURES["_cyl"][1]            # in no table
PAIR = {"layer_height": "0.2", "initial_layer_print_height": "0.25"}


def _fixture(digest):
    return next((REPO / path).read_bytes() for path, sha in [(LAYER_FIXTURE, CUBE)] + list(FIXTURE_SUFFIXES.values())
                 if sha == digest)


def _project(fixture, **values):
    """The fixture's project with `values` written into its settings: what the
    GUI save of #254 leaves."""
    with zipfile.ZipFile(io.BytesIO(fixture)) as archive:
        members = [(item, archive.read(item.filename)) for item in archive.infolist()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for item, data in members:
            if item.filename == SETTINGS_MEMBER:
                data = json.dumps({**json.loads(data), **values}).encode()
            archive.writestr(item.filename, data)
    return out.getvalue()


def _zs(count, *, first="0.25", step="0.2"):
    """The Z of `count` object layers: `first`, then every one `step` higher."""
    first, step = Decimal(first), Decimal(step)
    return [first + step * index for index in range(count)]


def _gcode(zs):
    lines = ["; EXECUTABLE_BLOCK_START", "G90", "M83", "T0", "G92 E0", "G1 X0 Y0 Z0"]
    for z in zs:
        lines += ["EXCLUDE_OBJECT_START NAME=object", f"G1 X5 Y5 Z{z}", "G1 X10 E2", "G92 E0",
                  "EXCLUDE_OBJECT_END NAME=object"]
    lines += ["; EXECUTABLE_BLOCK_END", "; CONFIG_BLOCK_START",
              "; layer_height = 0.2", "; first_layer_height = 0.25", "; CONFIG_BLOCK_END", ""]
    return "\n".join(lines).encode()


def _verify(digest, zs):
    fixture = _fixture(digest)
    return pilot.verify_business(_project(fixture, **PAIR), fixture, _gcode(zs))


def test_cube_keeps_its_pinned_schedule():
    result = _verify(CUBE, _zs(135))
    assert (result["layer_count"], result["first_z"], result["last_z"]) == (135, "0.25", "27.05")
    assert result["schedule_asserted"] is True and result["other_settings_preserved"] is True


def test_a_wrong_layer_count_is_red_where_the_schedule_is_pinned():
    with pytest.raises(_InvalidEvidence, match="layer_pair_(last_z|layer_count)"):
        _verify(CUBE, _zs(134))


def test_the_pinned_count_itself_is_what_is_asserted(monkeypatch):
    monkeypatch.setattr(pilot, "analyze_gcode", lambda *_a, **_k: {
        "layer_count": 134, "first_z": "0.25", "last_z": "27.05", "sha256": "0" * 64})
    with pytest.raises(_InvalidEvidence, match="layer_pair_layer_count"):
        _verify(CUBE, [])


def test_an_unpinned_fixture_records_its_layers_and_asserts_no_count(monkeypatch):
    # the state a fixture is MEASURED in before its run pins it
    monkeypatch.setitem(pilot.SCHEDULE_BY_FIXTURE, STD, {"height_mm": "27"})
    recorded = [_verify(STD, _zs(count)) for count in (135, 134)]
    assert [(r["layer_count"], r["first_z"], r["last_z"], r["schedule_asserted"]) for r in recorded] == [
        (135, "0.25", "27.05", False), (134, "0.25", "26.85", False)]


def test_what_a_run_measured_is_asserted_once_pinned(monkeypatch):
    monkeypatch.setitem(pilot.SCHEDULE_BY_FIXTURE, SPHERE, {"height_mm": "20", "layer_count": 99, "last_z": "19.85"})
    good = _verify(SPHERE, _zs(99))
    assert good["schedule_asserted"] is True and (good["layer_count"], good["last_z"]) == (99, "19.85")
    with pytest.raises(_InvalidEvidence, match="layer_pair_last_z"):
        _verify(SPHERE, _zs(100))        # top 20.05: inside the height bound, not the pinned Z


def test_the_precondition_cube_and_the_sphere_are_registered_by_their_height():
    assert pilot.SCHEDULE_BY_FIXTURE[STD]["height_mm"] == "27"
    assert pilot.SCHEDULE_BY_FIXTURE[SPHERE]["height_mm"] == "20"
    assert _fixture(STD) != _fixture(CUBE)          # another project: the pair's own starting values


def test_a_fixture_outside_the_table_is_recorded_with_no_bound_on_its_height():
    assert CYLINDER not in pilot.SCHEDULE_BY_FIXTURE
    result = _verify(CYLINDER, _zs(300))
    assert result["schedule_asserted"] is False and (result["layer_count"], result["last_z"]) == (300, "60.05")


@pytest.mark.parametrize("digest", [CUBE, STD, SPHERE, CYLINDER])
@pytest.mark.parametrize("zs, reason", [
    (_zs(135, first="0.20"), "gcode_first_actual_layer_mismatch"),       # Feishu result 2: first Z = 0.25
    (_zs(135, step="0.25"), "gcode_actual_layer_step_mismatch"),         # Feishu result 3: every layer +0.20
])
def test_first_z_and_the_step_are_required_on_every_fixture(digest, zs, reason):
    with pytest.raises(_InvalidEvidence, match=reason):
        _verify(digest, zs)


# ---- what fa706g3 measured (runs 66cbd0c1 and 8e6363ab, 2026-11-24), pinned ------

@pytest.mark.parametrize("digest, count, last", [(STD, 135, "27.05"), (SPHERE, 100, "20.05")])
def test_the_measured_schedules_are_pinned_and_asserted(digest, count, last):
    result = _verify(digest, _zs(count))
    assert result["schedule_asserted"] is True and (result["layer_count"], result["last_z"]) == (count, last)


@pytest.mark.parametrize("digest, count, reason", [
    (STD, 134, "layer_pair_last_z"), (SPHERE, 99, "layer_pair_last_z"),
    # one layer higher than the model's top: the height bound speaks first
    (SPHERE, 101, "gcode_fixture_height_mismatch")])
def test_one_layer_off_the_measured_count_is_red(digest, count, reason):
    with pytest.raises(_InvalidEvidence, match=reason):
        _verify(digest, _zs(count))
