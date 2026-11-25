"""Feishu #228 replayed offline: a synthetic passing harvest for tools/replay_colored_obj.py and each
of its counterexamples.

The positive is built here with zipfile from what the application really wrote: the #227 project
(one imported 20 mm STL) with its mesh exchanged for the fixture's two boxes, named after the OBJ and
left as the OBJ import of 2.4.0 leaves it (the faces of the first filament without paint, those of
the second painted ``8``), and the #236 G-code with one tool change inserted in the shape the real
five-tool export 0ac8ba5d shows. The recorded digests of the fixture files are those of the guest
run dev228c-9b3291c, where the application saved that OBJ with the faces of the red material
unpainted and printed with one tool: the real files of that run are stood in when they are on this
machine, and every counterexample is refused by a reading of its own.

Nothing here imports a module that can move the real mouse or keyboard: an autouse fixture replaces
the Win32 calls and the functions named in the task with sentinels that fail the test, and refuses
the import of every GUI-driving module.
"""
from hashlib import sha256
from io import BytesIO
import importlib
import json
from pathlib import Path
import struct
import sys
import zlib
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from colored_obj_oracle import (  # noqa: E402
    CLAUSE_COLORS, CLAUSE_FILAMENTS, decode_paint, filament_readings, material_triangles, painted_readings)
from file_io_replay_support import CORE, MAIN, PROD, archive, as_recorded, copy_of, manifest, png, project, zipped  # noqa: E402
from tools import replay_colored_obj as colored  # noqa: E402
from tools.replay_case_evidence import ADAPTERS, replay_receipt  # noqa: E402

EVIDENCE = ROOT / "docs/runs/evidence"
REAL_227 = EVIDENCE / "feishu-227-2026-11-26/11858f17-run1-imported.3mf"
REAL_236 = EVIDENCE / "feishu-236-2026-11-26/48e3aa7d-run1-plate.gcode"
REAL_202 = EVIDENCE / "feishu-140-201-202-2026-11-25/row-202-hyperv/7a7a584f-after-save-as.3mf"
# the guest run whose judged OBJ printed with one colour; outside the repository and not required
REAL_RED = Path("C:/coil/vm_setup/elevenhour_1125/runs/dev228c-9b3291cc/m7x_228_import_colored_obj-1")
PREFIX = "abc12345-run1"
MESH, OBJECT_SETTINGS, PROJECT = "3D/Objects/cube_20mm.stl_2.model", "Metadata/model_settings.config", \
    "Metadata/project_settings.config"
WORK = "C:\\coil\\orca-blackbox-v3-r1\\artifacts\\feishu-object-cases\\228\\run-synthetic"
RED, BLUE = "#FF0000", "#0000FF"
# what the case wrote for its Kd-only fixture on the guest (run dev228c-9b3291c)
GUEST_FIXTURE = {"model.obj": (522, "9b892eb0455fc920b7840583a3bfca1ddcfbb27785874e979bf8cd3b27d41aa5"),
                 "model.mtl": (89, "ba697704148a55a679125232360f54590475dcafc86da7da1fe96e999db53702"),
                 "texture.png": (79, "204f864f62153665a75f20ece9f0fd6ece67de16f87a63690a96898ebb1eef9c")}
GUI = {"winutil", "topbar_util", "export_util", "mix_dialog_util", "mixing_util", "add_shape", "process_panel",
       "native_script_baseline", "agent_project_ui", "colored_obj_cases", "file_export_cases", "m7_common",
       "m8_common", "m5_common", "m3_common", "plate_reserve_case", "m7x_228_import_colored_obj",
       "m7x_227_import_stl", "m7x_244_add_model", "m7x_249_add_part", "m7x_236_export_gcode"}
WIN32 = ("SendInput", "SetCursorPos", "mouse_event", "keybd_event")
NAMED = ("real_click_screen", "real_right_click_screen", "real_wheel_screen", "real_drag_screen",
         "_send_keys", "_send_chars")


# --- no real input can be reached -------------------------------------------------

class RefuseGui:
    """A finder that fails the import of any module that drives the GUI."""

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[-1] in GUI or name == "tests.gui" or name.startswith("tests.gui."):
            raise AssertionError(f"the #228 replay reached for the GUI module {name}")
        return None


@pytest.fixture(autouse=True)
def no_real_input(monkeypatch):
    """The lowest-level real input calls become sentinels, and no GUI-driving module can be imported."""
    for name in list(sys.modules):
        if name.split(".")[-1] in GUI or name.startswith("tests.gui"):
            monkeypatch.delitem(sys.modules, name)
    # harness.winutil only binds the WinDLL handles at import; it is loaded once, on purpose, before
    # the refusing finder is in place, so that its real-input entry points can be replaced
    if "harness.winutil" not in sys.modules:
        with monkeypatch.context() as plain:
            importlib.import_module("harness.winutil")
        del plain
    winutil = sys.modules["harness.winutil"]
    reached = []

    def sentinel(name):
        def refuse(*_args, **_kwargs):
            reached.append(name)
            raise AssertionError(f"the #228 replay called {name}")
        return refuse

    for name in NAMED:
        for module in [sys.modules["harness.winutil"], *(sys.modules[member] for member in list(sys.modules)
                                                        if member.split(".")[-1] in GUI)]:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, sentinel(name))
    for name in WIN32:
        monkeypatch.setattr(winutil.user32, name, sentinel(name), raising=False)
    monkeypatch.setattr(sys, "meta_path", [RefuseGui(), *sys.meta_path])
    yield reached
    assert reached == [], reached
    # harness.winutil itself stays loaded: its entry points are the sentinels above
    assert not [name for name in sys.modules if name != "harness.winutil"
                and (name.split(".")[-1] in GUI or name.startswith("tests.gui"))]


# --- the fixture, as the case writes it --------------------------------------------

def _png(pixels):
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in pixels)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    header = struct.pack(">IIBBBBB", len(pixels[0]), len(pixels), 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def fixture_files():
    """``model.obj``, ``model.mtl`` and ``texture.png`` of the Kd-only fixture, written as
    tests/colored_obj_cases.py writes them (no texture referenced, no UVs)."""
    from colored_obj_oracle import MATERIALS, mesh_geometry

    vertices, faces = mesh_geometry("two-boxes")
    lines = [f"mtllib model.mtl", "# Feishu #228: a 20 mm cube, the left half red and the right half blue"]
    lines += [f"v {x:g} {y:g} {z:g}" for x, y, z in vertices]
    for material in MATERIALS:
        lines.append(f"usemtl {material}")
        lines += ["f %d %d %d" % (i + 1, j + 1, k + 1) for i, j, k, owner in faces if owner == material]
    return {"model.obj": ("\n".join(lines) + "\n").encode("ascii"),
            "model.mtl": "\n".join(["# Feishu #228: two materials", "newmtl red", "Ka 0 0 0", "Kd 1 0 0", "",
                                    "newmtl blue", "Ka 0 0 0", "Kd 0 0 1", ""]).encode("ascii"),
            "texture.png": _png([[(255, 0, 0)] * 16 for _ in range(16)])}


# --- the synthetic passing harvest -------------------------------------------------

def encode(state):
    if state < 3:
        return format(state << 2, "X")
    chunks, rest = [], state - 3
    while rest >= 15:
        chunks.append("F")
        rest -= 15
    chunks.append(format(rest, "X"))
    return "".join(reversed(chunks)) + "C"


def mesh_xml(faces):
    """A mesh member whose triangles are `(corners, paint value or None)`, with its vertices indexed."""
    ET.register_namespace("", CORE[1:-1])
    model = ET.Element(CORE + "model", {"unit": "millimeter"})
    mesh = ET.SubElement(ET.SubElement(ET.SubElement(model, CORE + "resources"), CORE + "object", {"id": "1"}),
                         CORE + "mesh")
    vertices, triangles = ET.SubElement(mesh, CORE + "vertices"), ET.SubElement(mesh, CORE + "triangles")
    index = {}
    for corners, paint in faces:
        ids = []
        for corner in corners:
            if tuple(corner) not in index:
                index[tuple(corner)] = str(len(index))
                ET.SubElement(vertices, CORE + "vertex", dict(zip("xyz", (str(value) for value in corner))))
            ids.append(index[tuple(corner)])
        attrs = dict(zip(("v1", "v2", "v3"), ids))
        if paint is not None:
            attrs["paint_color"] = paint
        ET.SubElement(triangles, CORE + "triangle", attrs)
    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def object_settings(raw, extruder="1"):
    """The real #227 record with its object and its part named after the OBJ and both extruders set as
    given; the part names the OBJ it was imported from."""
    root = ET.fromstring(raw)
    for node, keys in ((root.find("object"), ("extruder", "name")),
                       (root.find("object/part"), ("extruder", "name", "source_file"))):
        for row in node.findall("metadata"):
            if row.get("key") in keys:
                node.remove(row)
        for index, (key, value) in enumerate(zip(keys, (extruder, "model.obj", WORK + "\\model.obj"))):
            node.insert(index, ET.Element("metadata", {"key": key, "value": value}))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def two_colours(raw):
    settings = json.loads(raw)
    settings["filament_colour"] = [RED, BLUE] + list(settings["filament_colour"])[2:]
    return json.dumps(settings).encode("utf-8")


def rewrite(source, target, members):
    with ZipFile(source) as src, ZipFile(target, "w", ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info.filename, members.get(info.filename, src.read(info.filename)))
        for name, raw in members.items():
            if name not in src.namelist():
                dst.writestr(name, raw)


def painted_project(target, painter=None, settings=two_colours):
    """The real #227 project with its mesh replaced by the fixture's. By default it is what the OBJ import
    of 2.4.0 leaves when both colours take: the faces of the red material without paint (they print
    with the part's extruder, the first filament), those of blue painted with the second."""
    choose = painter or (lambda material, number: 0 if material == "red" else 2)
    faces = [(face, encode(choose(material, number)) if choose(material, number) else None)
             for material, triangles in material_triangles().items() for number, face in enumerate(triangles)]
    with ZipFile(REAL_227) as archive:
        old = {name: archive.read(name) for name in (OBJECT_SETTINGS, PROJECT)}
    rewrite(REAL_227, target, {MESH: mesh_xml(faces), OBJECT_SETTINGS: object_settings(old[OBJECT_SETTINGS]),
                               PROJECT: settings(old[PROJECT])})
    return Path(target).read_bytes()


def two_tool_gcode():
    """The real #236 G-code with one tool change inserted before the 20th extruding move of layer 1, its
    filament colours made the project's and its filament note made to name two filaments."""
    lines = [line.rstrip("\r") for line in REAL_236.read_text(encoding="utf-8").split("\n")]
    first = next(number for number, line in enumerate(lines) if line.startswith(";LAYER_CHANGE"))
    count = 0
    for number in range(first, len(lines)):
        code = lines[number].split(";", 1)[0]
        if code.startswith(("G1", "G2", "G3")) and " E" in code and (" X" in code or " Y" in code):
            count += 1
            if count == 20:
                lines[number:number] = ["; Change Tool0 -> Tool1 (layer 1)", "G91", "G1 Z1.5 F1800", "G90",
                                        "G1 F21000", "M109 S220 T1", "M400", "T1", "G90"]
                break
    with ZipFile(REAL_227) as archive:
        colours = ";".join(json.loads(two_colours(archive.read(PROJECT)))["filament_colour"])
    out = []
    for line in lines:
        if line.startswith("; filament used [mm]"):
            line = "; filament used [mm] = 135.00, 45.00, 0.00, 0.00, 0.00"
        elif line.startswith("; filament_colour "):
            line = "; filament_colour = " + colours
        out.append(line)
    return "\n".join(out).encode("utf-8")


def picture(width=640, height=400, seed=1):
    ramp = np.linspace(0, 255, width, dtype=np.float32)[None, :, None]
    pixels = (ramp + np.random.default_rng(seed).uniform(0, 40, (height, width, 3))).clip(0, 255).astype(np.uint8)
    out = BytesIO()
    Image.fromarray(pixels, "RGB").save(out, "PNG")
    return out.getvalue()


def fixture_record(texture):
    files = dict(fixture_files(), **{"texture.png": texture})
    return {"obj": "model.obj", "mtl": "model.mtl", "form": "kd-only",
            "form_says": "Kd colours only; the texture is beside the file and not referenced; no UVs",
            "geometry": "two-boxes", "texture_referenced": False, "obj_has_uv": False,
            "faces": {name: len(faces) for name, faces in material_triangles().items()},
            "files": {name: {"bytes": len(raw), "sha256": sha256(raw).hexdigest()} for name, raw in files.items()},
            "template": colored._template()}


def dialog(image):
    return {"class": "#32770", "title": "Obj file Import color", "rect": [760, 391, 1246, 950],
            "children": [{"class": "wxWindowNR", "text": "OK", "id": 5100, "enabled": True, "visible": True}],
            "image": image, "pressed": {"text": "OK", "id": 5100, "class": "wxWindowNR"},
            "tiers": [{"how": "message click inside dialog", "closed": True}], "closed": True}


ROWS = [{"index": index, "label": label, "enabled": True, "submenu": False} for index, label in enumerate((
    "Export all objects as one STL...", "Export all objects as STLs...", "Export Generic 3MF...",
    "Export plate sliced file...\tCtrl+G", "Export all plate sliced file...", "Export G-code...",
    "Export Preset Bundle..."))]


def analysis_record(folder, prefix, parts):
    """What the GUI records for these files, read with the oracle as the case reads it."""
    imported = as_recorded(painted_readings(folder / f"{prefix}-imported.3mf", "model.obj", material_triangles()))
    code = as_recorded(filament_readings(folder / f"{prefix}-plate.gcode", imported))
    template = colored.FIXTURE.read_bytes()
    return {
        "case": 228, "results": {CLAUSE_COLORS: colored._verdict(imported), CLAUSE_FILAMENTS: colored._verdict(code)},
        "fixture": dict(fixture_record(parts["texture.png"]), template={
            "name": colored.FIXTURE.name, "bytes": len(template), "sha256": sha256(template).hexdigest()}),
        "chooser": {"import_rows": [{"label": "Import 3MF/STL/STEP/SVG/OBJ/AMF...\tCtrl+I", "enabled": True}],
                    "row": "Import 3MF/STL/STEP/SVG/OBJ/AMF...\tCtrl+I",
                    "title": "Choose one or more files (3mf/step/stl/svg/obj/amf):",
                    "image": {"width_px": 944, "height_px": 501}, "entered": WORK + "\\model.obj", "dialog_closed": True},
        "import_dialogs": [dialog("import-dialog-0.png")],
        "imported": imported, "gcode": code,
        "route": {"judged": {"form": "kd-only", "texture_referenced": False, "obj_has_uv": False,
                             "filaments": imported["filaments"], "checks": imported["checks"],
                             "gcode": {"tools_extruding": code["tools_extruding"], "change_count": code["change_count"]}},
                  "control": {"form": "textured", "texture_referenced": True, "obj_has_uv": True, "dialogs": []}},
        "slice": {"export_enabled_after_seconds": 8.6, "export_menu_after": ROWS},
        "export": {"item": "Export G-code", "saved_name": "plate.gcode", "saved_extension": ".gcode",
                   "file_bytes": len(parts["plate.gcode"]), "file_sha256": sha256(parts["plate.gcode"]).hexdigest(),
                   "dialog_closed": True, "app_alive": True,
                   "dialog_image": {"width_px": 944, "height_px": 501}, "directory": WORK},
        "editor_after_export": {"alive": True, "dialog": None},
    }


def write_run(folder, record=None, **stood_in):
    """A synthetic passing harvest in the shape the collector leaves: `<prefix>-<part>` files, a manifest,
    a log and a receipt whose digest matches the log."""
    folder.mkdir(parents=True, exist_ok=True)
    shown = {"chooser.png": picture(seed=1, width=944, height=501), "imported.png": picture(seed=2),
             "sliced.png": picture(seed=3), "export-dialog.png": picture(seed=4, width=944, height=501),
             "import-dialog-0.png": picture(seed=5, width=486, height=559)}
    parts = {"new-project.3mf": colored.FIXTURE.read_bytes(),
             "imported.3mf": painted_project(folder / "built.3mf"), "plate.gcode": two_tool_gcode(),
             "texture.png": fixture_files()["texture.png"], **shown}
    parts.update(stood_in)
    for part, raw in parts.items():
        (folder / f"{PREFIX}-{part}").write_bytes(raw)
    default = analysis_record(folder, PREFIX, parts)
    parts["analysis.json"] = json.dumps(record(default) if callable(record) else default, ensure_ascii=False,
                                        indent=2).encode("utf-8")
    (folder / f"{PREFIX}-analysis.json").write_bytes(parts["analysis.json"])
    (folder / f"{PREFIX}-object_artifacts.json").write_text(json.dumps(
        [{"part": part, "bytes": len(raw), "sha256": sha256(raw).hexdigest()} for part, raw in parts.items()]),
        encoding="utf-8")
    log = f"[m7x228] retained work directory: {WORK}\n".encode()
    (folder / f"{PREFIX}-case.log").write_bytes(log)
    (folder / f"{PREFIX}-receipt.json").write_text(json.dumps({
        "case": "m7x_228_import_colored_obj", "commit": "0" * 40, "summary": "SUMMARY: PASS=2 FAIL=0",
        "dispatched_at": "2026-11-26T00:00:00+00:00", "scenario_completed_at": "2026-11-26T00:00:10+00:00",
        "log_sha256": sha256(log).hexdigest()}), encoding="utf-8")
    return folder, PREFIX


def failed_readings(folder, prefix, **how):
    """The readings a stand-in refuses, on a copy whose manifest agrees with it."""
    with copy_of(folder, prefix, **how) as (other, altered):
        return colored._read(other, altered)[1]["failed"]


# --- the positive -----------------------------------------------------------------

def test_synthetic_run_passes_every_reading_and_every_counterexample(tmp_path):
    folder, prefix = write_run(tmp_path)
    result = colored.replay(folder, prefix)
    not_true = [key for key, value in result["checks"].items() if value is not True]
    assert not not_true, (not_true, result["import"]["failed"])
    assert set(colored.POSITIVE) <= set(result["checks"])
    report = result["import"]
    assert report["clauses"] == {CLAUSE_COLORS: "PASS", CLAUSE_FILAMENTS: "PASS"}
    assert report["independent"]["clauses"] == {CLAUSE_COLORS: "PASS", CLAUSE_FILAMENTS: "PASS"}
    # both colours print where the fixture puts them: red with the first filament, blue with the second
    assert report["filaments"] == {"red": 1, "blue": 2} and report["paint_on_faces"] == {"red": [0], "blue": [2]}
    assert report["unpainted_faces"] == {"red": 12, "blue": 0} and report["tools_extruding"] == [0, 1]
    assert report["tool_changes"] == 1


def test_the_replay_writes_the_fixture_the_case_wrote_on_the_guest():
    # the replay's own OBJ and MTL against the digests the guest run recorded for them
    mine = colored._fixture_files("model", "two-boxes")
    for name in ("model.obj", "model.mtl"):
        size, digest = GUEST_FIXTURE[name]
        assert (len(mine[name]), sha256(mine[name]).hexdigest()) == (size, digest), name
    # the texture is text built by no rule: its bytes differ with the zlib that compresses them (the
    # host writes 79 bytes of another digest), so it is read as a picture, here as in the replay
    texture = fixture_files()["texture.png"]
    assert len(texture) == GUEST_FIXTURE["texture.png"][0] and colored._texture(texture)
    assert colored._texture(texture) and not colored._texture(colored.blank_png(16, 16))


def test_the_guest_run_that_printed_with_one_colour_is_reproduced_not_repaired(tmp_path):
    if not (REAL_RED / "imported.3mf").is_file():
        pytest.skip("the guest run dev228c-9b3291c is not on this machine")
    real_imported = (REAL_RED / "imported.3mf").read_bytes()
    real_gcode = (REAL_RED / "plate.gcode").read_bytes()
    folder, prefix = write_run(tmp_path, **{"imported.3mf": real_imported, "plate.gcode": real_gcode})
    result = colored.replay(folder, prefix)
    report = result["import"]
    assert report["clauses"] == {
        CLAUSE_COLORS: "FAIL (different_filaments, different_filament_colours)",
        CLAUSE_FILAMENTS: "FAIL (two_filaments_print, change_between_them, filaments_have_distinct_colours)"}
    assert report["filaments"] == {"red": 2, "blue": 2} and report["paint_on_faces"] == {"red": [0], "blue": [2]}
    assert report["unpainted_faces"] == {"red": 12, "blue": 0} and report["tools_extruding"] == [1]
    assert report["tool_changes"] == 0
    assert "counterexamples" not in report            # a run that failed is not asked for its counterexamples


@pytest.mark.parametrize("state", [1, 2, 3, 15, 16, 17, 18, 32])
def test_the_stand_ins_paint_value_round_trips_through_the_oracles_decoder(state):
    assert decode_paint(colored._paint_value(state)) == [state]


def test_the_case_runs_through_the_shared_driver_like_the_other_replays(tmp_path, monkeypatch):
    folder, prefix = write_run(tmp_path)
    monkeypatch.setitem(ADAPTERS, "m7x_228_import_colored_obj", colored.replay)
    report = replay_receipt(folder / f"{prefix}-receipt.json")
    assert report["offline_checks_passed"] and report["result"]["import"]["clauses"] == {
        CLAUSE_COLORS: "PASS", CLAUSE_FILAMENTS: "PASS"}, report
    (folder / f"{prefix}-case.log").write_bytes(b"another log\n")
    report = replay_receipt(folder / f"{prefix}-receipt.json")
    assert not report["offline_checks_passed"] and "SHA-256 differs" in report["error"]


def test_replay_actually_reads_every_counterexample_on_a_temporary_copy(tmp_path, monkeypatch):
    folder, prefix = write_run(tmp_path)
    reads, real = [], colored._read
    monkeypatch.setattr(colored, "_read", lambda place, pre: reads.append(place.name) or real(place, pre))
    result = colored.replay(folder, prefix)
    controls = [key for key in result["checks"] if key.endswith("_rejected")]
    assert all(result["checks"][key] is True for key in controls) and len(controls) == 20
    assert len(reads) == 21 and sum(name.startswith("replay-") for name in reads) == 20


# --- what each counterexample refuses ----------------------------------------------

@pytest.mark.parametrize("label,readings", [
    # the textured OBJ: nothing painted, both materials on the part's filament, one tool in the G-code
    ("unpainted_project_rejected", ["filaments_differ", "filaments_are_red_and_blue", "oracle_accepts_project"]),
    ("first_filament_left_unpainted_rejected", ["filaments_differ", "filaments_are_red_and_blue",
                                                 "gcode_prints_both_filaments", "gcode_changes_between_them"]),
    ("same_filament_on_both_materials_rejected", ["filaments_differ", "filaments_are_red_and_blue"]),
    ("material_split_over_two_filaments_rejected", ["red_faces_one_filament", "filaments_differ",
                                                    "gcode_prints_both_filaments"]),
    ("colours_swapped_on_the_faces_rejected", ["filaments_are_red_and_blue"]),
    ("same_colour_for_both_filaments_rejected", ["filaments_are_red_and_blue", "gcode_names_the_projects_colours"]),
    ("monochrome_gcode_rejected", ["gcode_prints_both_filaments", "gcode_changes_between_them",
                                   "gcode_trailer_names_two_filaments", "oracle_accepts_gcode"]),
    # the second tool is still selected and the trailer untouched: only the extrusion tells
    ("tool_selected_never_extruding_rejected", ["gcode_prints_both_filaments", "oracle_accepts_gcode"]),
    ("another_painted_project_rejected", ["saved_object_is_the_fixture_once", "object_is_named_after_the_obj"]),
    ("template_replaced_rejected", ["start_is_the_redblue_template_with_its_cube"]),
    ("texture_replaced_rejected", ["texture_is_the_fixture_picture"]),
    ("blank_screenshot_rejected", ["pictures_are_pictures"]),
    ("chooser_entered_another_file_rejected", ["chooser_entered_this_runs_obj"]),
    ("export_receipt_edited_rejected", ["export_receipt_matches_file"]),
    ("fixture_record_edited_rejected", ["recorded_fixture_matches_its_bytes"]),
    ("route_record_edited_rejected", ["recorded_route_matches_readings"]),
    # every clause recorded PASS over an unpainted project
    ("flattering_analysis_rejected", ["recorded_verdicts_match_readings", "filaments_differ",
                                      "recorded_imported_matches_file"]),
    # the whole record of the passing run over the files of a monochrome one
    ("green_record_over_unpainted_files_rejected", ["recorded_imported_matches_file",
                                                    "recorded_gcode_matches_file", "filaments_differ"]),
    ("missing_dialog_picture_rejected", ["recorded_dialogs_have_their_pictures"]),
    ("manifest_mismatch_rejected", ["manifest_sizes_and_sha256_match"]),
])
def test_each_counterexample_is_refused_by_a_reading_of_its_own(tmp_path, label, readings):
    folder, prefix = write_run(tmp_path)
    _checks, _report, kept = colored._read(folder, prefix)
    how = dict(colored._stand_ins(*kept))[label]
    if label == "manifest_mismatch_rejected":
        # the collector that recorded one file and kept another: the manifest no longer describes the run
        with pytest.raises(ValueError, match="manifest"):
            failed_readings(folder, prefix, **how)
        return
    failed = failed_readings(folder, prefix, **how)
    assert set(readings) <= set(failed), (label, failed)


def test_the_real_single_tool_gcode_and_the_real_two_colour_project_are_refused(tmp_path):
    if not (REAL_RED / "imported.3mf").is_file():
        pytest.skip("the guest run dev228c-9b3291c is not on this machine")
    # the untouched #236 export: one tool, the standard cube's colours
    failed = failed_readings(*write_run(tmp_path), **{"replace": {"plate.gcode": REAL_236.read_bytes()}})
    assert {"gcode_prints_both_filaments", "gcode_changes_between_them", "gcode_names_the_projects_colours",
            "gcode_trailer_names_two_filaments"} <= set(failed)
    # a project the application painted for another row (#202): two filaments, but not this fixture
    failed = failed_readings(*write_run(tmp_path), **{"replace": {"imported.3mf": REAL_202.read_bytes()}})
    assert {"saved_object_is_the_fixture_once", "oracle_accepts_project"} <= set(failed)


def test_the_input_sentinels_are_live(no_real_input):
    """The guard itself is asked to go red: each sentinel refuses its call, each GUI module its import."""
    winutil = sys.modules["harness.winutil"]
    with pytest.raises(AssertionError, match="#228 replay"):
        winutil.user32.SetCursorPos(0, 0)
    with pytest.raises(AssertionError, match="#228 replay"):
        winutil.user32.SendInput(0, None, 0)
    with pytest.raises(AssertionError, match="#228 replay"):
        winutil.real_click_screen(0, 0)
    with pytest.raises(AssertionError, match="#228 replay"):
        importlib.import_module("colored_obj_cases")      # refused by the finder, not by a sentinel
    assert no_real_input == ["SetCursorPos", "SendInput", "real_click_screen"]
    no_real_input.clear()


def test_the_replay_never_imports_a_module_that_drives_the_gui(tmp_path):
    write_run(tmp_path)
    assert all(value is True for value in colored.replay(tmp_path, PREFIX)["checks"].values())
    # harness.winutil was loaded by the fixture itself, to have its entry points replaced
    assert not [name for name in sys.modules if name != "harness.winutil"
                and (name.split(".")[-1] in GUI or name.startswith("tests.gui"))]
