"""Feishu precondition fixtures: the rows' own "add model" models on the standard settings.

    python tools/build_model_fixtures.py [--template fixtures/feishu_std_cube.3mf]
                                         [--models <slicer>/resources/handy_models] [--only NAME ...]

Every fixture is derived from one template (default fixtures/feishu_std_cube.3mf:
U1 0.4 nozzle, 0.20 mm Standard, all PLA) the way tools/build_shapes_fixture.py
derives the shapes plate, whose module this one reuses: settings and every other
non-geometry member are copied record for record, ids are continued from the
template, the XML is the template's own lines with values replaced.

An imported model keeps its geometry exactly as the source file carries it:
the vertex and triangle lines go into the mesh document verbatim, the source's
component transform and build-item transform are kept, and only the item's x /
y translation changes to place the object. Imported meshes are NOT required to
be closed or consistently oriented; they are checked for parsing, for triangle
indices in range and for counts equal to the source's. The meshes generated
here (cube, cylinder, sphere) get the closed-shell checks of the other module.

    feishu_std_boat       one 3DBenchy, extruder 1, bounding-box centre at 135,135
    feishu_std_boat2      two 3DBenchy, extruders 1 and 3, side by side, 20 mm apart
    feishu_std_fdmt       ksr_fdmtest_v4 (the menu's "Autodesk FDM Test"), as above
    feishu_std_fdmt2
    feishu_std_cubes2     two 20 mm cubes, extruders 1 and 3, centres 40 mm apart
    feishu_std_sphere     generated sphere, diameter 20 mm, extruder 1
    feishu_std_cylinder   the shapes plate's cylinder, d20 x 20 mm, extruder 1

Deterministic: two runs write the same bytes. Not done here: the thumbnails are
the template's (the cube); whether the application loads the files as intended
is for a real run to confirm. Needs Python 3.10 or newer.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import math
import os
import re
import sys
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))   # run as a script, `tools` is the script's folder and not yet a package
from tools import build_shapes_fixture as bf   # noqa: E402

DEFAULT_TEMPLATE = "fixtures/feishu_std_cube.3mf"
DEFAULT_MODELS = "C:/coil/Projects/SnapmakerOrca/resources/handy_models"   # the slicer's "add model" folder, read-only
MODEL_MEMBER = bf.MODEL_MEMBER
RELS_MEMBER = bf.MODEL_RELS_MEMBER
SETTINGS_MEMBER = bf.SETTINGS_MEMBER

CENTRE = (135.0, 135.0)   # mm; where a single object's bounding-box centre sits
GAP = 20.0                # mm; between the bounding boxes of a two-copy fixture (the task asks for at least 20)
IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
PLACE_TOLERANCE = 1e-5    # mm; a translation is written with 6 decimals
SOURCE_MEMBER = "3D/3dmodel.model"

VERTEX_BLOCK = re.compile(r"<vertices>\n(.*?)</vertices>", re.S)
TRIANGLE_BLOCK = re.compile(r"<triangles>\n(.*?)</triangles>", re.S)
VERTEX = re.compile(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>\n')
TRIANGLE = re.compile(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"/>\n')

Say = Callable[[str], None]


# ---------------------------------------------------------------- sources

@dataclass(frozen=True)
class Source:
    """A mesh exactly as its model 3MF carries it."""
    path: Path
    name: str
    vertex_block: str                      # the vertex lines, verbatim
    triangle_block: str                    # the triangle lines, verbatim
    vertices: tuple[tuple[float, float, float], ...]
    triangles: int
    component: tuple[str, ...]             # the component's transform, 12 tokens as written
    item: tuple[str, ...]                  # the build item's transform, 12 tokens as written


_sources: dict[Path, Source] = {}


def source_of(path: Path) -> Source:
    """The one mesh object of a plain model 3MF, read once per file."""
    if path in _sources:
        return _sources[path]
    try:
        with zipfile.ZipFile(path) as archive:
            model = archive.read(SOURCE_MEMBER)
            settings = archive.read(SETTINGS_MEMBER)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise bf.TemplateError(f"cannot read the model {path}: {exc}") from exc
    root = bf.xml_root(model, str(path), bf.TemplateError)
    objects = bf.find_all(root, "resources", "object")
    tops = [obj for obj in objects if bf.find_all(obj, "components", "component")]
    meshes = [obj for obj in objects if bf.find_all(obj, "mesh")]
    if len(tops) != 1 or len(meshes) != 1:
        raise bf.TemplateError(f"{path.name}: not one top-level object with one mesh object")
    components = bf.find_all(tops[0], "components", "component")
    top_id = bf.attributes(tops[0]).get("id")
    items = [item for item in bf.find_all(root, "build", "item") if bf.attributes(item).get("objectid") == top_id]
    if len(components) != 1 or len(items) != 1:
        raise bf.TemplateError(f"{path.name}: not one component and one build item")
    component = bf.attributes(components[0])
    if component.get("objectid") != bf.attributes(meshes[0]).get("id"):
        raise bf.TemplateError(f"{path.name}: the component does not point at the mesh object")
    setting_objects = bf.find_all(bf.xml_root(settings, f"{path.name}: {SETTINGS_MEMBER}", bf.TemplateError), "object")
    names = [bf.metadata_of(obj).get("name") for obj in setting_objects if bf.attributes(obj).get("id") == top_id]
    if len(names) != 1 or names[0] is None:
        raise bf.TemplateError(f"{path.name}: {SETTINGS_MEMBER} does not name the object")
    text = model.decode("utf-8")
    vertex_block = bf.present(VERTEX_BLOCK.search(text), f"{path.name}: no <vertices> block").group(1)
    triangle_block = bf.present(TRIANGLE_BLOCK.search(text), f"{path.name}: no <triangles> block").group(1)
    vertices = VERTEX.findall(vertex_block)
    if len(vertices) != vertex_block.count("\n") or len(TRIANGLE.findall(triangle_block)) != triangle_block.count("\n"):
        raise bf.TemplateError(f"{path.name}: vertex or triangle lines are not all of the form this tool copies")
    found = Source(path, names[0], vertex_block, triangle_block,
                   tuple((float(x), float(y), float(z)) for x, y, z in vertices), len(TRIANGLE.findall(triangle_block)),
                   tuple((component.get("transform") or bf.IDENTITY_TRANSFORM).split()),
                   tuple(bf.present(bf.attributes(items[0]).get("transform"), f"{path.name}: build item has no transform").split()))
    if len(found.component) != 12 or len(found.item) != 12:
        raise bf.TemplateError(f"{path.name}: a transform does not have 12 numbers")
    _sources[path] = found
    return found


def on_plate(vertices: Sequence[tuple[float, float, float]], *transforms: Sequence[str]) -> tuple[float, float, float, float, float, float]:
    """Bounding box (x0, y0, z0, x1, y1, z1) of the vertices after the transforms are applied in order."""
    points = vertices
    for tokens in transforms:
        m = [float(token) for token in tokens]
        if m[:9] == IDENTITY:
            points = [(x + m[9], y + m[10], z + m[11]) for x, y, z in points]
        else:
            points = [(m[0] * x + m[1] * y + m[2] * z + m[9], m[3] * x + m[4] * y + m[5] * z + m[10],
                       m[6] * x + m[7] * y + m[8] * z + m[11]) for x, y, z in points]
    return (min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points),
            max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points))


# ---------------------------------------------------------------- generated meshes

def ring(radius: int, sides: int) -> list[tuple[int, int]]:
    """A regular polygon on a vertex-first circle, rounded to a micrometre with the design's symmetry (as the cylinder)."""
    step = 2 * math.pi / sides
    arc = [(round(radius * math.cos(k * step)), round(radius * math.sin(k * step))) for k in range(sides // 8)]
    diagonal = round(radius * math.cos(math.pi / 4))
    arc.append((diagonal, diagonal))
    quarter = arc + [(y, x) for x, y in reversed(arc[:-1])]
    points: list[tuple[int, int]] = []
    turn = quarter[:-1]
    for _ in range(4):
        points += turn
        turn = [(-y, x) for x, y in turn]
    return points


def sphere(sides: int, bands: int, radius: float) -> bf.Shape:
    """A UV sphere of radius `radius` mm centred on x = y = 0, poles at z = 0 and z = 2r:
    `bands` equal-angle bands, `sides` longitudes."""
    bf.need(sides % 8 == 0 and sides >= 16 and bands % 2 == 0 and bands >= 4, "sphere: sides a multiple of 8, bands even")
    r = bf.mm(radius)
    step = math.pi / bands
    heights = [round(r * (1 - math.cos(i * step))) for i in range(bands // 2 + 1)]      # from the bottom pole
    heights += [2 * r - heights[bands - i] for i in range(bands // 2 + 1, bands)]          # mirrored about the equator
    radii = [round(r * math.sin(i * step)) for i in range(1, bands)]
    vertices: list[tuple[int, int, int]] = [(0, 0, 0), (0, 0, 2 * r)]
    for height, ring_radius in zip(heights[1:], radii):
        vertices += [(x, y, height) for x, y in ring(ring_radius, sides)]
    triangles: list[tuple[int, int, int]] = []
    for j in range(sides):
        k = (j + 1) % sides
        triangles.append((0, 2 + k, 2 + j))                      # bottom cap, pointing down
    for band in range(bands - 2):
        low, high = 2 + band * sides, 2 + (band + 1) * sides
        for j in range(sides):
            k = (j + 1) % sides
            triangles += [(low + j, low + k, high + k), (low + j, high + k, high + j)]
    top = 2 + (bands - 2) * sides
    for j in range(sides):
        triangles.append((1, top + j, top + (j + 1) % sides))    # top cap, pointing up
    # The design volume: every band is the frustum of a pyramid with regular `sides`-gon bases.
    area = lambda ring_radius: sides / 2 * ring_radius * ring_radius * math.sin(2 * math.pi / sides)   # noqa: E731
    exact_radii = [radius * math.sin(i * step) for i in range(1, bands)]
    exact_heights = [radius * (1 - math.cos(i * step)) for i in range(1, bands)]
    volume = exact_heights[0] / 3 * area(exact_radii[0])
    for lower in range(bands - 2):
        span = exact_heights[lower + 1] - exact_heights[lower]
        a, b = area(exact_radii[lower]), area(exact_radii[lower + 1])
        volume += span / 3 * (a + b + math.sqrt(a * b))
    volume += (2 * radius - exact_heights[-1]) / 3 * area(exact_radii[-1])
    return bf.Shape("球体", None, (bf.ShellDesign(volume, (-radius, radius, -radius, radius, 0, 2 * radius)),),
                    bf.Mesh(tuple(vertices), tuple(triangles)))


def cube(edge: float) -> bf.Shape:
    half = edge / 2
    design = bf.box_design((-half, half, -half, half, 0, edge))
    return bf.Shape("立方体", None, (design,), bf.box_mesh(design.box))


# ---------------------------------------------------------------- fixtures

@dataclass(frozen=True)
class Item:
    """One object of a fixture."""
    shape: bf.Shape
    extruder: str
    centre: tuple[float, float]
    source: Source | None = None      # None: the mesh is generated here


def two_apart(width: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Centres for two copies of a `width` mm wide object: side by side, GAP between their boxes, the pair on CENTRE."""
    return ((CENTRE[0] - (width + GAP) / 2, CENTRE[1]), (CENTRE[0] + (width + GAP) / 2, CENTRE[1]))


def specs(models: Path) -> dict[str, list[Item]]:
    """The fixtures in priority order."""
    boat, fdmt = source_of(models / "3DBenchy.3mf"), source_of(models / "ksr_fdmtest_v4.3mf")
    imported = bf.Shape("", None, (), bf.Mesh((), ()))      # the mesh is not generated, the source's lines are copied
    out: dict[str, list[Item]] = {}
    for stem, model in (("boat", boat), ("fdmt", fdmt)):
        box = on_plate(model.vertices, model.component, model.item)
        left, right = two_apart(box[3] - box[0])
        out[f"feishu_std_{stem}"] = [Item(replace(imported, name=model.name), "1", CENTRE, model)]
        out[f"feishu_std_{stem}2"] = [Item(replace(imported, name=model.name), "1", left, model),
                                      Item(replace(imported, name=model.name), "3", right, model)]
    out["feishu_std_cubes2"] = [Item(cube(20), "1", (CENTRE[0] - 20, CENTRE[1])), Item(replace(cube(20), name="立方体2"), "3", (CENTRE[0] + 20, CENTRE[1]))]
    out["feishu_std_sphere"] = [Item(sphere(64, 32, 10.0), "1", CENTRE)]
    out["feishu_std_cylinder"] = [Item(bf.shapes()[1], "1", CENTRE)]
    return dict(sorted(out.items(), key=lambda entry: ["feishu_std_boat", "feishu_std_boat2", "feishu_std_fdmt", "feishu_std_fdmt2",
                                                        "feishu_std_cubes2", "feishu_std_sphere", "feishu_std_cylinder"].index(entry[0])))


def place(template: bf.Template, items: Sequence[Item]) -> list[bf.Placed]:
    """The items with the ids the template's ids continue to (as the shapes plate's plan does)."""
    bf.need(len(items) <= 5, "at most five objects: the template's ids are continued for five")
    folder, _, stem = template.mesh_member.rpartition("/")
    extension = "." + stem.rsplit(".", 1)[1]
    placed = []
    for item, base in zip(items, bf.plan(template)):
        if item.source is None:
            transform = f"{bf.NO_ROTATION} {bf.number(item.centre[0])} {bf.number(item.centre[1])} 0"
        else:
            box = on_plate(item.source.vertices, item.source.component, item.source.item)
            tokens = item.source.item
            shift = (item.centre[0] - (box[0] + box[3]) / 2, item.centre[1] - (box[1] + box[4]) / 2)
            transform = " ".join(tokens[:9] + (bf.number(round(float(tokens[9]) + shift[0], 6)),
                                               bf.number(round(float(tokens[10]) + shift[1], 6)), tokens[11]))
        member = f"{folder + '/' if folder else ''}{item.shape.name}_{base.backup_id}{extension}"
        placed.append(replace(base, shape=item.shape, extruder=item.extruder, transform=transform,
                              member=member, path=template.path_style(member)))
    return placed


def imported_mesh_document(doc: bf.Doc, placed: bf.Placed, model: Source) -> str:
    """The template's mesh document around the source's vertex and triangle lines, verbatim."""
    skeleton = bf.mesh_skeleton(doc)
    obj = doc.tag(skeleton.object_open, "object")
    lines = doc.span(0, skeleton.resources + 1)
    lines.append(obj.with_values({"id": str(placed.volume_id), "UUID": placed.mesh_uuid}, doc.member).render() + doc.eol)
    lines.append(doc.line(skeleton.object_open + 1))
    lines.append(doc.line(skeleton.object_open + 2))
    lines.append(model.vertex_block)
    lines.append(doc.line(skeleton.vertices_close))
    lines.append(doc.line(skeleton.triangles_open))
    lines.append(model.triangle_block)
    lines.append(doc.line(skeleton.triangles_close))
    lines.append(doc.line(skeleton.mesh_close))
    lines.append(doc.line(skeleton.object_end))
    lines += doc.span(skeleton.resources_end, len(doc.body))
    return "".join(lines)


def assemble(template: bf.Template, objects: Sequence[bf.Placed], documents: dict[str, str]) -> bytes:
    entries = []
    for entry in template.entries:
        if entry.name in (MODEL_MEMBER, RELS_MEMBER, SETTINGS_MEMBER):
            entries.append(entry.clone(entry.name, documents[entry.name].encode("utf-8"), entry.deflate_level()))
        elif entry.name == template.mesh_member:
            level = entry.deflate_level()
            for placed in objects:
                entries.append(entry.clone(placed.member, documents[placed.member].encode("utf-8"), level))
        else:
            entries.append(entry)   # copied: header fields and bytes exactly as the template holds them
    return bf.write_archive(entries)


def build(template: bf.Template, items: Sequence[Item]) -> tuple[bytes, list[bf.Placed]]:
    objects = place(template, items)
    mesh = bf.Doc(template.contents[template.mesh_member], template.mesh_member)
    documents = {
        MODEL_MEMBER: bf.model_document(bf.Doc(template.contents[MODEL_MEMBER], MODEL_MEMBER), objects),
        RELS_MEMBER: bf.rels_document(bf.Doc(template.contents[RELS_MEMBER], RELS_MEMBER), objects),
        SETTINGS_MEMBER: bf.settings_document(bf.Doc(template.contents[SETTINGS_MEMBER], SETTINGS_MEMBER), objects),
    }
    for placed, item in zip(objects, items):
        documents[placed.member] = (imported_mesh_document(mesh, placed, item.source) if item.source is not None
                                    else bf.mesh_document(mesh, placed))
    return assemble(template, objects, documents), objects


# ---------------------------------------------------------------- validation

def validate(output: bytes, template: bf.Template, items: Sequence[Item], objects: Sequence[bf.Placed], say: Say) -> None:
    written = {MODEL_MEMBER, RELS_MEMBER, SETTINGS_MEMBER} | {placed.member for placed in objects}
    order: list[str] = []
    for entry in template.entries:
        order += [placed.member for placed in objects] if entry.name == template.mesh_member else [entry.name]
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        bf.require(archive.testzip() is None, "zip: a member does not match its CRC")
        bf.require([info.filename for info in archive.infolist()] == order, "zip: member order is not the template's")
        contents = {name: archive.read(name) for name in order}
    indexed = {entry.name: entry for entry in bf.read_archive(output, bf.ValidationError)[0]}
    copied = [entry for entry in template.entries
              if entry.name not in {MODEL_MEMBER, RELS_MEMBER, SETTINGS_MEMBER, template.mesh_member}]
    for entry in copied:
        bf.require(contents[entry.name] == template.contents[entry.name] and indexed[entry.name] == entry,
                   f"{entry.name}: differs from the template")
    roots = {name: bf.xml_root(contents[name], name, bf.ValidationError) for name in order if name in written}
    say(f"zip opens, {len(order)} members, CRCs match; {len(roots)} generated members parse as XML; "
        f"copied members byte-identical to the template {len(copied)} of {len(copied)} "
        f"({', '.join(entry.name for entry in copied)})")

    model = roots[MODEL_MEMBER]
    model_objects = bf.find_all(model, "resources", "object")
    build_items = bf.find_all(model, "build", "item")
    relationships = [rel for rel in roots[RELS_MEMBER] if bf.short_name(rel.tag) == "Relationship"]
    bf.require(len(model_objects) == len(build_items) == len(relationships) == len(objects),
               f"not {len(objects)} objects / build items / relationships")
    boxes: list[tuple[float, float, float, float, float, float]] = []
    for k, (placed, item) in enumerate(zip(objects, items)):
        components = bf.find_all(model_objects[k], "components", "component")
        bf.require(len(components) == 1, f"object {k} has {len(components)} components")
        obj, component, built, relation = (bf.attributes(model_objects[k]), bf.attributes(components[0]),
                                           bf.attributes(build_items[k]), bf.attributes(relationships[k]))
        bf.require(obj.get("id") == str(placed.object_id) and component.get("objectid") == str(placed.volume_id),
                   f"object {k}: ids are {obj.get('id')} / {component.get('objectid')}, not {placed.object_id} / {placed.volume_id}")
        bf.require(template.path_style(placed.member) == component.get("path") == relation.get("Target"),
                   "p:path, Target and member disagree")
        bf.require(relation.get("Id") == placed.rel_id and relation.get("Type") == template.rel_type, "relationship id or type")
        bf.require(built.get("objectid") == str(placed.object_id) and built.get("transform") == placed.transform,
                   f"build item {k} does not reference the object with the planned transform")
        bf.require(obj.get("UUID") == placed.object_uuid and component.get("UUID") == placed.component_uuid
                   and built.get("UUID") == placed.item_uuid, "p:UUIDs")
        component_transform = (component.get("transform") or bf.IDENTITY_TRANSFORM).split()

        text = contents[placed.member].decode("utf-8")
        vertex_block = bf.present(VERTEX_BLOCK.search(text), f"{placed.member}: no <vertices> block").group(1)
        triangle_block = bf.present(TRIANGLE_BLOCK.search(text), f"{placed.member}: no <triangles> block").group(1)
        mesh_objects = bf.find_all(roots[placed.member], "resources", "object")
        bf.require(len(mesh_objects) == 1 and bf.attributes(mesh_objects[0]).get("id") == str(placed.volume_id)
                   and bf.attributes(mesh_objects[0]).get("UUID") == placed.mesh_uuid, f"{placed.member}: object id / p:UUID")
        if item.source is not None:
            # verbatim: the lines themselves; only the indentation before the closing tags is the template's
            bf.require(vertex_block.strip(" ") == item.source.vertex_block.strip(" ")
                       and triangle_block.strip(" ") == item.source.triangle_block.strip(" "),
                       f"{placed.member}: vertex or triangle lines differ from the source")
            parsed_vertices = bf.find_all(mesh_objects[0], "mesh", "vertices", "vertex")
            parsed_triangles = bf.find_all(mesh_objects[0], "mesh", "triangles", "triangle")
            bf.require(len(parsed_vertices) == len(item.source.vertices) and len(parsed_triangles) == item.source.triangles,
                       f"{placed.member}: counts differ from the source")
            bf.require(all(int(value) < len(parsed_vertices) for triangle in TRIANGLE.findall(triangle_block) for value in triangle),
                       f"{placed.member}: a triangle index is out of range")
            bf.require([(float(bf.attributes(vertex)["x"]), float(bf.attributes(vertex)["y"]), float(bf.attributes(vertex)["z"]))
                        for vertex in parsed_vertices] == list(item.source.vertices), f"{placed.member}: parsed vertices differ from the source's")
            bf.require([(int(bf.attributes(triangle)["v1"]), int(bf.attributes(triangle)["v2"]), int(bf.attributes(triangle)["v3"]))
                        for triangle in parsed_triangles]
                       == [tuple(int(value) for value in triangle) for triangle in TRIANGLE.findall(triangle_block)],
                       f"{placed.member}: parsed triangles differ from the source's")
            say(f"  {item.source.name} ({item.source.path.name}): source lines verbatim, {len(parsed_vertices)} vertices and "
                f"{len(parsed_triangles)} triangles as in the source, every triangle index < {len(parsed_vertices)}")
        else:
            bf.require(all(bf.DECIMAL_TEXT.fullmatch(value) for vertex in VERTEX.findall(vertex_block) for value in vertex),
                       f"{placed.member}: a coordinate has more than 6 decimals")
            vertices = [tuple(round(float(value) * bf.MICRO) for value in vertex) for vertex in VERTEX.findall(vertex_block)]
            triangles = [tuple(int(value) for value in triangle) for triangle in TRIANGLE.findall(triangle_block)]
            bf.require(all(0 <= min(triangle) and max(triangle) < len(vertices) for triangle in triangles), f"{placed.member}: triangle index")
            bf.check_mesh(item.shape.name, vertices, triangles, item.shape, say)   # type: ignore[arg-type]
        floats = [(float(x), float(y), float(z)) for x, y, z in VERTEX.findall(vertex_block)]
        box = on_plate(floats, component_transform, (built.get("transform") or "").split())
        centre = ((box[0] + box[3]) / 2, (box[1] + box[4]) / 2)
        bf.require(abs(centre[0] - item.centre[0]) <= PLACE_TOLERANCE and abs(centre[1] - item.centre[1]) <= PLACE_TOLERANCE,
                   f"{item.shape.name}: bounding-box centre is {centre}, not {item.centre}")
        bf.require(abs(box[2]) <= 1e-3, f"{item.shape.name}: bottom at z = {box[2]}, not on the bed")
        boxes.append(box)
        say(f"  {item.shape.name}: extruder {item.extruder}, plate bbox read from the vertices x {bf.number(box[0])}..{bf.number(box[3])}, "
            f"y {bf.number(box[1])}..{bf.number(box[4])}, z {bf.number(box[2])}..{bf.number(box[5])} mm "
            f"(centre {bf.number(centre[0])}, {bf.number(centre[1])}); transform {built.get('transform')}")
    if len(boxes) == 2:
        gap = boxes[1][0] - boxes[0][3] if boxes[1][0] >= boxes[0][3] else boxes[0][0] - boxes[1][3]   # side by side in x
        bf.require(gap >= GAP - PLACE_TOLERANCE or len(items) == 2 and items[0].source is None,
                   f"the two boxes are {gap} mm apart")
        say(f"  two objects: gap between their bounding boxes {bf.number(gap)} mm")

    settings = roots[SETTINGS_MEMBER]
    setting_objects = bf.find_all(settings, "object")
    instances = bf.find_all(settings, "plate", "model_instance")
    assembled = bf.find_all(settings, "assemble", "assemble_item")
    bf.require(len(setting_objects) == len(instances) == len(assembled) == len(objects), "model_settings: object, instance and assemble counts")
    before = bf.xml_root(template.contents[SETTINGS_MEMBER], SETTINGS_MEMBER, bf.ValidationError)
    template_items = bf.find_all(before, "assemble", "assemble_item")
    for k, (placed, item) in enumerate(zip(objects, items)):
        meta = bf.metadata_of(setting_objects[k])
        parts = bf.find_all(setting_objects[k], "part")
        bf.require(bf.attributes(setting_objects[k]).get("id") == str(placed.object_id) and meta.get("name") == item.shape.name
                   and meta.get("extruder") == item.extruder, f"model_settings: object {k} id, name or extruder")
        bf.require(len(parts) == 1 and bf.attributes(parts[0]).get("id") == str(placed.volume_id), f"model_settings: part of object {k}")
        bf.require(bf.metadata_of(instances[k]) == {**bf.metadata_of(bf.find_all(before, "plate", "model_instance")[0]),
                                                      "object_id": str(placed.object_id), "identify_id": str(placed.identify_id)},
                   f"model_settings: model_instance {k}")
        bf.require(bf.attributes(assembled[k]) == {**bf.attributes(template_items[0]), "object_id": str(placed.object_id),
                                                    "transform": placed.transform}, f"model_settings: assemble_item {k}")
    bf.require(bf.metadata_of(bf.find_all(settings, "plate")[0]) == bf.metadata_of(bf.find_all(before, "plate")[0]),
               "model_settings: the plate's metadata differ from the template's")
    say(f"  model_settings: {len(setting_objects)} objects {[bf.metadata_of(obj).get('name') for obj in setting_objects]}, "
        f"extruders {[bf.metadata_of(obj).get('extruder') for obj in setting_objects]}, {len(instances)} model_instance, "
        f"{len(assembled)} assemble_items with the build items' transforms, plate metadata = the template's")


# ---------------------------------------------------------------- entry point

def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Feishu precondition fixtures: the rows' models on the template's settings.")
    parser.add_argument("--template", default=str(ROOT / DEFAULT_TEMPLATE), help="the project the settings and container come from")
    parser.add_argument("--models", default=DEFAULT_MODELS, help="the slicer's handy_models folder (read-only)")
    parser.add_argument("--only", nargs="*", default=None, metavar="NAME", help="build only these (file names without .3mf)")
    args = parser.parse_args(argv)
    lines: list[str] = []
    say: Say = lines.append
    try:
        template_path = Path(args.template)
        raw = template_path.read_bytes()
        template = bf.read_template(raw)
        say(f"template {template_path}: {len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()}")
        wanted = specs(Path(args.models))
        if args.only:
            bf.need(set(args.only) <= set(wanted), f"unknown fixture(s): {sorted(set(args.only) - set(wanted))}")
            wanted = {name: wanted[name] for name in wanted if name in args.only}
        for name, items in wanted.items():
            output, objects = build(template, items)
            validate(output, template, items, objects, say)
            out_path = ROOT / "fixtures" / f"{name}.3mf"
            if out_path.exists():
                say(f"existing {out_path.name}: " + ("byte-identical to this build" if out_path.read_bytes() == output else "DIFFERENT, it is replaced"))
            handle = tempfile.NamedTemporaryFile(dir=out_path.parent, prefix=out_path.name + ".", suffix=".tmp", delete=False)
            try:
                with handle:
                    handle.write(output)
                os.replace(handle.name, out_path)
            except BaseException:
                Path(handle.name).unlink(missing_ok=True)
                raise
            bf.require(out_path.read_bytes() == output, "the file read back from disk differs from what was built")
            say(f"output {out_path}: {len(output)} bytes, sha256 {hashlib.sha256(output).hexdigest()}")
    except bf.FixtureError as exc:
        if lines:
            print("\n".join(lines))
        sys.stdout.flush()
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
