"""Recheck Feishu #233's merged STL from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
The STL is then read twice, by tests/export_io_oracle.py and by the
independent reader in tests/file_io_replay_support.py: it must hold every
triangle of every object of the saved plate, each at the object's own place.
On its own the plate must be the fixture's cube beside a sphere, apart, on
the bed and inside the printable area. The viewer evidence must be tied to
the exported bytes by digests and by the file names in its logs, and the
control it refused must really not be an STL. Last, each counterexample of
the row is stood in for a harvested part on a temporary copy of the run and
must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path, PureWindowsPath
import re
import sys
from tempfile import TemporaryDirectory

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from export_io_oracle import merged_stl_expectation_gaps, plate_object_layout, verify_merged_stl, viewer_gaps
from file_io_replay_support import (at_origin, blank_png, box, flattering, in_polygon, manifest, moved_project,
                                    paired, png, printable_area, project, refused, screenshots, stl, stl_bytes,
                                    work_directories)
from plate_reserve_oracle import verify_f3d_image

CASE = 233
FIXTURE = ROOT / "fixtures" / "feishu_std_cube.3mf"
PICTURES = ("before.png", "export-dialog.png")
LOGS = ("f3d-version.log", "f3d-view.log", "f3d-invalid.log")
CONTROL, RENDER = "invalid.stl", "f3d-view.png"
STL_HEADER = 80
CLAUSES = ("生成 .stl 文件", "包含两个模型的合并几何", "文件非 0 字节", "可正常打开")
TOL = 1e-4           # the STL stores float32: a coordinate of 150 mm is exact to about 1e-5 mm
SPHERE_TOL = 0.05    # how far a corner of a tessellated sphere may sit from its radius
PLATE = ("plate_is_the_cube_and_a_sphere", "objects_rest_on_the_bed", "objects_apart",
         "objects_inside_printable_area")
MERGED = ("stl_holds_every_plate_triangle_once", "each_object_keeps_its_place")
VIEWER = ("viewer_identified_itself", "viewer_log_names_the_export", "render_shows_a_mesh",
          "oracle_accepts_the_render", "viewer_read_the_exported_bytes", "render_matches_its_digest",
          "recorded_version_is_the_log", "control_is_not_an_stl", "viewer_refused_the_control",
          "viewer_verdict_without_gaps")
CLAIMS = ("recorded_hashes_match_file", "recorded_geometry_matches_file", "recorded_plate_matches_file",
          "recorded_verdict_matches_file", "recorded_case_and_fixture", "oracle_accepts_export",
          "export_targets_this_run")
POSITIVE = ("stl_artifact_is_dot_stl", "manifest_sizes_and_sha256_match", *PLATE, *MERGED, *VIEWER, *CLAIMS,
            "screenshots_are_pictures", "dialog_picture_matches_record")
UNREADABLE = (ValueError, OSError, KeyError, TypeError)


@lru_cache(maxsize=8)
def _fixture():
    return FIXTURE.read_bytes()


@lru_cache(maxsize=8)
def _project(raw: bytes) -> dict:
    """`project`, kept per content: the counterexamples leave the plate as it is most of the time."""
    return project(raw)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_recorded(value):
    """A reading as the GUI's analysis.json holds it: the oracle returns tuples, JSON keeps lists."""
    return json.loads(json.dumps(value))


def _mins(item):
    """The corner where an object's box starts."""
    return item["box"][0], item["box"][2], item["box"][4]


def _sphere(item):
    """Whether an object is a sphere: every one of its corners lies on the ball that fills its box."""
    corners = {corner for triangle in item["triangles"] for corner in triangle}
    x0, x1, y0, y1, z0, z1 = item["box"]
    sides = (x1 - x0, y1 - y0, z1 - z0)
    center = (x0 + sides[0] / 2, y0 + sides[1] / 2, z0 + sides[2] / 2)
    return (min(sides) > 1 and max(sides) - min(sides) <= 1e-3
            and max(abs(math.dist(corner, center) - sides[0] / 2) for corner in corners) <= SPHERE_TOL)


def _plate(saved, fixture):
    """The saved plate on its own: the fixture's cube beside a sphere, on the bed, apart, inside the bed."""
    objects, (cube,) = saved["objects"], fixture["objects"]
    copies = [item for item in objects if item["name"] == cube["name"] and at_origin(item) == at_origin(cube)]
    balls = [item for item in objects if _sphere(item)]
    recognised = (len(objects) == 2 and len(copies) == 1 and len(balls) == 1 and balls[0] is not copies[0]
                  and len({item["plate"] for item in objects}) == 1)
    apart = False
    if len(objects) == 2:
        (ax0, ax1, ay0, ay1, _, _), (bx0, bx1, by0, by1, _, _) = (item["box"] for item in objects)
        apart = ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0
    area, height = printable_area(saved["settings"]), _number(saved["settings"].get("printable_height"))
    inside = area is not None and height is not None and all(
        in_polygon(area, corner) and item["box"][5] <= height + 1e-3
        for item in objects for x in item["box"][:2] for y in item["box"][2:4] for corner in ((x, y),))
    return {
        "plate_is_the_cube_and_a_sphere": recognised,
        "objects_rest_on_the_bed": len(objects) == 2 and all(abs(item["box"][4]) <= 1e-3 for item in objects),
        "objects_apart": apart,
        "objects_inside_printable_area": inside,
    }


def _merged(saved, triangles, pairs, worst):
    """The STL against the plate: every triangle once, and each object where the plate has it."""
    expected = sum(len(item["triangles"]) for item in saved["objects"])
    placed, start = True, 0
    for item in saved["objects"]:
        mine = pairs[start:start + len(item["triangles"])]
        start += len(item["triangles"])
        if None in mine:
            placed = False
            continue
        placed = placed and all(abs(a - b) <= TOL for a, b in zip(
            box([corner for number in mine for corner in triangles[number]]), item["box"]))
    return {"stl_holds_every_plate_triangle_once": len(triangles) == expected and None not in pairs
            and len(set(pairs)) == len(pairs) and worst <= TOL,
            "each_object_keeps_its_place": placed}


def _viewer(raw, analysis, name, digest, render_path, render):
    """The third-party viewer's evidence: what it says it opened, what it rendered, what it refused."""
    viewer = analysis.get("viewer") if isinstance(analysis.get("viewer"), dict) else {}
    # the GUI read its logs as text, with every line ending turned into a newline
    texts = {part: raw[part].decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
             for part in LOGS}
    solid = render["solid"] or {}
    try:
        verify_f3d_image(render_path)
        accepted = True
    except (OSError, ValueError):
        accepted = False
    try:
        stl(raw[CONTROL])
        broken = False
    except ValueError:
        broken = True
    return {
        "viewer_identified_itself": "f3d" in texts["f3d-version.log"].casefold() and bool(
            re.search(r"Version:\s*\d+\.\d+", texts["f3d-version.log"])),
        "viewer_log_names_the_export": name in texts["f3d-view.log"],
        # a render has a bounded body of fully opaque pixels in several colours; a blank has none
        "render_shows_a_mesh": render["format"] == "PNG" and solid.get("inside") is True
        and 0.01 <= solid.get("fraction", 0) <= 0.9 and solid.get("colors", 0) >= 3,
        "oracle_accepts_the_render": accepted,
        "viewer_read_the_exported_bytes": viewer.get("source_sha256") == digest
        and viewer.get("same_bytes_as_export") is True and viewer.get("positive_rc") == 0,
        "render_matches_its_digest": viewer.get("output_sha256") == sha256(raw[RENDER]).hexdigest(),
        "recorded_version_is_the_log": viewer.get("version_rc") == 0
        and viewer.get("version") == texts["f3d-version.log"].strip(),
        "control_is_not_an_stl": broken,
        "viewer_refused_the_control": type(viewer.get("negative_rc")) is int and viewer["negative_rc"] != 0
        and viewer.get("negative_rejected") is True and CONTROL in texts["f3d-invalid.log"],
        "viewer_verdict_without_gaps": viewer_gaps(viewer) == [],
    }


@lru_cache(maxsize=6)
def _pairing(project_raw: bytes, stl_raw: bytes) -> tuple:
    """The STL's triangles and how each pairs with a plate triangle, kept per content."""
    saved = _project(project_raw)
    triangles = tuple(stl(stl_raw)[1])
    expected = tuple(triangle for item in saved["objects"] for triangle in item["triangles"])
    pairs, worst = paired(expected, triangles)
    return triangles, tuple(pairs), worst


@lru_cache(maxsize=6)
def _oracle(project_raw: bytes, stl_raw: bytes, name: str, suffix) -> tuple:
    """The oracle's three readings of one plate and one STL, kept per content: the counterexamples
    keep most of the harvest as it is. A refusal comes back as its message. The STL is written under
    the name the harvest gave it, because the oracle's messages quote it."""
    with TemporaryDirectory(prefix="replay-oracle-") as temporary:
        folder = Path(temporary)
        (folder / "before.3mf").write_bytes(project_raw)
        (folder / name).write_bytes(stl_raw)
        readings = []
        for read in (lambda: verify_merged_stl(folder / "before.3mf", folder / name),
                     lambda: plate_object_layout(folder / "before.3mf"),
                     lambda: merged_stl_expectation_gaps(folder / "before.3mf", folder / name, suffix)):
            try:
                readings.append(_as_recorded(read()))
            except UNREADABLE as exc:
                readings.append({"refused": f"{type(exc).__name__}: {exc}"})
    return tuple(readings)


def _claims(analysis, name, raw, digest, triangles, work):
    """What the GUI recorded, held against the files it kept."""
    export, geometry, plate = analysis.get("export"), analysis.get("merged_geometry"), analysis.get("plate")
    results, gaps = analysis.get("results"), analysis.get("expectation_gaps")
    known = all(isinstance(part, dict) for part in (export, geometry, plate, results, gaps))
    suffix = export.get("saved_extension") if isinstance(export, dict) and isinstance(
        export.get("saved_extension"), str) else None
    again, layout, recomputed = _oracle(raw["before.3mf"], raw[name], name, suffix)
    oracle = "refused" not in again and "refused" not in layout and all(layout["checks"].values())
    if isinstance(gaps, dict):
        recomputed = dict(recomputed, **{"可正常打开": viewer_gaps(analysis.get("viewer"))})
    verdict = known and all(results.get(clause) == "PASS" for clause in CLAUSES) and gaps == recomputed and not any(
        recomputed.values())
    fixture = _fixture()
    return {
        "recorded_hashes_match_file": known and export.get("file_sha256") == digest
        and export.get("file_bytes") == len(raw[name]) and export.get("saved_name") == name
        and export.get("saved_extension") == ".stl" and geometry.get("file_sha256") == digest
        and geometry.get("file_bytes") == len(raw[name]) and geometry.get("triangle_count") == len(triangles),
        "recorded_geometry_matches_file": known and geometry == again,
        "recorded_plate_matches_file": known and plate == layout,
        "recorded_verdict_matches_file": verdict,
        "recorded_case_and_fixture": analysis.get("case") == CASE and analysis.get("fixture") == {
            "name": FIXTURE.name, "bytes": len(fixture), "sha256": sha256(fixture).hexdigest()},
        "oracle_accepts_export": oracle,
        # the save dialog was pointed at the directory this run kept
        "export_targets_this_run": known and len(work) == 1 and isinstance(export.get("directory"), str)
        and PureWindowsPath(export["directory"]) == PureWindowsPath(work[0]),
    }


def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings and what the counterexamples are built from."""
    entries = manifest(directory, prefix)
    beside = [entry["part"] for entry in entries
              if entry["part"].lower().endswith(".stl") and entry["part"] != CONTROL]
    if len(beside) != 1:
        raise ValueError(f"expected one exported .stl beside {CONTROL}, found {[entry['part'] for entry in entries]}")
    name = beside[0]
    try:
        paths = {part: verified_part(directory, prefix, entries, part)
                 for part in ("analysis.json", "before.3mf", name, *PICTURES, *LOGS, CONTROL, RENDER)}
        raw = {part: path.read_bytes() for part, path in paths.items()}
        work = work_directories((directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig"), "m7x233")
    except OSError as exc:
        raise ValueError(f"an artifact could not be read ({type(exc).__name__})") from exc
    analysis = json.loads(raw["analysis.json"].decode("utf-8-sig"))
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    saved, fixture = _project(raw["before.3mf"]), _project(_fixture())
    triangles, pairs, worst = _pairing(raw["before.3mf"], raw[name])
    digest = sha256(raw[name]).hexdigest()
    export = analysis.get("export")
    render = png(raw[RENDER])
    checks = {"stl_artifact_is_dot_stl": name.endswith(".stl"), "manifest_sizes_and_sha256_match": True,
              **_plate(saved, fixture), **_merged(saved, triangles, pairs, worst),
              **_viewer(raw, analysis, name, digest, paths[RENDER], render),
              **_claims(analysis, name, raw, digest, triangles, work),
              **screenshots(raw, export if isinstance(export, dict) else None, PICTURES, "export-dialog.png")}
    report = {"exported": name, "bytes": len(raw[name]), "sha256": digest, "triangles": len(triangles),
              "worst_vertex_deviation_mm": worst,
              "objects": [{"name": item["name"], "triangles": len(item["triangles"]), "plate_box_mm": item["box"],
                           "sphere": _sphere(item)} for item in saved["objects"]],
              "stl_box_mm": box([corner for triangle in triangles for corner in triangle]),
              "render": render["solid"],
              "failed": [key for key in POSITIVE if not checks[key]]}
    return checks, report, (raw, name, saved, raw[name][:STL_HEADER], triangles, pairs)


# --- counterexamples --------------------------------------------------------------

def _moved(group, delta):
    return [tuple(tuple(c + d for c, d in zip(corner, delta)) for corner in triangle) for triangle in group]


def _viewer_edited(raw, **changes):
    """analysis.json with the viewer record changed and everything else as the GUI wrote it."""
    analysis = json.loads(raw.decode("utf-8-sig"))
    analysis["viewer"] = dict(analysis.get("viewer") or {}, **changes)
    return json.dumps(analysis, indent=2, ensure_ascii=False).encode("utf-8")


def _stand_ins(kept) -> list:
    """(label, what is stood in and how) for every counterexample of the row.

    Each entry is meant for `refused` on a copy whose manifest agrees with the stand-in."""
    raw, name, saved, header, triangles, pairs = kept
    mine, start = {}, 0
    for item in saved["objects"]:
        mine[id(item)] = pairs[start:start + len(item["triangles"])]
        start += len(item["triangles"])
    kept_of = lambda item: [triangles[number] for number in mine[id(item)]]  # noqa: E731
    cube = next(item for item in saved["objects"] if not _sphere(item))
    ball = next(item for item in saved["objects"] if _sphere(item))
    onto_cube = tuple(a - b for a, b in zip(_mins(cube), _mins(ball)))
    size = png(raw[RENDER])
    record = raw["analysis.json"]
    return [
        ("cube_only_export_rejected", {"replace": {name: stl_bytes(header, kept_of(cube))}}),
        ("sphere_only_export_rejected", {"replace": {name: stl_bytes(header, kept_of(ball))}}),
        # the sphere where the cube is, and both of them re-centred on the origin
        ("objects_moved_together_rejected",
         {"replace": {name: stl_bytes(header, kept_of(cube) + _moved(kept_of(ball), onto_cube))}}),
        ("objects_moved_to_origin_rejected", {"replace": {name: stl_bytes(
            header, _moved(kept_of(cube), tuple(-value for value in _mins(cube)))
            + _moved(kept_of(ball), tuple(-value for value in _mins(ball))))}}),
        ("empty_stl_rejected", {"replace": {name: stl_bytes(header, [])}}),
        # the right count of triangles, none of them a surface
        ("collapsed_export_rejected",
         {"replace": {name: stl_bytes(header, [(t[0], t[0], t[0]) for t in triangles])}}),
        ("truncated_stl_rejected", {"replace": {name: raw[name][:-50 * 7]}}),
        ("shifted_export_rejected", {"replace": {name: stl_bytes(header, _moved(triangles, (40.0, 0.0, 0.0)))}}),
        ("blank_render_rejected",
         {"replace": {RENDER: blank_png(size["width"], size["height"])}}),
        ("viewer_accepted_the_control_rejected",
         {"replace": {"analysis.json": _viewer_edited(record, negative_rc=0)}}),
        ("viewer_read_other_bytes_rejected", {"replace": {"analysis.json": _viewer_edited(
            record, source_sha256="0" * 64, same_bytes_as_export=False)}}),
        ("valid_control_stl_rejected", {"replace": {CONTROL: stl_bytes(header, triangles[:1])}}),
        ("wrong_extension_rejected", {"rename": {name: f"{Path(name).stem}.3mf"}}),
        ("project_moved_rejected", {"replace": {"before.3mf": moved_project(raw["before.3mf"], dy=20.0)}}),
        ("manifest_mismatch_rejected", {"replace": {name: b""}, "keep_manifest": False}),
        ("edited_analysis_rejected", {"replace": {
            name: stl_bytes(header, kept_of(cube)), "analysis.json": flattering(record, CLAUSES)}}),
    ]


def _controls(directory, prefix, kept):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it."""
    return {label: refused(_read, POSITIVE, directory, prefix, **how) for label, how in _stand_ins(kept)}


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #233 harvest after the driver verified its log."""
    checks, report, kept = _read(directory, prefix)
    result = {"checks": checks, "export": report}
    if not report["failed"]:
        result["checks"].update(_controls(directory, prefix, kept))
    return result
