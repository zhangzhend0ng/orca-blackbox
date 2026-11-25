"""Recheck Feishu #228's coloured OBJ import from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
``imported.3mf`` and ``plate.gcode`` are then read twice: by
tests/colored_obj_oracle.py, the oracle the case judged with on the guest, and
by the independent reader below, which parses the archive and the G-code with
tests/file_io_replay_support.py and takes from the oracle only the paint
decoder and the fixture's triangles:

* the saved project holds the fixture once, one object with one normal part on
  the one plate; the faces of the material ``red`` print with one filament and
  those of ``blue`` with another (a face prints with its paint where it carries
  one and with its part's extruder otherwise, which is how the OBJ import of
  2.4.0 leaves the faces of the first filament); the first filament is red and
  the second blue in ``filament_colour``;
* the G-code extrudes with both of those tools and changes between them; its
  configuration names the project's filament colours and its trailer says both
  were used.

What analysis.json records may not outrun those readings: the recorded
readings are held against the oracle's reading of the archived files, the
recorded fixture against the OBJ and the MTL written again here and against the
archived texture, the chooser's path against the work directory the case log
names, the export receipt against the archived G-code, and every dialog survey
against a picture the harvest kept. The two clauses are recomputed and reported
as they come out, PASS or FAIL; a run whose expectation does not hold is
reproduced, not repaired. Last, each counterexample of the row is stood in for
a harvested part on a temporary copy of a passing run and must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PureWindowsPath
import re
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from colored_obj_oracle import (  # noqa: E402
    CLAUSE_COLORS, CLAUSE_FILAMENTS, DEFAULT_EXTRUDER, GEOMETRIES, MATERIALS, PAINT_ATTRS, face_filament,
    filament_readings, material_triangles, mesh_geometry, painted_readings, verify_filament_change,
    verify_painted_import)
from file_io_replay_support import (  # noqa: E402
    CORE, MAIN, OBJECT_SETTINGS, PROD, SETTINGS, WORD, _at, _matrix, _mesh, _metadata, _serialise, _xml, archive,
    as_recorded, at_origin, blank_png, box, compose, copy_of, filament_used, flattering, gcode, manifest, paired, png,
    project, with_project_settings, with_settings, zipped)

CASE = 228
FIXTURE = ROOT / "fixtures" / "agent_layer_redblue.3mf"      # the U1 0.8 template, its first two filaments red and blue
OTHER_PAINTED = ROOT / "docs/runs/evidence/feishu-140-201-202-2026-11-25/row-202-hyperv/7a7a584f-after-save-as.3mf"
SOURCE, MTL, TEXTURE = "model.obj", "model.mtl", "texture.png"
START, IMPORTED, PLATE = "new-project.3mf", "imported.3mf", "plate.gcode"
PARTS = (START, IMPORTED, PLATE, TEXTURE)
PICTURES = ("chooser.png", "imported.png", "sliced.png", "export-dialog.png")
ITEM, FORM = "Export G-code", "kd-only"
RED, BLUE = "#ff0000", "#0000ff"
TOL = 1e-3
TOOL = re.compile(r"T(\d+)")
E_WORD = re.compile(r"\s+E-?(?:\d+\.?\d*|\.\d+)")
GENERATOR = re.compile(r"Snapmaker Orca \d+\.\d+\.\d+")
OTHER_RUN = r"C:\coil\orca-blackbox-v3-r1\artifacts\feishu-object-cases\228\run-elsewhere"
PROJECT_READINGS = ("saved_object_is_the_fixture_once", "object_is_named_after_the_obj", "red_faces_one_filament",
                    "blue_faces_one_filament", "filaments_differ", "filaments_are_red_and_blue")
GCODE_READINGS = ("gcode_prints_both_filaments", "gcode_changes_between_them", "gcode_names_the_projects_colours",
                  "gcode_trailer_names_two_filaments", "generated_by_snapmaker_orca")
RECORD = ("recorded_case_and_template", "recorded_fixture_matches_its_bytes", "recorded_imported_matches_file",
          "recorded_gcode_matches_file", "recorded_verdicts_match_readings", "recorded_route_matches_readings",
          "chooser_entered_this_runs_obj", "chooser_picture_matches_record", "export_receipt_matches_file",
          "slice_waited_for_the_export_row", "editor_left_running_after_export", "recorded_dialogs_have_their_pictures")
POSITIVE = ("manifest_sizes_and_sha256_match", "start_is_the_redblue_template_with_its_cube", *PROJECT_READINGS,
            *GCODE_READINGS, "oracle_accepts_project", "oracle_accepts_gcode", *RECORD, "pictures_are_pictures",
            "texture_is_the_fixture_picture")
UNREADABLE = (ValueError, OSError, KeyError, TypeError)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _leaf(path):
    return str(path).replace("\\", "/").rsplit("/", 1)[-1] if path else None


def _block(analysis, key):
    value = analysis.get(key)
    return value if isinstance(value, dict) else {}


def _extents(points):
    return [(min(point[axis] for point in points), max(point[axis] for point in points)) for axis in range(3)]


def _triangles(corners):
    """Flat corners as triangles of three."""
    return [corners[index:index + 3] for index in range(0, len(corners), 3)]


def _paint(triangle):
    """The one paint attribute a triangle carries, None when it has none; ValueError when it has two."""
    found = [value for key, value in triangle.attrib.items() if key.rsplit("}", 1)[-1] in PAINT_ATTRS]
    if len(found) > 1:
        raise ValueError("a triangle carries more than one paint attribute")
    return found[0] if found else None


def _colour(colours, filament):
    if isinstance(colours, list) and isinstance(filament, int) and 0 < filament <= len(colours) \
            and isinstance(colours[filament - 1], str):
        return colours[filament - 1].casefold()
    return None


# --- the fixture the case writes -------------------------------------------------

def _fixture_files(stem, geometry):
    """The OBJ and the MTL of the judged fixture, written again here as tests/colored_obj_cases.py writes
    them for the Kd-only form: no texture referenced, no UVs, a line feed at the end of every line."""
    vertices, faces = mesh_geometry(geometry)
    lines = [f"mtllib {stem}.mtl", "# Feishu #228: a 20 mm cube, the left half red and the right half blue"]
    lines += [f"v {x:g} {y:g} {z:g}" for x, y, z in vertices]
    for material in MATERIALS:
        lines.append(f"usemtl {material}")
        lines += [f"f {i + 1} {j + 1} {k + 1}" for i, j, k, owner in faces if owner == material]
    obj = ("\n".join(lines) + "\n").encode("ascii")
    mtl = "\n".join(["# Feishu #228: two materials", "newmtl red", "Ka 0 0 0", "Kd 1 0 0", "",
                     "newmtl blue", "Ka 0 0 0", "Kd 0 0 1", ""]).encode("ascii")
    return {f"{stem}.obj": obj, f"{stem}.mtl": mtl}


def _fixture_record(geometry, texture):
    """What the case records of the three fixture files, for a `texture` of these bytes."""
    files = _fixture_files(SOURCE.rsplit(".", 1)[0], geometry)
    files[TEXTURE] = texture
    return {"obj": SOURCE, "mtl": MTL, "form": FORM, "geometry": geometry, "texture_referenced": False,
            "obj_has_uv": False, "faces": {name: len(faces) for name, faces in material_triangles(geometry).items()},
            "files": {name: {"bytes": len(raw), "sha256": sha256(raw).hexdigest()} for name, raw in files.items()}}


def _template():
    raw = FIXTURE.read_bytes()
    return {"name": FIXTURE.name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def _texture(raw) -> bool:
    """Whether a picture is the fixture's texture: a 16 x 16 square of one colour, red."""
    try:
        from PIL import Image

        with Image.open(BytesIO(raw)) as image:
            image.load()
            return image.width == image.height == 16 and image.convert("RGB").getcolors(2) == [(256, (255, 0, 0))]
    except Exception:  # noqa: BLE001 - whatever keeps a picture from decoding leaves it no texture
        return False


# --- the saved project, read independently ---------------------------------------

def _painted(raw, geometry):
    """The independent reading of a saved project: where the faces of its one part lie among the
    fixture's triangles, which of them carry paint, and which filament each prints with. Nothing
    is judged here; a project that holds other than one printable object with one part leaves the
    reading short and ``matched`` False."""
    expected = material_triangles(geometry)
    reading = {"objects": 0, "plates": 0, "on_plate": False, "normal_part": False, "name": None, "source": None,
               "member": None, "mesh_id": None, "faces": 0, "matched": False, "order": [], "painted": {}, "bare": {},
               "filaments": {},
               "prints_with": DEFAULT_EXTRUDER, "colours": {}, "object_extruder": None, "part_extruder": None,
               "filament_colour": None, "box": None, "offset": None}
    files = archive(raw)
    main, rows = _xml(files[MAIN], MAIN), _xml(files[OBJECT_SETTINGS], OBJECT_SETTINGS)
    settings = json.loads(files[SETTINGS].decode("utf-8-sig"))
    if not isinstance(settings, dict):
        raise ValueError("project settings are not an object")
    colours = settings.get("filament_colour")
    reading["plates"], reading["filament_colour"] = len(rows.findall("plate")), colours
    items = main.findall(f"{CORE}build/{CORE}item")
    if len(items) != 1:
        reading["objects"] = len(items)
        return reading
    item = items[0]
    row = next((node for node in rows.findall("object") if node.get("id") == item.get("objectid")), None)
    if row is None or item.get("printable", "1") not in ("1", "true"):
        return reading
    reading["objects"] = 1
    on_plate = {_metadata(placed, "object_id") for plate in rows.findall("plate")
                for placed in plate.findall("model_instance")}
    parent = next((node for node in main.iter(CORE + "object") if node.get("id") == row.get("id")), None)
    parts = row.findall("part")
    components = [] if parent is None else parent.findall(f"{CORE}components/{CORE}component")
    reading.update(on_plate=row.get("id") in on_plate, name=_metadata(row, "name"),
                   object_extruder=_int(_metadata(row, "extruder")))
    if len(parts) != 1 or len(components) != 1:
        return reading
    part, component = parts[0], components[0]
    reading.update(normal_part=part.get("subtype") == "normal_part" and part.get("id") == component.get("objectid"),
                   source=_leaf(_metadata(part, "source_file")), part_extruder=_int(_metadata(part, "extruder")))
    member = component.get(PROD + "path", MAIN).lstrip("/")
    if member not in files:
        return reading
    mesh_id = component.get("objectid")
    node = next((obj for obj in _xml(files[member], member).iter(CORE + "object") if obj.get("id") == mesh_id), None)
    if node is None:
        return reading
    points, faces = _mesh(node)
    triangles = node.find(f"{CORE}mesh/{CORE}triangles")
    if triangles is None or len(triangles) != len(faces):
        raise ValueError("a part lists other than its own triangles")
    place = compose(_matrix(item.get("transform")), _matrix(component.get("transform")))
    saved = [{"corners": [_at(place, points[index]) for index in face], "paint": _paint(triangle)}
             for face, triangle in zip(faces, triangles)]
    corners = [corner for face in saved for corner in face["corners"]]
    reading.update(member=member, mesh_id=mesh_id, faces=len(saved), box=box(corners))
    # what a face without paint prints with: its part's extruder, else its object's, else the first filament
    reading["prints_with"] = next((value for value in (reading["part_extruder"], reading["object_extruder"]) if value),
                                  DEFAULT_EXTRUDER)
    flat = [corner for group in expected.values() for triangle in group for corner in triangle]
    if len(saved) != sum(len(group) for group in expected.values()):
        return reading
    offset = [low - other for (low, _high), (other, _high) in zip(_extents(corners), _extents(flat))]
    moved = [tuple(corner[axis] + offset[axis] for axis in range(3))
             for material in MATERIALS for triangle in expected[material] for corner in triangle]
    # every three corners are one triangle; a pair's number is the saved face's own
    pairs, _worst = paired(_triangles(moved), _triangles(corners), TOL, 10 * TOL)
    reading["offset"] = [round(value, 6) for value in offset]
    if len(pairs) != len(saved) or None in pairs:
        return reading
    reading["matched"] = True
    painted, printing = {material: set() for material in MATERIALS}, {material: set() for material in MATERIALS}
    bare = dict.fromkeys(MATERIALS, 0)
    first = len(expected[MATERIALS[0]])
    for index, face_index in enumerate(pairs):
        material = MATERIALS[0] if index < first else MATERIALS[1]
        paint = face_filament(saved[face_index]["paint"])
        reading["order"].append((face_index, material))
        bare[material] += not paint
        painted[material].add(paint)
        # a face prints with its paint where it carries one and with its part's extruder otherwise
        printing[material].add(paint or reading["prints_with"])
    reading["painted"], reading["bare"] = {material: sorted(found) for material, found in painted.items()}, bare
    reading["filaments"] = {material: next(iter(found)) if len(found) == 1 else None
                            for material, found in printing.items()}
    reading["colours"] = {value: _colour(colours, value) for found in printing.values() for value in found if value}
    return reading


def _project_checks(reading) -> dict:
    """The first clause as the independent reading sees it."""
    filaments, colours = reading["filaments"], reading["colours"]
    red, blue = (filaments.get(material) for material in MATERIALS)
    return {
        "saved_object_is_the_fixture_once": reading["matched"] and reading["objects"] == 1
        and reading["plates"] == 1 and reading["on_plate"] and reading["normal_part"],
        "object_is_named_after_the_obj": reading["name"] in (SOURCE, "model") and reading["source"] == SOURCE,
        "red_faces_one_filament": red is not None and red > 0,
        "blue_faces_one_filament": blue is not None and blue > 0,
        "filaments_differ": red is not None and blue is not None and red != blue,
        "filaments_are_red_and_blue": bool(red) and bool(blue)
        and colours.get(red) == RED and colours.get(blue) == BLUE,
    }


# --- the G-code, read independently ----------------------------------------------

def _walk(raw):
    """The independent reading of a G-code's tools: which tools extrude while travelling in XY,
    where the tool changes, and which tool each line runs under (so that a stand-in can take a
    tool's work out). ``M82``, ``M83`` and ``G92 E`` are followed."""
    lines = raw.decode("utf-8", errors="replace").split("\n")
    tools, changes, states = {}, [], []
    tool, e_at, relative = None, None, False
    for line in lines:
        code = line.partition(";")[0]
        words = code.split()
        token = words[0].upper() if words else ""
        found = TOOL.fullmatch(token)
        if found:
            new = int(found.group(1))
            if tool is not None and new != tool:
                changes.append([tool, new])
            tool, e_at = new, None
            tools.setdefault(tool, {"moves": 0, "e": 0.0})
        elif token == "M82":
            relative, e_at = False, None
        elif token == "M83":
            relative = True
        elif token in ("G0", "G1", "G92"):
            values = {key: float(value) for key, value in WORD.findall(code)}
            if token == "G92":
                e_at = values.get("E", e_at)
            elif "E" in values and tool is not None:
                delta = values["E"] if relative else None if e_at is None else values["E"] - e_at
                e_at = values["E"]
                if delta is not None and delta > 0 and ("X" in values or "Y" in values):
                    tools[tool]["moves"] += 1
                    tools[tool]["e"] += delta
        states.append(tool)
    return {"extruding": sorted(number for number, row in tools.items() if row["moves"]), "changes": changes,
            "states": states, "lines": lines, "first": next((tool for tool in states if tool is not None), None),
            "per_tool": {str(number): {"moves": row["moves"], "e": round(row["e"], 5)}
                         for number, row in sorted(tools.items())}}


def _gcode_checks(walk, plate, filaments, colours) -> dict:
    """The second clause as the independent reading sees it: the two filaments the faces print with
    both extrude, the print changes between them, the file's configuration carries the project's
    filament colours and its trailer says both were used."""
    wanted = sorted({value - 1 for value in filaments.values() if value})
    swaps = [change for change in walk["changes"] if change[0] in wanted and change[1] in wanted]
    used, config = filament_used(plate), plate["config"].get("filament_colour", [])
    return {
        "gcode_prints_both_filaments": len(wanted) == 2 and all(number in walk["extruding"] for number in wanted),
        "gcode_changes_between_them": len(wanted) == 2 and bool(swaps),
        "gcode_names_the_projects_colours": isinstance(colours, list) and len(config) == 1
        and [part.strip().strip('"').casefold() for part in config[0].split(";")] == [value.casefold() for value in colours],
        "gcode_trailer_names_two_filaments": len(wanted) == 2 and len(used) > max(wanted)
        and all(used[number] > 0 for number in wanted),
        "generated_by_snapmaker_orca": bool(GENERATOR.match(plate["generator"] or "")),
    }


# --- what the case recorded -------------------------------------------------------

def _verdict(readings) -> str:
    """The case's verdict for a reading: 'PASS', or 'FAIL (...)' naming what could not be read or failed."""
    checks = readings.get("checks") or {}
    if not checks:
        return 'FAIL (not read: ' + str(readings.get("error", "no readings")) + ')'
    failed = [name for name, passed in checks.items() if not passed]
    return "PASS" if not failed else "FAIL (" + ", ".join(failed) + ")"


def _size(raw):
    try:
        facts = png(raw)
    except ValueError:
        return None
    return {"width_px": facts["width"], "height_px": facts["height"]}


def _is_picture(raw, least=32, full=False) -> bool:
    try:
        facts = png(raw)
    except ValueError:
        return False
    return (facts["format"] == "PNG" and facts["gray_levels"] >= least
            and (not full or (facts["width"] >= 640 and facts["height"] >= 400 and facts["std"] >= 5)))


def _dialog_pictures(analysis, listed):
    """(whether every survey the case kept names a picture the harvest kept and no error dialog, those
    pictures): the surveys of the judged import and those of the control, when there was one."""
    judged = analysis.get("import_dialogs")
    control = analysis.get("control")
    blocks = [judged] + ([control.get("import_dialogs")] if isinstance(control, dict) else [])
    names, ok = [], isinstance(judged, list) and all(isinstance(block, list) for block in blocks)
    for block in blocks:
        for record in block if isinstance(block, list) else []:
            image = record.get("image") if isinstance(record, dict) else None
            title = record.get("title") if isinstance(record, dict) else None
            if (not isinstance(image, str) or not image.endswith(".png") or image not in listed
                    or not isinstance(title, str) or "error" in title.casefold()):
                ok = False
                continue
            names.append(image)
    return ok, list(dict.fromkeys(names))


def _waited(block) -> bool:
    """Whether the case waited for slicing by the enabled state of the G-code export row."""
    rows = block.get("export_menu_after")
    enabled = isinstance(rows, list) and any(
        isinstance(row, dict) and str(row.get("label", "")).startswith(ITEM) and row.get("enabled") is True
        for row in rows)
    return enabled and (_number(block.get("export_enabled_after_seconds")) or 0) > 0


def _record(analysis, raw, work, imported, code, geometry, dialogs, pictures) -> dict:
    """What the GUI recorded, held against the files, against the case log and against its own content."""
    fixture, chooser, export = _block(analysis, "fixture"), _block(analysis, "chooser"), _block(analysis, "export")
    route, judged, control = _block(analysis, "route"), _block(_block(analysis, "route"), "judged"), \
        _block(_block(analysis, "route"), "control")
    results = analysis.get("results") if isinstance(analysis.get("results"), dict) else {}
    said = {key: value for key, value in fixture.items() if key not in ("form_says", "template")}
    rows = [row for row in chooser.get("import_rows") or [] if isinstance(row, dict)]
    hits = [row for row in rows if "obj" in str(row.get("label", "")).casefold() and row.get("enabled") is True]
    entered = chooser.get("entered")
    route_gcode = _block(judged, "gcode")
    return {
        "recorded_case_and_template": analysis.get("case") == CASE and fixture.get("template") == _template(),
        "recorded_fixture_matches_its_bytes": (
            isinstance(fixture.get("form_says"), str) and bool(fixture["form_says"])
            and said == _fixture_record(geometry, raw[TEXTURE])),
        "recorded_imported_matches_file": analysis.get("imported") == imported,
        "recorded_gcode_matches_file": analysis.get("gcode") == code,
        "recorded_verdicts_match_readings": isinstance(results, dict) and (
            [results.get(clause) for clause in (CLAUSE_COLORS, CLAUSE_FILAMENTS)]
            == [_verdict(imported), _verdict(code)]),
        # the route the case summed up is what the oracle reads in the archived files
        "recorded_route_matches_readings": (
            judged.get("form") == FORM and judged.get("texture_referenced") is False
            and judged.get("obj_has_uv") is False and judged.get("filaments") == imported.get("filaments")
            and judged.get("checks") == imported.get("checks")
            and route_gcode.get("tools_extruding") == code.get("tools_extruding")
            and route_gcode.get("change_count") == code.get("change_count")),
        "chooser_entered_this_runs_obj": (
            len(work) == 1 and isinstance(entered, str)
            and PureWindowsPath(entered) == PureWindowsPath(work[0]) / SOURCE and chooser.get("dialog_closed") is True
            and len(hits) == 1 and chooser.get("row") == hits[0]["label"]),
        "chooser_picture_matches_record": chooser.get("image") == _size(raw["chooser.png"]),
        "export_receipt_matches_file": (
            export.get("item") == ITEM and export.get("saved_name") == PLATE
            and export.get("saved_extension") == ".gcode" and export.get("file_bytes") == len(raw[PLATE])
            and export.get("file_sha256") == sha256(raw[PLATE]).hexdigest() and export.get("dialog_closed") is True
            and export.get("app_alive") is True and export.get("dialog_image") == _size(raw["export-dialog.png"])
            and export.get("directory") in work),
        "slice_waited_for_the_export_row": _waited(_block(analysis, "slice")),
        "editor_left_running_after_export": analysis.get("editor_after_export") == {"alive": True, "dialog": None},
        "recorded_dialogs_have_their_pictures": dialogs and all(_is_picture(picture) for picture in pictures),
    }


def _same(first, second) -> bool:
    if len(first) != len(second):
        return False
    pairs, _worst = paired(list(first), list(second), 1e-4)
    return None not in pairs


def _as_loaded(value):
    suffix = "(" + FIXTURE.name + ")"
    return value[:-len(suffix)] if isinstance(value, str) and value.endswith(suffix) else value


def _printer(settings):
    return (settings.get("printer_model"), _as_loaded(settings.get("printer_settings_id")),
            (settings.get("nozzle_diameter") or [""])[0])


def _start(state, fixture) -> bool:
    """The first saved project is the U1 0.8 template with its own cube and its red and blue filaments."""
    if len(state["objects"]) != 1 or len(fixture["objects"]) != 1 or state["plates"] != fixture["plates"]:
        return False
    item, cube = state["objects"][0], fixture["objects"][0]
    mine = state["settings"].get("filament_colour")
    return (item["name"] == cube["name"] and _same(at_origin(item), at_origin(cube))
            and _printer(state["settings"]) == _printer(fixture["settings"])
            and mine == fixture["settings"].get("filament_colour") == [RED.upper(), BLUE.upper()] + list(mine or [])[2:])


def _accepts(call, *args) -> bool:
    try:
        call(*args)
    except UNREADABLE:
        return False
    return True


# --- one harvest ------------------------------------------------------------------

def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings (the two clauses recomputed among them) and what the counterexamples
    are built from. A reading that fails is reported False, never raised: a run whose expectation
    the product does not meet is reproduced here with its FAIL readings."""
    entries = manifest(directory, prefix)
    for entry in entries:      # every artifact the collector listed, before anything is read
        verified_part(directory, prefix, entries, entry["part"])
    analysis = json.loads(verified_part(directory, prefix, entries, "analysis.json").read_bytes().decode("utf-8-sig"))
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    record = json.dumps(analysis, ensure_ascii=False).encode("utf-8")
    geometry = _block(analysis, "fixture").get("geometry")
    if geometry not in GEOMETRIES:
        raise ValueError(f"the record names no known fixture geometry: {geometry!r}")
    dialogs, pictures = _dialog_pictures(analysis, [entry["part"] for entry in entries])
    try:
        paths = {part: verified_part(directory, prefix, entries, part) for part in (*PARTS, *PICTURES, *pictures)}
        raw = {part: path.read_bytes() for part, path in paths.items()}
        log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"a listed part could not be read ({type(exc).__name__})") from exc
    work = re.findall(r"^\[m7x228\] retained work directory: (.+?)[ \t\r]*$", log, re.M)
    expected = material_triangles(geometry)
    with TemporaryDirectory(prefix="replay-228-") as temporary:
        plain = Path(temporary)
        (plain / IMPORTED).write_bytes(raw[IMPORTED])
        (plain / PLATE).write_bytes(raw[PLATE])
        imported = as_recorded(painted_readings(plain / IMPORTED, SOURCE, expected))
        code = as_recorded(filament_readings(plain / PLATE, imported))
        # the oracle's own verdict on the archived files, read under the names the case gave them
        accepted = {"project": _accepts(verify_painted_import, plain / IMPORTED, SOURCE, expected),
                    "gcode": "error" not in code and _accepts(verify_filament_change, plain / PLATE, imported)}
    saved, walk, plate = _painted(raw[IMPORTED], geometry), _walk(raw[PLATE]), gcode(raw[PLATE])
    project_checks = _project_checks(saved)
    gcode_checks = _gcode_checks(walk, plate, saved["filaments"], saved["filament_colour"])
    checks = {"manifest_sizes_and_sha256_match": True,
              "start_is_the_redblue_template_with_its_cube": _start(project(raw[START]), project(FIXTURE.read_bytes())),
              **project_checks, **gcode_checks,
              "oracle_accepts_project": accepted["project"], "oracle_accepts_gcode": accepted["gcode"],
              **_record(analysis, raw, work, imported, code, geometry, dialogs, [raw[name] for name in pictures]),
              "pictures_are_pictures": all(_is_picture(raw[part], full=True) for part in PICTURES),
              "texture_is_the_fixture_picture": _texture(raw[TEXTURE])}
    dropped = sorted(set(POSITIVE) - set(checks))
    if dropped:
        raise ValueError(f"readings dropped: {dropped}")
    failed = [key for key in POSITIVE if checks[key] is not True]
    report = {"geometry": geometry, "faces": saved["faces"],
              # what each material's faces print with, what paint they carry and how many carry none
              "filaments": saved["filaments"], "paint_on_faces": saved["painted"],
              "unpainted_faces": saved["bare"],
              "filament_colours": saved["colours"], "filament_colour": saved["filament_colour"],
              "extruders": [saved["object_extruder"], saved["part_extruder"]],
              "tools_extruding": walk["extruding"], "tool_changes": len(walk["changes"]),
              "filament_used_mm": filament_used(plate), "generator": plate["generator"],
              "dialog_pictures": pictures, "work_directories": work,
              # the two clauses as they come out of the archived files, by the oracle and by the replay's own reading
              "clauses": {CLAUSE_COLORS: _verdict(imported), CLAUSE_FILAMENTS: _verdict(code)},
              "independent": {"clauses": {
                  CLAUSE_COLORS: _failed_names(project_checks), CLAUSE_FILAMENTS: _failed_names(gcode_checks)},
                  "oracle": {"checks": imported.get("checks"), "filaments": imported.get("filaments")},
                  "gcode": {"checks": code.get("checks"), "tools_extruding": code.get("tools_extruding"),
                            "change_count": code.get("change_count")}},
              "failed": failed}
    return checks, report, (dict(raw, **{"analysis.json": record}), saved, walk)


def _failed_names(checks) -> str:
    failed = [name for name, passed in checks.items() if not passed]
    return "PASS" if not failed else "FAIL (" + ", ".join(failed) + ")"


# --- counterexamples --------------------------------------------------------------

def _paint_value(state) -> str:
    """The paint value of an unsplit face painted with filament `state`: the bit layout
    colored_obj_oracle's module docstring describes, two bits of state in the last digit first."""
    if state < 3:
        return format(state << 2, "X")
    chunks, rest = [], state - 3
    while rest >= 15:
        chunks.append("F")
        rest -= 15
    chunks.append(format(rest, "X"))
    return "".join(reversed(chunks)) + "C"


def _repainted(raw, saved, choose, extruder):
    """The project with the paint of every face of its one part chosen again by `choose(material,
    number)` (the filament to paint, 0 for none) and the extruder of its object and its part set
    to `extruder` (None: neither names one)."""
    count = {material: 0 for material in MATERIALS}

    def paint(root):
        node = next(obj for obj in root.iter(CORE + "object") if obj.get("id") == saved["mesh_id"])
        triangles = node.find(f"{CORE}mesh/{CORE}triangles")
        for face_index, material in saved["order"]:
            count[material] += 1
            filament = choose(material, count[material] - 1)
            triangle = triangles[face_index]
            for key in [key for key in triangle.attrib if key.rsplit("}", 1)[-1] in PAINT_ATTRS]:
                del triangle.attrib[key]
            if filament:
                triangle.set("paint_color", _paint_value(filament))

    def extruders(rows):
        for node in (rows.find("object"), rows.find("object/part")):
            if node is None:
                continue
            for row in node.findall("metadata"):
                if row.get("key") == "extruder":
                    node.remove(row)
            if extruder is not None:
                node.insert(0, ET.Element("metadata", {"key": "extruder", "value": extruder}))

    files = archive(raw)
    files[saved["member"]] = _serialise(_edited(files[saved["member"]], saved["member"], paint))
    return with_settings(zipped(files), extruders)


def _edited(raw, name, edit):
    root = _xml(raw, name)
    edit(root)
    return root


def _rewritten(raw, keep_selects):
    """The G-code with the work of every tool but the first taken out: their extruding moves lose their
    E word, and their selects either stay (`keep_selects`) or name the first tool, in which case the
    filament note of the trailer is made to agree as a one-tool export writes it."""
    walk = _walk(raw)
    others = {tool for tool in walk["states"] if tool is not None and tool != walk["first"]}
    out = []
    for line, tool in zip(walk["lines"], walk["states"]):
        code, sep, comment = line.partition(";")
        words = code.split()
        token = words[0].upper() if words else ""
        other = tool in others
        if other and TOOL.fullmatch(token) and not keep_selects:
            out.append(f"T{walk['first']}" + sep + comment)
        elif other and token in ("G0", "G1") and E_WORD.search(code):
            out.append(E_WORD.sub("", code, count=1) + sep + comment)
        elif not keep_selects and line.startswith("; filament used [mm]"):
            note, _, values = line.partition("=")
            used = [0.0 if index in others else float(value) for index, value in enumerate(values.split(","))]
            out.append(f"{note}= " + ", ".join(f"{value:.2f}" for value in used))
        else:
            out.append(line)
    return "\n".join(out).encode("utf-8")


def _stand_ins(raw, saved, walk):
    """(label, how) for every counterexample of the row, each meant for a copy whose manifest agrees
    with the stand-in. Built from a passing run; the readings each must refuse are named in
    unit_tests/test_replay_colored_obj.py."""
    record = raw["analysis.json"]
    analysis = json.loads(record.decode("utf-8-sig"))
    chooser, fixture = _block(analysis, "chooser"), _block(analysis, "fixture")
    files = fixture.get("files") if isinstance(fixture.get("files"), dict) else {}
    dialogs = analysis.get("import_dialogs") if isinstance(analysis.get("import_dialogs"), list) else []
    size = png(raw["imported.png"])
    project_ = raw[IMPORTED]
    red_first = MATERIALS[0]

    def recorded(**changes):
        return json.dumps(dict(analysis, **changes), indent=2, ensure_ascii=False).encode("utf-8")

    unpainted = _repainted(project_, saved, lambda material, number: 0, "0")
    stand_ins = {
        # what the textured OBJ left on the guest: nothing painted, the object on extruder 0
        "unpainted_project_rejected": {"replace": {IMPORTED: unpainted}},
        # what the Kd-only OBJ left on the guest (run 9b3291c): the faces of the first filament without paint,
        # the object on the second filament, so both materials print with one filament
        "first_filament_left_unpainted_rejected": {"replace": {IMPORTED: _repainted(
            project_, saved, lambda material, number: 0 if material == red_first else 2, "2")}},
        "same_filament_on_both_materials_rejected": {"replace": {IMPORTED: _repainted(
            project_, saved, lambda material, number: 2, "2")}},
        "material_split_over_two_filaments_rejected": {"replace": {IMPORTED: _repainted(
            project_, saved, lambda material, number: 1 + number % 2 if material == red_first else 2, "1")}},
        # the faces named red are painted blue and those named blue red
        "colours_swapped_on_the_faces_rejected": {"replace": {IMPORTED: _repainted(
            project_, saved, lambda material, number: 2 if material == red_first else 1, "1")}},
        "monochrome_gcode_rejected": {"replace": {PLATE: _rewritten(raw[PLATE], keep_selects=False)}},
        "tool_selected_never_extruding_rejected": {"replace": {PLATE: _rewritten(raw[PLATE], keep_selects=True)}},
        "another_painted_project_rejected": {"replace": {IMPORTED: OTHER_PAINTED.read_bytes()}},
        "template_replaced_rejected": {"replace": {START: project_}},
        "manifest_mismatch_rejected": {"replace": {IMPORTED: b""}, "keep_manifest": False},
    }

    def same_colour(settings):
        settings["filament_colour"] = [settings["filament_colour"][0]] * 2 + list(settings["filament_colour"])[2:]

    stand_ins["same_colour_for_both_filaments_rejected"] = {"replace": {
        IMPORTED: with_project_settings(project_, same_colour)}}
    another = blank_png(16, 16)
    stand_ins["texture_replaced_rejected"] = {"replace": {
        TEXTURE: another, "analysis.json": recorded(fixture=dict(
            fixture, files=dict(files, **{TEXTURE: {"bytes": len(another), "sha256": sha256(another).hexdigest()}})))}}
    stand_ins["blank_screenshot_rejected"] = {"replace": {"imported.png": blank_png(size["width"], size["height"])}}
    stand_ins["chooser_entered_another_file_rejected"] = {"replace": {"analysis.json": recorded(
        chooser=dict(chooser, entered=str(PureWindowsPath(OTHER_RUN) / SOURCE)))}}
    stand_ins["export_receipt_edited_rejected"] = {"replace": {"analysis.json": recorded(
        export=dict(_block(analysis, "export"), file_sha256="0" * 64))}}
    stand_ins["fixture_record_edited_rejected"] = {"replace": {"analysis.json": recorded(
        fixture=dict(fixture, texture_referenced=True))}}
    # the route says both materials print with one filament, which no passing run records
    stand_ins["route_record_edited_rejected"] = {"replace": {"analysis.json": recorded(
        route=dict(_block(analysis, "route"), judged=dict(_block(_block(analysis, "route"), "judged"),
                                                           filaments={"red": 1, "blue": 1})))}}
    stand_ins["flattering_analysis_rejected"] = {"replace": {IMPORTED: unpainted,
                                                             "analysis.json": flattering(record, (CLAUSE_COLORS, CLAUSE_FILAMENTS))}}
    stand_ins["green_record_over_unpainted_files_rejected"] = {"replace": {
        IMPORTED: unpainted, PLATE: _rewritten(raw[PLATE], keep_selects=False)}}
    if dialogs:
        stand_ins["missing_dialog_picture_rejected"] = {"replace": {"analysis.json": recorded(
            import_dialogs=[dict(dialogs[0], image="import-dialog-9.png")])}}
    return list(stand_ins.items())


def _controls(directory, prefix, kept):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it: True when it
    was refused, and the readings that refused it."""
    controls, refused_by = {}, {}
    for label, how in _stand_ins(*kept):
        with copy_of(directory, prefix, **how) as (folder, altered):
            try:
                failed = _read(folder, altered)[1]["failed"]
            except ValueError as exc:
                failed = [f"unreadable ({exc})"]
        controls[label] = bool(failed)
        refused_by[label] = failed
    return controls, refused_by


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #228 harvest after the driver verified its log."""
    checks, report, kept = _read(directory, prefix)
    result = {"checks": dict(checks), "import": report}
    if not report["failed"]:
        controls, refused_by = _controls(directory, prefix, kept)
        result["checks"].update(controls)
        report["counterexamples"] = refused_by
    return result
