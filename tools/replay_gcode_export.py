"""Recheck Feishu #236's exported G-code from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
The G-code is then read three times: by tests/export_io_oracle.py, by the
same oracle's footprint reading against the project that was sliced, and by
the independent reader in tests/file_io_replay_support.py. The last ties the
file to the run: its configuration must equal the sliced project's settings,
its layer schedule must fit the object's height, its extrusion must lie over
the object, and the saved project must be the standard cube fixture by
content. What analysis.json records may not outrun those readings. Last, each
counterexample of the row is stood in for a harvested part on a temporary
copy of the run and must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from export_io_oracle import gcode_checks, gcode_export_facts, gcode_expectation_gaps, gcode_footprint
from file_io_replay_support import (LAYER, MARKS, PRINTED, as_recorded, fan_off, flattering, gcode, head, heat_off,
                                    heat_on, paired)
from file_io_replay_support import manifest, moved_project, png, project, refused, screenshots

CASE = 236
FIXTURE = ROOT / "fixtures" / "feishu_std_cube.3mf"
PICTURES = ("sliced.png", "export-dialog.png")
CLAUSES = ("生成 .gcode 文件", "含起始/结束 G-code", "无空文件", "层命令连续")
# the exported configuration must say these exactly as the sliced project does
TIED = ("layer_height", "initial_layer_print_height", "printer_model", "printer_settings_id", "print_settings_id",
        "print_sequence", "brim_type", "gcode_flavor", "nozzle_diameter", "filament_type")
# the sliced project must share these with the fixture it was loaded from
FROM_FIXTURE = ("layer_height", "initial_layer_print_height", "printer_model", "print_settings_id",
                "printer_settings_id", "nozzle_diameter", "filament_type")
SOURCE_SUFFIX = "(" + FIXTURE.name + ")"     # the app appends the opened file's name to every preset ID it saves
GENERATOR = re.compile(r"Snapmaker Orca \d+\.\d+\.\d+")
EDGE_MM = 1.0     # an outer wall's centre line ends this far inside its object's footprint at most
STRUCTURE = ("blocks_complete_and_ordered", "generated_by_snapmaker_orca", "layers_present",
             "declared_layer_count_agrees", "layer_numbers_run_from_1", "layer_z_present_and_nondecreasing",
             "start_gcode_present", "end_gcode_after_last_extrusion", "trailer_notes_present",
             "every_layer_extrudes", "config_block_filled", "text_is_intact")
TIES = ("printed_objects_are_saved_objects", "extrusion_lies_on_the_objects", "layer_schedule_matches_object_height",
        "config_matches_sliced_project", "saved_project_is_the_fixture")
CLAIMS = ("recorded_hashes_match_file", "recorded_verdict_matches_file", "recorded_case_and_fixture",
          "oracle_accepts_export", "oracle_locates_the_extrusion_on_the_objects",
          "recorded_footprint_matches_file")
POSITIVE = ("gcode_artifact_is_dot_gcode", "manifest_sizes_and_sha256_match", *STRUCTURE, *TIES, *CLAIMS,
            "screenshots_are_pictures", "dialog_picture_matches_record")


@lru_cache(maxsize=1)
def _fixture():
    return FIXTURE.read_bytes()


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_setting(value, emitted):
    """A project setting against the text the G-code carries; a list is joined with ',' or ';' there."""
    if isinstance(value, list):
        return [part.strip().strip('"') for part in re.split(r"[;,]", emitted)] == [str(item) for item in value]
    return emitted.strip().strip('"') == str(value)


def _structure(plate):
    """What the file says about itself: blocks, layers, the commands around them and its configuration."""
    marks = plate["markers"]
    once = all(len(marks[mark]) == 1 for mark in MARKS)
    ordered = False
    if once:
        header, executable, closed, block = (marks[mark][0] for mark in (MARKS[1], MARKS[2], MARKS[3], MARKS[4]))
        first = plate["layers"][0]["line"] if plate["layers"] else None
        ordered = (marks[MARKS[0]] == [1] and header < executable and (first is None or executable < first)
                   and (first is None or first < closed) and (first is not None or executable < closed)
                   and closed < block and block < marks[MARKS[5]][0])
    start, end, trailer, heights = plate["start_commands"], plate["after_last_extrusion"], plate["trailer"], plate["z"]
    layers = plate["layer_count"]
    return {
        "blocks_complete_and_ordered": once and ordered and plate["after_config"] == [],
        "generated_by_snapmaker_orca": bool(GENERATOR.match(plate["generator"] or "")),
        "layers_present": layers > 0,
        "declared_layer_count_agrees": bool(plate["declared"]) and all(
            values == [layers] for values in plate["declared"].values()),
        "layer_numbers_run_from_1": plate["layer_numbers"] == list(range(1, layers + 1)),
        "layer_z_present_and_nondecreasing": layers > 0 and None not in heights and all(
            b >= a for a, b in zip(heights, heights[1:])),
        "start_gcode_present": any(heat_on(code) for code in start) and any(
            head(code) in ("G28", "PRINT_START") for code in start),
        "end_gcode_after_last_extrusion": any(
            fan_off(code) or heat_off(code) or head(code) == "PRINT_END" for code in end),
        "trailer_notes_present": any(line.startswith("; filament used") for line in trailer) and any(
            line.startswith("; estimated printing time") for line in trailer),
        "every_layer_extrudes": layers > 0 and plate["layers_without_extrusion"] == 0,
        "config_block_filled": plate["config_lines"] >= 20,
        "text_is_intact": plate["bytes"] > 0 and plate["replacement_chars"] == 0,
    }


def _printed(saved, printed):
    """The objects of the saved project that carry the names the G-code prints, if they fill one plate."""
    groups = {}
    for item in saved["objects"]:
        groups.setdefault(item["plate"], []).append(item["name"])
    matching = [names for names in groups.values() if sorted(names) == printed]
    return matching == [printed], [item for item in saved["objects"] if item["name"] in printed]


def _ties(plate, saved, fixture, suffix=SOURCE_SUFFIX):
    """The G-code against the project that was sliced, and that project against the fixture. `suffix`
    is what the app appended to a preset ID: the name of the file the fixture was opened as."""
    settings, config, heights = saved["settings"], plate["config"], plate["z"]
    named, objects = _printed(saved, plate["object_names"])
    height, first = _number(settings.get("layer_height")), _number(settings.get("initial_layer_print_height"))
    schedule = False
    if named and heights and None not in heights and height and first:
        # the top layer ends within half a layer of the object's top; without a custom profile the steps are even
        top = max(item["box"][5] for item in objects)
        even = not settings.get("layer_height_profile")
        schedule = (abs(heights[0] - first) <= 1e-6 and top - height < heights[-1] <= top + height / 2 + 1e-6
                    and (not even or abs(heights[-1] - heights[0] - (len(heights) - 1) * height) <= 1e-4 * len(heights)))
    box, footprints = plate["extrusion_box"], [item["box"] for item in objects]
    # a box is (xmin, xmax, ymin, ymax, zmin, zmax): the extrusion must reach within EDGE_MM of each side
    covers = named and box is not None and all(
        box[0] <= side[0] + EDGE_MM and box[1] <= side[2] + EDGE_MM
        and box[2] >= side[1] - EDGE_MM and box[3] >= side[3] - EDGE_MM for side in footprints)
    return {
        "printed_objects_are_saved_objects": named,
        "extrusion_lies_on_the_objects": covers,
        "layer_schedule_matches_object_height": schedule,
        "config_matches_sliced_project": plate["config_lines"] > 0 and all(
            len(config.get(key, [])) == 1 and _same_setting(settings.get(key), config[key][0]) for key in TIED),
        "saved_project_is_the_fixture": _same_shape(saved, fixture) and all(
            _as_loaded(saved["settings"].get(key), suffix) == _as_loaded(fixture["settings"].get(key), suffix)
            for key in FROM_FIXTURE),
    }


def _as_loaded(value, suffix=SOURCE_SUFFIX):
    """A setting before the app appended the opened file's name to a preset ID."""
    if isinstance(value, str) and value.endswith(suffix):
        return value[:-len(suffix)]
    return value


SHAPE_TOL = 1e-4     # the application writes a mesh it loaded again with differences in its last digits


def _same_shape(saved, fixture):
    """Whether two projects hold the same objects: as many of each name, and every triangle of each
    one within a ten-thousandth of a millimetre of one of the other's. A sphere the application
    saved again differs from its fixture by a micron; a moved or resized object is told apart just
    as it is by exact equality."""
    names = sorted(item["name"] for item in saved["objects"])
    if names != sorted(item["name"] for item in fixture["objects"]):
        return False
    for name in set(names):
        mine = [triangle for item in saved["objects"] if item["name"] == name for triangle in item["triangles"]]
        its = [triangle for item in fixture["objects"] if item["name"] == name for triangle in item["triangles"]]
        pairs, _ = paired(its, mine, SHAPE_TOL)
        if len(mine) != len(its) or None in pairs:
            return False
    return True


def _footprint(path, name, project):
    """The oracle's reading of where the G-code deposits material, read under the name the case gave
    the file (a harvest keeps it under the run's prefix), and kept as the case keeps it when the
    oracle cannot read it."""
    try:
        reading = gcode_footprint(path, project)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "checks": {"footprint_unreadable": False}}
    reading["file_name"] = name
    return reading


def _same(recorded, again):
    """Whether two readings agree where both have a key: a dictionary is compared key for key by what
    both hold, anything else must be equal. A dictionary on one side only against more than nothing
    on the other agrees to nothing."""
    if isinstance(recorded, dict) and isinstance(again, dict):
        if not recorded or not again:
            return recorded == again
        return all(_same(value, again[key]) for key, value in recorded.items() if key in again)
    return recorded == again


def _agrees(recorded, again):
    """Whether what the record holds of the footprint comes out the same from the files, key for key
    where both have the key: the oracle may have learned a key since the run, but nothing the record
    holds may differ from the file. A record that shares no key with the reading agrees to nothing."""
    again = as_recorded(again)
    shared = set(recorded) & set(again) if isinstance(recorded, dict) else set()
    return bool(shared) and _same(recorded, again)


def _claims(analysis, name, raw, digest, facts, footprint):
    """What the GUI recorded, held against the files: a recorded verdict cannot outrun the readings."""
    export, recorded = analysis.get("export"), analysis.get("gcode")
    results, gaps = analysis.get("results"), analysis.get("expectation_gaps")
    known = all(isinstance(part, dict) for part in (export, recorded, results, gaps))
    if known:
        recomputed = gcode_expectation_gaps(facts, export.get("saved_extension"), footprint)
        verdict = (all(results.get(clause) == "PASS" for clause in CLAUSES) and gaps == recomputed
                   and not any(recomputed.values()))
    else:
        verdict = False
    fixture = _fixture()
    return {
        "recorded_hashes_match_file": known and export.get("file_sha256") == digest
        and export.get("file_bytes") == len(raw) and recorded.get("sha256") == digest
        and export.get("saved_name") == name and export.get("saved_extension") == ".gcode",
        "recorded_verdict_matches_file": verdict,
        "recorded_case_and_fixture": analysis.get("case") == CASE and analysis.get("fixture") == {
            "name": FIXTURE.name, "bytes": len(fixture), "sha256": sha256(fixture).hexdigest()},
        # the oracle's own reading of the file, of its layers and of where it prints
        "oracle_accepts_export": all(gcode_checks(facts).values()),
        "oracle_locates_the_extrusion_on_the_objects": bool(footprint["checks"])
        and all(footprint["checks"].values()),
        # a record from before the case kept the footprint has no such entry to hold against it
        "recorded_footprint_matches_file": "footprint" not in analysis or _agrees(analysis["footprint"], footprint),
    }


def _pictures(raw, analysis):
    """The retained screenshots are pictures with something in them; the dialog one has the recorded size."""
    export = analysis.get("export")
    return screenshots(raw, export if isinstance(export, dict) else None, PICTURES, "export-dialog.png")


def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings, the raw artifacts and the name of the exported file."""
    entries = manifest(directory, prefix)
    exported = [entry["part"] for entry in entries if entry["part"].lower().endswith(".gcode")]
    if len(exported) != 1:
        raise ValueError(f"expected one .gcode part, found {[entry['part'] for entry in entries]}")
    name = exported[0]
    try:
        paths = {part: verified_part(directory, prefix, entries, part)
                 for part in ("analysis.json", "before.3mf", name, *PICTURES)}
        raw = {part: path.read_bytes() for part, path in paths.items()}
    except OSError as exc:
        raise ValueError(f'a listed part could not be read ({type(exc).__name__})') from exc
    analysis = json.loads(raw["analysis.json"].decode("utf-8-sig"))
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    saved, fixture, plate = project(raw["before.3mf"]), project(_fixture()), gcode(raw[name])
    facts, digest = gcode_export_facts(paths[name]), sha256(raw[name]).hexdigest()
    footprint = _footprint(paths[name], name, paths["before.3mf"])
    checks = {"gcode_artifact_is_dot_gcode": name.endswith(".gcode"), "manifest_sizes_and_sha256_match": True,
              **_structure(plate), **_ties(plate, saved, fixture),
              **_claims(analysis, name, raw[name], digest, facts, footprint), **_pictures(raw, analysis)}
    report = {"exported": name, "bytes": len(raw[name]), "sha256": digest, "generator": plate["generator"],
              "application": saved["application"], "layers": plate["layer_count"], "z_first": plate["z"][:1],
              "z_last": plate["z"][-1:], "declared": plate["declared"], "object_names": plate["object_names"],
              "object_box_mm": [item["box"] for item in saved["objects"]], "extrusion_box_mm": plate["extrusion_box"],
              "start_evidence": [code for code in plate["start_commands"] if heat_on(code) or head(code) in ("G28", "PRINT_START")][:4],
              "end_evidence": [code for code in plate["after_last_extrusion"] if fan_off(code) or heat_off(code) or head(code) == "PRINT_END"][:4],
              "oracle": {key: facts[key] for key in ("layer_count", "layer_marker", "z_first", "z_last", "blocks",
                                                     "declared_layer_counts", "config_lines")},
              "oracle_footprint": {key: footprint.get(key) for key in ("max_excursion_mm", "allowances_mm", "checks")},
              "failed": [key for key in POSITIVE if not checks[key]]}
    return checks, report, raw, name


# --- counterexamples --------------------------------------------------------------

def _join(lines):
    return "\n".join(lines).encode("utf-8")


def _through(lines, marker):
    """The file as it stood up to and including the first `marker`."""
    end = next((index for index, line in enumerate(lines) if line.strip() == marker), len(lines) - 1)
    return lines[:end + 1]


def _before(lines, marker):
    """The file as it stood just before the first `marker`."""
    end = next((index for index, line in enumerate(lines) if line.strip() == marker), len(lines))
    return lines[:end]


def _layer_starts(lines):
    return [index for index, line in enumerate(lines) if LAYER.fullmatch(line.strip())]


def _without_layer(lines, index):
    starts = _layer_starts(lines)
    return lines[:starts[index]] + lines[starts[index + 1]:]


def _totals(lines, total):
    """Every declared layer total rewritten, as a forger leaves them after taking layers out."""
    out = []
    for line in lines:
        code = line.strip()
        if re.fullmatch(r";\s*total layer number:\s*\d+", code):
            line = f"; total layer number: {total}"
        elif re.fullmatch(r";\s*total layers count\s*=\s*\d+", code):
            line = f"; total layers count = {total}"
        else:
            line = re.sub(r"TOTAL_LAYER=\d+", f"TOTAL_LAYER={total}", line)
        out.append(line)
    return out


def _without_end(lines, last):
    """The end G-code taken out: nothing that switches the printer off is left after the last extruding move."""
    out = []
    for index, line in enumerate(lines):
        code = line.strip().partition(";")[0].strip()
        gone = last is not None and index >= last and (fan_off(code) or heat_off(code) or head(code) == "PRINT_END")
        out.append("" if gone else line)
    return out


def _shifted(raw, dx=40.0, dy=0.0):
    """The same print moved sideways: complete in itself, but no longer over the saved object."""
    out = []
    for line in raw.decode("utf-8").split("\n"):
        code, sep, comment = line.partition(";")
        if re.match(r"\s*G[01](?![0-9])", code):
            code = re.sub(r"\bX(-?[\d.]+)", lambda found: f"X{float(found.group(1)) + dx:.3f}", code)
            code = re.sub(r"\bY(-?[\d.]+)", lambda found: f"Y{float(found.group(1)) + dy:.3f}", code)
        out.append(code + sep + comment)
    return _join(out)


def _renamed(raw):
    """The same print attributed to an object the saved project does not hold."""
    out = []
    for line in raw.decode("utf-8").split("\n"):
        found = PRINTED.fullmatch(line.strip())
        out.append(line.replace(found.group(1), "another object", 1) if found else line)
    return _join(out)


def _controls(directory, prefix, raw, name, plate):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it."""
    lines, count = raw[name].decode("utf-8").split("\n"), plate["layer_count"]
    stand_ins = {
        "empty_file_rejected": b"",
        "header_only_rejected": _join(_through(lines, MARKS[1])),
        "missing_layer_rejected": _join(_without_layer(lines, count // 2)),
        "declared_total_mismatch_rejected": _join(_totals(lines, count - 1)),
        "layer_removed_with_rewritten_totals_rejected": _join(_totals(_without_layer(lines, count // 2), count - 1)),
        "no_end_gcode_rejected": _join(_without_end(lines, plate["last_extruding_line"])),
        "tail_truncated_rejected": _join(_before(lines, MARKS[4])),
        "foreign_gcode_rejected": _shifted(raw[name]),
        # a short move along Y only leaves the footprint test: every count, block and total still holds
        "print_moved_off_the_object_rejected": _shifted(raw[name], dx=0.0, dy=3.0),
        # the file is whole and prints where the object lies; only the name it prints is not a saved object's
        "another_object_printed_rejected": _renamed(raw[name]),
    }
    checks = {label: refused(_read, POSITIVE, directory, prefix, {name: replacement})
              for label, replacement in stand_ins.items()}
    checks["wrong_extension_rejected"] = refused(_read, POSITIVE, directory, prefix, rename={name: "plate.gcode.3mf"})
    checks["other_project_rejected"] = refused(
        _read, POSITIVE, directory, prefix, {"before.3mf": moved_project(raw["before.3mf"], dx=40.0)})
    checks["manifest_mismatch_rejected"] = refused(_read, POSITIVE, directory, prefix, {name: b""}, keep_manifest=False)
    checks["edited_analysis_rejected"] = refused(_read, POSITIVE, directory, prefix, {
        name: _join(_without_end(lines, plate["last_extruding_line"])),
        "analysis.json": flattering(raw["analysis.json"], CLAUSES)})
    return checks


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #236 harvest after the driver verified its log."""
    checks, report, raw, name = _read(directory, prefix)
    result = {"checks": checks, "export": report}
    if not report["failed"]:
        result["checks"].update(_controls(directory, prefix, raw, name, gcode(raw[name])))
    return result
