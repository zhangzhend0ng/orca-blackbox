"""Bounded, read-only 3MF oracle for the fixed single-part 27 mm project."""
from decimal import Decimal
import hashlib
import io
from pathlib import PurePosixPath
import stat
import xml.etree.ElementTree as ET
import zipfile

from .agent_verify import _require
from .script_verify import _check_cancel, _json

_CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
_PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
_PRINTER_IDS = {"Snapmaker U1 (0.8 nozzle)", "Snapmaker U1 (0.8 nozzle)(fixture.3mf)"}


def _numbers(text, count):
    _require(type(text) is str and len(text) <= 2048, "project_matrix")
    values = tuple(Decimal(x) for x in text.split())
    _require(len(values) == count and all(x.is_finite() and abs(x) < 10**6 for x in values), "project_matrix")
    return values


def _xml(raw):
    _require(len(raw) <= 2 * 1024 * 1024 and b"\0" not in raw, "project_xml_size")
    text = raw.decode("utf-8", errors="strict")
    _require("<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(), "project_xml_entities")
    root = ET.fromstring(text)
    pending, count = [(root, 0)], 0
    while pending:
        item, depth = pending.pop(); count += 1
        _require(depth <= 16 and count <= 10000 and all(len(x) <= 4096 for x in item.attrib.values()), "project_xml_complexity")
        pending.extend((child, depth + 1) for child in item)
    return root


def _archive(raw, cancelled):
    _require(type(raw) is bytes and 1 <= len(raw) <= 16 * 1024 * 1024, "project_zip_size")
    files, names, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        _require(1 <= len(entries) <= 80, "project_zip_entries")
        for item in entries:
            _check_cancel(cancelled)
            name = item.filename
            _require(1 <= len(name) <= 256 and "\\" not in name and ":" not in name
                     and not PurePosixPath(name).is_absolute() and all(x not in ("", ".", "..") for x in name.split("/"))
                     and not any(ord(x) < 32 for x in name) and name.casefold() not in names, "project_zip_path")
            names.add(name.casefold())
            _require(not stat.S_ISLNK(item.external_attr >> 16) and not item.flag_bits & 1
                     and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                     and 0 <= item.file_size <= 16 * 1024 * 1024, "project_zip_member")
            total += item.file_size
            _require(total <= 64 * 1024 * 1024, "project_zip_total")
            with archive.open(item) as source:
                chunks, remaining = [], item.file_size
                while remaining:
                    _check_cancel(cancelled)
                    chunk = source.read(min(remaining, 65536))
                    _require(bool(chunk), "project_zip_truncated")
                    chunks.append(chunk); remaining -= len(chunk)
                _require(not source.read(1), "project_zip_overflow")
            files[name] = b"".join(chunks)
    for name in files:
        _require(name not in ("Metadata/layer_heights_profile.txt", "Metadata/layer_config_ranges.xml"), "project_layer_override")
        if name.endswith(".rels"):
            for link in _xml(files[name]):
                target = link.get("Target", "")
                _require(link.get("TargetMode") != "External" and ":" not in target and "\\" not in target
                         and ".." not in target.split("/"), "project_external_reference")
    return files


def _apply(matrix, point):
    return tuple(sum(matrix[3 * col + row] * point[col] for col in range(3)) + matrix[9 + row] for row in range(3))


def _geometry(files):
    models = {name: _xml(raw) for name, raw in files.items() if name.endswith(".model")}
    _require("3D/3dmodel.model" in models and len(models) <= 8, "project_model_missing")
    objects = {}
    for name, model in models.items():
        _require(model.tag == _CORE + "model" and model.get("unit", "millimeter") == "millimeter", "project_model_units")
        for obj in model.findall(_CORE + "resources/" + _CORE + "object"):
            key = name, obj.get("id")
            _require(key not in objects and obj.get("type", "model") == "model", "project_object_identity")
            objects[key] = obj
    items = models["3D/3dmodel.model"].findall(_CORE + "build/" + _CORE + "item")
    _require(len(items) == 1 and items[0].get("printable", "1") == "1", "project_build_count")
    build = items[0]
    transform = _numbers(build.get("transform", "1 0 0 0 1 0 0 0 1 0 0 0"), 12)
    visited, meshes = set(), []
    def walk(key, transforms):
        _require(key in objects and key not in visited and len(visited) < 8, "project_component_reference")
        visited.add(key); obj = objects[key]
        mesh, components = obj.find(_CORE + "mesh"), obj.find(_CORE + "components")
        _require((mesh is None) != (components is None), "project_component_shape")
        if components is not None:
            _require(len(components) == 1, "project_component_count")
            part = components[0]
            path = part.get(_PROD + "path", key[0]).lstrip("/")
            _require(path in models, "project_component_path")
            walk((path, part.get("objectid")), transforms + [_numbers(part.get("transform", "1 0 0 0 1 0 0 0 1 0 0 0"), 12)])
        else:
            vertices = mesh.findall(_CORE + "vertices/" + _CORE + "vertex")
            triangles = mesh.findall(_CORE + "triangles/" + _CORE + "triangle")
            _require(len(vertices) == 8 and len(triangles) == 12, "project_mesh_count")
            points = []
            for vertex in vertices:
                _require(set(vertex.attrib) == {"x", "y", "z"}, "project_vertex")
                point = tuple(Decimal(vertex.get(axis)) for axis in "xyz")
                _require(all(x.is_finite() and abs(x) < 10**6 for x in point), "project_vertex")
                for matrix in reversed(transforms):
                    point = _apply(matrix, point)
                points.append(point)
            faces = []
            for triangle in triangles:
                _require(set(triangle.attrib) == {"v1", "v2", "v3"}, "project_paint_or_triangle")
                ids = [int(triangle.get(k)) for k in ("v1", "v2", "v3")]
                _require(len(set(ids)) == 3 and all(0 <= x < 8 for x in ids), "project_triangle_index")
                face = tuple(points[x] for x in ids)
                faces.append(min(face, face[1:] + face[:1], face[2:] + face[:2]))
            _require(len(set(points)) == 8 and len(set(faces)) == 12, "project_mesh_degenerate")
            meshes.append(tuple(sorted(faces)))
    walk(("3D/3dmodel.model", build.get("objectid")), [transform])
    _require(visited == set(objects) and len(meshes) == 1, "project_extra_object")
    return meshes[0], build.get("objectid"), transform


def inspect_project(raw, fixture, *, layer_height="0.24", expected_extruder="1",
                    expected_assembly_transform=None, cancelled=lambda: False):
    """Compare physical triangles and fixed slicing semantics, not ZIP byte order."""
    _require(type(expected_extruder) is str and expected_extruder in {"1", "2"}, "project_expected_tool")
    _require(expected_assembly_transform is None or
             (type(expected_assembly_transform) is tuple and len(expected_assembly_transform) == 12
              and all(type(x) is Decimal and x.is_finite() and abs(x) < 10**6 for x in expected_assembly_transform)),
             "project_expected_assembly")
    files, original = _archive(raw, cancelled), _archive(fixture, cancelled)
    config = _json(files["Metadata/project_settings.config"])
    _require(type(layer_height) is str and layer_height in ("0.24", "0.4"), "project_expected_layer")
    _require(type(config) is dict and type(config.get("layer_height")) is str and Decimal(config["layer_height"]) == Decimal(layer_height)
             and type(config.get("initial_layer_print_height")) is str and Decimal(config["initial_layer_print_height"]) == Decimal("0.4"), "project_layer_config")
    _require(config.get("enable_support") == config.get("raft_layers") == config.get("spiral_mode") == "0"
             # External import names the preset original_name + '(' + basename
             # + ')' (PresetBundle.cpp:2944, Preset.cpp:2284). Only this fixed
             # fixture alias is in scope, never an arbitrary prefix/suffix match.
             and config.get("printer_settings_id") in _PRINTER_IDS
             and type(config.get("nozzle_diameter")) is list and config["nozzle_diameter"]
             and all(Decimal(x) == Decimal("0.8") for x in config["nozzle_diameter"]), "project_slicing_scope")
    geometry, object_id, transform = _geometry(files)
    expected, _, original_transform = _geometry(original)
    _require(geometry == expected, "project_physical_geometry_changed")
    settings = _xml(files["Metadata/model_settings.config"])
    objects, parts = settings.findall("object"), settings.findall("object/part")
    _require(len(objects) == len(parts) == 1 and objects[0].get("id") == object_id
             and parts[0].get("subtype") == "normal_part", "project_part_scope")
    for obj in (objects[0], parts[0]):
        allowed = {"name", "extruder"} if obj is objects[0] else {"name", "matrix", "source_file", "source_object_id", "source_volume_id", "source_offset_x", "source_offset_y", "source_offset_z"}
        records = obj.findall("metadata")
        keys = [x.get("key") for x in records]
        _require(len(set(keys)) == len(keys) and set(keys) <= allowed, "project_object_override")
        values = {x.get("key"): x.get("value") for x in records}
        if obj is objects[0]:
            _require(values.get("extruder") == expected_extruder, "project_object_tool")
        else:
            _require(_numbers(values.get("matrix", ""), 16) == tuple(Decimal(x) for x in (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)), "project_part_matrix")
    assembly = settings.findall("assemble/assemble_item")
    wanted_assembly = original_transform if expected_assembly_transform is None else expected_assembly_transform
    _require(len(assembly) == 1 and assembly[0].get("object_id") == object_id
             and _numbers(assembly[0].get("transform", ""), 12) == wanted_assembly
             and _numbers(assembly[0].get("offset", ""), 3) == (0, 0, 0), "project_assembly_transform")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "layer_height": layer_height, "initial_layer_print_height": "0.4",
            "vertices": 8, "triangles": 12, "geometry_unchanged": True}
