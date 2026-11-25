"""Feishu #262's balance identity: synthetic negative controls and the archived plates."""
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

from tools import check_surface_flow_balance as balance

UNIT = 1e-5
WALL, SPARSE, INNER = "Outer wall", "Sparse infill", "Inner wall"
TOP, BOTTOM = balance.TOP, balance.BOTTOM
# Base extrusion of each move of the test object, in units of 1e-5 mm: the
# object extrudes 3.23126 mm, of which 0.9 mm (UNEQUAL) or 1.0 mm (EQUAL) is top.
UNEQUAL = [(WALL, [12346, 20001, 3]), (SPARSE, [777]), (BOTTOM, [50000, 25000, 25000]),
           (INNER, [99999]), (TOP, [40000, 30000, 20000])]
EQUAL = [(WALL, [12346, 20001, 3]), (SPARSE, [777]), (BOTTOM, [50000, 25000, 25000]),
         (INNER, [99999]), (TOP, [40000, 30000, 30000])]
TARGET, CONTROL = (1.1, 0.9, 1), (0.9, 1.1, 1)
EVIDENCE = Path(__file__).resolve().parents[1] / "docs/runs/evidence"
MAC = EVIDENCE / "mac-262-2026-11-25"


def plate(ratios=(1, 1, 1), layout=UNEQUAL, *, applied=None, absolute=False, eol="\n", bom=False,
          tweak=None) -> str:
    """G-code of one object: a purge line outside it, then five feature blocks.

    `ratios` are what the CONFIG block emits, `applied` what the E values used;
    `tweak(feature, base_units, units)` edits one move's written extrusion.
    """
    top, bottom, flow = applied or ratios

    def units(feature, base):
        factor = flow * (top if feature == TOP else bottom if feature == BOTTOM else 1)
        value = round(base * factor)
        return tweak(feature, base, value) if tweak else value

    position = 0.0

    def emit(x, amount):
        nonlocal position
        if absolute:
            position += amount
            word = f"{position:.5f}"
        else:
            word = f"{amount:.5f}"
        return f"G1 X{x} Y10 E{word}" if x is not None else f"G1 E{word}"

    lines = ["; HEADER_BLOCK_START", "; total layer number: 2", "; HEADER_BLOCK_END",
             "; EXECUTABLE_BLOCK_START", "G90", "G1 Z0.2", "M82" if absolute else "M83", emit(185, 15.0),
             ";LAYER_CHANGE", "; printing object Cube id:7 copy 0",
             emit(None, 1.5), ";WIPE_START", emit(0.5, -0.08), ";WIPE_END"]
    for feature, values in layout:
        lines.append(";TYPE:" + feature)
        lines += [emit(f"{index}.5", units(feature, base) * UNIT) for index, base in enumerate(values)]
    lines += ["; stop printing object Cube id:7 copy 0", "M104 S0", "; EXECUTABLE_BLOCK_END",
              "; CONFIG_BLOCK_START", f"; print_flow_ratio = {ratios[2]}",
              f"; top_solid_infill_flow_ratio = {ratios[0]}",
              f"; bottom_solid_infill_flow_ratio = {ratios[1]}", "; CONFIG_BLOCK_END"]
    return ("\ufeff" if bom else "") + eol.join(lines) + eol


def _read(tmp_path, name, text):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return balance.read_plate(path)


def _other(result):
    return sum(row["baseline"] for row in result["other_features"].values())


def _failed(result):
    skip = {"object_positive_unchanged", "balance_identity_holds"}
    return [key for key, value in result["checks"].items() if not value and key not in skip]


def test_only_top_and_bottom_scaling_moves_the_object_by_the_formula(tmp_path):
    baseline = _read(tmp_path, "base.gcode", plate())
    result = balance.compare(baseline, _read(tmp_path, "target.gcode", plate(TARGET)))
    # 0.1 * (0.9 mm top) - 0.1 * (1.0 mm bottom); every value is exact at five decimals
    assert result["measured_delta"] == pytest.approx(-0.01, abs=1e-12)
    assert result["predicted_delta"] == pytest.approx(-0.01, abs=1e-12)
    assert result["residual"] == pytest.approx(0.0, abs=1e-12)
    assert [result["top"]["baseline"], result["top"]["target"]] == pytest.approx([0.9, 0.99])
    assert [result["bottom"]["baseline"], result["bottom"]["target"]] == pytest.approx([1.0, 0.9])
    assert all(row["target"] == row["baseline"] for row in result["other_features"].values())
    assert result["checks"] == {"top_and_bottom_paths_identical": True, "other_features_identical": True,
                                "top_and_bottom_within_write_step": True, "print_flow_ratio_unchanged": True,
                                "balance_identity_holds": True, "object_positive_unchanged": False}


def test_equal_surfaces_are_the_one_case_where_the_object_total_stays_put(tmp_path):
    baseline = _read(tmp_path, "base.gcode", plate(layout=EQUAL))
    result = balance.compare(baseline, _read(tmp_path, "target.gcode", plate(TARGET, EQUAL)))
    assert result["measured_delta"] == pytest.approx(0.0, abs=1e-12)
    assert result["predicted_delta"] == pytest.approx(0.0, abs=1e-12)
    assert result["checks"]["balance_identity_holds"] and result["checks"]["object_positive_unchanged"]


def test_reversed_control_cancels_the_target(tmp_path):
    baseline = _read(tmp_path, "base.gcode", plate())
    target = balance.compare(baseline, _read(tmp_path, "target.gcode", plate(TARGET)))
    control = balance.compare(baseline, _read(tmp_path, "control.gcode", plate(CONTROL)))
    assert target["measured_delta"] == pytest.approx(-0.01) and control["measured_delta"] == pytest.approx(0.01)
    assert target["measured_delta"] + control["measured_delta"] == pytest.approx(0.0, abs=1e-12)
    assert control["emitted_ratios"]["top"] == [1.0, 0.9] and control["emitted_ratios"]["bottom"] == [1.0, 1.1]


def test_one_write_step_on_a_top_move_is_indistinguishable_from_rounding(tmp_path):
    tweak = lambda feature, base, units: units + 1 if feature == TOP else units  # noqa: E731
    baseline = _read(tmp_path, "base.gcode", plate())
    result = balance.compare(baseline, _read(tmp_path, "target.gcode", plate(TARGET, tweak=tweak)))
    assert result["top"]["max_abs_deviation"] == pytest.approx(UNIT)
    assert result["residual"] == pytest.approx(3 * UNIT) and result["checks"]["balance_identity_holds"]


@pytest.mark.parametrize("ratios,kwargs,detected_by", [
    (TARGET, {"tweak": lambda f, b, u: u + 1 if f == INNER else u}, ["other_features_identical"]),
    (TARGET, {"tweak": lambda f, b, u: u + 3 if f == TOP else u}, ["top_and_bottom_within_write_step"]),
    (TARGET, {"applied": (1.1, 1, 1)}, ["top_and_bottom_within_write_step"]),
    ((1.1, 0.9, 1.01), {}, ["other_features_identical", "top_and_bottom_within_write_step",
                            "print_flow_ratio_unchanged"]),
], ids=["one unit on an inner wall move", "three units on top moves", "bottom ratio emitted but not applied",
        "object flow ratio applied to everything"])
def test_changed_plate_cannot_pass_as_top_and_bottom_only(tmp_path, ratios, kwargs, detected_by):
    baseline = _read(tmp_path, "base.gcode", plate())
    result = balance.compare(baseline, _read(tmp_path, "target.gcode", plate(ratios, **kwargs)))
    assert not result["checks"]["balance_identity_holds"]
    assert _failed(result) == detected_by


@pytest.mark.parametrize("new", ["G1 X0.62 Y10 E0.44000", "G1 X0.5 Y10 E0.44000\nG1 X0.5 Y10 E0.44000"],
                         ids=["top path shifted 0.12 mm", "top move duplicated"])
def test_changed_top_paths_are_not_paired(tmp_path, new):
    baseline = _read(tmp_path, "base.gcode", plate())
    old = "G1 X0.5 Y10 E0.44000"
    assert plate(TARGET).count(old) == 1
    result = balance.compare(baseline, _read(tmp_path, "target.gcode", plate(TARGET).replace(old, new)))
    assert _failed(result) == ["top_and_bottom_paths_identical", "top_and_bottom_within_write_step"]


def test_purge_line_and_retract_prime_are_kept_apart_from_the_object(tmp_path):
    first = _read(tmp_path, "base.gcode", plate())
    assert first["outside"]["Custom"]["positive"] == 15.0 and first["outside"]["Custom"]["segments"] == 1
    assert first["side_e"] == pytest.approx(1.5 - 0.08)
    assert sum(row["positive"] for row in first["features"].values()) == pytest.approx(3.23126)
    assert first["objects"] == [{"name": "Cube", "id": "7", "copy": "0", "positive": pytest.approx(3.23126)}]
    assert first["layers"] == 1 and first["ratios"] == {"top": 1.0, "bottom": 1.0, "object": 1.0}


def test_absolute_e_mode_bom_and_crlf_read_the_same_plate(tmp_path):
    plain = _read(tmp_path, "plain.gcode", plate(TARGET))
    for name, kwargs in (("absolute.gcode", {"absolute": True}), ("crlf.gcode", {"eol": "\r\n", "bom": True})):
        other = _read(tmp_path, name, plate(TARGET, **kwargs))
        # absolute E is differenced from two written positions: equal to 1e-12, not bit for bit
        for key in ("features", "outside"):
            assert {k: (v["segments"], round(v["positive"], 9)) for k, v in other[key].items()} == {
                k: (v["segments"], round(v["positive"], 9)) for k, v in plain[key].items()}, f"{name}: {key}"
        assert other["side_e"] == pytest.approx(plain["side_e"]) and other["layers"] == plain["layers"], name
        assert {k: [tuple(round(c, 9) for c in s) for s in v] for k, v in other["surface"].items()} == {
            k: [tuple(round(c, 9) for c in s) for s in v] for k, v in plain["surface"].items()}, name


@pytest.mark.parametrize("old,new,message", [
    ("; CONFIG_BLOCK_START", "; CONFIG_BLOCK_MISSING", "one emitted configuration block"),
    ("; print_flow_ratio = 1\n", "", "print_flow_ratio: expected one emitted value, found 0"),
    ("; print_flow_ratio = 1\n", "; print_flow_ratio = 1\n; print_flow_ratio = 2\n",
     "print_flow_ratio: expected one emitted value, found 2"),
    ("print_flow_ratio = 1", "print_flow_ratio = 0", "positive ratio"),
    ("print_flow_ratio = 1", "print_flow_ratio = high", "not a number"),
    ("G90", "G90\nM221 S90", "firmware extrusion scaling"),
    ("G1 X0.5 Y10 E0.50000", "G2 X0.5 Y10 I1 J0 E0.50000", "extruding arc"),
    ("; stop printing object Cube id:7 copy 0\n", "", "never closed"),
    (";TYPE:Outer wall", "; printing object Cube id:7 copy 0\n;TYPE:Outer wall", "nested object"),
], ids=["no config block", "ratio missing", "ratio twice", "ratio zero", "ratio text", "M221", "extruding arc",
        "object never closed", "nested object"])
def test_unreadable_or_out_of_scope_plate_is_rejected(tmp_path, old, new, message):
    assert plate().count(old) == 1
    with pytest.raises(ValueError, match=message):
        _read(tmp_path, "bad.gcode", plate().replace(old, new))


def test_cli_exit_status_and_json_report(tmp_path, monkeypatch):
    paths = {name: tmp_path / f"{name}.gcode" for name in ("base", "good", "control", "bad")}
    for name, text in (("base", plate()), ("good", plate(TARGET)), ("control", plate(CONTROL)),
                       ("bad", plate(TARGET, applied=(1.1, 1, 1)))):
        paths[name].write_bytes(text.encode())
    report = tmp_path / "report.json"

    def run(*arguments):
        argv = ["check"]
        for argument in arguments:
            argv.append(str(paths[argument]) if argument in paths else argument)
        monkeypatch.setattr(sys, "argv", argv)
        return balance.main()

    assert run("--baseline", "base", "--target", "good", "--control", "control", "--json", str(report)) == 0
    assert set(json.loads(report.read_text(encoding="utf-8"))) == {"baseline", "target", "control"}
    assert run("--baseline", "base", "--target", "bad") == 1


def _archived(tmp_path, directory, names):
    """Copies of archived plates whose bytes are checked against the recorded digest."""
    copied = []
    for name, digest in names:
        raw = (directory / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        copied.append(tmp_path / name)
        copied[-1].write_bytes(raw)
    return copied


@pytest.mark.parametrize("baseline,target,top,bottom,total,other,delta", [
    ("cli-baseline.gcode", "cli-target.gcode", 127.51311, 21.21259, 3787.25918, 3638.53348, 10.63031),
    ("cli-baseline.gcode", "cli-control.gcode", 127.51311, 21.21259, 3787.25918, 3638.53348, -10.62978),
    ("cb5ac024-baseline.gcode", "cb5ac024-edited.gcode", 127.37739, 21.03846, 3785.59731, 3637.18146, 10.63421),
], ids=["CLI target", "CLI control", "GUI"])
def test_archived_mac_plates_follow_the_identity(tmp_path, baseline, target, top, bottom, total, other, delta):
    runs = json.loads((MAC / "cli-verified.json").read_text(encoding="utf-8"))["runs"]
    slices = json.loads((MAC / "cb5ac024-result.json").read_text(encoding="utf-8"))["slices"]
    digests = {"cli-" + stage + ".gcode": runs[stage]["sha256"] for stage in ("baseline", "target", "control")}
    digests.update({"cb5ac024-" + row["artifact"]: row["sha256"] for row in slices.values()})
    first, last = _archived(tmp_path, MAC, [(baseline, digests[baseline]), (target, digests[target])])
    result = balance.compare(balance.read_plate(first), balance.read_plate(last))
    assert result["checks"]["balance_identity_holds"] and not result["checks"]["object_positive_unchanged"]
    assert [result["top"]["baseline"], result["bottom"]["baseline"], _other(result)] == pytest.approx([top, bottom, other])
    assert result["object_positive"]["baseline"] == pytest.approx(total)
    assert result["measured_delta"] == pytest.approx(delta, abs=1e-9)
    assert result["predicted_delta"] == pytest.approx(delta, abs=3.2e-4)
    assert abs(result["residual"]) <= result["residual_bound"]


def test_archived_physical_machine_plate_follows_the_identity(tmp_path):
    folder = EVIDENCE / "feishu-262-fa-2026-11-25"
    recorded = json.loads((folder / "measurements.json").read_text(encoding="utf-8"))
    with ZipFile(folder / "harvest.zip") as archive:
        plates = []
        for stage, digest in zip(("baseline", "target"), recorded["input_sha256"]):
            raw = archive.read(f"{stage}/export.gcode")
            assert hashlib.sha256(raw).hexdigest() == digest
            plates.append(tmp_path / f"{stage}.gcode")
            plates[-1].write_bytes(raw)
    result = balance.compare(balance.read_plate(plates[0]), balance.read_plate(plates[1]))
    assert result["checks"]["balance_identity_holds"] and not result["checks"]["object_positive_unchanged"]
    assert [result["object_positive"]["baseline"], result["object_positive"]["target"]] == pytest.approx(
        recorded["all_labelled_features_extrusion_mm"])
    assert [result["top"]["baseline"], result["bottom"]["baseline"]] == pytest.approx([107.75821, 21.21237])
    assert result["measured_delta"] == pytest.approx(8.65434, abs=1e-9)
    assert result["predicted_delta"] == pytest.approx(8.654584, abs=1e-9)
    assert result["residual"] == pytest.approx(-2.44e-4, abs=1e-6)
