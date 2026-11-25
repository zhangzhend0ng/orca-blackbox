"""Feishu #236, #233 and #227 replayed offline: synthetic harvests for tools/replay_gcode_export.py,
tools/replay_merged_stl.py and tools/replay_import_stl.py, and the independent readers of
tests/file_io_replay_support.py against real archived bytes.

The #236 run is built here with zipfile, string templates and Pillow: a project equal to the
standard cube fixture by content, a G-code that prints it, two screenshots and the record the GUI
would keep. The #233 run adds a ball beside the cube, an STL of both written with struct, a viewer
render with an opaque body in a transparent frame, and the viewer's logs. The #227 run is assembled
from what the application really wrote for #244 (the same cube_20mm.stl imported the same way); its
moved and turned projects are those bytes with the instance transform rewritten. The readings on a
real move and a real turn by the application were checked on the green guest run of 0d7222e7 and on
the two formal sessions of 11858f17, which live outside the repository.
"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from file_io_replay_support import CORE, MAIN, archive, copy_of, gcode, manifest, png, project, zipped
from tools import replay_gcode_export as export
from tools.replay_case_evidence import ADAPTERS, replay_receipt

FIXTURE = ROOT / "fixtures" / "feishu_std_cube.3mf"
EVIDENCE = ROOT / "docs" / "runs" / "evidence"
PREFIX = "abc12345-run1"
SETTINGS = {"layer_height": "0.2", "initial_layer_print_height": "0.25", "printer_model": "Snapmaker U1",
            "printer_settings_id": "Snapmaker U1 (0.4 nozzle)",
            "print_settings_id": "0.20mm Standard @Snapmaker U1 (0.4 nozzle)", "print_sequence": "by layer",
            "brim_type": "auto_brim", "gcode_flavor": "klipper", "nozzle_diameter": ["0.4"] * 4,
            "filament_type": ["PLA"] * 5}
# the outer wall's centre line of the cube, a quarter millimetre inside its 122..149 x 122.5..149.5 footprint
WALL = (122.25, 122.75, 148.75, 149.25)
# the U1 bed, as the saved projects name it
BED = {"printable_area": ["0.5x1", "270.5x1", "270.5x271", "0.5x271"], "printable_height": "270.05",
       "bed_exclude_area": ["0x0"]}
CUBE_BOX = (122.0, 149.0, 122.5, 149.5, 0.0, 27.0)       # xmin, xmax, ymin, ymax, zmin, zmax
TURN = "0 1 0 -1 0 0 0 0 1 0 0 0"                        # a quarter turn about Z
UNIT_TURN = "1 0 0 0 1 0 0 0 1 0 0 0"


def soup(triangles):
    """One `<vertex>` per corner and one `<triangle>` each: the triangles as they are, without indexing."""
    vertices = "".join(f'<vertex x="{x:g}" y="{y:g}" z="{z:g}"/>'
                       for triangle in triangles for x, y, z in triangle)
    faces = "".join(f'<triangle v1="{3 * index}" v2="{3 * index + 1}" v3="{3 * index + 2}"/>'
                    for index in range(len(triangles)))
    return f"<mesh><vertices>{vertices}</vertices><triangles>{faces}</triangles></mesh>"


def model_xml(resources, transform):
    head = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xmlns="{CORE[1:-1]}" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">'
            '<metadata name="Application">Snapmaker_Orca-2.4.0</metadata>')
    return f"{head}<resources>{resources}</resources><build><item objectid=\"2\" transform=\"{transform}\"/></build></model>"


def object_settings(name="立方体"):
    return ('<config><object id="2"><metadata key="name" value="立方体"/><part id="1" subtype="normal_part">'
            f'<metadata key="name" value="{name}"/></part></object><plate><metadata key="plater_id" value="1"/>'
            '<metadata key="plater_name" value=""/><model_instance><metadata key="object_id" value="2"/>'
            '<metadata key="instance_id" value="0"/></model_instance></plate></config>').encode("utf-8")


def project_3mf(triangles=None, transform="1 0 0 0 1 0 0 0 1 0 0 0", settings=None):
    """A project from scratch: the given world triangles (the fixture cube's by default) under one build item."""
    if triangles is None:
        triangles = project(FIXTURE.read_bytes())["objects"][0]["triangles"]
    mesh = (f'<object id="2" type="model"><components><component objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
            '</components></object><object id="1" type="model">' + soup(triangles) + "</object>")
    return zipped({MAIN: model_xml(mesh, transform).encode("utf-8"),
                   "Metadata/project_settings.config": json.dumps(
                       dict(SETTINGS, **BED) if settings is None else settings).encode(),
                   "Metadata/model_settings.config": object_settings()})


def config_lines(settings=None):
    lines = []
    for key, value in (SETTINGS if settings is None else settings).items():
        joined = ",".join(value) if key == "nozzle_diameter" else ";".join(value) if isinstance(value, list) else value
        lines.append(f"; {key} = {joined}")
    return lines + [f"; filler_{index} = {index}" for index in range(12)]


def plate_gcode(settings=None, wall=WALL, layers=135, name="立方体"):
    """A G-code that prints one square wall per layer over the cube, with every block and note of a real export."""
    lines = ["; HEADER_BLOCK_START", "; generated by Snapmaker Orca 2.4.0 on 2026-11-26 at 00:00:00",
             f"; total layer number: {layers}", "; max_z_height: 27.05", "; HEADER_BLOCK_END",
             "; EXECUTABLE_BLOCK_START", "M73 P0 R21", "M140 S65", "M104 T0 S220", "G28", "PRINT_START", "G90", "M83"]
    for index in range(layers):
        lines += [";LAYER_CHANGE", f";Z:{0.25 + 0.2 * index:.2f}", ";HEIGHT:0.2",
                  f"SET_PRINT_STATS_INFO TOTAL_LAYER={layers} CURRENT_LAYER={index + 1}",
                  f"; printing object {name} id:1 copy 0", ";TYPE:Outer wall",
                  f"G1 X{wall[0]} Y{wall[1]} F30000", f"G1 X{wall[2]} Y{wall[1]} E0.1",
                  f"G1 X{wall[2]} Y{wall[3]} E0.1", f"G1 X{wall[0]} Y{wall[3]} E0.1",
                  f"G1 X{wall[0]} Y{wall[1]} E0.1", f"; stop printing object {name} id:1 copy 0"]
    lines += ["M106 S0", "M104 S0", "PRINT_END", "; EXECUTABLE_BLOCK_END",
              "; filament used [mm] = 135.00, 0.00, 0.00, 0.00, 0.00", f"; total layers count = {layers}",
              "; estimated printing time (normal mode) = 1m 0s", "; CONFIG_BLOCK_START", *config_lines(settings),
              "; CONFIG_BLOCK_END", ""]
    return "\n".join(lines).encode("utf-8")


def picture(width=640, height=400, seed=1, blank=False):
    """A screenshot-like PNG, or a uniformly grey one."""
    if blank:
        pixels = np.full((height, width, 3), 128, np.uint8)
    else:
        ramp = np.linspace(0, 255, width, dtype=np.float32)[None, :, None]
        pixels = (ramp + np.random.default_rng(seed).uniform(0, 40, (height, width, 3))).clip(0, 255).astype(np.uint8)
    out = BytesIO()
    Image.fromarray(pixels, "RGB").save(out, "PNG")
    return out.getvalue()


def write_run(folder, prefix=PREFIX, *, gcode=None, project=None, record=None, pictures=None, entries=None):
    """A synthetic #236 harvest in the shape the collector leaves: `<prefix>-<part>` files, a manifest, a
    log and a receipt whose digest matches the log. The record is what the GUI would write for these files."""
    folder.mkdir(parents=True, exist_ok=True)
    parts = {"before.3mf": project_3mf() if project is None else project,
             "plate.gcode": plate_gcode() if gcode is None else gcode,
             "sliced.png": picture(seed=1) if pictures is None else pictures[0],
             "export-dialog.png": picture(seed=2) if pictures is None else pictures[1]}
    for part, raw in parts.items():
        (folder / f"{prefix}-{part}").write_bytes(raw)
    facts = export.gcode_export_facts(folder / f"{prefix}-plate.gcode")
    # the case keeps the oracle's footprint reading, taken under the name it gave the file (a harvest
    # stores that file under the run's prefix), and judges the clauses with it
    plain = folder / "plate.gcode"
    plain.write_bytes(parts["plate.gcode"])
    footprint = export.gcode_footprint(plain, folder / f"{prefix}-before.3mf")
    plain.unlink()
    shown = pictures or (picture(seed=1), picture(seed=2))
    gaps = export.gcode_expectation_gaps(facts, ".gcode", footprint)
    default = {"case": 236,
               "results": {clause: "PASS" if not failed else f"FAIL ({', '.join(failed)})"
                           for clause, failed in gaps.items()},
               "fixture": {"name": FIXTURE.name, "bytes": len(FIXTURE.read_bytes()),
                           "sha256": sha256(FIXTURE.read_bytes()).hexdigest()},
               "export": {"typed_name": "plate", "saved_name": "plate.gcode", "saved_extension": ".gcode",
                          "file_bytes": len(parts["plate.gcode"]),
                          "file_sha256": sha256(parts["plate.gcode"]).hexdigest(),
                          "dialog_image": {"width_px": png(shown[1])["width"], "height_px": png(shown[1])["height"]}},
               "gcode": facts, "footprint": footprint, "expectation_gaps": gaps}
    # `record` may be a callable that edits what the GUI would have written
    parts["analysis.json"] = json.dumps(record(default) if callable(record) else default if record is None else record,
                                        ensure_ascii=False, indent=2).encode("utf-8")
    (folder / f"{prefix}-analysis.json").write_bytes(parts["analysis.json"])
    manifest_ = [{"part": part, "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                 for part, raw in parts.items()] if entries is None else entries
    (folder / f"{prefix}-object_artifacts.json").write_text(json.dumps(manifest_, indent=1), encoding="utf-8")
    log = f"[m7x236] retained work directory: C:\\coil\\runs\\{prefix}\n".encode()
    (folder / f"{prefix}-case.log").write_bytes(log)
    (folder / f"{prefix}-receipt.json").write_text(json.dumps({
        "case": "m7x_236_export_gcode", "commit": "0" * 40, "summary": "SUMMARY: PASS=4 FAIL=0",
        "dispatched_at": "2026-11-26T00:00:00+00:00", "scenario_completed_at": "2026-11-26T00:00:10+00:00",
        "log_sha256": sha256(log).hexdigest()}), encoding="utf-8")
    return folder, prefix


def refused(tmp_path, failed, **changes):
    """A run with a stand-in whose manifest agrees with it: the replay must name `failed` among its readings."""
    folder, prefix = write_run(tmp_path, **changes)
    result = export.replay(folder, prefix)
    assert set(failed) <= set(result["export"]["failed"]), result["export"]["failed"]
    assert not all(result["checks"].values())
    return result


def lines_of(raw):
    return raw.decode("utf-8").split("\n")


# --- the synthetic run and the driver's path ---------------------------------------

def test_synthetic_run_passes_every_reading_and_every_counterexample(tmp_path):
    folder, prefix = write_run(tmp_path)
    result = export.replay(folder, prefix)
    # the driver counts a check only when it is literally True
    not_true = [key for key, value in result["checks"].items() if value is not True]
    assert not not_true, not_true
    assert set(export.POSITIVE) <= set(result["checks"])
    assert {key for key in result["checks"] if key.endswith("_rejected")} == {
        "empty_file_rejected", "header_only_rejected", "missing_layer_rejected", "declared_total_mismatch_rejected",
        "layer_removed_with_rewritten_totals_rejected", "no_end_gcode_rejected", "tail_truncated_rejected",
        "foreign_gcode_rejected", "print_moved_off_the_object_rejected", "another_object_printed_rejected",
        "wrong_extension_rejected", "other_project_rejected", "manifest_mismatch_rejected", "edited_analysis_rejected"}
    assert (result["export"]["layers"], result["export"]["z_last"], result["export"]["object_names"]) == (
        135, [27.05], ["立方体"])


def test_the_case_runs_through_the_shared_driver_like_the_other_replays(tmp_path, monkeypatch):
    folder, prefix = write_run(tmp_path)
    monkeypatch.setitem(ADAPTERS, "m7x_236_export_gcode", export.replay)
    report = replay_receipt(folder / f"{prefix}-receipt.json")
    assert report["offline_checks_passed"] and report["historical_scenario_seconds"] == 10.0, report
    (folder / f"{prefix}-case.log").write_bytes(b"another log\n")
    report = replay_receipt(folder / f"{prefix}-receipt.json")
    assert not report["offline_checks_passed"] and "SHA-256 differs" in report["error"]


def test_replay_actually_reads_every_counterexample_on_a_temporary_copy(tmp_path, monkeypatch):
    # the counterexamples are reported by the replay itself: make sure none was dropped without a reading
    folder, prefix = write_run(tmp_path)
    reads, real = [], export._read
    monkeypatch.setattr(export, "_read", lambda place, pre: reads.append(place.name) or real(place, pre))
    result = export.replay(folder, prefix)
    assert all(result["checks"].values())
    assert len([key for key in result["checks"] if key.endswith("_rejected")]) == 14
    assert len(reads) == 15 and sum(name.startswith("replay-") for name in reads) == 14


# --- what each reading refuses when the manifest agrees with the stand-in ------------

def test_empty_and_header_only_files_are_refused(tmp_path):
    refused(tmp_path, ["text_is_intact"], gcode=b"")
    refused(tmp_path, ["blocks_complete_and_ordered", "layers_present"],
            gcode=plate_gcode().split(b"; EXECUTABLE_BLOCK_START")[0])


def test_a_layer_taken_out_is_refused_whatever_the_declared_totals_say(tmp_path):
    lines = lines_of(plate_gcode())
    starts = [index for index, line in enumerate(lines) if line == ";LAYER_CHANGE"]
    gone = lines[:starts[60]] + lines[starts[61]:]
    refused(tmp_path, ["declared_layer_count_agrees"], gcode="\n".join(gone).encode())
    # a forger who also rewrites the totals leaves only the numbering and the layer heights to tell
    forged = [line.replace("number: 135", "number: 134").replace("count = 135", "count = 134").replace(
        "TOTAL_LAYER=135", "TOTAL_LAYER=134") for line in gone]
    result = refused(tmp_path, ["layer_numbers_run_from_1", "layer_schedule_matches_object_height"],
                     gcode="\n".join(forged).encode())
    assert not result["checks"]["oracle_accepts_export"]


def test_declared_totals_that_disagree_are_refused(tmp_path):
    refused(tmp_path, ["declared_layer_count_agrees"],
            gcode=plate_gcode().replace(b"; total layer number: 135", b"; total layer number: 134"))


def test_export_without_end_gcode_or_without_its_tail_is_refused(tmp_path):
    lines = lines_of(plate_gcode())
    without_end = [line for line in lines if line not in ("M106 S0", "M104 S0", "PRINT_END")]
    refused(tmp_path, ["end_gcode_after_last_extrusion"], gcode="\n".join(without_end).encode())
    refused(tmp_path, ["blocks_complete_and_ordered", "config_matches_sliced_project"],
            gcode="\n".join(lines[:lines.index("; CONFIG_BLOCK_START")]).encode())


def test_layer_heights_out_of_order_are_refused(tmp_path):
    lines = lines_of(plate_gcode())
    first, second = lines.index(";Z:0.25"), lines.index(";Z:0.45")
    lines[first], lines[second] = ";Z:0.45", ";Z:0.25"
    refused(tmp_path, ["layer_z_present_and_nondecreasing"], gcode="\n".join(lines).encode())


def test_configuration_that_differs_from_the_sliced_project_is_refused(tmp_path):
    refused(tmp_path, ["config_matches_sliced_project"],
            gcode=plate_gcode().replace(b"; layer_height = 0.2", b"; layer_height = 0.3"))
    refused(tmp_path, ["config_matches_sliced_project"],
            gcode=plate_gcode().replace(b"; CONFIG_BLOCK_START", b"; CONFIG_BLOCK_START\n; layer_height = 0.2"))


@pytest.mark.parametrize("dx,dy", [(3, 0), (-3, 0), (0, 3), (0, -3)], ids=["x+3", "x-3", "y+3", "y-3"])
def test_a_print_that_misses_the_saved_object_is_refused_in_every_direction(tmp_path, dx, dy):
    # the oracle's reading of the file alone passes it wherever it prints: the file is whole and its
    # layers run on. Two readings tie it to the saved object, the oracle's footprint and the replay's
    # own, and both must hold on all four sides
    result = refused(tmp_path, [], gcode=export._shifted(plate_gcode(), dx, dy))
    assert {"extrusion_lies_on_the_objects", "oracle_locates_the_extrusion_on_the_objects"} <= set(
        result["export"]["failed"])
    assert result["checks"]["oracle_accepts_export"]
    assert not result["checks"]["recorded_verdict_matches_file"]      # the case records the first clause as failed


def test_a_print_attributed_to_another_object_is_refused(tmp_path):
    # whole in itself and in place; only the name it prints belongs to no object of the saved project
    result = refused(tmp_path, ["printed_objects_are_saved_objects"], gcode=export._renamed(plate_gcode()))
    assert result["checks"]["oracle_accepts_export"]


def test_the_footprint_reading_is_live_and_an_edited_or_older_record_is_told_apart(tmp_path):
    folder, prefix = write_run(tmp_path)
    readings = export._read(folder, prefix)[1]["oracle_footprint"]
    assert readings["checks"] and all(readings["checks"].values())
    assert readings["max_excursion_mm"]["model"] <= readings["allowances_mm"]["model"] == 1.0
    # the record's footprint is held against the file's
    refused(tmp_path, ["recorded_footprint_matches_file"], record=lambda default: dict(
        default, footprint=dict(default["footprint"], max_excursion_mm={"model": 9.0})))
    # a run from before the case kept the footprint has no such entry: that alone is no refusal
    older = write_run(tmp_path, record=lambda default: {key: value for key, value in default.items()
                                                       if key != "footprint"})
    assert all(value is True for value in export.replay(*older)["checks"].values())
    # the formal runs were recorded by an earlier oracle under the plain file name: it had no plate
    # keys yet, and what it did hold comes out the same from the file
    earlier = lambda default: dict(default, footprint={key: value for key, value in default["footprint"].items()  # noqa: E731
                                                       if key not in ("plate", "plate_count")})
    place = write_run(tmp_path, record=earlier)
    held = json.loads((place[0] / f"{PREFIX}-analysis.json").read_text("utf-8"))["footprint"]
    assert held["file_name"] == "plate.gcode" and "plate" not in held and "plate_count" not in held
    assert all(value is True for value in export.replay(*place)["checks"].values())
    # a record that shares nothing with the reading, or whose checks differ, agrees to nothing
    refused(tmp_path, ["recorded_footprint_matches_file"], record=lambda default: dict(default, footprint={}))
    refused(tmp_path, ["recorded_footprint_matches_file"], record=lambda default: dict(
        default, footprint=dict(default["footprint"], checks=dict(
            default["footprint"]["checks"], model_on_objects=False))))
    # a flattering record over a print that misses the object: the footprint is what gives the lie
    flattering = lambda default: dict(  # noqa: E731
        default, results={clause: "PASS" for clause in export.CLAUSES},
        expectation_gaps={clause: [] for clause in export.CLAUSES})
    refused(tmp_path, ["recorded_verdict_matches_file", "oracle_locates_the_extrusion_on_the_objects",
                       "extrusion_lies_on_the_objects"],
            gcode=export._shifted(plate_gcode(), 3.0, 0.0), record=flattering)


def test_a_project_that_is_not_the_fixture_is_refused(tmp_path):
    moved = project_3mf(transform="1 0 0 0 1 0 0 0 1 40 0 0")
    result = refused(tmp_path, ["saved_project_is_the_fixture", "extrusion_lies_on_the_objects"], project=moved)
    assert result["checks"]["config_matches_sliced_project"]      # the settings still agree; the place does not
    raised = refused(tmp_path, ["saved_project_is_the_fixture"], project=project_3mf(transform="1 0 0 0 1 0 0 0 1 0 0 5"))
    assert raised["checks"]["extrusion_lies_on_the_objects"]      # the footprint is still printed
    refused(tmp_path, ["saved_project_is_the_fixture", "config_matches_sliced_project"],
            project=project_3mf(settings=dict(SETTINGS, **BED, layer_height="0.3")))


def test_a_record_that_claims_more_than_the_file_shows_is_refused(tmp_path):
    flattering = lambda default: dict(  # noqa: E731
        default, results={clause: "PASS" for clause in export.CLAUSES},
        expectation_gaps={clause: [] for clause in export.CLAUSES})
    lines = lines_of(plate_gcode())
    without_end = export._without_end(lines, gcode(plate_gcode())["last_extruding_line"])
    refused(tmp_path, ["end_gcode_after_last_extrusion", "recorded_verdict_matches_file"],
            gcode="\n".join(without_end).encode(), record=flattering)
    refused(tmp_path, ["recorded_hashes_match_file"],
            record=lambda default: dict(default, export=dict(default["export"], file_sha256="0" * 64)))
    refused(tmp_path, ["recorded_verdict_matches_file", "recorded_case_and_fixture"],
            record=lambda default: dict(default, results={"生成 .gcode 文件": "FAIL (x)"}, case=227))


def test_pictures_that_are_blank_or_not_the_recorded_dialog_are_refused(tmp_path):
    refused(tmp_path, ["screenshots_are_pictures"], pictures=(picture(seed=3), picture(blank=True)))
    # the record says the dialog was captured at 640x400; the picture kept is another size
    refused(tmp_path, ["dialog_picture_matches_record"], pictures=(picture(seed=3), picture(800, 500)),
            record=lambda default: dict(default, export=dict(
                default["export"], dialog_image={"width_px": 640, "height_px": 400})))


def test_a_wrong_extension_or_a_manifest_that_disagrees_stops_the_replay(tmp_path):
    folder, prefix = write_run(tmp_path)
    with copy_of(folder, prefix, rename={"plate.gcode": "plate.gcode.3mf"}) as (other, altered):
        with pytest.raises(ValueError, match="expected one .gcode part"):
            export.replay(other, altered)
    with copy_of(folder, prefix, {"plate.gcode": b""}, keep_manifest=False) as (other, altered):
        with pytest.raises(ValueError, match="size differs from manifest"):
            export.replay(other, altered)


@pytest.mark.parametrize("entries", [
    [], {"part": "plate.gcode"}, [{"part": "plate.gcode", "bytes": "10", "sha256": "0" * 64}],
    [{"part": "plate.gcode", "bytes": 10, "sha256": "abc"}], [{"part": "plate.gcode", "bytes": 1, "sha256": "0" * 64}] * 2,
], ids=["empty", "not a list", "text byte count", "short digest", "listed twice"])
def test_a_manifest_that_is_not_a_list_of_parts_is_refused(tmp_path, entries):
    folder, prefix = write_run(tmp_path, entries=entries)
    with pytest.raises(ValueError):
        manifest(folder, prefix)


def test_copy_of_follows_a_replacement_into_the_manifest_or_leaves_it_for_a_bad_collector(tmp_path):
    folder, prefix = write_run(tmp_path)
    with copy_of(folder, prefix, {"plate.gcode": b"other"}) as (other, altered):
        assert [entry["part"] for entry in manifest(other, altered)] == [
            "before.3mf", "plate.gcode", "sliced.png", "export-dialog.png", "analysis.json"]
        assert (other / f"{altered}-plate.gcode").read_bytes() == b"other"
        assert all(entry["sha256"] == sha256((other / f"{altered}-{entry['part']}").read_bytes()).hexdigest()
                   for entry in manifest(other, altered))
    with copy_of(folder, prefix, {"plate.gcode": b"other"}, keep_manifest=False) as (other, altered):
        assert manifest(other, altered) == manifest(folder, prefix)


# --- the independent readers ------------------------------------------------------

def test_gcode_reader_sees_what_a_real_plate_contains():
    sphere = gcode((EVIDENCE / "win11-254-2026-11-25/1d2de6b4-run1-baseline.gcode").read_bytes())
    assert (sphere["layer_count"], sphere["z"][0], sphere["z"][-1]) == (100, 0.25, 20.05)
    assert sphere["layer_numbers"] == list(range(1, 101))
    assert sphere["declared"] == {"total layer number": [100], "total layers count": [100], "TOTAL_LAYER=": [100]}
    assert (sphere["object_names"], sphere["layers_without_extrusion"], sphere["config_lines"]) == (["球体"], 0, 572)
    assert sphere["markers"]["; CONFIG_BLOCK_END"] == [26955] and sphere["after_config"] == []
    assert {"M106 S0", "PRINT_END"} <= set(sphere["after_last_extrusion"])
    assert sphere["start_commands"][:3] == ["M73 P0 R13", "M106 S0", "M106 P2 S0"]
    # the sphere is 20 mm across at 125..145; its walls end a fifth of a millimetre inside that
    assert sphere["extrusion_box"] == (125.213, 125.213, 144.787, 144.787)


def test_gcode_reader_numbers_layers_from_tags_when_there_are_no_statistics():
    lines, number = [], 0
    for line in lines_of(plate_gcode()):
        if line == ";LAYER_CHANGE":
            lines.append(f";LAYER:{number}")
            number += 1
        elif not line.startswith("SET_PRINT_STATS_INFO"):
            lines.append(line)
    numbered = gcode("\n".join(lines).encode())
    assert numbered["layer_marker"] == ";LAYER:" and numbered["layer_count"] == 135
    assert numbered["layer_numbers"] == list(range(135)) and "TOTAL_LAYER=" not in numbered["declared"]


def test_gcode_reader_counts_extrusion_in_absolute_e_mode_as_well():
    position, out = 0.0, []
    for line in plate_gcode().decode("utf-8").replace("\nM83", "\nM82").split("\n"):
        if line.startswith("G1 X") and line.endswith(" E0.1"):
            position = round(position + 0.1, 2)
            line = line.replace("E0.1", f"E{position:.2f}")
        out.append(line)
    absolute = gcode("\n".join(out).encode())
    assert (absolute["layer_count"], absolute["layers_without_extrusion"]) == (135, 0)
    assert absolute["layers"][0]["extruding"] == 4 and absolute["layers"][1]["extruding"] == 4


def test_project_reader_reads_real_projects_with_parts_in_their_own_members():
    cube = project(FIXTURE.read_bytes())
    assert cube["application"] == "BambuStudio-2.3.6" and cube["settings"]["printer_model"] == "Snapmaker U1"
    (item,) = cube["objects"]
    assert (item["name"], item["plate"], len(item["triangles"])) == ("立方体", "1", 12)
    assert item["box"] == CUBE_BOX
    imported = project((EVIDENCE / "multi-244-254-2026-11-25/win11-test/e7ba1cd2-run1-imported.3mf").read_bytes())
    assert (imported["application"], imported["objects"][0]["name"], len(imported["objects"][0]["triangles"])) == (
        "Snapmaker_Orca-2.4.0", "cube_20mm.stl", 12)
    assert imported["objects"][0]["box"] == (125.5, 145.5, 126.0, 146.0, 0.0, 20.0)
    sphere = project((EVIDENCE / "win11-254-2026-11-25/1d2de6b4-run1-sphere-edited.3mf").read_bytes())
    assert (sphere["objects"][0]["name"], len(sphere["objects"][0]["triangles"])) == ("球体", 3968)
    assert sphere["objects"][0]["box"] == (125.0, 145.0, 125.0, 145.0, 0.0, 20.0)


def test_project_reader_applies_the_part_transform_first_and_the_item_transform_after_it():
    # one triangle with a corner at x = 1: the part moves it to x = 11, the item turns x into y and y into -x
    corner = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    part = ('<object id="2" type="model"><components><component objectid="1" p:path="/3D/Objects/part.model" '
            'transform="1 0 0 0 1 0 0 0 1 10 0 0"/></components></object>')
    files = {MAIN: model_xml(part, TURN).encode(), "3D/Objects/part.model": (
        f'<model unit="millimeter" xmlns="{CORE[1:-1]}"><resources><object id="1" type="model">{soup([corner])}'
        "</object></resources></model>").encode(), "Metadata/project_settings.config": b"{}",
        "Metadata/model_settings.config": object_settings()}
    (item,) = project(zipped(files))["objects"]
    assert item["triangles"] == (((-1.0, 10.0, 0.0), (0.0, 10.0, 0.0), (0.0, 11.0, 0.0)),)
    assert project(project_3mf([corner], transform=TURN))["objects"][0]["triangles"] == (
        ((-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),)


def test_project_reader_refuses_what_it_cannot_read(monkeypatch):
    import file_io_replay_support as support

    assert len(support.project(FIXTURE.read_bytes())["objects"]) == 1
    monkeypatch.setattr(support, "TOTAL_BYTES", 1000)
    with pytest.raises(ValueError, match="too many, too large"):
        support.project(FIXTURE.read_bytes())
    monkeypatch.undo()
    with pytest.raises(ValueError, match="not a readable project archive"):
        support.archive(b"PK\x03\x04 not a zip")
    with pytest.raises(ValueError, match="project lacks"):
        support.project(zipped({MAIN: b"<model/>"}))
    with pytest.raises(ValueError, match="twelve numbers"):
        support.project(zipped({MAIN: model_xml("<object id=\"1\" type=\"model\">x</object>", "1 2 3").encode(),
                                "Metadata/project_settings.config": b"{}", "Metadata/model_settings.config": b"<config/>"}))
    with pytest.raises(ValueError, match="not a 3MF model"):
        support.project(zipped({MAIN: b"<model/>", "Metadata/project_settings.config": b"{}",
                                "Metadata/model_settings.config": b"<config/>"}))
    with pytest.raises(ValueError, match="not an object"):
        support.project(zipped({MAIN: model_xml("", UNIT_TURN).encode(),
                                "Metadata/project_settings.config": b"[]",
                                "Metadata/model_settings.config": b"<config/>"}))


def test_picture_reader_reports_a_blank_and_a_real_screenshot():
    assert (png(picture(blank=True))["gray_levels"], png(picture(blank=True))["std"]) == (1, 0.0)
    real = png((EVIDENCE / "win11-254-2026-11-25/1d2de6b4-run1-baseline-preview.png").read_bytes())
    assert (real["format"], real["width"], real["height"]) == ("PNG", 1920, 1032) and real["std"] > 5
    with pytest.raises(ValueError, match="not a readable picture"):
        png(b"not a picture")


# --- Feishu #233: the merged STL ---------------------------------------------------
# The synthetic run is a saved plate with the fixture's cube and a ball built here, an STL of both
# written with struct, a viewer render with an opaque body in a transparent frame, the viewer's
# logs and the record the case writes for them.

import math
import struct

import file_io_replay_support as support
from plate_reserve_oracle import verify_f3d_image
from tools import replay_merged_stl as merged

MERGE_PREFIX = "be234567-run1"
VERSION_LOG = b"F3D 4.0.1\r\n\r\nF3D - A fast and minimalist 3D viewer\r\nVersion: 4.0.1.\r\n"
BROKEN = b"not an STL mesh\n"
# where Arrange leaves the two: the cube's low corner and the ball's centre, a plate's width apart in Y
CUBE_AT, BALL_AT = (122.0, 137.0, 0.0), (135.5, 121.5, 13.5)
UNOPENABLE = object()     # a stand-in the replay cannot even open, so no reading names it
BALL_TRIANGLES = 224      # 8 rings of 16 segments: 16 + 6 * 32 + 16


def indexed(triangles):
    """A triangle soup as (vertices, faces): every corner once, named by its index in each triangle."""
    vertices, faces = [], []
    for triangle in triangles:
        face = []
        for corner in triangle:
            if corner not in vertices:
                vertices.append(corner)
            face.append(vertices.index(corner))
        faces.append(tuple(face))
    return vertices, faces


def local_cube():
    """The fixture's cube mesh in its own frame, which starts at the cube's low corner on the plate."""
    world = project(FIXTURE.read_bytes())["objects"][0]["triangles"]
    return indexed([tuple(tuple(c - o for c, o in zip(corner, CUBE_BOX[0::2])) for corner in triangle)
                    for triangle in world])


def ball_mesh(radius=13.5, rings=8, segments=16):
    """A tessellated ball around the origin: two poles and rings of vertices, all exactly on its surface."""
    vertices = [(0.0, 0.0, radius)]
    for ring in range(1, rings):
        theta = math.pi * ring / rings
        vertices += [(radius * math.sin(theta) * math.cos(2 * math.pi * step / segments),
                      radius * math.sin(theta) * math.sin(2 * math.pi * step / segments),
                      radius * math.cos(theta)) for step in range(segments)]
    vertices.append((0.0, 0.0, -radius))
    faces = [(0, 1 + step, 1 + (step + 1) % segments) for step in range(segments)]
    for ring in range(rings - 2):
        top, below = 1 + ring * segments, 1 + (ring + 1) * segments
        for step in range(segments):
            a, b = top + step, top + (step + 1) % segments
            c, d = below + step, below + (step + 1) % segments
            faces += [(a, c, d), (a, d, b)]
    last = 1 + (rings - 2) * segments
    faces += [(last + step, len(vertices) - 1, last + (step + 1) % segments) for step in range(segments)]
    return vertices, faces


def plate_3mf(objects, settings=None):
    """A saved plate from scratch: a (name, vertices, faces, translation) per object, in build order."""
    resources, items, rows, instances = [], [], [], []
    for index, (name, vertices, faces, at) in enumerate(objects):
        outer, mesh = 2 * index + 2, 2 * index + 1
        resources.append(
            f'<object id="{outer}" type="model"><components><component objectid="{mesh}" '
            'transform="1 0 0 0 1 0 0 0 1 0 0 0"/></components></object>'
            f'<object id="{mesh}" type="model"><mesh><vertices>'
            + "".join(f'<vertex x="{x:g}" y="{y:g}" z="{z:g}"/>' for x, y, z in vertices)
            + "</vertices><triangles>"
            + "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
            + "</triangles></mesh></object>")
        items.append(f'<item objectid="{outer}" transform="1 0 0 0 1 0 0 0 1 {at[0]:g} {at[1]:g} {at[2]:g}"/>')
        rows.append(f'<object id="{outer}"><metadata key="name" value="{name}"/>'
                    f'<part id="{mesh}" subtype="normal_part"><metadata key="name" value="{name}"/></part></object>')
        instances.append(f'<model_instance><metadata key="object_id" value="{outer}"/>'
                         '<metadata key="instance_id" value="0"/></model_instance>')
    head = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xmlns="{CORE[1:-1]}" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">'
            '<metadata name="Application">Snapmaker_Orca-2.4.0</metadata>')
    return zipped({
        MAIN: (f"{head}<resources>{''.join(resources)}</resources>"
               f"<build>{''.join(items)}</build></model>").encode(),
        "Metadata/project_settings.config": json.dumps(
            dict(SETTINGS, **BED) if settings is None else settings).encode(),
        "Metadata/model_settings.config": (
            f"<config>{''.join(rows)}<plate><metadata key=\"plater_id\" value=\"1\"/>"
            "<metadata key=\"plater_name\" value=\"\"/>" + "".join(instances) + "</plate></config>").encode()})


def default_plate():
    return plate_3mf([("立方体", *local_cube(), CUBE_AT), ("Sphere", *ball_mesh(), BALL_AT)])


def float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def merged_stl_of(plate):
    """A binary STL of a plate's triangles as the application writes one: float32, in plate order."""
    return support.stl_bytes(bytes(80), [
        tuple(tuple(float32(value) for value in corner) for corner in triangle)
        for item in project(plate)["objects"] for triangle in item["triangles"]])


PALETTE = np.array([[230, 60, 60], [60, 200, 90], [70, 110, 230], [240, 210, 60], [200, 80, 200],
                    [80, 220, 220], [250, 150, 60], [160, 160, 160]], np.uint8)


def render_png(width=800, height=600, body=True):
    """What a viewer render looks like: a transparent frame around an opaque disc of eight sectors."""
    y, x = np.mgrid[0:height, 0:width]
    pixels = np.zeros((height, width, 4), np.uint8)
    disc = (x - width / 2) ** 2 + (y - height / 2) ** 2 < (min(width, height) / 2 - 20) ** 2
    if body:
        sector = ((np.arctan2(y - height / 2, x - width / 2) + math.pi) / (2 * math.pi) * len(PALETTE)).astype(int)
        pixels[disc, :3] = PALETTE[sector[disc] % len(PALETTE)]
        pixels[disc, 3] = 255
    out = BytesIO()
    Image.fromarray(pixels, "RGBA").save(out, "PNG")
    return out.getvalue()


def write_merge_run(folder, prefix=MERGE_PREFIX, *, stl=None, plate=None, record=None, render=None, logs=None,
                    control=BROKEN):
    """A synthetic #233 harvest in the shape the collector leaves. The record is what the case writes
    for these files: the oracle's readings of the plate and the STL, the viewer's exit codes and digests."""
    folder.mkdir(parents=True, exist_ok=True)
    plate = default_plate() if plate is None else plate
    stl = merged_stl_of(plate) if stl is None else stl
    render = render_png() if render is None else render
    work = f"C:\\coil\\runs\\{prefix}"
    texts = {"f3d-version.log": VERSION_LOG,
             "f3d-view.log": "Loading all-objects.stl : 100% [00:00/00:00]\r\n".encode(),
             "f3d-invalid.log": (f"{work}\\invalid.stl contains unsupported contents, use --skip-content-check "
                                 "to try reading it anyway\r\nNo files loaded, no rendering performed\r\n").encode()}
    parts = {"before.3mf": plate, "all-objects.stl": stl, "before.png": picture(seed=1),
             "export-dialog.png": picture(seed=2), "f3d-view.png": render, "invalid.stl": control,
             **dict(texts, **(logs or {}))}
    for part, raw in parts.items():
        (folder / f"{prefix}-{part}").write_bytes(raw)
    before, shown, rendered = (folder / f"{prefix}-{part}" for part in
                               ("before.3mf", "all-objects.stl", "f3d-view.png"))
    gaps = merged.merged_stl_expectation_gaps(before, shown, ".stl")
    try:
        geometry = merged.verify_merged_stl(before, shown)       # what the case keeps when the geometry holds
    except (OSError, ValueError):
        geometry = None
    try:
        image = verify_f3d_image(rendered)
    except (OSError, ValueError):
        image = None
    viewer = {"path": "C:/coil/tools/orca-bb-f3d/bin/f3d-console.exe",
              "version": VERSION_LOG.decode().replace("\r\n", "\n").strip(), "version_rc": 0,
              "source_sha256": sha256(stl).hexdigest(), "positive_rc": 0, "image": image,
              "output_sha256": sha256(render).hexdigest(), "negative_rc": 1, "negative_rejected": True,
              "same_bytes_as_export": True}
    gaps["可正常打开"] = merged.viewer_gaps(viewer)
    dialog = png(picture(seed=2))
    default = {"case": 233,
               "results": {clause: "PASS" if not failed else f"FAIL ({'; '.join(failed)[:400]})"
                           for clause, failed in gaps.items()},
               "fixture": {"name": FIXTURE.name, "bytes": len(FIXTURE.read_bytes()),
                           "sha256": sha256(FIXTURE.read_bytes()).hexdigest()},
               "plate": merged.plate_object_layout(before), "arranged": True,
               "export": {"item": "Export all objects as one STL", "typed_name": "all-objects",
                          "title": "Export STL file:", "directory": work, "saved_name": "all-objects.stl",
                          "saved_extension": ".stl", "file_bytes": len(stl), "file_sha256": sha256(stl).hexdigest(),
                          "dialog_image": {"width_px": dialog["width"], "height_px": dialog["height"]},
                          "dialog_closed": True, "app_alive": True},
               "expectation_gaps": gaps, "viewer": viewer,
               "editor_after_export": {"alive": True, "dialog": None}, "wall_seconds": 1.0}
    if geometry is not None:
        default["merged_geometry"] = geometry
    # `record` may be a callable that edits what the case would have written
    parts["analysis.json"] = json.dumps(record(default) if callable(record) else default, ensure_ascii=False,
                                        indent=2).encode("utf-8")
    (folder / f"{prefix}-analysis.json").write_bytes(parts["analysis.json"])
    manifest_ = [{"part": part, "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                 for part, raw in parts.items()]
    (folder / f"{prefix}-object_artifacts.json").write_text(json.dumps(manifest_, indent=1), encoding="utf-8")
    log = f"[m7x233] retained work directory: {work}\n".encode()
    (folder / f"{prefix}-case.log").write_bytes(log)
    (folder / f"{prefix}-receipt.json").write_text(json.dumps({
        "case": "m7x_233_export_merged_stl", "commit": "0" * 40, "summary": "SUMMARY: PASS=1 FAIL=0",
        "dispatched_at": "2026-11-26T00:00:00+00:00", "scenario_completed_at": "2026-11-26T00:02:00+00:00",
        "log_sha256": sha256(log).hexdigest()}), encoding="utf-8")
    return folder, prefix


def merge_refused(tmp_path, failed, **changes):
    """A run whose files differ and whose record was written for those files: the replay names `failed`."""
    folder, prefix = write_merge_run(tmp_path, **changes)
    result = merged.replay(folder, prefix)
    assert set(failed) <= set(result["export"]["failed"]), result["export"]["failed"]
    assert not all(value is True for value in result["checks"].values())
    return result


# every stand-in of the merged STL replay with the readings that own it; UNOPENABLE: the replay
# cannot even read the run
MERGE_REFUSED_BY = {
    "cube_only_export_rejected": ["stl_holds_every_plate_triangle_once", "oracle_accepts_export"],
    "sphere_only_export_rejected": ["stl_holds_every_plate_triangle_once", "oracle_accepts_export"],
    "objects_moved_together_rejected": ["stl_holds_every_plate_triangle_once", "each_object_keeps_its_place",
                                        "oracle_accepts_export"],
    "objects_moved_to_origin_rejected": ["stl_holds_every_plate_triangle_once", "each_object_keeps_its_place",
                                         "oracle_accepts_export"],
    "empty_stl_rejected": ["stl_holds_every_plate_triangle_once", "oracle_accepts_export"],
    "collapsed_export_rejected": ["stl_holds_every_plate_triangle_once", "each_object_keeps_its_place",
                                  "oracle_accepts_export"],
    "truncated_stl_rejected": UNOPENABLE,
    "shifted_export_rejected": ["stl_holds_every_plate_triangle_once", "each_object_keeps_its_place",
                                "oracle_accepts_export"],
    "blank_render_rejected": ["render_shows_a_mesh", "oracle_accepts_the_render"],
    "viewer_accepted_the_control_rejected": ["viewer_refused_the_control"],
    "viewer_read_other_bytes_rejected": ["viewer_read_the_exported_bytes"],
    "valid_control_stl_rejected": ["control_is_not_an_stl"],
    "wrong_extension_rejected": UNOPENABLE,
    "project_moved_rejected": ["stl_holds_every_plate_triangle_once", "oracle_accepts_export"],
    "manifest_mismatch_rejected": UNOPENABLE,
    "edited_analysis_rejected": ["recorded_verdict_matches_file", "oracle_accepts_export"],
}


def test_synthetic_merged_run_passes_every_reading_and_every_counterexample(tmp_path):
    folder, prefix = write_merge_run(tmp_path)
    result = merged.replay(folder, prefix)
    not_true = [key for key, value in result["checks"].items() if value is not True]
    assert not not_true, not_true
    assert set(merged.POSITIVE) <= set(result["checks"])
    assert {key for key in result["checks"] if key.endswith("_rejected")} == set(MERGE_REFUSED_BY)
    report = result["export"]
    assert (report["exported"], report["triangles"]) == ("all-objects.stl", 12 + BALL_TRIANGLES)
    assert 0 < report["worst_vertex_deviation_mm"] < 1e-5      # float32 corners against the project's


def test_merged_stl_runs_through_the_shared_driver_like_the_other_replays(tmp_path, monkeypatch):
    folder, prefix = write_merge_run(tmp_path)
    monkeypatch.setitem(ADAPTERS, "m7x_233_export_merged_stl", merged.replay)
    assert replay_receipt(folder / f"{prefix}-receipt.json")["offline_checks_passed"]
    (folder / f"{prefix}-case.log").write_bytes(b"another log\n")
    assert not replay_receipt(folder / f"{prefix}-receipt.json")["offline_checks_passed"]


@pytest.mark.parametrize("label,failed", sorted(MERGE_REFUSED_BY.items()))
def test_each_counterexample_is_refused_by_the_reading_that_owns_it(tmp_path, label, failed):
    folder, prefix = write_merge_run(tmp_path)
    how = dict(merged._stand_ins(merged._read(folder, prefix)[2]))[label]
    with copy_of(folder, prefix, **how) as (other, altered):
        if failed is UNOPENABLE:
            with pytest.raises(ValueError):
                merged._read(other, altered)
            return
        readings = merged._read(other, altered)[1]
    assert set(failed) <= set(readings["failed"]), readings["failed"]


def test_replay_reads_every_counterexample_of_the_merged_stl_on_a_temporary_copy(tmp_path, monkeypatch):
    folder, prefix = write_merge_run(tmp_path)
    reads, real = [], merged._read
    monkeypatch.setattr(merged, "_read", lambda place, pre: reads.append(place.name) or real(place, pre))
    result = merged.replay(folder, prefix)
    assert all(value is True for value in result["checks"].values())
    assert len(reads) == 17 and sum(name.startswith("replay-") for name in reads) == 16


def lumpy_ball():
    """The ball with its rings at 45 degrees pushed outwards: the same box, corners no longer on one ball."""
    vertices, faces = ball_mesh()
    segments = 16

    def ring(index):          # the poles are outside the rings; ring 1 and ring 5 sit at 45 degrees
        return -1 if index in (0, len(vertices) - 1) else (index - 1) // segments
    grown = [tuple(value * (1.01 if ring(index) in (1, 5) else 1.0) for value in vertex)
             for index, vertex in enumerate(vertices)]
    return grown, faces


@pytest.mark.parametrize("second", ["Cube", "Sphere"], ids=["second cube", "lumpy ball"])
def test_a_plate_whose_second_object_is_no_ball_is_refused_whatever_the_stl_holds(tmp_path, second):
    other = local_cube() + ((122.0, 90.0, 0.0),) if second == "Cube" else lumpy_ball() + (BALL_AT,)
    plate = plate_3mf([("立方体", *local_cube(), CUBE_AT), (second, *other)])
    result = merge_refused(tmp_path, ["plate_is_the_cube_and_a_sphere", "oracle_accepts_export"], plate=plate)
    # the STL is that plate, faithfully, and the plate is otherwise in order: only the ball reading refuses
    assert all(result["checks"][key] for key in ("stl_holds_every_plate_triangle_once", "objects_rest_on_the_bed",
                                                 "objects_apart", "objects_inside_printable_area"))


def test_a_ball_nudged_by_a_fifth_of_a_millimetre_is_refused(tmp_path):
    plate = default_plate()
    cube, ball = support.stl(merged_stl_of(plate))[1][:12], support.stl(merged_stl_of(plate))[1][12:]
    nudged = [tuple((corner[0], corner[1] + 0.2, corner[2]) for corner in triangle) for triangle in ball]
    merge_refused(tmp_path, ["stl_holds_every_plate_triangle_once", "each_object_keeps_its_place",
                             "oracle_accepts_export"], stl=support.stl_bytes(bytes(80), cube + nudged))


def test_viewer_logs_that_name_something_else_or_no_version_are_refused(tmp_path):
    merge_refused(tmp_path, ["viewer_log_names_the_export"],
                  logs={"f3d-view.log": b"Loading another-file.stl : 100%\r\n"})
    merge_refused(tmp_path, ["viewer_identified_itself", "recorded_version_is_the_log"],
                  logs={"f3d-version.log": b"some other program 1.0\r\n"})


def test_a_record_that_points_the_export_elsewhere_or_overstates_it_is_refused(tmp_path):
    merge_refused(tmp_path, ["export_targets_this_run"], record=lambda default: dict(
        default, export=dict(default["export"], directory="C:\\coil\\runs\\somewhere-else")))
    merge_refused(tmp_path, ["recorded_geometry_matches_file"], record=lambda default: dict(
        default, merged_geometry=dict(default["merged_geometry"], max_vertex_deviation_mm=0.0)))
    merge_refused(tmp_path, ["recorded_plate_matches_file"], record=lambda default: dict(default, plate={}))
    merge_refused(tmp_path, ["recorded_verdict_matches_file"], record=lambda default: dict(
        default, results={clause: "FAIL (x)" for clause in merged.CLAUSES}))


def test_stl_reader_reads_a_real_export_and_refuses_what_is_not_one():
    real = (EVIDENCE / "feishu-252-2026-11-25/74b49b23-run1-selected-object.stl").read_bytes()
    header, triangles = support.stl(real)
    assert (len(real), len(triangles)) == (1284, 24)
    assert support.box([corner for triangle in triangles for corner in triangle]) == (
        122.0, 211.300003, 122.5, 149.5, 0.0, 27.0)           # float32: 211.3 is kept as 211.300003
    assert support.stl(support.stl_bytes(bytes(80), triangles))[1] == triangles
    assert support.stl(bytes(84))[1] == []                # a header and a count of zero is an empty, whole STL
    for not_an_stl in (b"", bytes(83), BROKEN, real[:-50], real + b"\x00"):
        with pytest.raises(ValueError):
            support.stl(not_an_stl)


def moved_by(group, index, dx):
    """The group with one triangle shifted by dx along X."""
    return [tuple((corner[0] + dx, corner[1], corner[2]) for corner in triangle)
            if number == index else triangle for number, triangle in enumerate(group)]


def test_paired_matches_whatever_the_winding_and_names_what_is_missing_or_moved():
    cube = project(FIXTURE.read_bytes())["objects"][0]["triangles"]
    shuffled = [tuple(reversed(triangle)) for triangle in reversed(cube)]
    pairs, worst = support.paired(cube, shuffled)
    assert pairs == list(reversed(range(12))) and worst == 0.0
    pairs, worst = support.paired(cube, moved_by(shuffled, 4, 5e-5))
    assert pairs == list(reversed(range(12))) and math.isclose(worst, 5e-5, abs_tol=1e-9)
    assert support.paired(cube, moved_by(shuffled, 4, 5e-4))[0][7] is None      # beyond the tolerance
    assert support.paired(cube, shuffled[:11])[0][0] is None                     # a triangle left out
    assert support.paired(cube[:1] * 2, [tuple(reversed(cube[0]))])[0] == [0, None]   # a copy is not a second one
    with pytest.raises(ValueError, match="wider than the tolerance"):
        support.paired(cube[:1], shuffled[:1], tol=1e-3, cell=1e-4)


def test_render_reader_tells_a_body_from_a_blank_and_an_opaque_frame():
    body = png(render_png())["solid"]
    assert body["inside"] and 0.4 < body["fraction"] < 0.6 and body["colors"] == len(PALETTE)
    assert png(render_png(body=False))["solid"] == {"fraction": 0.0, "inside": False, "box": None, "colors": 0}
    frame = BytesIO()
    Image.fromarray(np.full((600, 800, 4), 255, np.uint8), "RGBA").save(frame, "PNG")
    assert png(frame.getvalue())["solid"]["fraction"] == 1.0 and not png(frame.getvalue())["solid"]["inside"]
    assert png(support.blank_png(200, 150))["solid"] == {"fraction": 0.0, "inside": False, "box": None, "colors": 0}
    real = png((EVIDENCE / "feishu-252-2026-11-25/74b49b23-run1-f3d-view.png").read_bytes())["solid"]
    assert real["inside"] and real["fraction"] > 0.1 and real["colors"] > 3
    assert png(picture())["solid"] is None                 # a screenshot has no alpha channel


def test_project_stand_in_log_marker_and_shared_helpers(tmp_path):
    before, after = project(default_plate()), project(support.moved_project(default_plate(), dy=20.0))
    assert [[round(p - q, 6) for p, q in zip(x["box"], y["box"])] for x, y in zip(after["objects"], before["objects"])] == [
        [0.0, 0.0, 20.0, 20.0, 0.0, 0.0]] * 2
    log = "[m7x233] retained work directory: C:\\coil\\runs\\abc\r\n[m7x233] another line\r\n"
    assert support.work_directories(log, "m7x233") == ["C:\\coil\\runs\\abc"]
    assert support.work_directories(log, "m7x244") == []
    assert support.faces([(0, 0, 0), (1, 0, 0), (0, 1, 0)]) == (((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),)
    assert support.box([(1, 2, 3), (5, 4, 2)]) == (1, 5, 2, 4, 2, 3)
    flattered = json.loads(support.flattering(b'{"case": 233, "results": {"a": "FAIL (x)"}}', ("a", "b")))
    assert flattered["results"] == {"a": "PASS", "b": "PASS"} and flattered["expectation_gaps"] == {"a": [], "b": []}
    pictures = {"before.png": picture(seed=1), "export-dialog.png": picture(seed=2)}
    size = png(pictures["export-dialog.png"])
    shown = support.screenshots(pictures, {"dialog_image": {"width_px": size["width"], "height_px": size["height"]}},
                                tuple(pictures), "export-dialog.png")
    assert shown == {"screenshots_are_pictures": True, "dialog_picture_matches_record": True}
    blanked = support.screenshots(dict(pictures, **{"export-dialog.png": picture(blank=True)}), {},
                                  tuple(pictures), "export-dialog.png")
    assert blanked == {"screenshots_are_pictures": False, "dialog_picture_matches_record": False}
    folder, prefix = write_merge_run(tmp_path)
    assert support.refused(merged._read, merged.POSITIVE, folder, prefix,
                           {"f3d-view.png": support.blank_png(800, 600)})
    assert not support.refused(merged._read, merged.POSITIVE, folder, prefix)


# --- Feishu #227: the imported STL ------------------------------------------------
# No green #227 run exists yet, so the run is assembled here from what the application really wrote
# for #244, which imports the same cube_20mm.stl through the same File > Import row: the STL, the
# template the run started from and the project saved after the import. The moved and the turned
# project are those bytes with the instance transform rewritten; the screenshots, the viewer-side
# record and the case log are written here.

from pathlib import PureWindowsPath

from import_stl_oracle import stl_filter_label, verify_imported, verify_moved, verify_rotated
from tools import replay_import_stl as imported_replay

IMPORT_PREFIX = "cf3a5219-run1"
REAL_244 = EVIDENCE / "multi-244-254-2026-11-25/win11-test/e7ba1cd2-run1-"      # a real import by the application
RUN_244 = r"C:\coil\orca-blackbox-v3-r1\artifacts\feishu-object-cases\244\run-bspxyqai"   # the directory it named
CHOOSER_TYPES = [{"selected": -1, "items": []},
                 {"selected": 0, "items": ["Supported files (*.3mf *.step *.stl *.svg *.obj *.amf)",
                                           "3MF files (*.3mf)", "STL files (*.stl)"]},
                 {"selected": -1, "items": []}]
IMPORT_ROWS = [{"label": "Import 3MF/STL/STEP/SVG/OBJ/AMF...", "enabled": True},
               {"label": "Import Zip Archive", "enabled": True},
               {"label": "Import Configs", "enabled": True}]
SOURCE, START, IMPORTED = imported_replay.SOURCE, imported_replay.START, imported_replay.IMPORTED
MOVED, TURNED = imported_replay.MOVED, imported_replay.TURNED


def real_import() -> dict:
    """The bytes the application wrote for a real import of cube_20mm.stl: the STL, the template the
    run started from and the project saved after the import."""
    return {part: Path(f"{REAL_244}{part}").read_bytes() for part in (SOURCE, START, IMPORTED)}


def moved_copy(project) -> bytes:
    return support.with_item_transform(
        project, support.compose(support.shift(10.0, 0.0, 0.0), support.item_transform(project)))


def turned_copy(project, degrees=45.0, move=10.0) -> bytes:
    """The project with its only object turned about the vertical axis through the moved object's centre."""
    x0, x1, y0, y1, _, _ = support.project(project)["objects"][0]["box"]
    centre = ((x0 + x1) / 2 + move, (y0 + y1) / 2, 0.0)
    about = support.compose(support.compose(support.shift(*centre), support.turn(degrees)),
                            support.shift(-centre[0], -centre[1], -centre[2]))
    return support.with_item_transform(project, support.compose(about, support.item_transform(project)))


def write_import_run(folder, prefix=IMPORT_PREFIX, *, parts=None, record=None, log_lines=None):
    """A #227 harvest in the shape the collector leaves. The record is what the case writes for these
    files: the oracle's readings of the three projects and what the chooser showed."""
    folder.mkdir(parents=True, exist_ok=True)
    pieces = real_import()
    pieces[MOVED] = moved_copy(pieces[IMPORTED])
    pieces[TURNED] = turned_copy(pieces[MOVED], move=0.0)       # turned where the move left it
    shots = dict(zip(imported_replay.PICTURES, (picture(seed=index) for index in range(8))))
    files = {**pieces, **shots, **(parts or {})}
    for part, raw in files.items():
        (folder / f"{prefix}-{part}").write_bytes(raw)
    source, saved, after, final = (folder / f"{prefix}-{part}" for part in (SOURCE, IMPORTED, MOVED, TURNED))
    (folder / "plain").mkdir(exist_ok=True)     # the oracle wants the STL under the name the case gave it
    plain = folder / "plain" / SOURCE
    plain.write_bytes(files[SOURCE])
    shown = json.loads(Path(f"{REAL_244}analysis.json").read_text(encoding="utf-8-sig"))["chooser"]
    filters = [item for group in CHOOSER_TYPES for item in group["items"]]
    size = png(shots["chooser.png"])
    chooser = {"import_rows": IMPORT_ROWS, "row": IMPORT_ROWS[0]["label"], "title": shown["title"],
               "labels": shown["labels"], "types": CHOOSER_TYPES,
               "image": {"width_px": size["width"], "height_px": size["height"]},
               "entered": str(PureWindowsPath(RUN_244) / SOURCE), "dialog_closed": True}
    chooser["stl_filter"] = stl_filter_label([chooser["title"], *chooser["labels"], *filters])
    settings = support.project(pieces[START])["settings"]
    readings = {}
    for key, reading in (("imported", lambda: verify_imported(saved, plain)),
                         ("moved", lambda: verify_moved(saved, after)),
                         ("rotated", lambda: verify_rotated(after, final))):
        try:
            readings[key] = reading()
        except (OSError, ValueError):
            break                      # the case stops at the first reading that fails
    default = {"case": 227, "source": {"name": SOURCE, "bytes": len(files[SOURCE]),
                                       "sha256": sha256(files[SOURCE]).hexdigest()},
               "results": {clause: "PASS" for clause in imported_replay.CLAUSES},
               "sidebar": {"imported": ["Objects", "cube_20mm"]}, "import_fraction": 0.004,
               "initial_printer": {"model": settings.get("printer_model"),
                                   "profile": settings.get("printer_settings_id")},
               "selection": {phase: {"menu": "Select All", "panel_words": [
                   "Plate", "plate,", "object", "cube_20mm.stl", "default", "Outside"]} for phase in imported_replay.PHASES},
               "keys": dict(imported_replay.KEYS),
               "object_list_name": ["cube_20mm"], "editor_at_end": {"alive": True, "dialog": None},
               **readings, "chooser": chooser}
    files["analysis.json"] = json.dumps(record(default) if callable(record) else default, ensure_ascii=False,
                                        indent=2).encode("utf-8")
    (folder / f"{prefix}-analysis.json").write_bytes(files["analysis.json"])
    (folder / f"{prefix}-object_artifacts.json").write_text(json.dumps(
        [{"part": part, "bytes": len(raw), "sha256": sha256(raw).hexdigest()} for part, raw in files.items()],
        indent=1), encoding="utf-8")
    lines = [f"[m7x227] retained work directory: {RUN_244}",
             f"[m7x227] chooser {chooser['title']!r}: labels {chooser['labels']!r}, types {filters!r}",
             "[m7x227] sidebar after the import: ['Objects', 'cube_20mm']",
             f"[m7x227] imported: {readings.get('imported')!r}",
             "[m7x227] moved: {'centroid': [900, 500], 'click': [900, 500], 'click_method': 'physical', 'key': '0x27'}",
             "[m7x227] rotated: {'centroid': [950, 500], 'click': [950, 500], 'click_method': 'physical', "
             "'key': '0x52'}"] if log_lines is None else log_lines
    log = ("\n".join(lines) + "\n").encode()
    (folder / f"{prefix}-case.log").write_bytes(log)
    (folder / f"{prefix}-receipt.json").write_text(json.dumps({
        "case": "m7x_227_import_stl", "commit": "0" * 40, "summary": "SUMMARY: PASS=1 FAIL=0",
        "dispatched_at": "2026-11-26T00:00:00+00:00", "scenario_completed_at": "2026-11-26T00:03:00+00:00",
        "log_sha256": sha256(log).hexdigest()}), encoding="utf-8")
    return folder, prefix


def import_refused(tmp_path, failed, **changes):
    """A run whose files differ and whose record was written for those files: the replay names `failed`."""
    folder, prefix = write_import_run(tmp_path, **changes)
    result = imported_replay.replay(folder, prefix)
    assert set(failed) <= set(result["import"]["failed"]), result["import"]["failed"]
    assert not all(value is True for value in result["checks"].values())
    return result


# every stand-in of the import replay with the readings that own it; UNOPENABLE: the replay cannot
# even read the run
IMPORT_REFUSED_BY = {
    "start_replaced_rejected": ["start_is_the_u1_template_with_its_cube"],
    "empty_plate_rejected": ["imported_once", "imported_is_the_stl_upright"],
    "thirty_mm_cube_rejected": ["source_is_a_binary_20_mm_cube", "imported_is_20_mm"],
    "two_objects_rejected": ["imported_once"],
    "object_off_the_plate_rejected": ["imported_on_the_plate"],
    "imported_off_the_bed_rejected": ["imported_on_the_bed"],
    "move_reversed_rejected": ["moved_is_the_import_10_mm_along_x"],
    "move_along_y_rejected": ["moved_is_the_import_10_mm_along_x"],
    "moved_off_the_bed_rejected": ["moved_on_the_bed"],
    "turn_left_out_rejected": ["rotated_is_the_moved_turned_45_degrees"],
    "turn_about_x_rejected": ["rotated_is_the_moved_turned_45_degrees", "rotated_on_the_bed"],
    "template_as_import_rejected": ["imported_is_the_stl_upright", "imported_is_20_mm",
                                    "imported_named_after_the_file", "imported_points_at_this_runs_file"],
    "another_runs_file_rejected": ["imported_points_at_this_runs_file"],
    "source_not_a_cube_rejected": ["source_is_a_binary_20_mm_cube", "imported_is_the_stl_upright"],
    "blank_screenshot_rejected": ["pictures_are_pictures"],
    "invented_filter_rejected": ["chooser_record_offers_stl"],
    "chooser_entered_another_file_rejected": ["chooser_entered_this_runs_file"],
    "manifest_mismatch_rejected": UNOPENABLE,
    "edited_analysis_rejected": ["recorded_readings_match_files"],
    "selection_names_another_object_rejected": ["selection_names_the_import"],
    "sidebar_names_nothing_rejected": ["sidebar_names_the_import"],
    "recorded_box_edited_rejected": ["recorded_boxes_match_projects"],
    "another_key_pressed_rejected": ["keys_are_the_procedure_s"],
}


def test_import_run_passes_every_reading_and_every_counterexample(tmp_path):
    folder, prefix = write_import_run(tmp_path)
    result = imported_replay.replay(folder, prefix)
    not_true = [key for key, value in result["checks"].items() if value is not True]
    assert not not_true, not_true
    # every reading the replay names is produced, and every counterexample has a label of its own
    assert set(imported_replay.POSITIVE) == set(result["checks"]) - set(IMPORT_REFUSED_BY)
    report = result["import"]
    assert (report["imported"]["name"], report["imported"]["box_mm"]) == (
        "cube_20mm.stl", (125.5, 145.5, 126.0, 146.0, 0.0, 20.0))
    assert report["moved"]["box_mm"] == (135.5, 155.5, 126.0, 146.0, 0.0, 20.0)
    assert report["rotated"]["box_mm"] == (131.357864, 159.642136, 121.857864, 150.142136, 0.0, 20.0)
    assert set(report["screen_changes"]) == {"select", "move", "reselect", "turn"}


def test_import_runs_through_the_shared_driver_like_the_other_replays(tmp_path, monkeypatch):
    folder, prefix = write_import_run(tmp_path)
    monkeypatch.setitem(ADAPTERS, "m7x_227_import_stl", imported_replay.replay)
    assert replay_receipt(folder / f"{prefix}-receipt.json")["offline_checks_passed"]
    (folder / f"{prefix}-case.log").write_bytes(b"another log\n")
    assert not replay_receipt(folder / f"{prefix}-receipt.json")["offline_checks_passed"]


@pytest.mark.parametrize("label,failed", sorted(IMPORT_REFUSED_BY.items()))
def test_each_import_counterexample_is_refused_by_the_reading_that_owns_it(tmp_path, label, failed):
    folder, prefix = write_import_run(tmp_path)
    how = dict(imported_replay._stand_ins(imported_replay._read(folder, prefix)[2][0]))[label]
    with copy_of(folder, prefix, **how) as (other, altered):
        if failed is UNOPENABLE:
            with pytest.raises(ValueError):
                imported_replay._read(other, altered)
            return
        readings = imported_replay._read(other, altered)[1]
    assert set(failed) <= set(readings["failed"]), readings["failed"]


def test_replay_reads_every_counterexample_of_the_import_on_a_temporary_copy(tmp_path, monkeypatch):
    folder, prefix = write_import_run(tmp_path)
    reads, real = [], imported_replay._read
    monkeypatch.setattr(imported_replay, "_read", lambda place, pre: reads.append(place.name) or real(place, pre))
    result = imported_replay.replay(folder, prefix)
    assert all(value is True for value in result["checks"].values())
    assert len(reads) == 24 and sum(name.startswith("replay-") for name in reads) == 23


@pytest.mark.parametrize("degrees", [30.0, 90.0], ids=["30 degrees", "90 degrees: the cube onto itself"])
def test_a_turn_that_is_not_45_degrees_is_refused(tmp_path, degrees):
    pieces = real_import()
    import_refused(tmp_path, ["rotated_is_the_moved_turned_45_degrees", "oracle_accepts_the_three_projects"],
                    parts={TURNED: turned_copy(pieces[IMPORTED], degrees)})


def test_a_record_that_differs_from_the_files_is_refused(tmp_path):
    import_refused(tmp_path, ["recorded_readings_match_files"], record=lambda default: dict(
        default, moved=dict(default["moved"], delta_mm=[10.0, 1.0, 0.0])))
    import_refused(tmp_path, ["recorded_source_matches_file"], record=lambda default: dict(
        default, source=dict(default["source"], sha256="0" * 64)))
    # the oracle forgives one misread character in a name; this one is three away from the import's
    import_refused(tmp_path, ["object_list_names_the_import"], record=lambda default: dict(
        default, object_list_name=["box_20mm"]))
    import_refused(tmp_path, ["recorded_verdict_matches_readings"], record=lambda default: dict(
        default, results={"可旋转": "FAIL"}))
    import_refused(tmp_path, ["chooser_picture_matches_record"], parts={"chooser.png": picture(700, 450)})


def test_the_sidebar_selection_printer_and_key_records_are_held_against_the_run(tmp_path):
    # the oracle forgives one misread character in a name: such a record still passes whole
    misread = lambda default: dict(  # noqa: E731
        default, sidebar={"imported": ["Objects", "cube_20mn"]},
        selection={phase: dict(default["selection"][phase], panel_words=["Plate", "object", "cube 20mm"])
                   for phase in imported_replay.PHASES})
    passed = imported_replay.replay(*write_import_run(tmp_path, record=misread))["checks"]
    assert all(value is True for value in passed.values()), sorted(k for k, v in passed.items() if v is not True)
    import_refused(tmp_path, ["printer_as_recorded"], record=lambda default: dict(
        default, initial_printer=dict(default["initial_printer"], profile="Snapmaker U1 (0.4 nozzle)")))
    import_refused(tmp_path, ["editor_left_running"], record=lambda default: dict(
        default, editor_at_end={"alive": True, "dialog": "Save Sliced file as:"}))
    # the recorded boxes are read against the projects a second time, without the oracle
    import_refused(tmp_path, ["recorded_boxes_match_projects"], record=lambda default: dict(
        default, imported=dict(default["imported"], dimensions_mm=[20.0, 20.0, 20.1])))


def test_a_case_log_that_never_showed_the_filter_or_another_directory_is_refused(tmp_path):
    folder, prefix = write_import_run(tmp_path)
    lines = (folder / f"{prefix}-case.log").read_text(encoding="utf-8").splitlines()
    without = [line for line in lines if not line.startswith("[m7x227] chooser")]
    import_refused(tmp_path, ["filter_text_is_in_the_case_log"], log_lines=without)
    elsewhere = [line.replace(RUN_244, RUN_244 + "-other") for line in lines]
    import_refused(tmp_path, ["imported_points_at_this_runs_file", "chooser_entered_this_runs_file"],
                   log_lines=elsewhere)


def test_import_readings_hold_on_what_the_application_really_wrote():
    pieces = real_import()
    source = support.stl(pieces[SOURCE])[1]
    assert imported_replay._cube(pieces[SOURCE]) and len(source) == 12
    thirty = (EVIDENCE / "feishu-250-251-2026-11-25/row-251-hyperv/1149a497-source-30mm.stl").read_bytes()
    assert not imported_replay._cube(thirty) and not imported_replay._cube(b"not an STL")
    start, saved = support.project(pieces[START]), support.project(pieces[IMPORTED])
    assert imported_replay._start(start, support.project((ROOT / "fixtures/agent_layer_cube.3mf").read_bytes())) == {
        "start_is_the_u1_template_with_its_cube": True}
    readings, item = imported_replay._imported(saved, source, [RUN_244])
    assert all(readings.values()) and item["source_file"] == str(PureWindowsPath(RUN_244) / SOURCE)
    assert not imported_replay._imported(saved, source, [RUN_244 + "-another"])[0]["imported_points_at_this_runs_file"]
    # the saved project must not pass for the import itself: its cube is the template's, 27 mm
    assert not all(imported_replay._imported(start, source, [RUN_244])[0].values())
    # a real move by the application (#201: the cube 10 mm along X)
    row = EVIDENCE / "feishu-140-201-202-2026-11-25/row-201-hyperv"
    before, after = (support.project((row / f"1216dc9e-run1-{part}-save.3mf").read_bytes()) for part in ("before", "after"))
    assert imported_replay._moved_step(before, after) == {
        "moved_once_on_the_plate": True, "moved_is_the_import_10_mm_along_x": True, "moved_on_the_bed": True}
    assert not imported_replay._moved_step(after, before)["moved_is_the_import_10_mm_along_x"]


def test_transform_helpers_and_project_edits():
    pieces = real_import()
    raw, moved = pieces[IMPORTED], moved_copy(pieces[IMPORTED])
    assert support.item_transform(raw) == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 135.5, 136.0, 10.0)
    assert support.compose(support.shift(1, 2, 3), support.shift(10, 0, 0)) == support.UNIT[:9] + (11.0, 2.0, 3.0)
    assert support.compose(support.grow(2.0), support.shift(10, 0, 0)) == (2.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 2.0, 20.0, 0.0, 0.0)
    cosine, sine = math.cos(math.pi / 2), math.sin(math.pi / 2)
    assert all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(support.turn(90.0), (cosine, sine, 0.0, -sine, cosine, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)))
    assert support.project(support.with_item_transform(raw, support.item_transform(raw)))["objects"] == support.project(raw)["objects"]
    # a turn of 90 degrees puts the cube back on itself; 45 degrees widens its footprint
    assert support.project(turned_copy(raw, 90.0, move=0.0))["objects"][0]["box"] == support.project(raw)["objects"][0]["box"]
    assert support.project(turned_copy(raw))["objects"][0]["triangles"] != support.project(moved)["objects"][0]["triangles"]
    assert support.at_origin(support.project(moved)["objects"][0]) == support.at_origin(support.project(raw)["objects"][0])

    def rename(root):
        root.find("object/metadata[@key='name']").set("value", "renamed")

    def drop(root):
        root.find(f"{CORE}build").clear()

    assert support.project(support.with_settings(raw, rename))["objects"][0]["name"] == "renamed"
    assert support.project(support.with_model(raw, drop))["objects"] == []
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert support.printable_area({"printable_area": ["0x0", "10x0", "10x10", "0x10"]}) == square
    assert support.printable_area({"printable_area": ["0 0", "10 0", "10 10", "0 10"]}) == square
    assert support.printable_area({"printable_area": ["0x0", "10x0"]}) is None and support.printable_area({}) is None
    assert support.in_polygon(square, (5, 5)) and not support.in_polygon(square, (15, 5))
    assert support.in_polygon(square[::-1], (5, 5)) and support.in_polygon(square, (0, 0))     # either way round, edge included
    state, (item,) = support.project(raw), support.project(raw)["objects"]
    assert support.on_the_bed(state["settings"], item)
    assert not support.on_the_bed(state["settings"], dict(item, box=(125.5, 145.5, 126.0, 146.0, 5.0, 25.0)))
    assert not support.on_the_bed(state["settings"], dict(item, box=(265.5, 285.5, 226.0, 246.0, 0.0, 20.0)))
    assert not support.on_the_bed(state["settings"], dict(item, box=(125.5, 145.5, 126.0, 146.0, 0.0, 300.0)))
