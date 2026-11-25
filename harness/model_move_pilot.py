"""Bound a supplied mesh to the existing native save/reopen translation trial."""
from decimal import Decimal
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

from .agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256, valid_run_id
from .agent_verify import _require
from .native_config_cases import CATALOG
from .project_3mf import _archive, _CORE, _PROD, _numbers, _xml
from .script_verify import _check_cancel, _json

SCENARIO = "bound_model_move"
TEMPLATE = {"id": "move_x_save_reopen", "version": 1, "target": "sole_printable_instance",
            "operations": [{"name": "translate", "axis": "x", "delta_mm": 10}, {"name": "save_as"}],
            "required_checks": ["instance_delta", "preserved_shape", "preserved_project_settings",
                                "fresh_profile_reslice", "object_extrusion_xy"]}
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 16 * 1024 * 1024
MESH_LIMIT = 24 * 1024 * 1024
FACE_LIMIT = 300_000
MODEL_DECIMAL_PLACES = 5
MAIN = "3D/3dmodel.model"
CONFIG = "Metadata/project_settings.config"
SETTINGS = "Metadata/model_settings.config"
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(plan):
    return json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def request_dir(run_id):
    valid_run_id(run_id)
    return ROOT / "artifacts/native_model_requests" / run_id


def validate_plan(plan, run_id):
    valid_run_id(run_id)
    _require(type(plan) is dict and set(plan) == {"run_id", "template", "source_sha256", "model",
        "environment", "prepared_sha256", "import_policy"}, "model_plan_fields")
    _require(plan["run_id"] == run_id and plan["template"] == TEMPLATE
             and plan["import_policy"] == "geometry_in_fixed_process"
             and plan["environment"] == CATALOG["sut"], "model_plan_identity")
    model = plan["model"]
    _require(type(model) is dict and set(model) == {"name", "format", "size", "sha256"}
             and model["format"] in {"3mf", "stl"}
             and type(model["size"]) is int and 0 < model["size"] <= LIMIT
             and type(model["name"]) is str and 0 < len(model["name"]) <= 255
             and Path(model["name"]).name == model["name"], "model_plan_source")
    for value, length in ((model["sha256"], 64), (plan["prepared_sha256"], 64), (plan["source_sha256"], 40)):
        _require(type(value) is str and re.fullmatch("[0-9a-f]{%d}" % length, value) is not None, "model_plan_digest")
    return plan


def read_request(run_id):
    folder = request_dir(run_id)
    with (folder / "resolved_plan.json").open("rb") as stream:
        plan = validate_plan(_json(stream.read(65537)), run_id)
    fixture = folder / "prepared.3mf"
    _require(0 < fixture.stat().st_size <= LIMIT and digest(fixture.read_bytes()) == plan["prepared_sha256"],
             "model_prepared_digest")
    return plan, fixture


def mesh_point(values):
    point = tuple(float(value) for value in values)
    _require(len(point) == 3 and all(math.isfinite(x) and abs(x) < 10**6 for x in point), "model_vertex")
    return point


def stl_mesh(raw):
    count = struct.unpack_from("<I", raw, 80)[0] if len(raw) >= 84 else 0
    if count and 84 + 50 * count == len(raw):
        _require(count <= FACE_LIMIT, "model_triangle_budget")
        points = [mesh_point(row[start:start + 3]) for row in struct.iter_unpack("<12fH", raw[84:])
                  for start in (3, 6, 9)]
    else:
        text = raw.decode("ascii", errors="strict")
        _require(text.lstrip().startswith("solid") and "endsolid" in text, "model_stl_format")
        points = [mesh_point(row.split()) for row in re.findall(r"^\s*vertex[ \t]+([^\r\n]+)", text, re.MULTILINE)]
        _require(0 < len(points) <= 3 * FACE_LIMIT and len(points) % 3 == 0
                 and len(points) // 3 == len(re.findall(r"^\s*endfacet\b", text, re.MULTILINE)), "model_stl_faces")
    return points, [(i, i + 1, i + 2) for i in range(0, len(points), 3)]


def transform_point(point, matrix):
    return tuple(sum(matrix[3 * col + axis] * point[col] for col in range(3)) + matrix[9 + axis]
                 for axis in range(3))


def mesh_3mf(files, cancelled):
    """Read the sole printable instance and flatten its component geometry."""
    objects = {}
    models = {}
    for name, raw in files.items():
        if not name.endswith(".model"):
            continue
        _check_cancel(cancelled)
        _require(len(raw) <= MESH_LIMIT and b"\0" not in raw and not re.search(br"<!\s*(?:DOCTYPE|ENTITY)", raw, re.I),
                 "model_xml_scope")
        model = ET.fromstring(raw)
        _require(model.tag == _CORE + "model" and model.get("unit", "millimeter") == "millimeter", "model_units")
        models[name] = model
        for obj in model.findall(_CORE + "resources/" + _CORE + "object"):
            key = name, obj.get("id")
            _require(key not in objects, "model_duplicate_object")
            objects[key] = obj
    _require(MAIN in models, "model_missing")
    items = models[MAIN].findall(_CORE + "build/" + _CORE + "item")
    _require(len(items) == 1 and items[0].get("printable", "1") == "1", "model_needs_sole_printable_instance")
    item = items[0]
    build = _numbers(item.get("transform", IDENTITY), 12)
    points, faces = [], []

    def visit(key, matrices, ancestors):
        _check_cancel(cancelled)
        _require(key in objects and key not in ancestors and len(ancestors) < 8, "model_component_reference")
        obj = objects[key]
        mesh, components = obj.find(_CORE + "mesh"), obj.find(_CORE + "components")
        _require((mesh is None) != (components is None), "model_component_shape")
        if components is not None:
            for part in components:
                name = part.get(_PROD + "path", key[0]).lstrip("/")
                matrix = tuple(map(float, _numbers(part.get("transform", IDENTITY), 12)))
                visit((name, part.get("objectid")), (matrix, *matrices), ancestors | {key})
            return
        offset = len(points)
        vertices = mesh.findall(_CORE + "vertices/" + _CORE + "vertex")
        triangles = mesh.findall(_CORE + "triangles/" + _CORE + "triangle")
        _require(vertices and triangles and offset + len(vertices) <= FACE_LIMIT * 3
                 and len(faces) + len(triangles) <= FACE_LIMIT, "model_triangle_budget")
        for i, vertex in enumerate(vertices):
            if i % 2048 == 0:
                _check_cancel(cancelled)
            point = mesh_point(vertex.get(axis) for axis in "xyz")
            for matrix in matrices:
                point = transform_point(point, matrix)
            points.append(point)
        for tri in triangles:
            face = tuple(int(tri.get(key)) for key in ("v1", "v2", "v3"))
            _require(all(0 <= i < len(vertices) for i in face), "model_triangle_index")
            faces.append(tuple(offset + i for i in face))

    visit((MAIN, item.get("objectid")), (), set())
    _require(faces, "model_empty")
    return points, faces, build


def bounds(points):
    return tuple((min(values), max(values)) for values in zip(*points))


def source_models(raw):
    # Geometry-only import consumes internal model entries and their component
    # paths. Source settings, thumbnails and toolpaths never reach the guest.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = [item for item in archive.infolist() if item.filename.endswith(".model")]
        _require(0 < len(entries) <= 32 and sum(item.file_size for item in entries) <= 64 * 1024 * 1024,
                 "model_source_archive_budget")
        files = {}
        for item in entries:
            name = item.filename
            _require(name.startswith("3D/") and not {"", ".", ".."}.intersection(name.split("/"))
                     and "\\" not in name and name not in files and 0 < item.file_size <= MESH_LIMIT
                     and item.compress_type in {zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED},
                     "model_source_entry")
            with archive.open(item) as stream:
                files[name] = stream.read(item.file_size + 1)
            _require(len(files[name]) == item.file_size, "model_source_entry_length")
        return files


def geometry_unchanged(saved, original):
    """Compare indexed faces and bed-space coordinates after Orca recenters a mesh."""
    def geometry(raw):
        points, faces, build = mesh_3mf(source_models(raw), lambda: False)
        matrix = tuple(map(float, build))
        return [transform_point(point, matrix) for point in points], faces

    a, a_faces = geometry(saved)
    b, b_faces = geometry(original)
    return (a_faces == b_faces and len(a) == len(b)
            and all(abs(x - y) <= 0.00001 for p, q in zip(a, b) for x, y in zip(p, q)))


def prepare_mesh(raw, model_format, carrier):
    _require(0 < len(raw) <= LIMIT and digest(carrier) == LAYER_FIXTURE_SHA256, "model_input_or_context")
    if model_format == "stl":
        points, faces = stl_mesh(raw)
    else:
        _require(model_format == "3mf", "model_input_format")
        points, faces, build = mesh_3mf(source_models(raw), lambda: False)
        linear = tuple(map(float, build[:9])) + (0, 0, 0)
        points = [transform_point(point, linear) for point in points]
    extents = bounds(points)
    center = tuple((low + high) / 2 for low, high in extents)
    centered, vertex_ids = [], {}
    indices = []
    for point in points:
        key = tuple(round(a - b, MODEL_DECIMAL_PLACES) for a, b in zip(point, center))
        if key not in vertex_ids:
            vertex_ids[key] = len(centered)
            centered.append(key)
        indices.append(vertex_ids[key])
    faces = [tuple(indices[i] for i in face) for face in faces]
    faces = [face for face in faces if len(set(face)) == 3]
    _require(faces and 0.8 < extents[2][1] - extents[2][0], "model_unsliceable_height")

    files = _archive(carrier, lambda: False)
    ET.register_namespace("", _CORE[1:-1])
    ET.register_namespace("p", _PROD[1:-1])
    ET.register_namespace("", _CORE[1:-1])
    ET.register_namespace("p", _PROD[1:-1])
    model = _xml(files[MAIN])
    item = model.find(_CORE + "build/" + _CORE + "item")
    matrix = _numbers(item.get("transform"), 12)
    matrix = (*matrix[:11], Decimal(str(-min(v[2] for v in centered))))
    # This fixed rectangular bed and process context is selected by the carrier,
    # while shape, dimensions, floor and extrusion bounds come from the input.
    config = _json(files[CONFIG])
    area = [tuple(Decimal(v) for v in corner.split("x")) for corner in config["printable_area"]]
    for axis, (low, high) in enumerate(bounds(centered)[:2]):
        bed_lo, bed_hi = min(p[axis] for p in area), max(p[axis] for p in area)
        delta = TEMPLATE["operations"][0]["delta_mm"] if axis == 0 else 0
        _require(bed_lo + 2 <= matrix[9 + axis] + Decimal(str(low))
                 and matrix[9 + axis] + Decimal(str(high)) + delta <= bed_hi - 2, "model_does_not_fit_move")
    _require(max(v[2] for v in centered) - min(v[2] for v in centered)
             <= float(config["printable_height"]), "model_does_not_fit_height")
    item.set("transform", " ".join(map(str, matrix)))
    files[MAIN] = ET.tostring(model, encoding="utf-8", xml_declaration=True)
    part = next(name for name in files if name.startswith("3D/Objects/") and name.endswith(".model"))
    part_model = _xml(files[part])
    mesh = part_model.find(_CORE + "resources/" + _CORE + "object/" + _CORE + "mesh")
    vertices, triangles = mesh.find(_CORE + "vertices"), mesh.find(_CORE + "triangles")
    vertices.clear()
    triangles.clear()
    for point in centered:
        ET.SubElement(vertices, _CORE + "vertex", dict(zip("xyz", (str(v) for v in point))))
    for face in faces:
        ET.SubElement(triangles, _CORE + "triangle", dict(zip(("v1", "v2", "v3"), map(str, face))))
    files[part] = ET.tostring(part_model, encoding="utf-8", xml_declaration=True)
    settings = _xml(files[SETTINGS])
    for metadata in settings.findall("object/metadata") + settings.findall("object/part/metadata"):
        if metadata.get("key") == "name":
            metadata.set("value", "Bound mesh")
    settings.find("assemble/assemble_item").set("transform", item.get("transform"))
    files[SETTINGS] = ET.tostring(settings, encoding="utf-8", xml_declaration=True)
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, files[name])
    _require(result.tell() <= LIMIT and len(files[part]) <= MESH_LIMIT, "model_prepared_size")
    return result.getvalue()


def instance(raw, cancelled):
    return mesh_3mf(_archive(raw, cancelled, member_limit=MESH_LIMIT), cancelled)


def shape_digest(points, faces, cancelled):
    # The prepared mesh already sits on this grid. Using a coarser grid can
    # put a legitimate float32 round-trip on the opposite side of a midpoint.
    scale = 10 ** MODEL_DECIMAL_PLACES
    rounded = [tuple(round(x * scale) for x in p) for p in points]
    encoded = []
    for i, face in enumerate(faces):
        if i % 2048 == 0:
            _check_cancel(cancelled)
        a, b, c = (rounded[j] for j in face)
        encoded.append(struct.pack("<9q", *min(a + b + c, b + c + a, c + a + b)))
    return digest(b"".join(sorted(encoded)))


def verify_move(plan, prepared, saved, gcode, cancelled):
    from .agent_layer_verify import analyze_gcode
    from .pilot_common import inspect_preserved_settings, require_gcode_settings
    from .pilot_transform import _object_xy

    _require(digest(prepared) == plan["prepared_sha256"], "model_prepared_binding")
    before = _archive(prepared, cancelled, member_limit=MESH_LIMIT)
    after = _archive(saved, cancelled, member_limit=MESH_LIMIT)
    old, old_faces, old_matrix = mesh_3mf(before, cancelled)
    new, new_faces, new_matrix = mesh_3mf(after, cancelled)
    delta = TEMPLATE["operations"][0]["delta_mm"]
    _require(new_matrix[:9] == old_matrix[:9] and all(
        abs(b - a - (delta if index == 9 else 0)) <= Decimal("0.0001")
        for index, (a, b) in enumerate(zip(old_matrix, new_matrix)) if index >= 9), "model_instance_delta")
    _require(shape_digest(old, old_faces, cancelled) == shape_digest(new, new_faces, cancelled),
             "model_local_mesh_changed")
    config = _json(before[CONFIG])
    inspect_preserved_settings(_json(after[CONFIG]), config, cancelled=cancelled)
    settings = {"layer_height": config["layer_height"], "initial_layer_print_height": config["initial_layer_print_height"]}
    require_gcode_settings(gcode, settings, "model_gcode_settings")
    world = [transform_point(point, tuple(map(float, new_matrix))) for point in new]
    extents = bounds(world)
    actual = analyze_gcode(gcode, layer_height=settings["layer_height"],
                           first_layer_height=settings["initial_layer_print_height"], cancelled=cancelled,
                           expected_height_mm=Decimal(str(extents[2][1])))
    xy = [(Decimal(str(a)), Decimal(str(b))) for a, b in extents[:2]]
    measured_xy = _object_xy(gcode, xy, cancelled, minimum_span=tuple(max(Decimal(0), b - a - 3) for a, b in xy))
    return {"translation_mm": [delta, 0, 0], "old_xyz": list(map(str, old_matrix[9:])),
            "new_xyz": list(map(str, new_matrix[9:])), "triangles": len(new_faces), "gcode": actual,
            "object_xy_bounds": measured_xy}
