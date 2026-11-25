"""Recheck Feishu #234's exported sliced plate from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
Each of the two archives, the cube's and the sphere's, is then read three
times: by tests/export_io_oracle.py, by the same oracle's footprint reading of
the G-code inside it against the project that was sliced, and by the
independent reader in tests/file_io_replay_support.py. The last wants one
plate G-code whose recorded checksum holds, two previews that are pictures,
slice records that name the saved objects and agree with the G-code's own time
and filament notes, a first layer over the pattern the archive describes,
settings equal to the sliced project's and one application throughout. The
G-code itself must pass the readings the #236 replay gives an export, and the
complex archive must be the larger one over the more complex model. What
analysis.json records may not outrun those readings; the case log, the save
dialog's receipts and the guard dialog the case reports are held against the
record. Last, each counterexample of the row is stood in for a harvested part
on a temporary copy of the run and must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
from functools import lru_cache
from hashlib import md5, sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from export_io_oracle import plate_object_layout, sliced_expectation_gaps
from file_io_replay_support import (MAIN, SETTINGS, as_recorded, changed_share, close, filament_used, first_layer,
                                    flattering, gcode, guard_dialogs, guard_parts, guards_answered, manifest,
                                    moved_project, png, presets_match, project, refused, seconds, shows_picture,
                                    sliced, screenshots, work_directories, zipped)
# the readings the #236 replay gives an exported G-code, applied here to the one inside each archive
from tools.replay_gcode_export import (STRUCTURE, TIES, _agrees, _join, _shifted, _structure, _ties, _totals,
                                       _without_layer)

CASE = 234
ITEM = "Export plate sliced file"
TITLE = "Save Sliced file as:"
FILTER = "Gcode 3MF files (*.gcode.3mf)"
CLAUSES = ("生成 .gcode.3mf 文件", "内含 G-code 与预览信息", "文件大小随切片复杂度合理增大")
# the label of a sample: the project that was sliced, the archive the application saved, the bare name
# typed into its save dialog and the prefix of its retained screenshots
SAMPLES = {"simple": ("before.3mf", "plate.gcode.3mf", "plate", ""),
           "complex": ("sphere-before.3mf", "sphere.gcode.3mf", "sphere", "sphere-")}
FIXTURES = {"simple": "feishu_std_cube.3mf", "complex": "feishu_std_sphere.3mf"}
PICTURES = ("before.png", "sliced.png", "export-dialog.png")
DIALOG = "export-dialog.png"
MEMBER = "Metadata/plate_1.gcode"
PREVIEWS = ("Metadata/plate_1.png", "Metadata/plate_1_small.png")
SLICE_INFO = "Metadata/slice_info.config"
PATTERN = "Metadata/plate_1.json"
CHANGED = 0.01     # slicing repaints a fifth of the window on the archived runs; a copied screenshot changes none
VERSION = re.compile(r"\d+\.\d+\.\d+")
SIZE_LINE = re.compile(r"\[m7x234\] file bytes (\d+) -> (\d+), G-code bytes (\d+) -> (\d+)")
TIME_NOTE = "; estimated printing time (normal mode)"
ARCHIVE_READINGS = ("archive_holds_one_plate_gcode", "gcode_checksum_recorded_and_consistent",
                    "previews_are_pictures", "slice_info_present", "settings_equal_the_sliced_project",
                    "slice_info_names_the_printed_objects", "slice_info_agrees_with_the_gcode",
                    "pattern_box_holds_the_first_layer", "same_application_throughout")
PER_SAMPLE = (*ARCHIVE_READINGS, *STRUCTURE, *TIES, "oracle_accepts_archive",
              "oracle_locates_the_extrusion_on_the_objects", "screenshots_are_pictures",
              "dialog_picture_matches_record")
RECORD = ("recorded_case", "recorded_fixtures_match_files", "recorded_readings_match_files",
          "recorded_size_comparison_matches_files", "recorded_verdict_matches_files",
          "recorded_presets_match_projects", "recorded_objects_match_projects", "slice_waited_for_the_export_row",
          "export_receipts_match_files", "dialog_default_names_carry_the_slice_time",
          "editor_left_running_after_each_export", "guard_dialogs_answered", "size_line_is_in_the_case_log",
          "work_directory_named_in_the_case_log")
POSITIVE = ("manifest_sizes_and_sha256_match", "archives_carry_the_gcode_3mf_extension",
            "complex_model_is_the_more_complex_one", "complex_gcode_larger_than_simple",
            "complex_archive_larger_than_simple", "sliced_view_differs_from_before", *RECORD,
            *(f"{label}_{name}" for label in SAMPLES for name in PER_SAMPLE))


@lru_cache(maxsize=None)
def _fixture(name: str) -> bytes:
    return (ROOT / "fixtures" / name).read_bytes()


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _version(text):
    found = VERSION.search(text or "")
    return found.group(0) if found else None


def _inside(inner, outer, tolerance=1e-3):
    """Whether the box `inner` lies within the box `outer`, both [xmin, ymin, xmax, ymax]."""
    return (len(inner) == 4 and all(isinstance(value, (int, float)) for value in inner)
            and inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)


def _notes(plate):
    """The time and filament notes of a G-code's trailer: the note, its seconds and the millimetres
    each extruder used."""
    note = next((line for line in plate["trailer"] if line.startswith(TIME_NOTE)), "")
    return note, seconds(note), filament_used(plate)


def _sample(box, plate, saved):
    """One archive against the project it was sliced from, read by the independent reader."""
    objects = {item["name"]: item for item in saved["objects"]}
    pattern = box["pattern"] if isinstance(box["pattern"], dict) else {}
    drawn = pattern.get("bbox_objects") if isinstance(pattern.get("bbox_objects"), list) else []
    first = first_layer(box["gcode"])
    _, seconds_, used = _notes(plate)
    versions = (_version(saved["application"]), _version(box["application"]), _version(plate["generator"]))
    return {
        "archive_holds_one_plate_gcode": box["gcode_member"] == MEMBER and box["declared_gcode"] == MEMBER,
        "gcode_checksum_recorded_and_consistent": bool(box["md5_recorded"])
        and box["md5_recorded"] == box["md5_computed"],
        "previews_are_pictures": all(shows_picture(box["previews"].get(name)) for name in PREVIEWS),
        "slice_info_present": box["has_slice_info"] and box["objects"] is not None,
        "settings_equal_the_sliced_project": isinstance(box["settings"], dict) and box["settings"] == saved["settings"],
        "slice_info_names_the_printed_objects": box["objects"] is not None
        and sorted(box["objects"]) == sorted(objects) == sorted(plate["object_names"]),
        # the prediction is the trailer's printing time, and what a filament used is the trailer's note of it
        "slice_info_agrees_with_the_gcode": box["prediction_s"] is not None and box["prediction_s"] == seconds_
        and bool(box["filament_m"]) and bool(used) and all(
            key.isdigit() and 0 < int(key) <= len(used)
            and abs(1000 * metres - used[int(key) - 1]) <= 5.5 for key, metres in box["filament_m"].items()),
        "pattern_box_holds_the_first_layer": first is not None and first["box"] is not None and first["moves"] > 0
        and len(drawn) == len(objects) and all(
            isinstance(entry, dict) and entry.get("name") in objects
            and _inside(entry.get("bbox", []), _foot(objects[entry["name"]])) for entry in drawn)
        # the first layer's extrusion lies over the pattern the archive describes, a millimetre apart at most
        and close(pattern.get("bbox_all"), first["box"], 1.0),
        "same_application_throughout": all(versions) and len(set(versions)) == 1,
    }


def _foot(item):
    """An object's box on the bed as the archive writes one: [xmin, ymin, xmax, ymax]."""
    return [item["box"][0], item["box"][2], item["box"][1], item["box"][3]]


def _waited(block):
    """Whether the case waited for slicing by the enabled state of the export row."""
    waited = block.get("slice")
    if not isinstance(waited, dict):
        return False
    rows = waited.get("export_menu_after")
    enabled = isinstance(rows, list) and any(
        isinstance(row, dict) and str(row.get("label", "")).startswith(ITEM) and row.get("enabled") is True
        for row in rows)
    return enabled and (_number(waited.get("export_enabled_after_seconds")) or 0) > 0


def _named_after_time(plate, receipt):
    """Whether the save dialog's default name carries the printing time of the G-code that was sliced."""
    default = receipt.get("default_name")
    token = None if plate is None else _notes(plate)[0].partition("=")[2].replace(" ", "")
    return isinstance(default, str) and default.endswith(".gcode") and bool(token) and token in default


def _layout(recorded, saved):
    """Whether the recorded plate objects are what the project holds, name for name, triangle count and
    bounds; the shape it names each is only asked to be a word."""
    if not isinstance(recorded, list) or not all(isinstance(row, dict) for row in recorded):
        return False
    mine = sorted((item["name"], len(item["triangles"]), [[item["box"][0], item["box"][1]],
                 [item["box"][2], item["box"][3]], [item["box"][4], item["box"][5]]]) for item in saved["objects"])
    key = lambda row: (str(row.get("name")), row.get("triangles") if isinstance(row.get("triangles"), int) else -1)  # noqa: E731
    theirs = sorted(recorded, key=key)
    return (len(theirs) == len(mine) and all(
        key(row) == (name, count) and close(row.get("bounds_mm"), bounds, 1e-3)
        for row, (name, count, bounds) in zip(theirs, mine))
        and all(isinstance(row.get("shape"), str) and row["shape"] for row in recorded))


def _oracle(call, *args):
    try:
        return call(*args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return None


def _receipt(receipt, name, bare, raw, shown):
    """Whether the save dialog's receipt tells of this archive and nothing else."""
    types = receipt.get("types") if isinstance(receipt.get("types"), list) else []
    return (receipt.get("item") == ITEM and receipt.get("title") == TITLE
            and receipt.get("typed_name") == bare and receipt.get("filename_before_save") == bare
            and receipt.get("saved_name") == name and receipt.get("saved_extension") == ".gcode.3mf"
            and receipt.get("file_bytes") == len(raw) and receipt.get("file_sha256") == sha256(raw).hexdigest()
            and receipt.get("dialog_closed") is True and receipt.get("app_alive") is True
            and any(isinstance(group, dict) and FILTER in (group.get("items") or []) for group in types)
            and receipt.get("dialog_image") == shown)


def _extension(analysis, label):
    """The extension the case says the application appended: what it judged the first clause with."""
    block = analysis.get(label)
    receipt = block.get("export") if isinstance(block, dict) else None
    saved = receipt.get("saved_extension") if isinstance(receipt, dict) else None
    return saved if isinstance(saved, str) else ""


def _record(analysis, raw, log, work, readings, gaps, comparison, layouts, boxes, plates, saved, kept, shown):
    """What the GUI recorded, held against the files, against the case log and against its own content."""
    blocks = {label: analysis.get(label) if isinstance(analysis.get(label), dict) else {} for label in SAMPLES}
    exports = {label: block.get("export") if isinstance(block.get("export"), dict) else {}
               for label, block in blocks.items()}
    results, recorded = analysis.get("results"), analysis.get("expectation_gaps")
    files = analysis.get("sliced_files") if isinstance(analysis.get("sliced_files"), dict) else {}
    line = SIZE_LINE.search(log)
    sizes = tuple(map(int, line.groups())) if line else None
    return {
        "recorded_case": analysis.get("case") == CASE,
        "recorded_fixtures_match_files": all(blocks[label].get("fixture") == {
            "name": FIXTURES[label], "bytes": len(_fixture(FIXTURES[label])),
            "sha256": sha256(_fixture(FIXTURES[label])).hexdigest()} for label in SAMPLES),
        # the oracle's readings and its comparison of the sizes, as the case recorded them
        "recorded_readings_match_files": all(_agrees(files.get(label), readings[label] or {}) for label in SAMPLES),
        "recorded_size_comparison_matches_files": comparison is not None
        and _agrees(analysis.get("size_comparison"), comparison),
        "recorded_verdict_matches_files": isinstance(results, dict) and isinstance(recorded, dict)
        and [results.get(clause) for clause in CLAUSES] == ["PASS"] * len(CLAUSES)
        and recorded == gaps and not any(gaps.values()),
        "recorded_presets_match_projects": all(
            presets_match(blocks[label].get("presets"), saved[label]["settings"]) for label in SAMPLES),
        "recorded_objects_match_projects": all(
            layouts[label] is not None and as_recorded(layouts[label]["objects"]) == blocks[label].get("plate_objects")
            and _layout(blocks[label].get("plate_objects"), saved[label]) for label in SAMPLES),
        # the case waited for slicing by the export row's enabled state, as #254's lesson asks
        "slice_waited_for_the_export_row": all(_waited(block) for block in blocks.values()),
        "export_receipts_match_files": all(
            _receipt(exports[label], name, bare, raw[name], shown[label]) for label, (_, name, bare, _) in SAMPLES.items()),
        # the dialog offered the slice's own printing time in its default name
        "dialog_default_names_carry_the_slice_time": all(
            _named_after_time(plates[label], exports[label]) for label in SAMPLES),
        "editor_left_running_after_each_export": all(
            blocks[label].get("editor_after_export") == {"alive": True, "dialog": None} for label in SAMPLES),
        "guard_dialogs_answered": guards_answered(analysis, raw, kept, log),
        "size_line_is_in_the_case_log": sizes == (
            len(raw[SAMPLES["simple"][1]]), len(raw[SAMPLES["complex"][1]]),
            len(boxes["simple"]["gcode"] or b""), len(boxes["complex"]["gcode"] or b"")),
        "work_directory_named_in_the_case_log": bool(work) and all(
            exports[label].get("directory") in work for label in SAMPLES),
    }


def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings, the raw artifacts and what the counterexamples are built from."""
    entries = manifest(directory, prefix)
    record = verified_part(directory, prefix, entries, "analysis.json").read_bytes()
    analysis = json.loads(record.decode("utf-8-sig"))
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    listed = {entry["part"] for entry in entries}
    parts = [part for label in SAMPLES for part in (SAMPLES[label][0], SAMPLES[label][1])]
    parts += [SAMPLES[label][3] + part for label in SAMPLES for part in PICTURES]
    # a guard dialog's screenshot is read when the harvest kept it; one that is missing fails the reading
    parts += [part for part in guard_parts(analysis, listed) if part not in parts]
    try:
        paths = {part: verified_part(directory, prefix, entries, part) for part in parts}
        raw = {part: path.read_bytes() for part, path in paths.items()}
        log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"a listed part could not be read ({type(exc).__name__})") from exc
    raw["analysis.json"] = record
    boxes = {label: sliced(raw[name]) for label, (_, name, _, _) in SAMPLES.items()}
    saved = {label: project(raw[project_]) for label, (project_, _, _, _) in SAMPLES.items()}
    fixtures = {label: project(_fixture(FIXTURES[label])) for label in SAMPLES}
    plates = {label: gcode(boxes[label]["gcode"]) if boxes[label]["gcode"] is not None else None for label in SAMPLES}
    with TemporaryDirectory(prefix="replay-234-") as temporary:
        # the oracle reads each archive under the name the case gave it, not under the harvest's prefix
        samples, projects = {}, {}
        for label, (project_, name, _, _) in SAMPLES.items():
            (Path(temporary) / name).write_bytes(raw[name])
            projects[label] = Path(temporary) / project_
            projects[label].write_bytes(raw[project_])
            samples[label] = (Path(temporary) / name, _extension(analysis, label))
        gaps, readings, comparison = sliced_expectation_gaps(samples, projects)
        layouts = {label: _oracle(plate_object_layout, projects[label]) for label in SAMPLES}
    checks = {"manifest_sizes_and_sha256_match": True}
    for label, (_, name, _, pictures) in SAMPLES.items():
        plate, box, facts = plates[label], boxes[label], readings[label]
        sample, structure, ties = (_sample(box, plate, saved[label]), _structure(plate),
                                   _ties(plate, saved[label], fixtures[label], "(" + FIXTURES[label] + ")")) \
            if plate is not None else (dict.fromkeys(ARCHIVE_READINGS, False), dict.fromkeys(STRUCTURE, False),
                                       dict.fromkeys(TIES, False))
        oracle = {"oracle_accepts_archive": facts is not None and isinstance(facts.get("checks"), dict)
                  and bool(facts["checks"]) and all(facts["checks"].values()),
                  "oracle_locates_the_extrusion_on_the_objects": facts is not None
                  and isinstance(facts.get("footprint"), dict) and bool(facts["footprint"].get("checks"))
                  and all(facts["footprint"]["checks"].values())}
        shot = screenshots({part: raw[pictures + part] for part in PICTURES},
                           analysis.get(label).get("export") if isinstance(analysis.get(label), dict) else None,
                           PICTURES, DIALOG)
        checks.update({f"{label}_{key}": value for key, value in {**sample, **structure, **ties, **oracle, **shot}.items()})
    triangles = {label: sum(len(item["triangles"]) for item in saved[label]["objects"]) for label in SAMPLES}
    checks.update({
        "archives_carry_the_gcode_3mf_extension": all(name.endswith(".gcode.3mf") for _, name, _, _ in SAMPLES.values()),
        "complex_model_is_the_more_complex_one": triangles["complex"] > triangles["simple"] > 0,
        "complex_gcode_larger_than_simple": all(boxes[label]["gcode"] is not None for label in SAMPLES)
        and len(boxes["complex"]["gcode"]) > len(boxes["simple"]["gcode"]),
        "complex_archive_larger_than_simple": len(raw[SAMPLES["complex"][1]]) > len(raw[SAMPLES["simple"][1]]),
    })
    changes = {label: changed_share(raw[pictures + "before.png"], raw[pictures + "sliced.png"])
               for label, (_, _, _, pictures) in SAMPLES.items()}
    checks["sliced_view_differs_from_before"] = all(share is not None and share >= CHANGED for share in changes.values())
    kept = set(parts)
    shown = {}
    for label, (_, _, _, pictures) in SAMPLES.items():
        try:
            size = png(raw[pictures + DIALOG])
        except ValueError:
            size = {}
        shown[label] = {"width_px": size.get("width"), "height_px": size.get("height")}
    work = work_directories(log, "m7x234")
    checks.update(_record(analysis, raw, log, work, readings, gaps, comparison, layouts, boxes, plates, saved, kept, shown))
    missing = sorted(set(POSITIVE) - set(checks))
    if missing:
        raise ValueError(f"readings dropped: {missing}")
    report = {"samples": {}, "size_comparison": comparison, "screen_changes": changes,
              "guard_dialogs": len(guard_dialogs(analysis)), "work_directories": work, "failed": list(_failed(checks))}
    for label, (_, name, _, _) in SAMPLES.items():
        plate, box, facts = plates[label], boxes[label], readings[label] or {}
        report["samples"][label] = {
            "archive": {"name": name, "bytes": len(raw[name]), "sha256": sha256(raw[name]).hexdigest()},
            "gcode": None if plate is None else {
                "member": box["gcode_member"], "bytes": plate["bytes"], "generator": plate["generator"],
                "layers": plate["layer_count"], "z_first": plate["z"][:1], "z_last": plate["z"][-1:],
                "object_names": plate["object_names"], "extrusion_box_mm": plate["extrusion_box"]},
            "object_box_mm": [item["box"] for item in saved[label]["objects"]], "triangles": triangles[label],
            "previews": {part: box["previews"].get(part) for part in PREVIEWS},
            "slice_info": {"objects": box["objects"], "prediction_s": box["prediction_s"], "filament_m": box["filament_m"]},
            "oracle": {"checks": facts.get("checks"),
                       "footprint": None if "footprint" not in facts else {
                           key: facts["footprint"].get(key) for key in ("max_excursion_mm", "allowances_mm", "checks")}},
        }
    return checks, report, (raw, boxes)


def _failed(checks):
    return (key for key in POSITIVE if checks[key] is not True)


# --- counterexamples --------------------------------------------------------------

def _uniform(raw: bytes) -> bytes:
    """A picture of the same size as `raw`, in one colour."""
    from PIL import Image

    with Image.open(BytesIO(raw)) as image:
        size = image.size
    out = BytesIO()
    Image.new("RGB", size, (200, 200, 200)).save(out, "PNG")
    return out.getvalue()


def _restamped(files: dict, code: bytes) -> bytes:
    """The archive with another G-code in its plate member and the checksum record made to agree."""
    files = dict(files, **{MEMBER: code})
    files[MEMBER + ".md5"] = md5(code).hexdigest().upper().encode("ascii")
    return zipped(files)


def _without_previews(files: dict) -> bytes:
    return zipped({name: data for name, data in files.items() if name not in PREVIEWS})


def _resized(raw: bytes) -> bytes:
    """A picture at another size than it was recorded with."""
    from PIL import Image

    with Image.open(BytesIO(raw)) as image:
        out = BytesIO()
        image.resize((image.width + 16, image.height + 16)).save(out, "PNG")
    return out.getvalue()


def _stand_ins(raw, boxes):
    """Each counterexample of the row: {label: the parts stood in for harvested ones and how}, each
    meant for `refused` on a copy whose manifest agrees with the stand-in."""
    simple, complex_ = boxes["simple"], boxes["complex"]
    files, code = simple["members"], simple["gcode"]
    lines, count = code.decode("utf-8").split("\n"), gcode(code)["layer_count"]
    another = dict(simple["settings"] or {}, layer_height="0.3")
    replace = {
        "plain_gcode_under_the_archive_name_rejected": {"plate.gcode.3mf": code},
        "archive_without_gcode_rejected": {
            "plate.gcode.3mf": zipped({name: data for name, data in files.items() if not name.startswith(MEMBER)})},
        "archive_without_previews_rejected": {"plate.gcode.3mf": _without_previews(files)},
        "blank_preview_rejected": {
            "plate.gcode.3mf": zipped(dict(files, **{name: _uniform(files[name]) for name in PREVIEWS}))},
        "checksum_left_behind_rejected": {
            "plate.gcode.3mf": zipped(dict(files, **{MEMBER: _join(_without_layer(lines, count // 2))}))},
        # a layer gone and nothing left to tell but the heights: the totals and the checksum were rewritten
        "layer_removed_with_rewritten_checksum_rejected": {
            "plate.gcode.3mf": _restamped(files, _join(_totals(_without_layer(lines, count // 2), count - 1)))},
        "print_moved_off_the_object_rejected": {
            "plate.gcode.3mf": _restamped(files, _shifted(code, dx=0.0, dy=3.0))},
        "sphere_archive_under_the_cube_name_rejected": {"plate.gcode.3mf": raw["sphere.gcode.3mf"]},
        "cube_archive_under_the_sphere_name_rejected": {"sphere.gcode.3mf": raw["plate.gcode.3mf"]},
        "other_project_rejected": {"before.3mf": moved_project(raw["before.3mf"], dx=40.0)},
        "archive_settings_from_another_profile_rejected": {
            "plate.gcode.3mf": zipped(dict(files, **{SETTINGS: json.dumps(another).encode("utf-8")}))},
        "slice_info_of_the_other_plate_rejected": {
            "plate.gcode.3mf": zipped(dict(files, **{SLICE_INFO: complex_["members"].get(SLICE_INFO, b"")}))},
        # the archive's own records point at another file than the plate G-code it holds
        "archive_declares_another_gcode_rejected": {"plate.gcode.3mf": zipped(dict(files, **{
            "Metadata/model_settings.config": re.sub(rb'(key="gcode_file" value=")[^"]+',
                                                     rb"Metadata/plate_9.gcode",
                                                     files["Metadata/model_settings.config"])}))},
        "archive_without_slice_info_rejected": {
            "plate.gcode.3mf": zipped({name: data for name, data in files.items() if name != SLICE_INFO})},
        # the pattern box of the other plate: its first layer lies somewhere else
        "pattern_box_of_another_plate_rejected": {
            "plate.gcode.3mf": zipped(dict(files, **{PATTERN: complex_["members"].get(PATTERN, b"{}")}))},
        # an archive that says another application wrote it than the project and the G-code do
        "another_application_in_the_archive_rejected": {"plate.gcode.3mf": zipped(dict(files, **{
            MAIN: files[MAIN].replace(b"Snapmaker_Orca-2.4.0", b"Snapmaker_Orca-2.3.6")}))},
        "sliced_picture_copied_from_before_rejected": {"sliced.png": raw["before.png"]},
        # a screenshot replaced by a uniform picture of the same size, and a dialog picture of another size
        "blank_screenshot_rejected": {"before.png": _uniform(raw["before.png"])},
        "dialog_picture_resized_rejected": {"export-dialog.png": _resized(raw["export-dialog.png"])},
        # a record that claims every clause over an archive that has lost its previews
        "flattering_record_rejected": {"plate.gcode.3mf": _without_previews(files),
                                       "analysis.json": flattering(raw["analysis.json"], CLAUSES)},
        # a guard dialog the record itself says was left open
        "guard_left_open_rejected": {"analysis.json": flattering(raw["analysis.json"], CLAUSES, memory_guard_dialogs=[{
            "title": "Memory Usage Warning", "texts": ["Yes, Continue", "No, Stop"], "closed": False,
            "screenshot": "memory-guard-0.png", "image": {"width_px": 796, "height_px": 216}}])},
    }
    stand_ins = {label: {"replace": parts} for label, parts in replace.items()}
    stand_ins["wrong_extension_rejected"] = {"rename": {"plate.gcode.3mf": "plate.3mf"}}
    # the collector that recorded one file and kept another
    stand_ins["manifest_mismatch_rejected"] = {"replace": {"plate.gcode.3mf": b""}, "keep_manifest": False}
    return stand_ins


def _controls(directory, prefix, raw, boxes):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it."""
    return {label: refused(_read, POSITIVE, directory, prefix, **how)
            for label, how in _stand_ins(raw, boxes).items()}


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #234 harvest after the driver verified its log."""
    checks, report, (raw, boxes) = _read(directory, prefix)
    result = {"checks": checks, "sliced_plates": report}
    if not report["failed"]:
        result["checks"].update(_controls(directory, prefix, raw, boxes))
    return result
