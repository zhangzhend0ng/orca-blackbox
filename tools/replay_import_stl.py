"""Recheck Feishu #227's imported STL from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
The STL and the four saved projects are then read twice, by
tests/import_stl_oracle.py and by the independent reader in
tests/file_io_replay_support.py:

* `cube_20mm.stl` is one binary 20 mm cube;
* `new-project.3mf` is the U1 0.8 template with its own cube, the start of the run;
* `imported.3mf` holds exactly that STL once, upright and unturned, 20 mm on
  each axis, on the one plate and on the bed, named after the file and
  pointing at the copy this run wrote;
* `moved.3mf` is the imported object and nothing else, 10 mm along X, which
  is what the Right key does to the selection;
* `rotated.3mf` is the moved object turned 45 degrees about the vertical axis,
  which is what PageUp does on 2.4.0.

What analysis.json records is held against these readings, against its own
content and against the case log: the chooser texts that offered *.stl and
the path entered there must agree with the log whose digest the receipt
carries; the words the sidebar and the selection panel showed must name the
import; the boxes, the move and the turn recorded must be what the saved
projects hold by the second reading too; and the keys recorded must be the
procedure's. How much each screenshot changed is reported, not judged: on the
green guest run the selections changed nothing measurable. Last, each
counterexample of the row is stood in for a harvested part on a temporary
copy of the run and must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path, PureWindowsPath
import sys
from tempfile import TemporaryDirectory

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from import_stl_oracle import listed_object_names, stl_filter_label, verify_imported, verify_moved, verify_rotated
from file_io_replay_support import (CORE, as_recorded, at_origin, blank_png, box, changed_share, close, compose,
                                    faces, flattering, grow, item_transform, manifest, moved_project, on_the_bed,
                                    paired, png, project, refused, shift, stl, stl_bytes, with_item_transform,
                                    with_model, with_project_settings, with_settings, work_directories)

CASE = 227
FIXTURE = ROOT / "fixtures" / "agent_layer_cube.3mf"      # the U1 0.8 template the run starts from
TEMPLATE_PRINTER, NOZZLE = "Snapmaker U1 (0.8 nozzle)", "0.8"
SOURCE, STEM = "cube_20mm.stl", "cube_20mm"
START, IMPORTED, MOVED, TURNED = "new-project.3mf", "imported.3mf", "moved.3mf", "rotated.3mf"
PICTURES = ("chooser.png", "imported.png", "moved-before.png", "moved-selected.png", "moved.png",
            "rotated-before.png", "rotated-selected.png", "rotated.png")
CLAUSES = ("弹出文件选择对话框，格式筛选含 *.stl", "模型出现在盘上，尺寸显示 20×20×20mm",
           "对象列表新增 1 个对象", "可选中/平移", "可旋转")
SIDE, MOVE, TURN_DEG, TOL = 20.0, 10.0, 45.0, 1e-4
# the keys the procedure presses on the canvas: Right moves the selection, PageUp turns it (2.4.0)
KEYS = {"move": "0x27", "turn": "0x21"}
PHASES = ("moved", "rotated")
OTHER_RUN = r"C:\coil\orca-blackbox-v3-r1\artifacts\feishu-object-cases\227\run-elsewhere"
TILT = (1.0, 0.0, 0.0, 0.0, 0.7071067811865476, 0.7071067811865476,      # 45 degrees about X
        0.0, -0.7071067811865476, 0.7071067811865476, 0.0, 0.0, 0.0)
UNREADABLE = (ValueError, OSError, KeyError, TypeError)
START_READINGS = ("start_is_the_u1_template_with_its_cube",)
IMPORTED_READINGS = ("imported_once", "imported_on_the_plate", "imported_is_the_stl_upright", "imported_is_20_mm",
                     "imported_named_after_the_file", "imported_points_at_this_runs_file", "imported_on_the_bed")
MOVED_READINGS = ("moved_once_on_the_plate", "moved_is_the_import_10_mm_along_x", "moved_on_the_bed")
TURNED_READINGS = ("rotated_once_on_the_plate", "rotated_is_the_moved_turned_45_degrees", "rotated_on_the_bed")
RECORD_READINGS = ("recorded_source_matches_file", "recorded_readings_match_files",
                   "recorded_verdict_matches_readings", "chooser_record_offers_stl", "filter_text_is_in_the_case_log",
                   "chooser_entered_this_runs_file", "object_list_names_the_import", "sidebar_names_the_import",
                   "selection_names_the_import", "chooser_picture_matches_record", "recorded_boxes_match_projects",
                   "keys_are_the_procedure_s", "printer_as_recorded", "editor_left_running")
POSITIVE = ("manifest_sizes_and_sha256_match", "source_is_a_binary_20_mm_cube", *START_READINGS, *IMPORTED_READINGS,
            "printer_unchanged_throughout", *MOVED_READINGS, *TURNED_READINGS, *RECORD_READINGS,
            "pictures_are_pictures", "oracle_accepts_the_three_projects")


@lru_cache(maxsize=8)
def _fixture():
    return FIXTURE.read_bytes()


@lru_cache(maxsize=8)
def _project(raw: bytes) -> dict:
    """`project`, kept per content: the counterexamples keep most of the harvest as it is."""
    return project(raw)


def _as_loaded(value):
    """A setting as the fixture holds it, before the app appended the opened file's name to a preset ID."""
    if isinstance(value, str) and value.startswith(TEMPLATE_PRINTER + "(") and value.endswith(")"):
        return TEMPLATE_PRINTER
    return value


def _printer(settings):
    """What identifies the selected printer, in a form that can be compared and hashed."""
    return tuple(tuple(value) if isinstance(value, list) else value
                 for value in (_as_loaded(settings.get(key))
                               for key in ("printer_model", "printer_settings_id", "nozzle_diameter")))


def _cube(raw: bytes) -> bool:
    """Whether a binary STL holds one cube of the side the row names: eight corners, two coordinates
    a side apart on each axis, twelve triangles each lying in one face of the cube."""
    try:
        _header, triangles = stl(raw)
    except ValueError:
        return False
    corners = sorted({corner for triangle in triangles for corner in triangle})
    if len(triangles) != 12 or len(corners) != 8:
        return False
    for axis in range(3):
        values = sorted({corner[axis] for corner in corners})
        if len(values) != 2 or abs(values[1] - values[0] - SIDE) > 1e-6:
            return False
    return all(any(len({corner[axis] for corner in triangle}) == 1 for axis in range(3)) for triangle in triangles)


def _sole(state):
    """(the project holds exactly one object, that object or None, it sits on the project's only plate)."""
    objects = state["objects"]
    one = len(objects) == 1
    return one, objects[0] if one else None, one and state["plates"] == [objects[0]["plate"]]


def _same(first, second) -> bool:
    """Whether two sets of triangles are one set to the tolerance, every corner paired with one."""
    if len(first) != len(second):
        return False
    pairs, worst = paired(tuple(first), tuple(second))
    return None not in pairs and worst <= TOL


def _placed(triangles, offset):
    """A set of triangles moved by `offset`."""
    return faces([tuple(c + o for c, o in zip(corner, offset)) for triangle in triangles for corner in triangle])


def _turned(first, second, degrees) -> bool:
    """Whether `second` is `first` turned by `degrees` about a vertical axis, one way or the other.
    Wherever the pivot was, the turned set is moved to share the other's centre before comparing."""
    if len(first) != len(second):
        return False
    corners = [corner for triangle in first for corner in triangle]
    x0, x1, y0, y1, _, _ = box(corners)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def centre(points):
        return [sum(point[axis] for point in points) / len(points) for axis in range(3)]

    target = centre([corner for triangle in second for corner in triangle])
    for sign in (1, -1):
        angle = math.radians(sign * degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        around = [(cx + (x - cx) * cosine - (y - cy) * sine, cy + (x - cx) * sine + (y - cy) * cosine, z)
                  for x, y, z in corners]
        by = centre(around)
        pairs, worst = paired(faces([(x + t - o) for x, t, o in zip(corner, target, by)] for corner in around),
                              tuple(second))
        if None not in pairs and worst <= TOL:
            return True
    return False


def _start(template, fixture) -> dict:
    """The first saved project is the U1 0.8 template with its own cube on the plate."""
    one, item, on_plate = _sole(template)
    (cube,) = fixture["objects"]
    return {START_READINGS[0]: one and on_plate and item["name"] == cube["name"]
            and at_origin(item) == at_origin(cube)
            and _printer(template["settings"]) == _printer(fixture["settings"])
            and str(fixture["settings"].get("nozzle_diameter", [""])[0]) == NOZZLE}


def _imported(state, source, work) -> tuple:
    """The project saved after the import, on its own and against the STL. Returns the readings and
    the imported object, when the project holds exactly one."""
    one, item, on_plate = _sole(state)
    checks = dict.fromkeys(IMPORTED_READINGS, False)
    checks.update(imported_once=one, imported_on_the_plate=on_plate)
    if not one:
        return checks, None
    corners = [corner for triangle in source for corner in triangle]
    held = box(corners)
    offset = (item["box"][0] - held[0], item["box"][2] - held[2], item["box"][4] - held[4])
    recorded = PureWindowsPath(item["source_file"]) if isinstance(item["source_file"], str) else None
    checks.update({
        "imported_is_the_stl_upright": _same(_placed(source, offset), item["triangles"]),
        "imported_is_20_mm": all(abs(high - low - SIDE) <= 1e-4
                                 for low, high in zip(item["box"][0::2], item["box"][1::2])),
        "imported_named_after_the_file": item["name"] in (STEM, SOURCE),
        "imported_points_at_this_runs_file": recorded is not None and recorded.name.casefold() == SOURCE
        and len(work) == 1 and recorded.parent == PureWindowsPath(work[0]),
        "imported_on_the_bed": on_the_bed(state["settings"], item),
    })
    return checks, item


def _moved_step(before, after) -> dict:
    """The project saved after the move: the imported object 10 mm along X, and nothing else."""
    one, item, on_plate = _sole(after)
    previous = _sole(before)[1]
    checks = {"moved_once_on_the_plate": one and on_plate, "moved_is_the_import_10_mm_along_x": False,
              "moved_on_the_bed": False}
    if one and previous is not None:
        delta = [b - a for a, b in zip(previous["box"], item["box"])]
        checks["moved_is_the_import_10_mm_along_x"] = (
            item["name"] == previous["name"]
            and all(abs(a - b) <= 1e-4 for a, b in zip(delta, (MOVE, MOVE, 0.0, 0.0, 0.0, 0.0)))
            and _same(_placed(previous["triangles"], (MOVE, 0.0, 0.0)), item["triangles"]))
        checks["moved_on_the_bed"] = on_the_bed(after["settings"], item)
    return checks


def _turned_step(before, after) -> dict:
    """The project saved after the turn: the moved object turned 45 degrees about the vertical axis."""
    one, item, on_plate = _sole(after)
    previous = _sole(before)[1]
    checks = {"rotated_once_on_the_plate": one and on_plate, "rotated_is_the_moved_turned_45_degrees": False,
              "rotated_on_the_bed": False}
    if one and previous is not None:
        checks["rotated_is_the_moved_turned_45_degrees"] = (
            item["name"] == previous["name"] and _turned(previous["triangles"], item["triangles"], TURN_DEG))
        checks["rotated_on_the_bed"] = (
            on_the_bed(after["settings"], item)
            and abs((item["box"][5] - item["box"][4]) - (previous["box"][5] - previous["box"][4])) <= 1e-4)
    return checks


def _boxed(words):
    """OCR words as boxes, each on a line of its own so that no two of them are merged into one name."""
    return [[str(word), 0, 10 * index, 1, 1] for index, word in enumerate(words)]


def _names(words) -> bool:
    """Whether OCR words name the import exactly once, with the oracle's tolerance for a misread character."""
    try:
        return (isinstance(words, list) and bool(words) and all(isinstance(word, str) for word in words)
                and bool(listed_object_names(_boxed(words), [STEM])))
    except ValueError:
        return False


def _pairs(item) -> list:
    """An object's box as the oracle writes it: [low, high] for each axis."""
    return [[item["box"][0], item["box"][1]], [item["box"][2], item["box"][3]], [item["box"][4], item["box"][5]]]


def _boxes(analysis, states) -> bool:
    """Whether the boxes, the move and the turn the case recorded are what the saved projects hold, read
    by the independent reader and not by the oracle that wrote the record."""
    imported, moved, turned = (_sole(state)[1] for state in states[1:])
    if any(item is None for item in (imported, moved, turned)):
        return False
    first, second, third = analysis.get("imported"), analysis.get("moved"), analysis.get("rotated")
    if not all(isinstance(block, dict) for block in (first, second, third)):
        return False
    extents = [round(high - low, 6) for low, high in zip(imported["box"][0::2], imported["box"][1::2])]
    return (
        close(first.get("world_box_mm"), _pairs(imported), 1e-3)
        and close(first.get("dimensions_mm"), extents, 1e-3) and first.get("triangles") == len(imported["triangles"])
        and close(second.get("before_box_mm"), _pairs(imported), 1e-3)
        and close(second.get("after_box_mm"), _pairs(moved), 1e-3) and close(second.get("delta_mm"), (MOVE, 0.0, 0.0), 1e-4)
        and close(third.get("before_box_mm"), _pairs(moved), 1e-3)
        and close(third.get("after_box_mm"), _pairs(turned), 1e-3)
        and abs(_number(third.get("degrees_about_z")) - TURN_DEG) <= 1e-6)


def _record(analysis, raw, work, log, readings, states) -> dict:
    """What the GUI recorded, held against the files, against its own content and against the case log."""
    template = states[0]
    chooser = analysis.get("chooser") if isinstance(analysis.get("chooser"), dict) else {}
    title = chooser.get("title") if isinstance(chooser.get("title"), str) else ""
    labels = [text for text in chooser.get("labels") or [] if isinstance(text, str)]
    filters = [item for group in chooser.get("types") or [] if isinstance(group, dict)
               for item in group.get("items") or [] if isinstance(item, str)]
    rows = [row for row in chooser.get("import_rows") or [] if isinstance(row, dict)]
    stl_rows = [row for row in rows if "stl" in str(row.get("label", "")).casefold() and row.get("enabled") is True]
    offered = stl_filter_label([title, *labels, *filters])
    sidebar = analysis.get("sidebar") if isinstance(analysis.get("sidebar"), dict) else {}
    selection = analysis.get("selection") if isinstance(analysis.get("selection"), dict) else {}
    entered = chooser.get("entered")
    try:
        picture = png(raw["chooser.png"])
    except ValueError:
        picture = None
    printer = {"model": template["settings"].get("printer_model"),
               "profile": template["settings"].get("printer_settings_id")}
    imported = analysis.get("imported") if isinstance(analysis.get("imported"), dict) else {}
    return {
        "recorded_source_matches_file": analysis.get("source") == {
            "name": SOURCE, "bytes": len(raw[SOURCE]), "sha256": sha256(raw[SOURCE]).hexdigest()},
        "recorded_readings_match_files": all(
            analysis.get(key) == readings[key] for key in ("imported", "moved", "rotated")),
        "recorded_verdict_matches_readings": isinstance(analysis.get("results"), dict) and all(
            analysis["results"].get(clause) == "PASS" for clause in CLAUSES),
        # the recorded filter text is one of the recorded chooser's own texts, and the dialog did close
        "chooser_record_offers_stl": bool(offered) and chooser.get("stl_filter") == offered
        and chooser.get("dialog_closed") is True and len(stl_rows) == 1
        and "stl" in str(chooser.get("row", "")).casefold(),
        # and the receipt-hashed case log printed that same text
        "filter_text_is_in_the_case_log": bool(offered) and offered in log,
        "chooser_entered_this_runs_file": len(work) == 1 and isinstance(entered, str)
        and PureWindowsPath(entered) == PureWindowsPath(work[0]) / SOURCE,
        # the object list read after the import, and the sidebar words read right after it, name the import
        "object_list_names_the_import": _names(analysis.get("object_list_name")),
        "sidebar_names_the_import": _names(sidebar.get("imported")),
        # so do the panel words read after each Select All, which is how the object was selected
        "selection_names_the_import": all(
            isinstance(selection.get(phase), dict) and selection[phase].get("menu") == "Select All"
            and _names(selection[phase].get("panel_words")) for phase in PHASES),
        "chooser_picture_matches_record": picture is not None and chooser.get("image") == {
            "width_px": picture["width"], "height_px": picture["height"]},
        "recorded_boxes_match_projects": _boxes(analysis, states),
        "keys_are_the_procedure_s": analysis.get("keys") == KEYS,
        "printer_as_recorded": analysis.get("initial_printer") == printer and imported.get("printer") == printer,
        "editor_left_running": analysis.get("editor_at_end") == {"alive": True, "dialog": None},
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pictures(raw) -> bool:
    """Every retained screenshot is a picture with something in it."""
    for part in PICTURES:
        try:
            facts = png(raw[part])
        except ValueError:
            return False
        if not (facts["format"] == "PNG" and facts["width"] >= 640 and facts["height"] >= 400
                and facts["gray_levels"] >= 32 and facts["std"] >= 5):
            return False
    return True


def _screen_changes(raw) -> dict:
    """How much of the picture changed around each action: the share of pixels that differ by 24
    levels or more. Kept for the record only: on the green guest run of 0d7222e7 the two selections
    changed nothing measurable and the move and the turn about a thousandth of the picture, so no
    threshold would tell an action from a copied screenshot."""
    return {action: changed_share(raw[first], raw[second]) for action, (first, second) in {
        "select": ("moved-before.png", "moved-selected.png"), "move": ("moved-selected.png", "moved.png"),
        "reselect": ("rotated-before.png", "rotated-selected.png"),
        "turn": ("rotated-selected.png", "rotated.png")}.items()}


def _oracle(call, *args):
    try:
        return as_recorded(call(*args))
    except UNREADABLE as exc:
        return {"refused": f"{type(exc).__name__}: {exc}"}


def _kept(state):
    """An object as the report shows it, or None when the project does not hold exactly one."""
    one, item, on_plate = _sole(state)
    if item is None:
        return None
    return {"name": item["name"], "plate": item["plate"], "box_mm": item["box"], "on_the_one_plate": on_plate,
            "source_file": item["source_file"]}


def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings and what the counterexamples are built from."""
    entries = manifest(directory, prefix)
    try:
        paths = {part: verified_part(directory, prefix, entries, part)
                 for part in (SOURCE, START, IMPORTED, MOVED, TURNED, *PICTURES, "analysis.json")}
        raw = {part: path.read_bytes() for part, path in paths.items()}
        log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"an artifact could not be read ({type(exc).__name__})") from exc
    analysis = json.loads(raw["analysis.json"].decode("utf-8-sig"))
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    work = work_directories(log, "m7x227")
    template, imported, moved, turned = (_project(raw[part]) for part in (START, IMPORTED, MOVED, TURNED))
    fixture, source = _project(_fixture()), stl(raw[SOURCE])[1]
    with TemporaryDirectory(prefix="replay-source-") as temporary:
        # the oracle wants the STL under the name the case gave it, not under the harvest's prefix
        plain = Path(temporary) / SOURCE
        plain.write_bytes(raw[SOURCE])
        readings = {"imported": _oracle(verify_imported, paths[IMPORTED], plain),
                    "moved": _oracle(verify_moved, paths[IMPORTED], paths[MOVED]),
                    "rotated": _oracle(verify_rotated, paths[MOVED], paths[TURNED])}
    imported_checks, _item = _imported(imported, source, work)
    states = (template, imported, moved, turned)
    checks = {"manifest_sizes_and_sha256_match": True, "source_is_a_binary_20_mm_cube": _cube(raw[SOURCE]),
              **_start(template, fixture), **imported_checks,
              "printer_unchanged_throughout": len({_printer(state["settings"]) for state in states}) == 1,
              **_moved_step(imported, moved), **_turned_step(moved, turned),
              **_record(analysis, raw, work, log, readings, states), "pictures_are_pictures": _pictures(raw),
              "oracle_accepts_the_three_projects": all("refused" not in reading for reading in readings.values())}
    dropped = sorted(set(POSITIVE) - set(checks))
    if dropped:
        raise ValueError(f"readings dropped: {dropped}")
    try:
        changes = _screen_changes(raw)
    except (OSError, ValueError):
        changes = None
    report = {"case": CASE, "source": {"bytes": len(raw[SOURCE]), "sha256": sha256(raw[SOURCE]).hexdigest()},
              "start": _kept(template), "imported": _kept(imported), "moved": _kept(moved), "rotated": _kept(turned),
              "work_directories": work, "screen_changes": changes, "oracle": readings,
              "failed": [key for key in POSITIVE if not checks[key]]}
    return checks, report, (raw, work)


# --- counterexamples --------------------------------------------------------------

def _cube_stl(side: float) -> bytes:
    """A binary STL of a cube with the given side, written the way the case writes its 20 mm one."""
    points = ((0, 0, 0), (side, 0, 0), (side, side, 0), (0, side, 0), (0, 0, side), (side, 0, side),
              (side, side, side), (0, side, side))
    triangles = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
                 (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
    return stl_bytes(b"Orca black-box #251 cube".ljust(80, b"\0"),
                     [tuple(points[index] for index in triangle) for triangle in triangles])


def _tetrahedron() -> bytes:
    """A binary STL that is a whole mesh and no cube."""
    a, b, c, d = (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), (0.0, 20.0, 0.0), (0.0, 0.0, 20.0)
    return stl_bytes(bytes(80), [(a, c, b), (a, b, d), (a, d, c), (b, c, d)])


def _emptied(raw: bytes) -> bytes:
    """The project with nothing on its plate: no build item, no object, no instance."""
    def clear_model(root):
        for item in root.findall(f"{CORE}build/{CORE}item"):
            root.find(f"{CORE}build").remove(item)

    def clear_settings(root):
        for row in root.findall("object"):
            root.remove(row)
        for plate in root.findall("plate"):
            for row in plate.findall("model_instance"):
                plate.remove(row)

    return with_settings(with_model(raw, clear_model), clear_settings)


def _twice(raw: bytes) -> bytes:
    """The project with a second copy of its only object beside it, as a second import would leave it."""
    second = "9"

    def more_model(root):
        (item,) = root.findall(f"{CORE}build/{CORE}item")
        (outer,) = [node for node in root.findall(f"{CORE}resources/{CORE}object")
                    if node.get("id") == item.get("objectid")]
        values = [float(word) for word in item.get("transform").split()]
        values[10] += 30
        copy, clone = deepcopy(outer), deepcopy(item)
        copy.set("id", second)
        clone.set("objectid", second)
        clone.set("transform", " ".join(f"{value:g}" for value in values))
        for node in (copy, clone):
            for name in [key for key in node.attrib if key.endswith("}UUID")]:
                del node.attrib[name]
        root.find(f"{CORE}resources").append(copy)
        root.find(f"{CORE}build").append(clone)

    def more_settings(root):
        (row,) = root.findall("object")
        copy = deepcopy(row)
        copy.set("id", second)
        root.insert(list(root).index(row) + 1, copy)
        clone = deepcopy(root.find("plate/model_instance"))
        next(meta for meta in clone.findall("metadata") if meta.get("key") == "object_id").set("value", second)
        root.find("plate").append(clone)

    return with_settings(with_model(raw, more_model), more_settings)


def _off_plate(root):
    """Take the only object off the plate's list of instances."""
    (obj,) = root.findall("object")
    for plate in root.findall("plate"):
        for row in plate.findall("model_instance"):
            named = next((meta.get("value") for meta in row.findall("metadata") if meta.get("key") == "object_id"),
                         None)
            if named == obj.get("id"):
                plate.remove(row)


def _other_file(root):
    """Let the imported object name a copy of the STL in another run's directory."""
    field = root.find("./object/part/metadata[@key='source_file']")
    if field is not None:
        field.set("value", str(PureWindowsPath(OTHER_RUN) / SOURCE))


def _smaller_bed(settings):
    """A bed that no longer lies under the object that was moved along X."""
    settings["printable_area"] = ["0x0", "100x0", "100x100", "0x100"]


def _stand_ins(raw) -> list:
    """(label, what is stood in and how) for every counterexample of the row.

    Each entry is meant for `refused` on a copy whose manifest agrees with the stand-in."""
    imported, moved, record = raw[IMPORTED], raw[MOVED], raw["analysis.json"]
    x0, x1, y0, y1, z0, z1 = _sole(_project(imported))[1]["box"]
    centre = ((x0 + x1) / 2 + MOVE, (y0 + y1) / 2, (z0 + z1) / 2)
    tilted = compose(compose(shift(*centre), TILT),
                     compose(shift(-centre[0], -centre[1], -centre[2]), item_transform(moved)))
    analysis = json.loads(record.decode("utf-8-sig"))
    chooser = analysis.get("chooser") if isinstance(analysis.get("chooser"), dict) else {}
    selection = analysis.get("selection") if isinstance(analysis.get("selection"), dict) else {}
    size = png(raw["imported.png"])

    def recorded(**changes):
        return json.dumps(dict(analysis, **changes), indent=2, ensure_ascii=False).encode("utf-8")

    return [
        # the run did not start from the template: its first saved project already holds the import
        ("start_replaced_rejected", {"replace": {START: imported}}),
        ("empty_plate_rejected", {"replace": {IMPORTED: _emptied(raw[START])}}),
        # a 30 mm cube that calls itself cube_20mm.stl, imported faithfully
        ("thirty_mm_cube_rejected", {"replace": {
            SOURCE: _cube_stl(30.0),
            IMPORTED: with_item_transform(imported, compose(grow(1.5), item_transform(imported)))}}),
        ("two_objects_rejected", {"replace": {IMPORTED: _twice(imported)}}),
        ("object_off_the_plate_rejected", {"replace": {IMPORTED: with_settings(imported, _off_plate)}}),
        # the same import, floating 5 mm above the bed
        ("imported_off_the_bed_rejected", {"replace": {
            IMPORTED: with_item_transform(imported, compose(shift(0.0, 0.0, 5.0), item_transform(imported)))}}),
        ("move_reversed_rejected", {"replace": {MOVED: moved_project(imported, dx=-MOVE)}}),
        ("move_along_y_rejected", {"replace": {MOVED: moved_project(imported, dy=MOVE)}}),
        # the move itself is right; the bed saved with it no longer lies under the object
        ("moved_off_the_bed_rejected", {"replace": {MOVED: with_project_settings(moved, _smaller_bed)}}),
        ("turn_left_out_rejected", {"replace": {TURNED: moved}}),
        ("turn_about_x_rejected", {"replace": {TURNED: with_item_transform(moved, tilted)}}),
        ("template_as_import_rejected", {"replace": {IMPORTED: raw[START]}}),
        ("another_runs_file_rejected", {"replace": {IMPORTED: with_settings(imported, _other_file)}}),
        ("source_not_a_cube_rejected", {"replace": {SOURCE: _tetrahedron()}}),
        # a screenshot replaced by an empty picture of the same size
        ("blank_screenshot_rejected", {"replace": {"imported.png": blank_png(size["width"], size["height"])}}),
        # a filter text that neither the recorded chooser nor the case log ever showed
        ("invented_filter_rejected",
         {"replace": {"analysis.json": recorded(chooser=dict(chooser, stl_filter="*.stl"))}}),
        ("chooser_entered_another_file_rejected", {"replace": {"analysis.json": recorded(
            chooser=dict(chooser, entered=str(PureWindowsPath(OTHER_RUN) / SOURCE)))}}),
        ("manifest_mismatch_rejected", {"replace": {IMPORTED: b""}, "keep_manifest": False}),
        ("edited_analysis_rejected", {"replace": {IMPORTED: raw[START],
                                                  "analysis.json": flattering(record, CLAUSES)}}),
        # the panel words after Select All name an object the plate does not hold (one misread character
        # is forgiven by the oracle, so this name is three away from the import's)
        ("selection_names_another_object_rejected", {"replace": {"analysis.json": recorded(
            selection={phase: dict(selection.get(phase) or {}, panel_words=["Plate", "object", "box_20mm.stl"])
                       for phase in PHASES})}}),
        # the sidebar read after the import names nothing
        ("sidebar_names_nothing_rejected", {"replace": {"analysis.json": recorded(sidebar={"imported": []})}}),
        # a box recorded a millimetre away from where the saved project holds the object
        ("recorded_box_edited_rejected", {"replace": {"analysis.json": recorded(
            moved=dict(analysis.get("moved") or {},
                       after_box_mm=[[136.5, 156.5], [126.0, 146.0], [0.0, 20.0]]))}}),
        # another key than the procedure's
        ("another_key_pressed_rejected", {"replace": {"analysis.json": recorded(keys={"move": "0x25", "turn": "0x21"})}}),
    ]


def _controls(directory, prefix, kept):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it."""
    return {label: refused(_read, POSITIVE, directory, prefix, **how) for label, how in _stand_ins(kept[0])}


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #227 harvest after the driver verified its log."""
    checks, report, kept = _read(directory, prefix)
    result = {"checks": checks, "import": report}
    if not report["failed"]:
        result["checks"].update(_controls(directory, prefix, kept))
    return result
