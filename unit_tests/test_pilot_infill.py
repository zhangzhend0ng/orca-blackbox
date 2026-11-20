"""Pure infill evidence counterexamples. No GUI/model/VM execution."""
import io
import json
from pathlib import Path
import zipfile

import pytest

from harness.agent_layer_verify import analyze_gcode
from harness.agent_protocol import LAYER_FIXTURE
from harness.pilot_infill import _sparse_extrusion_moves, verify_business
from unit_tests.test_agent_layer_verify import gcode, labels


@pytest.fixture
def fixture():
    return Path(LAYER_FIXTURE).read_bytes()


def saved(fixture, **changes):
    with zipfile.ZipFile(io.BytesIO(fixture)) as z:
        files = {i.filename: z.read(i) for i in z.infolist()}
    c = json.loads(files["Metadata/project_settings.config"])
    c["sparse_infill_density"] = "30%"
    c["different_settings_to_system"][0] += ";sparse_infill_density"
    c.update(changes)
    files["Metadata/project_settings.config"] = json.dumps(c).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name, raw in files.items(): z.writestr(name, raw)
    return output.getvalue()


def sliced(*, region="sparse", mode="M83"):
    raw = gcode(e_mode=mode)
    if region == "sparse":
        raw = raw.replace(b";Z:", b";TYPE:Sparse infill\n;Z:")
    elif region == "solid":
        raw = raw.replace(b";Z:", b";TYPE:Internal solid infill\n;Z:")
    elif region == "outside":
        raw = raw.replace(b"G1 X10 E2", b";TYPE:Sparse infill\nG1 X10 E2")
    raw = raw.replace(b"; CONFIG_BLOCK_END", b"; sparse_infill_density = 30%\n; sparse_infill_pattern = grid\n; wall_loops = 2\n; CONFIG_BLOCK_END")
    return raw


@pytest.mark.parametrize("mode", ["M82", "M83"])
def test_saved_intent_and_real_sparse_object_moves_pass(fixture, mode):
    result = verify_business(saved(fixture), fixture, sliced(mode=mode))
    assert result["gcode"]["layer_count"] == 68
    assert result["sparse_positive_xy_e_moves"] > 0
    assert result["physical_density_ratio_verified"] is False


@pytest.mark.parametrize("changes", [
    {"sparse_infill_density": "15%"}, {"sparse_infill_density": "30"},
    {"wall_loops": "3"}, {"sparse_infill_pattern": "gyroid"},
], ids=["old-density", "density-without-percent", "wrong-walls", "wrong-pattern"])
def test_wrong_or_old_target_is_rejected(fixture, changes):
    with pytest.raises(ValueError, match="infill_target_settings"):
        verify_business(saved(fixture, **changes), fixture, sliced())


def test_unrelated_setting_change_is_rejected(fixture):
    with pytest.raises(ValueError, match="unrelated_setting_changed"):
        verify_business(saved(fixture, bridge_speed="999"), fixture, sliced())


@pytest.mark.parametrize("raw,reason", [
    (sliced().replace(b"sparse_infill_density = 30%", b"sparse_infill_density = 15%"), "gcode_setting"),
    (sliced().replace(b"sparse_infill_density = 30%", b"sparse_infill_density = 30%\n; sparse_infill_density = 15%"), "gcode_setting"),
    (sliced().replace(b"; sparse_infill_density = 30%\n", b"")+b"; sparse_infill_density = 30%\n", "gcode_setting"),
    (sliced(region="solid"), "missing_sparse_xy"),
    (sliced(region="outside"), "missing_sparse_xy"),
    (sliced(region="none"), "missing_sparse_xy"),
], ids=["old-echo", "conflicting-echo", "echo-outside-config", "solid-only", "outside-object", "no-feature"])
def test_echo_or_other_feature_moves_cannot_fake_sparse_printing(fixture, raw, reason):
    with pytest.raises(ValueError, match=reason):
        verify_business(saved(fixture), fixture, raw)


@pytest.mark.parametrize("transform", [lambda b:b, labels])
def test_sparse_motion_parser_accepts_both_generator_object_scope_forms(transform):
    raw = transform(sliced())
    analyze_gcode(raw, layer_height="0.4")
    assert _sparse_extrusion_moves(raw, lambda:False) > 0


def test_fake_comment_scope_outside_exclude_object_cannot_count_as_model():
    raw = sliced(region="outside").replace(b"G1 X10 E2", b"; printing object fake id:999 copy 0\nG1 X10 E2\n; stop printing object fake id:999 copy 0")
    analyze_gcode(raw, layer_height="0.4")
    with pytest.raises(ValueError, match="missing_sparse_xy"):
        _sparse_extrusion_moves(raw, lambda:False)


def test_sparse_comment_without_positive_xy_motion_is_not_an_extrusion():
    raw = sliced().replace(b";TYPE:Sparse infill", b";TYPE:Sparse infill\nG1 E-1\nG1 E1\n;TYPE:Outer wall")
    analyze_gcode(raw, layer_height="0.4")
    with pytest.raises(ValueError, match="missing_sparse_xy"):
        _sparse_extrusion_moves(raw, lambda:False)
