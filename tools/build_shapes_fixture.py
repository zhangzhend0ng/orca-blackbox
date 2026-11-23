"""A five-object plate for the Feishu process-parameter rows, derived from a
template project: the geometry is replaced, every other member is kept.

    python tools/build_shapes_fixture.py [--template fixtures/agent_layer_cube.3mf]
                                         [--out fixtures/feishu_shapes_plate.3mf]

The 44 "process parameter" rows run on fixtures/agent_layer_cube.3mf, one
27 mm cube. On a cube many of them have nothing to act on: no overhang (the
exported G-codes of the support-family cases hold no `;TYPE:Support` block),
nothing that bridges, no curve for arc fitting, and one object that never
changes a tool, prints by object or excludes one. This tool derives a second
plate from the template whose five objects carry those features (names are
the Feishu wording, order is plate order):

    立方体      cube, 20 mm edge
    圆柱体      cylinder, diameter 20 mm, 20 mm high, 96 segments
    搭桥        two 8x8x12 pillars 16 mm apart under a 32x8x3 beam: THREE closed
                shells in one mesh (the beam sits on the pillar tops at z = 12)
    悬垂台阶    four 4 mm tall boxes, footprints 20x8 / 20x12 / 20x16 / 20x20 mm,
                the narrow one on the bed: every box above overhangs the one
                below by 2 mm per side (ledges facing down at z = 4, 8, 12);
                FOUR closed shells in one mesh
    立方体2     cube, 15 mm edge, on extruder 3 (the others keep the template's)

Each mesh is centred on its own XY origin with z = 0 at the bottom and is
placed by the item transform alone: centres x = 35 / 80 / 128 / 176 / 215,
all on y = 135, never less than 20 mm apart. The plate carries the template's slicer settings unchanged.

How the project is derived. Nothing about the template's settings is assumed,
only its container: one top-level object with one component in its own mesh
document. Ids, UUIDs, relationship ids and file names are read from the
template and continued by the rules the slicer's own exporter uses
(_BBS_3MF_Exporter in src/libslic3r/Format/bbs_3mf.cpp): the k-th new object
gets object id + k, volume id + k and backup id + k; a UUID keeps its suffix
and its 8-hex-digit prefix is rebuilt from those numbers; the mesh file is
"<object name>_<backup id>" in the template's folder. The XML is produced by
text templating, never by re-serialising: each line that changes is the
template's own line with attribute values replaced, so attribute order,
indentation, quoting and line endings are the template's. Zip members other
than the model, its relationships, the mesh documents and model_settings
are copied record for record (header fields and compressed bytes).

Errors: exceptions of one family (FixtureError) - TemplateError for an input
the tool cannot build from, ValidationError for a failed check; main() prints
the message and exits 1. The required checks are `require(...)` calls, not
`assert` statements, so `python -O` cannot strip them, and they run on the
output read back from its bytes.

Not done here: the five PNG thumbnails are copied unchanged, so they still
show the cube until the application redraws them on save; whether the
application loads the result as intended is for a real run to confirm.

unit_tests/test_build_shapes_fixture.py ties the committed fixture to this
tool and shows every check going red on a deliberately broken variant.
Needs Python 3.10 or newer (union annotations), as the harness does.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = "fixtures/agent_layer_cube.3mf"
DEFAULT_OUT = "fixtures/feishu_shapes_plate.3mf"

MODEL_MEMBER = "3D/3dmodel.model"
MODEL_RELS_MEMBER = "3D/_rels/3dmodel.model.rels"
ROOT_RELS_MEMBER = "_rels/.rels"
SETTINGS_MEMBER = "Metadata/model_settings.config"
PROJECT_SETTINGS_MEMBER = "Metadata/project_settings.config"

PLATE_Y = 135                       # mm; the row every object centre sits on
# Spaced for the by-object rows (#292, #297): every gap is at least 20 mm so
# the slicer has room to print object after object (the first layout left 14
# mm beside the 32 mm bridge).
CENTRE_X = (35, 80, 128, 176, 215)   # mm; object centres in plate order
MIN_GAP = 20                        # mm; smallest clearance between two objects
NO_ROTATION = "1 0 0 0 1 0 0 0 1"    # rotation/scale part of the 3MF transform
IDENTITY_TRANSFORM = "1 0 0 0 1 0 0 0 1 0 0 0"
IDENTITY_MATRIX = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"
UUID_TEXT = re.compile(r"([0-9A-Fa-f]{8})((?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})")   # 8 hex digits, then the slicer's suffix
REL_ID = re.compile(r"rel-([0-9]+)")

MICRO = 1_000_000        # mesh coordinates are integers in millionths of a millimetre
DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?")   # at most 6 decimals, as the task requires
REL_TOLERANCE = 1e-6     # volumes, relative - the task's tolerance
ABS_TOLERANCE = 1e-6     # millimetres, bounding boxes and positions - the task's tolerance
MAX_MEMBER_TOTAL = 1 << 30   # uncompressed bytes read into memory; the largest fixture here is 36 MB

Say = Callable[[str], None]


class FixtureError(Exception):
    """A run that has to stop; the message says what failed and where."""


class TemplateError(FixtureError):
    """An input the tool cannot build from: the template, an argument, a design constant."""


class ValidationError(FixtureError):
    """A required check on the output failed."""


def need(condition: object, message: str) -> None:
    """Assert a property of an input; TemplateError otherwise."""
    if not condition:
        raise TemplateError(message)


def require(condition: object, message: str) -> None:
    """Assert a required property of the output; ValidationError otherwise."""
    if not condition:
        raise ValidationError(message)


# ---------------------------------------------------------------- numbers

def mm(value: float) -> int:
    """Millimetres (a design number) -> integer millionths."""
    scaled = round(value * MICRO)
    need(abs(value * MICRO - scaled) < 1e-6, f"design number {value!r} is not a multiple of a micrometre")
    return scaled


def text_of_micro(value: int) -> str:
    """Integer millionths -> decimal text: at most 6 decimals, no trailing zeros."""
    sign = "-" if value < 0 else ""
    whole, fraction = divmod(abs(value), MICRO)
    return f"{sign}{whole}.{fraction:06d}".rstrip("0") if fraction else f"{sign}{whole}"


def number(value: float) -> str:
    """A measured millimetre for the report."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def xml_attr(value: str) -> str:
    """Escape an attribute value the way the slicer's xml_escape does."""
    need(not re.search(r"[\x00-\x1f]", value), f"{value!r}: control characters cannot go into an attribute")
    for raw, entity in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&apos;")):
        value = value.replace(raw, entity)
    return value


# ---------------------------------------------------------------- geometry

Vertex = tuple[int, int, int]
Face = tuple[int, int, int]
Box = tuple[float, float, float, float, float, float]   # x0, x1, y0, y1, z0, z1 in mm


@dataclass(frozen=True)
class Mesh:
    """One object's mesh. Shells that touch do not share vertices."""
    vertices: tuple[Vertex, ...]
    triangles: tuple[Face, ...]


@dataclass(frozen=True)
class ShellDesign:
    """What one shell must measure: its design volume and its design box."""
    volume: float
    box: Box


@dataclass(frozen=True)
class Shape:
    """One object of the plate as designed (name and extruder are the task's)."""
    name: str
    extruder: str | None      # None: keep the template's value
    shells: tuple[ShellDesign, ...]
    mesh: Mesh

    @property
    def size(self) -> tuple[float, float, float]:
        low = (min(shell.box[0] for shell in self.shells), min(shell.box[2] for shell in self.shells),
               min(shell.box[4] for shell in self.shells))
        high = (max(shell.box[1] for shell in self.shells), max(shell.box[3] for shell in self.shells),
                max(shell.box[5] for shell in self.shells))
        return high[0] - low[0], high[1] - low[1], high[2] - low[2]


def box_design(box: Box) -> ShellDesign:
    x0, x1, y0, y1, z0, z1 = box
    need(x0 < x1 and y0 < y1 and z0 < z1, f"design box {box} is empty or inside-out")
    return ShellDesign((x1 - x0) * (y1 - y0) * (z1 - z0), box)


def box_mesh(box: Box) -> Mesh:
    """A closed axis-aligned box: 8 vertices, 12 triangles, counter-clockwise seen from outside."""
    x0, x1, y0, y1, z0, z1 = (mm(value) for value in box)
    corners = tuple((x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1))   # index 4*ix + 2*iy + iz
    faces = (
        ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)),   # +x
        ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),   # -x
        ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),   # +y
        ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),   # -y
        ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),   # +z
        ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)),   # -z
    )
    triangles: list[Face] = []
    for face in faces:
        a, b, c, d = (4 * ix + 2 * iy + iz for ix, iy, iz in face)
        triangles += [(a, b, c), (a, c, d)]
    return Mesh(corners, tuple(triangles))


def prism_mesh(sides: int, radius: int, height: int) -> Mesh:
    """A closed regular prism on a vertex-first polygon: z in [0, height], xy centred.

    Coordinates are rounded to a micrometre on an eighth of the ring and
    completed by mirror and quarter turns, so the rounded polygon keeps the
    design's symmetry (centre at the origin, extreme coordinates exact).
    """
    need(sides % 8 == 0 and sides >= 16, f"a {sides}-sided prism is not supported")
    step = 2 * math.pi / sides
    arc = [(round(radius * math.cos(k * step)), round(radius * math.sin(k * step))) for k in range(sides // 8)]
    diagonal = round(radius * math.cos(math.pi / 4))
    arc.append((diagonal, diagonal))
    quarter = arc + [(y, x) for x, y in reversed(arc[:-1])]
    ring: list[tuple[int, int]] = []
    turn = quarter[:-1]
    for _ in range(4):
        ring += turn
        turn = [(-y, x) for x, y in turn]
    bottom = [(x, y, 0) for x, y in ring]
    top = [(x, y, height) for x, y in ring]
    triangles: list[Face] = []
    for i in range(sides):
        j = (i + 1) % sides
        p, q = 2 + i, 2 + j
        r, s = 2 + sides + i, 2 + sides + j
        triangles += [(0, q, p), (1, r, s), (p, q, s), (p, s, r)]
    return Mesh(tuple([(0, 0, 0), (0, 0, height)] + bottom + top), tuple(triangles))


def join(*meshes: Mesh) -> Mesh:
    """Shells into one mesh; vertex indices are offset, vertices are never shared."""
    vertices: list[Vertex] = []
    triangles: list[Face] = []
    for mesh in meshes:
        offset = len(vertices)
        vertices += mesh.vertices
        triangles += [(a + offset, b + offset, c + offset) for a, b, c in mesh.triangles]
    return Mesh(tuple(vertices), tuple(triangles))


def shapes() -> tuple[Shape, ...]:
    """The five objects in plate order, as designed."""
    need(len(CENTRE_X) == 5, "the plate has five objects")
    cube = box_design((-10, 10, -10, 10, 0, 20))
    radius, height, sides = 10.0, 20.0, 96
    prism = ShellDesign(sides * radius * radius * math.sin(2 * math.pi / sides) / 2 * height,
                        (-radius, radius, -radius, radius, 0, height))
    # The brief gives the bridge at x in [0, 32]; it is moved by -16 to sit on its own origin.
    pillars = tuple(box_design((x0 - 16, x0 + 8 - 16, -4, 4, 0, 12)) for x0 in (0, 24))
    beam = box_design((-16, 16, -4, 4, 12, 15))
    steps = tuple(box_design(box) for box in (
        (-10, 10, -4, 4, 0, 4), (-10, 10, -6, 6, 4, 8),
        (-10, 10, -8, 8, 8, 12), (-10, 10, -10, 10, 12, 16)))
    cube2 = box_design((-7.5, 7.5, -7.5, 7.5, 0, 15))
    return (
        Shape("立方体", None, (cube,), box_mesh(cube.box)),
        Shape("圆柱体", None, (prism,), prism_mesh(sides, mm(radius), mm(height))),
        Shape("搭桥", None, pillars + (beam,), join(*(box_mesh(design.box) for design in pillars + (beam,)))),
        Shape("悬垂台阶", None, steps, join(*(box_mesh(design.box) for design in steps))),
        Shape("立方体2", "3", (cube2,), box_mesh(cube2.box)),
    )


# ---------------------------------------------------------------- mesh checks

def sub(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def cross(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def edge_keys(triangle: Sequence[int]) -> list[tuple[int, int]]:
    a, b, c = triangle
    return [(min(a, b), max(a, b)), (min(b, c), max(b, c)), (min(c, a), max(c, a))]


def shell_split(triangles: Sequence[Face]) -> list[list[int]]:
    """Triangle indices per shell; a shell is triangles joined by edges, shells come in order of first appearance."""
    parent = list(range(len(triangles)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    first_by_edge: dict[tuple[int, int], int] = {}
    for index, triangle in enumerate(triangles):
        for edge in edge_keys(triangle):
            if edge in first_by_edge:
                a, b = root(first_by_edge[edge]), root(index)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                first_by_edge[edge] = index
    groups: dict[int, list[int]] = {}
    for index in range(len(triangles)):
        groups.setdefault(root(index), []).append(index)
    return [members for _, members in sorted(groups.items())]


@dataclass(frozen=True)
class ShellStats:
    """What one shell measured; coordinates and volume are in micro-metre units."""
    triangles: int
    edges: int
    open_edges: int       # edges that do not join exactly two triangles
    repeated_edges: int   # directed edges that occur more than once
    volume: float
    low: tuple[float, float, float]
    high: tuple[float, float, float]


def shell_stats(vertices: Sequence[Vertex], triangles: Sequence[Face], indices: Sequence[int]) -> ShellStats:
    """Topology, signed volume and bounding box of one shell (the triangle indices it consists of)."""
    undirected: dict[tuple[int, int], int] = {}
    directed: set[tuple[int, int]] = set()
    repeated = 0
    volume6 = 0.0
    low = [math.inf] * 3
    high = [-math.inf] * 3
    for index in indices:
        a, b, c = triangles[index]
        pa, pb, pc = vertices[a], vertices[b], vertices[c]
        normal = cross(sub(pb, pa), sub(pc, pa))
        volume6 += pa[0] * normal[0] + pa[1] * normal[1] + pa[2] * normal[2]
        for axis in range(3):
            low[axis] = min(low[axis], pa[axis], pb[axis], pc[axis])
            high[axis] = max(high[axis], pa[axis], pb[axis], pc[axis])
        for p, q in ((a, b), (b, c), (c, a)):
            if (p, q) in directed:
                repeated += 1
            directed.add((p, q))
            edge = (min(p, q), max(p, q))
            undirected[edge] = undirected.get(edge, 0) + 1
    return ShellStats(len(indices), len(undirected),
                      sum(1 for count in undirected.values() if count != 2), repeated,
                      volume6 / 6.0, (low[0], low[1], low[2]), (high[0], high[1], high[2]))


def check_mesh(name: str, vertices: Sequence[Vertex], triangles: Sequence[Face], design: Shape, say: Say) -> int:
    """Every required property of one object's mesh, on what was read from the file; returns the shell count."""
    where = f"{name}: mesh"
    used: set[int] = set()
    seen: set[tuple[int, ...]] = set()
    for triangle in triangles:
        a, b, c = triangle
        used.update(triangle)
        require(0 <= min(triangle) and max(triangle) < len(vertices), f"{where} triangle {triangle} leaves the vertex list")
        require(len(set(triangle)) == 3, f"{where} triangle {triangle} repeats a vertex")
        normal = cross(sub(vertices[b], vertices[a]), sub(vertices[c], vertices[a]))
        require(abs(normal[0]) + abs(normal[1]) + abs(normal[2]) > 0.0, f"{where} triangle {triangle} has no area")
        key = tuple(sorted(triangle))
        require(key not in seen, f"{where} triangle {triangle} is a duplicate")
        seen.add(key)
    require(len(used) == len(vertices), f"{where} has {len(vertices) - len(used)} vertices no triangle uses")
    shells = shell_split(triangles)
    require(len(shells) == len(design.shells), f"{where} has {len(shells)} shells, the design has {len(design.shells)}")
    total = 0.0
    design_total = sum(shell.volume for shell in design.shells)
    for order, (indices, shell) in enumerate(zip(shells, design.shells), start=1):
        stats = shell_stats(vertices, triangles, indices)
        volume = stats.volume / MICRO ** 3   # the divergence theorem over micro-metre coordinates
        box_low = [value / MICRO for value in stats.low]
        box_high = [value / MICRO for value in stats.high]
        deviation = max(abs(a - b) for a, b in zip((box_low[0], box_high[0], box_low[1], box_high[1], box_low[2], box_high[2]), shell.box))
        drift = abs(volume - shell.volume) / shell.volume
        require(stats.open_edges == 0, f"{where} shell {order}: {stats.open_edges} of {stats.edges} edges do not join exactly two triangles")
        require(stats.repeated_edges == 0, f"{where} shell {order}: {stats.repeated_edges} directed edges occur twice (inconsistent winding)")
        require(volume > 0.0, f"{where} shell {order}: signed volume {volume:.6f} mm3 is not positive")
        require(drift <= REL_TOLERANCE, f"{where} shell {order}: volume {volume:.6f} against design {shell.volume:.6f} mm3 (relative {drift:.1e})")
        require(deviation <= ABS_TOLERANCE, f"{where} shell {order}: bounding box off the design by {deviation:.1e} mm")
        say(f"  shell {order}/{len(shells)}: {stats.triangles} triangles, {stats.edges} edges, closed (each edge in exactly 2 triangles), "
            f"oriented (each directed edge once), signed volume {volume:.6f} mm3 vs design {shell.volume:.6f} (rel {drift:.1e}), "
            f"bbox {box_text(box_low, box_high)} mm (dev {deviation:.1e})")
        total += volume
    drift = abs(total - design_total) / design_total
    require(drift <= REL_TOLERANCE, f"{where}: object volume {total:.6f} against the design {design_total:.6f} (relative {drift:.1e})")
    low = [min(vertex[axis] for vertex in vertices) / MICRO for axis in range(3)]
    high = [max(vertex[axis] for vertex in vertices) / MICRO for axis in range(3)]
    centre = ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2)
    require(abs(centre[0]) <= ABS_TOLERANCE and abs(centre[1]) <= ABS_TOLERANCE, f"{where}: not centred on its own XY origin (centre {centre})")
    require(abs(low[2]) <= ABS_TOLERANCE, f"{where}: bottom at z = {low[2]}, not 0")
    say(f"  object: {len(shells)} shells, {len(triangles)} triangles, {len(vertices)} vertices, volume {total:.6f} mm3, "
        f"bbox {box_text(low, high)} mm (own origin at the XY centre, bottom at z = 0)")
    return len(shells)


def box_text(low: Sequence[float], high: Sequence[float]) -> str:
    return " x ".join(f"[{number(a)}, {number(b)}]" for a, b in zip(low, high))


# ---------------------------------------------------------------- zip records

LOCAL = struct.Struct("<4sHHHHHIIIHH")
CENTRAL = struct.Struct("<4sHHHHHHIIIHHHHHII")
END = struct.Struct("<4sHHHHIIH")
ENCRYPTED, DATA_DESCRIPTOR, UTF8 = 0x0001, 0x0008, 0x0800
STORED, DEFLATED = 0, 8


@dataclass(frozen=True)
class Entry:
    """One zip member as the file stores it: every header field and the bytes as stored."""
    name: str
    raw_name: bytes
    flags: int
    method: int
    time: int
    date: int
    crc: int
    data: bytes
    size: int
    made_by: int
    local_version: int
    central_version: int
    internal_attr: int
    external_attr: int
    local_extra: bytes
    central_extra: bytes
    comment: bytes

    def content(self, error: type[FixtureError]) -> bytes:
        if self.method == STORED:
            data = self.data
        elif self.method == DEFLATED:
            try:
                data = zlib.decompress(self.data, -15)
            except zlib.error as exc:
                raise error(f"zip member {self.name}: broken deflate stream ({exc})") from exc
        else:
            raise error(f"zip member {self.name}: compression method {self.method} is not supported")
        if len(data) != self.size or zlib.crc32(data) & 0xFFFFFFFF != self.crc:
            raise error(f"zip member {self.name}: size or CRC does not match its content")
        return data

    def deflate_level(self) -> int:
        """The level whose output equals the member's own deflate stream; 6 when there is none such."""
        if self.method != DEFLATED:
            return 6
        content = self.content(TemplateError)
        for level in (6, 9, 8, 7, 5, 4, 3, 2, 1):
            if deflate(content, level) == self.data:
                return level
        return 6

    def clone(self, name: str, content: bytes, level: int) -> Entry:
        """The same record fields around a new name and new content (the template's method, time and attributes)."""
        if self.method == STORED:
            data = content
        elif self.method == DEFLATED:
            data = deflate(content, level)
        else:
            raise TemplateError(f"zip member {self.name}: compression method {self.method} is not supported")
        return replace(self, name=name, raw_name=name.encode("utf-8"),
                       flags=(self.flags & ~UTF8) | (UTF8 if not name.isascii() else 0),
                       crc=zlib.crc32(content) & 0xFFFFFFFF, data=data, size=len(content))


def deflate(content: bytes, level: int) -> bytes:
    packer = zlib.compressobj(level, zlib.DEFLATED, -15)
    return packer.compress(content) + packer.flush()


def valid_member_name(name: str) -> bool:
    return (bool(name) and not re.search(r'[\\:\x00-\x1f]', name) and not name.startswith("/")
            and all(part not in ("", ".", "..") for part in name.split("/")))


def read_archive(raw: bytes, error: type[FixtureError]) -> tuple[list[Entry], list[int]]:
    """Every member of a zip file in central-directory order, with each local header's offset."""
    if len(raw) < END.size:
        raise error("zip: shorter than an end record")
    end = raw.rfind(b"PK\x05\x06")
    if end < 0 or end + END.size != len(raw):
        raise error("zip: no end record at the end of the file (an archive comment is not supported)")
    _, disk, cd_disk, here, total, cd_size, cd_offset, comment = END.unpack_from(raw, end)
    if comment or disk or cd_disk or here != total:
        raise error("zip: split, commented or inconsistent archive")
    if (total == 0xFFFF or cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF
            or (end >= 20 and raw[end - 20:end - 16] == b"PK\x06\x07")):
        raise error("zip: zip64 is not supported")
    if cd_offset + cd_size != end:
        raise error("zip: the central directory does not end at the end record")
    entries: list[Entry] = []
    offsets: list[int] = []
    names: set[str] = set()
    position = cd_offset
    for _ in range(total):
        if raw[position:position + 4] != b"PK\x01\x02":
            raise error(f"zip: no central-directory record at byte {position}")
        (_, made_by, version, flags, method, time, date, crc, packed, size, name_len,
         extra_len, comment_len, start_disk, internal, external, local) = CENTRAL.unpack_from(raw, position)
        position += CENTRAL.size
        raw_name = raw[position:position + name_len]
        position += name_len
        central_extra = raw[position:position + extra_len]
        position += extra_len
        member_comment = raw[position:position + comment_len]
        position += comment_len
        try:
            name = raw_name.decode("utf-8" if flags & UTF8 else "cp437")
        except UnicodeDecodeError as exc:
            raise error(f"zip: a member name is not valid UTF-8 ({exc})") from exc
        if start_disk or flags & ENCRYPTED or flags & DATA_DESCRIPTOR:
            raise error(f"zip member {name}: split, encrypted or written with a data descriptor")
        if raw[local:local + 4] != b"PK\x03\x04" or local + LOCAL.size > cd_offset:
            raise error(f"zip member {name}: no local header at byte {local}")
        (_, local_version, local_flags, local_method, _, _, local_crc,
         local_packed, local_size, local_name_len, local_extra_len) = LOCAL.unpack_from(raw, local)
        name_start = local + LOCAL.size
        data_start = name_start + local_name_len + local_extra_len
        if (raw[name_start:name_start + local_name_len] != raw_name or local_method != method
                or local_packed != packed or local_size != size or local_crc != crc or local_flags != flags
                or data_start + packed > cd_offset):
            raise error(f"zip member {name}: local header and central directory disagree")
        data = raw[data_start:data_start + packed]
        if len(data) != packed:
            raise error(f"zip member {name}: data is shorter than the directory says")
        if name in names:
            raise error(f"zip member {name}: entered twice")
        names.add(name)
        entries.append(Entry(name, raw_name, flags, method, time, date, crc, data, size, made_by,
                             local_version, version, internal, external,
                             raw[name_start + local_name_len:data_start], central_extra, member_comment))
        offsets.append(local)
    if position != end:
        raise error("zip: central-directory records overrun the directory")
    return entries, offsets


def record_span(entry: Entry) -> int:
    """Length of a member's local record: header, name, extra field and data."""
    return LOCAL.size + len(entry.raw_name) + len(entry.local_extra) + len(entry.data)


def write_archive(entries: Sequence[Entry]) -> bytes:
    out = bytearray()
    offsets: list[int] = []
    for entry in entries:
        offsets.append(len(out))
        out += LOCAL.pack(b"PK\x03\x04", entry.local_version, entry.flags, entry.method, entry.time, entry.date,
                          entry.crc, len(entry.data), entry.size, len(entry.raw_name), len(entry.local_extra))
        out += entry.raw_name + entry.local_extra + entry.data
    directory = len(out)
    for entry, offset in zip(entries, offsets):
        out += CENTRAL.pack(b"PK\x01\x02", entry.made_by, entry.central_version, entry.flags, entry.method,
                            entry.time, entry.date, entry.crc, len(entry.data), entry.size, len(entry.raw_name),
                            len(entry.central_extra), len(entry.comment), 0, entry.internal_attr,
                            entry.external_attr, offset)
        out += entry.raw_name + entry.central_extra + entry.comment
    if len(entries) >= 0xFFFF or directory >= 0xFFFFFFFF or len(out) - directory >= 0xFFFFFFFF:
        raise ValidationError("zip: the result does not fit the plain zip format")
    out += END.pack(b"PK\x05\x06", 0, 0, len(entries), len(entries), len(out) - directory, directory, 0)
    return bytes(out)


# ---------------------------------------------------------------- the template

@dataclass(frozen=True)
class Template:
    raw: bytes
    entries: tuple[Entry, ...]
    offsets: tuple[int, ...]
    contents: dict[str, bytes]
    mesh_member: str                   # the one mesh document, in the template's folder
    path_style: Callable[[str], str]   # member name -> the path that p:path and Target write
    object_id: int
    volume_id: int
    backup_id: int
    upper_uuid: bool
    rel_number: int
    rel_type: str
    extruder: str
    identify_id: int
    object_suffix: str
    component_suffix: str
    mesh_suffix: str
    item_suffix: str


def short_name(name: str) -> str:
    """An attribute or tag name without namespace: `{ns}UUID` and `p:UUID` are both `UUID`."""
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def attributes(element: ET.Element) -> dict[str, str]:
    """Attributes by name without namespace."""
    return {short_name(key): value for key, value in element.attrib.items()}


def find_all(element: ET.Element, *names: str) -> list[ET.Element]:
    """Elements at or below `element` that start a chain of the given names, each the direct child of the last."""
    if short_name(element.tag) == names[0]:
        if len(names) == 1:
            return [element]
        return [found for child in element for found in find_all(child, *names[1:])]
    return [found for child in element for found in find_all(child, *names)]


def xml_root(content: bytes, member: str, error: type[FixtureError]) -> ET.Element:
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise error(f"{member}: a DTD or entity declaration is not allowed")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise error(f"{member}: not well-formed XML ({exc})") from exc


def int_text(value: str | None, what: str, error: type[FixtureError] = TemplateError) -> int:
    if value is None or re.fullmatch(r"-?[0-9]+", value) is None:
        raise error(f"{what} is not an integer: {value!r}")
    return int(value)


def present(value: T | None, message: str) -> T:
    """The value; TemplateError when it is None."""
    if value is None:
        raise TemplateError(message)
    return value


def uuid_parts(value: str | None, what: str) -> tuple[str, str]:
    found = UUID_TEXT.fullmatch(value or "")
    if found is None:
        raise TemplateError(f"template: {what} has no p:UUID in the slicer's form: {value!r}")
    return found.group(1), found.group(2)


def hex8(value: int, upper: bool) -> str:
    digits = f"{value:08x}"
    return digits.upper() if upper else digits


def read_template(raw: bytes) -> Template:
    """The template's members and the facts the derivation continues from them."""
    entries, offsets = read_archive(raw, TemplateError)
    need(entries, "template: the zip has no members")
    need(sum(entry.size for entry in entries) <= MAX_MEMBER_TOTAL, "template: more than 1 GiB of member content")
    contents: dict[str, bytes] = {}
    for entry in entries:
        need(valid_member_name(entry.name), f"template: member name {entry.name!r} is not a plain package path")
        contents[entry.name] = entry.content(TemplateError)
    for member in (ROOT_RELS_MEMBER, MODEL_MEMBER, MODEL_RELS_MEMBER, SETTINGS_MEMBER):
        need(member in contents, f"template: member {member} is missing")

    root_rels = xml_root(contents[ROOT_RELS_MEMBER], ROOT_RELS_MEMBER, TemplateError)
    starts = [rel for rel in root_rels if short_name(rel.tag) == "Relationship"
              and attributes(rel).get("Type", "").endswith("/3dmodel")]
    need(len(starts) == 1 and attributes(starts[0]).get("Target") == "/" + MODEL_MEMBER,
         f"template: {ROOT_RELS_MEMBER} does not name /{MODEL_MEMBER} as its one model")

    model = xml_root(contents[MODEL_MEMBER], MODEL_MEMBER, TemplateError)
    objects = find_all(model, "resources", "object")
    need(len(objects) == 1, f"template: {MODEL_MEMBER} must hold exactly one top-level object")
    object_attributes = attributes(objects[0])
    object_id = int_text(object_attributes.get("id"), "template object id")
    object_prefix, object_suffix = uuid_parts(object_attributes.get("UUID"), "object p:UUID")
    components = find_all(objects[0], "components", "component")
    need(len(components) == 1, "template: the top-level object must have exactly one component")
    component_attributes = attributes(components[0])
    volume_id = int_text(component_attributes.get("objectid"), "template component objectid")
    component_prefix, component_suffix = uuid_parts(component_attributes.get("UUID"), "component p:UUID")
    items = find_all(model, "build", "item")
    need(len(items) == 1 and int_text(attributes(items[0]).get("objectid"), "template build item objectid") == object_id,
         "template: the build must hold exactly one item, for the object")
    item_prefix, item_suffix = uuid_parts(attributes(items[0]).get("UUID"), "build item p:UUID")
    component_path = present(component_attributes.get("path"), "template: the component has no p:path")
    need(component_path.startswith("/"), f"template: the component's p:path {component_path!r} does not start with /")

    rels = xml_root(contents[MODEL_RELS_MEMBER], MODEL_RELS_MEMBER, TemplateError)
    relationships = [rel for rel in rels if short_name(rel.tag) == "Relationship"]
    need(len(relationships) == 1 and attributes(relationships[0]).get("Target") == component_path,
         "template: the model relationships must hold exactly the component's document")
    rel_attributes = attributes(relationships[0])
    number = present(REL_ID.fullmatch(rel_attributes.get("Id", "")),
                     f"template: relationship id {rel_attributes.get('Id')!r} is not rel-<number>")

    # Which zip member the component path names, and how the template writes a member name into a path:
    # as it is, or percent-escaped. The new names are written the same way.
    target = component_path[1:]
    if target in contents and target != MODEL_MEMBER:
        mesh_member, path_style = target, lambda member: "/" + member   # noqa: E731
    elif urllib.parse.unquote(target) in contents and urllib.parse.unquote(target) != MODEL_MEMBER:
        mesh_member = urllib.parse.unquote(target)
        path_style = lambda member: urllib.parse.quote("/" + member)   # noqa: E731
    else:
        raise TemplateError(f"template: the component's document {component_path!r} is not a member of the zip")
    mesh = xml_root(contents[mesh_member], mesh_member, TemplateError)
    mesh_objects = find_all(mesh, "resources", "object")
    need(len(mesh_objects) == 1, f"template: {mesh_member} must hold exactly one object")
    mesh_attributes = attributes(mesh_objects[0])
    need(int_text(mesh_attributes.get("id"), "template mesh object id") == volume_id,
         "template: the mesh document's object id is not the component's")
    mesh_prefix, mesh_suffix = uuid_parts(mesh_attributes.get("UUID"), "mesh object p:UUID")
    backup_id = int(object_prefix, 16)
    # The exporter writes: object prefix = backup id; component and mesh prefix = volume index + (backup id << 16);
    # item prefix = object id. Only a template that follows this scheme can be continued by it.
    need(int(component_prefix, 16) == backup_id << 16 and int(mesh_prefix, 16) == backup_id << 16,
         "template: the component and mesh UUIDs do not follow the object's backup id")
    need(int(item_prefix, 16) == object_id, "template: the build item's UUID prefix is not the object id")

    settings = xml_root(contents[SETTINGS_MEMBER], SETTINGS_MEMBER, TemplateError)
    setting_objects = find_all(settings, "object")
    need(len(setting_objects) == 1 and int_text(attributes(setting_objects[0]).get("id"), "template settings object id") == object_id,
         f"template: {SETTINGS_MEMBER} must hold exactly one object block, with the model's object id")
    extruders = [attributes(meta).get("value") for meta in setting_objects[0]
                 if short_name(meta.tag) == "metadata" and attributes(meta).get("key") == "extruder"]
    need(len(extruders) == 1, "template: the object block has no single extruder metadata")
    instances = find_all(settings, "plate", "model_instance")
    need(len(instances) == 1, "template: the plate must hold exactly one model_instance")
    identify = [attributes(meta).get("value") for meta in instances[0]
                if short_name(meta.tag) == "metadata" and attributes(meta).get("key") == "identify_id"]
    need(len(identify) == 1, "template: the model_instance has no single identify_id")

    return Template(raw, tuple(entries), tuple(offsets), contents, mesh_member, path_style,
                    object_id, volume_id, backup_id, object_prefix[:1].isupper(), int(number.group(1)),
                    rel_attributes.get("Type", ""), extruders[0] or "", int_text(identify[0], "template identify_id"),
                    object_suffix, component_suffix, mesh_suffix, item_suffix)


# ---------------------------------------------------------------- template lines

TAG_LINE = re.compile(r'^(?P<indent>[ \t]*)<(?P<name>[A-Za-z_][\w.:-]*)'
                      r'(?P<attrs>(?:[ \t]+[A-Za-z_][\w.:-]*="[^"]*")*)(?P<close>[ \t]*/>|[ \t]*>)$')
ATTRIBUTE = re.compile(r'([A-Za-z_][\w.:-]*)="([^"]*)"')


@dataclass(frozen=True)
class Tag:
    """A one-line element: the template's own text with its attribute values."""
    indent: str
    name: str
    attrs: tuple[tuple[str, str], ...]
    close: str

    def value(self, key: str) -> str | None:
        for name, value in self.attrs:
            if short_name(name) == key:
                return value
        return None

    def with_values(self, changes: dict[str, str], member: str) -> Tag:
        """The same tag with some attribute values replaced (keys are names without namespace)."""
        attrs = []
        for name, value in self.attrs:
            attrs.append((name, changes.get(short_name(name), value)))
        missing = sorted(set(changes) - {short_name(name) for name, _ in self.attrs})
        need(not missing, f"template: <{self.name}> in {member} has no attribute(s) {missing} to replace")
        return replace(self, attrs=tuple(attrs))

    def render(self) -> str:
        return f"{self.indent}<{self.name}" + "".join(f' {name}="{value}"' for name, value in self.attrs) + self.close


class Doc:
    """An XML member as lines, for text-level templating: generated lines take the template's line ending."""

    def __init__(self, content: bytes, member: str, error: type[FixtureError] = TemplateError) -> None:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise error(f"{member}: is not UTF-8 ({exc})") from exc
        if text.startswith("\ufeff"):
            raise error(f"{member}: starts with a byte-order mark")
        pieces = text.split("\n")
        self.member = member
        self.error = error
        self.body: list[str] = []
        self.endings: list[str] = []
        for index, piece in enumerate(pieces):
            last = index == len(pieces) - 1
            if piece.endswith("\r"):
                if last:
                    raise error(f"{member}: ends with a lone CR")
                self.body.append(piece[:-1])
                self.endings.append("\r\n")
            else:
                self.body.append(piece)
                self.endings.append("" if last else "\n")
        if "\r" in "".join(self.body):
            raise error(f"{member}: a CR that is not part of CRLF")
        self.eol = next((ending for ending in self.endings if ending), "\n")

    def line(self, index: int) -> str:
        return self.body[index] + self.endings[index]

    def span(self, start: int, stop: int) -> list[str]:
        return [self.line(index) for index in range(start, stop)]

    def find(self, pattern: str) -> list[int]:
        return [index for index, body in enumerate(self.body) if re.fullmatch(pattern, body.strip())]

    def one(self, pattern: str) -> int:
        found = self.find(pattern)
        if len(found) != 1:
            raise self.error(f"{self.member}: must hold exactly one {pattern}, found {len(found)}")
        return found[0]

    def tag(self, index: int, name: str) -> Tag:
        found = TAG_LINE.fullmatch(self.body[index])
        if found is None or short_name(found["name"]) != name:
            raise self.error(f"{self.member} line {index + 1}: expected a <{name}> line, found {self.body[index].strip()!r}")
        tag = Tag(found["indent"], found["name"], tuple(ATTRIBUTE.findall(found["attrs"])), found["close"])
        if tag.render() != self.body[index]:
            raise self.error(f"{self.member} line {index + 1}: attribute spacing this tool does not mirror")
        return tag

    def closing(self, index: int, name: str) -> None:
        if self.body[index].strip() != f"</{name}>":
            raise self.error(f"{self.member} line {index + 1}: expected </{name}>, found {self.body[index].strip()!r}")

    def any_tag(self, index: int) -> Tag:
        """The tag line at `index`, whatever its name."""
        found = TAG_LINE.fullmatch(self.body[index])
        if found is None:
            raise self.error(f"{self.member} line {index + 1}: expected a one-line tag, found {self.body[index].strip()!r}")
        return self.tag(index, short_name(found["name"]))

    def metadata(self, indices: range, key: str) -> int:
        """The one line in `indices` that is a `metadata` tag with key `key`; every line there must be a tag line."""
        wanted = [index for index in indices
                  if (found := TAG_LINE.fullmatch(self.body[index])) is not None
                  and short_name(found["name"]) == "metadata" and self.tag(index, "metadata").value("key") == key]
        if len(wanted) != 1:
            raise self.error(f"{self.member}: must hold exactly one metadata line with key {key!r} in that block, found {len(wanted)}")
        return wanted[0]

    def relationship_lines(self) -> list[int]:
        return [index for index, body in enumerate(self.body)
                if (found := TAG_LINE.fullmatch(body)) is not None and short_name(found["name"]) == "Relationship"]


def kept_lines(template_doc: Doc, output_doc: Doc, variable: set[int]) -> int:
    """Require every template line outside `variable` to be in the output as it was; return how many were checked."""
    kept = Counter(template_doc.line(index) for index in range(len(template_doc.body)) if index not in variable)
    missing = kept - Counter(output_doc.line(index) for index in range(len(output_doc.body)))
    require(not missing, f"{output_doc.member}: template line(s) missing or changed: {[line.strip() for line in missing][:3]}")
    return sum(kept.values())


# ---------------------------------------------------------------- rendering

@dataclass(frozen=True)
class Placed:
    """One object of the plate with every id and name it carries in the project."""
    shape: Shape
    object_id: int        # <object id> in the model and in model_settings.config
    volume_id: int        # component objectid, the mesh document's object id, <part id>
    backup_id: int        # the slicer's object backup id: file index and UUID prefix
    member: str           # zip member holding the mesh document
    path: str             # that member as p:path and Target write it
    transform: str        # build item and assemble_item transform
    extruder: str
    identify_id: int
    rel_id: str
    object_uuid: str
    component_uuid: str
    mesh_uuid: str
    item_uuid: str


def plan(template: Template) -> list[Placed]:
    """The five objects with the ids the template's ids continue to."""
    folder, _, stem = template.mesh_member.rpartition("/")
    folder = folder + "/" if folder else ""
    need("." in stem, f"template: mesh document {template.mesh_member!r} has no file extension")
    extension = "." + stem.rsplit(".", 1)[1]
    upper = template.upper_uuid
    placed = []
    for k, shape in enumerate(shapes()):
        need(not re.search(r'[\\/:*?"<>|\x00-\x1f]', shape.name), f"object name {shape.name!r} cannot go into a member name")
        backup = template.backup_id + k
        member = f"{folder}{shape.name}_{backup}{extension}"
        placed.append(Placed(
            shape=shape,
            object_id=template.object_id + k,
            volume_id=template.volume_id + k,
            backup_id=backup,
            member=member,
            path=template.path_style(member),
            transform=f"{NO_ROTATION} {text_of_micro(CENTRE_X[k] * MICRO)} {text_of_micro(PLATE_Y * MICRO)} 0",
            extruder=shape.extruder if shape.extruder is not None else template.extruder,
            identify_id=template.identify_id + k,
            rel_id=f"rel-{template.rel_number + k}",
            object_uuid=hex8(backup, upper) + template.object_suffix,
            component_uuid=hex8(backup << 16, upper) + template.component_suffix,
            mesh_uuid=hex8(backup << 16, upper) + template.mesh_suffix,
            item_uuid=hex8(template.object_id + k, upper) + template.item_suffix,
        ))
    return placed


@dataclass(frozen=True)
class ModelSkeleton:
    """Where the model member's one object, its component and its one item sit."""
    resources: int
    resources_end: int
    build: int
    build_end: int
    object_open: int
    components: int
    component: int
    components_end: int
    object_end: int
    item: int

    @property
    def variable(self) -> set[int]:
        return {self.object_open, self.component, self.item}


def model_skeleton(doc: Doc) -> ModelSkeleton:
    resources = doc.one(r"<resources\b[^>]*>")
    resources_end = doc.one(r"</resources>")
    build = doc.one(r"<build\b[^>]*>")
    build_end = doc.one(r"</build>")
    if not resources < resources_end < build < build_end:
        raise doc.error(f"{doc.member}: must hold its resources before its build")
    block = list(range(resources + 1, resources_end))
    if len(block) != 5:
        raise doc.error(f"{doc.member}: resources must hold one object with one component and nothing else")
    doc.tag(block[0], "object")
    doc.tag(block[1], "components")
    doc.tag(block[2], "component")
    doc.closing(block[3], "components")
    doc.closing(block[4], "object")
    if build_end - build != 2:
        raise doc.error(f"{doc.member}: build must hold one item and nothing else")
    doc.tag(build + 1, "item")
    object_open, components, component, components_end, object_end = block
    return ModelSkeleton(resources, resources_end, build, build_end, object_open, components, component,
                         components_end, object_end, build + 1)


@dataclass(frozen=True)
class MeshSkeleton:
    """Where the mesh document's object, its sample vertex and triangle lines and the lines around them sit."""
    resources: int
    resources_end: int
    object_open: int
    object_end: int
    vertices: tuple[int, ...]
    vertices_close: int
    triangles_open: int
    triangles: tuple[int, ...]
    triangles_close: int
    mesh_close: int

    @property
    def variable(self) -> set[int]:
        return {self.object_open, *self.vertices, *self.triangles}


def mesh_skeleton(doc: Doc) -> MeshSkeleton:
    resources = doc.one(r"<resources\b[^>]*>")
    resources_end = doc.one(r"</resources>")
    block = list(range(resources + 1, resources_end))
    if len(block) < 8:
        raise doc.error(f"{doc.member}: resources must hold one object with one mesh")
    doc.tag(block[0], "object")
    doc.tag(block[1], "mesh")
    doc.tag(block[2], "vertices")
    vertices: list[int] = []
    at = 3
    while at < len(block) and doc.body[block[at]].strip() != "</vertices>":
        doc.tag(block[at], "vertex")
        vertices.append(block[at])
        at += 1
    if not vertices or at > len(block) - 6:
        raise doc.error(f"{doc.member}: no vertices in the mesh, or lines after it")
    vertices_close = at
    triangles_open = at + 1
    doc.tag(block[triangles_open], "triangles")
    triangles: list[int] = []
    at = triangles_open + 1
    while at < len(block) and doc.body[block[at]].strip() != "</triangles>":
        doc.tag(block[at], "triangle")
        triangles.append(block[at])
        at += 1
    if not triangles or at != len(block) - 3:
        raise doc.error(f"{doc.member}: no triangles in the mesh, or lines after them")
    doc.closing(block[-2], "mesh")
    doc.closing(block[-1], "object")
    if [short_name(key) for key, _ in doc.tag(vertices[0], "vertex").attrs] != ["x", "y", "z"]:
        raise doc.error(f"{doc.member}: vertex attributes are not x, y, z")
    if [short_name(key) for key, _ in doc.tag(triangles[0], "triangle").attrs] != ["v1", "v2", "v3"]:
        raise doc.error(f"{doc.member}: triangle attributes are not v1, v2, v3")
    return MeshSkeleton(resources, resources_end, block[0], block[-1], tuple(vertices), block[vertices_close],
                        block[triangles_open], tuple(triangles), block[at], block[-2])


@dataclass(frozen=True)
class SettingsSkeleton:
    """Where everything that changes in model_settings.config sits."""
    object_open: int
    object_end: int
    part_open: int
    part_close: int
    object_level: range
    part_level: range
    name_object: int
    extruder: int
    name_part: int
    instance_open: int
    instance_close: int
    instance_object_id: int
    instance_identify_id: int
    assemble_open: int
    assemble_close: int
    assemble_item: int

    @property
    def variable(self) -> set[int]:
        return {self.object_open, self.name_object, self.extruder, self.part_open, self.name_part,
                self.instance_object_id, self.instance_identify_id, self.assemble_item}


def settings_skeleton(doc: Doc) -> SettingsSkeleton:
    object_open = doc.one(r"<object\b[^>]*>")
    object_end = doc.one(r"</object>")
    part_open = doc.one(r"<part\b[^>]*>")
    part_close = doc.one(r"</part>")
    plate_open = doc.one(r"<plate\b[^>]*>")
    plate_close = doc.one(r"</plate>")
    assemble_open = doc.one(r"<assemble\b[^>]*>")
    assemble_close = doc.one(r"</assemble>")
    if not object_open < part_open < part_close < object_end < plate_open < plate_close < assemble_open < assemble_close:
        raise doc.error(f"{doc.member}: must hold one object block, one plate block and one assemble block, in that order")
    if object_end != part_close + 1:
        raise doc.error(f"{doc.member}: lines between </part> and </object>")
    object_level = range(object_open + 1, part_open)
    part_level = range(part_open + 1, part_close)
    doc.tag(object_open, "object")
    doc.tag(part_open, "part")
    name_object = doc.metadata(object_level, "name")
    extruder = doc.metadata(object_level, "extruder")
    name_part = doc.metadata(part_level, "name")
    if doc.tag(doc.metadata(part_level, "matrix"), "metadata").value("value") != IDENTITY_MATRIX:
        raise doc.error(f"{doc.member}: the part matrix is not the identity")
    opens = [index for index in range(plate_open + 1, plate_close) if re.fullmatch(r"<model_instance\b[^>]*>", doc.body[index].strip())]
    closes = [index for index in range(plate_open + 1, plate_close) if doc.body[index].strip() == "</model_instance>"]
    if len(opens) != 1 or len(closes) != 1 or opens[0] > closes[0]:
        raise doc.error(f"{doc.member}: the plate must hold exactly one model_instance")
    inside = range(opens[0] + 1, closes[0])
    instance_object_id = doc.metadata(inside, "object_id")
    instance_identify_id = doc.metadata(inside, "identify_id")
    doc.metadata(inside, "instance_id")
    items = [index for index in range(assemble_open + 1, assemble_close) if TAG_LINE.fullmatch(doc.body[index]) is not None]
    if len(items) != 1 or assemble_close - assemble_open != 2:
        raise doc.error(f"{doc.member}: assemble must hold exactly one assemble_item")
    doc.tag(items[0], "assemble_item")
    return SettingsSkeleton(object_open, object_end, part_open, part_close, object_level, part_level, name_object,
                            extruder, name_part, opens[0], closes[0], instance_object_id, instance_identify_id,
                            assemble_open, assemble_close, items[0])


def model_document(doc: Doc, objects: Sequence[Placed]) -> str:
    skeleton = model_skeleton(doc)
    obj = doc.tag(skeleton.object_open, "object")
    component = doc.tag(skeleton.component, "component")
    if component.value("transform") not in (None, IDENTITY_TRANSFORM):
        raise doc.error(f"{doc.member}: the component transform is not the identity")
    item = doc.tag(skeleton.item, "item")
    lines = doc.span(0, skeleton.resources + 1)
    for placed in objects:
        lines.append(obj.with_values({"id": str(placed.object_id), "UUID": placed.object_uuid}, doc.member).render() + doc.eol)
        lines.append(doc.line(skeleton.components))
        lines.append(component.with_values({"path": placed.path, "objectid": str(placed.volume_id), "UUID": placed.component_uuid},
                                           doc.member).render() + doc.eol)
        lines.append(doc.line(skeleton.components_end))
        lines.append(doc.line(skeleton.object_end))
    lines += doc.span(skeleton.resources_end, skeleton.build + 1)
    for placed in objects:
        lines.append(item.with_values({"objectid": str(placed.object_id), "UUID": placed.item_uuid, "transform": placed.transform},
                                      doc.member).render() + doc.eol)
    lines += doc.span(skeleton.build_end, len(doc.body))
    return "".join(lines)


def rels_document(doc: Doc, objects: Sequence[Placed]) -> str:
    at = doc.relationship_lines()
    if len(at) != 1:
        raise doc.error(f"{doc.member}: must hold exactly one Relationship")
    tag = doc.tag(at[0], "Relationship")
    lines = doc.span(0, at[0])
    for placed in objects:
        lines.append(tag.with_values({"Target": placed.path, "Id": placed.rel_id}, doc.member).render() + doc.eol)
    lines += doc.span(at[0] + 1, len(doc.body))
    return "".join(lines)


def mesh_document(doc: Doc, placed: Placed) -> str:
    skeleton = mesh_skeleton(doc)
    obj = doc.tag(skeleton.object_open, "object")
    vertex = doc.tag(skeleton.vertices[0], "vertex")
    triangle = doc.tag(skeleton.triangles[0], "triangle")
    lines = doc.span(0, skeleton.resources + 1)
    lines.append(obj.with_values({"id": str(placed.volume_id), "UUID": placed.mesh_uuid}, doc.member).render() + doc.eol)
    lines.append(doc.line(skeleton.object_open + 1))      # <mesh>
    lines.append(doc.line(skeleton.object_open + 2))      # <vertices>
    for x, y, z in placed.shape.mesh.vertices:
        lines.append(vertex.with_values({"x": text_of_micro(x), "y": text_of_micro(y), "z": text_of_micro(z)},
                                        doc.member).render() + doc.eol)
    lines.append(doc.line(skeleton.vertices_close))       # </vertices>
    lines.append(doc.line(skeleton.triangles_open))      # <triangles>
    for a, b, c in placed.shape.mesh.triangles:
        lines.append(triangle.with_values({"v1": str(a), "v2": str(b), "v3": str(c)}, doc.member).render() + doc.eol)
    lines.append(doc.line(skeleton.triangles_close))     # </triangles>
    lines.append(doc.line(skeleton.mesh_close))          # </mesh>
    lines.append(doc.line(skeleton.object_end))          # </object>
    lines += doc.span(skeleton.resources_end, len(doc.body))
    return "".join(lines)


def settings_document(doc: Doc, objects: Sequence[Placed]) -> str:
    skeleton = settings_skeleton(doc)
    obj = doc.tag(skeleton.object_open, "object")
    part = doc.tag(skeleton.part_open, "part")
    instance_object_id = doc.tag(skeleton.instance_object_id, "metadata")
    instance_identify_id = doc.tag(skeleton.instance_identify_id, "metadata")
    assemble_item = doc.tag(skeleton.assemble_item, "assemble_item")
    lines = doc.span(0, skeleton.object_open)
    for placed in objects:
        name = xml_attr(placed.shape.name)
        lines.append(obj.with_values({"id": str(placed.object_id)}, doc.member).render() + doc.eol)
        for index in skeleton.object_level:
            if index == skeleton.name_object:
                lines.append(doc.tag(index, "metadata").with_values({"value": name}, doc.member).render() + doc.eol)
            elif index == skeleton.extruder:
                lines.append(doc.tag(index, "metadata").with_values({"value": placed.extruder}, doc.member).render() + doc.eol)
            else:
                lines.append(doc.line(index))
        lines.append(part.with_values({"id": str(placed.volume_id)}, doc.member).render() + doc.eol)
        for index in skeleton.part_level:
            if index == skeleton.name_part:
                lines.append(doc.tag(index, "metadata").with_values({"value": name}, doc.member).render() + doc.eol)
            else:
                lines.append(doc.line(index))
        lines.append(doc.line(skeleton.part_close))
        lines.append(doc.line(skeleton.object_end))
    lines += doc.span(skeleton.object_end + 1, skeleton.instance_open)
    for placed in objects:     # the plate's model_instance: one per object, its other lines as they are
        lines.append(doc.line(skeleton.instance_open))
        for index in range(skeleton.instance_open + 1, skeleton.instance_close):
            if index == skeleton.instance_object_id:
                lines.append(instance_object_id.with_values({"value": str(placed.object_id)}, doc.member).render() + doc.eol)
            elif index == skeleton.instance_identify_id:
                lines.append(instance_identify_id.with_values({"value": str(placed.identify_id)}, doc.member).render() + doc.eol)
            else:
                lines.append(doc.line(index))
        lines.append(doc.line(skeleton.instance_close))
    lines += doc.span(skeleton.instance_close + 1, skeleton.assemble_item)
    for placed in objects:
        lines.append(assemble_item.with_values({"object_id": str(placed.object_id), "transform": placed.transform},
                                               doc.member).render() + doc.eol)
    lines += doc.span(skeleton.assemble_item + 1, len(doc.body))
    return "".join(lines)


def generated_documents(template: Template, objects: Sequence[Placed]) -> dict[str, str]:
    """The members this tool writes, as text."""
    mesh = Doc(template.contents[template.mesh_member], template.mesh_member)
    documents = {
        MODEL_MEMBER: model_document(Doc(template.contents[MODEL_MEMBER], MODEL_MEMBER), objects),
        MODEL_RELS_MEMBER: rels_document(Doc(template.contents[MODEL_RELS_MEMBER], MODEL_RELS_MEMBER), objects),
        SETTINGS_MEMBER: settings_document(Doc(template.contents[SETTINGS_MEMBER], SETTINGS_MEMBER), objects),
    }
    for placed in objects:
        documents[placed.member] = mesh_document(mesh, placed)
    return documents


def generated_names(template: Template, objects: Sequence[Placed]) -> set[str]:
    return {MODEL_MEMBER, MODEL_RELS_MEMBER, SETTINGS_MEMBER} | {placed.member for placed in objects}


def build(template: Template) -> bytes:
    """The new project: the template's members in its order, geometry replaced, everything else copied."""
    objects = plan(template)
    kept = {entry.name for entry in template.entries} - {MODEL_MEMBER, MODEL_RELS_MEMBER, SETTINGS_MEMBER, template.mesh_member}
    clash = kept & {placed.member for placed in objects}
    need(not clash, f"template: a new mesh document would replace a copied member: {sorted(clash)}")
    documents = generated_documents(template, objects)
    entries: list[Entry] = []
    for entry in template.entries:
        if entry.name in (MODEL_MEMBER, MODEL_RELS_MEMBER, SETTINGS_MEMBER):
            entries.append(entry.clone(entry.name, documents[entry.name].encode("utf-8"), entry.deflate_level()))
        elif entry.name == template.mesh_member:
            level = entry.deflate_level()
            for placed in objects:
                entries.append(entry.clone(placed.member, documents[placed.member].encode("utf-8"), level))
        else:
            entries.append(entry)   # copied: header fields and bytes exactly as the template holds them
    return write_archive(entries)


# ---------------------------------------------------------------- validation

@dataclass(frozen=True)
class Measured:
    """What one object's mesh measured in the file, in the object's own coordinates (mm)."""
    low: tuple[float, float, float]
    high: tuple[float, float, float]
    shells: int
    triangles: int


@dataclass
class Audit:
    template: Template
    objects: list[Placed]
    contents: dict[str, bytes]
    roots: dict[str, ET.Element]


def metadata_of(element: ET.Element) -> dict[str | None, str | None]:
    """key -> value of an element's direct `metadata` children (the model_settings.config idiom).; a missing key or value is None"""
    return {attributes(meta).get("key"): attributes(meta).get("value")
            for meta in element if short_name(meta.tag) == "metadata"}


def validate_container(output: bytes, audit: Audit, say: Say) -> None:
    order: list[str] = []
    for entry in audit.template.entries:
        order += [placed.member for placed in audit.objects] if entry.name == audit.template.mesh_member else [entry.name]
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        require(archive.testzip() is None, "zip: a member does not match its CRC")
        require([info.filename for info in archive.infolist()] == order,
                "zip: member order is not the template's with the mesh documents in place")
        audit.contents = {name: archive.read(name) for name in order}
    say(f"zip opens (standard-library reader): {len(order)} members, every CRC matches, order = the template's order")

    for name, data in audit.contents.items():
        if data.lstrip()[:1] == b"<":
            audit.roots[name] = xml_root(data, name, ValidationError)
    say(f"xml: {len(audit.roots)} of {len(order)} members are XML and parse: {', '.join(sorted(audit.roots))}")

    written = generated_names(audit.template, audit.objects)
    indexed = {entry.name: (entry, offset) for entry, offset in zip(*read_archive(output, ValidationError))}
    copied = [entry for entry in audit.template.entries if entry.name not in written]
    for entry, offset in zip(audit.template.entries, audit.template.offsets):
        if entry.name in written:
            continue
        other, other_offset = indexed[entry.name]
        require(audit.contents[entry.name] == audit.template.contents[entry.name], f"{entry.name}: content differs from the template")
        require(other == entry, f"{entry.name}: zip record fields differ from the template")
        span = record_span(entry)
        require(output[other_offset:other_offset + span] == audit.template.raw[offset:offset + span],
                f"{entry.name}: raw local record differs from the template's")
    say(f"copied members byte-identical to the template (content, record fields, raw local record): {len(copied)} of {len(copied)}")
    say(f"  settings/config: {', '.join(entry.name for entry in copied if entry.name.endswith(('.config', '.rels', '.xml')))}")
    say(f"  others: {', '.join(entry.name for entry in copied if not entry.name.endswith(('.config', '.rels', '.xml')))}")


def validate_lines(audit: Audit, say: Say) -> None:
    """The template lines that carry no replaced value are still in the output, as they were."""
    template = audit.template
    counts: dict[str, int] = {}
    for name in (MODEL_MEMBER, MODEL_RELS_MEMBER, SETTINGS_MEMBER):
        before = Doc(template.contents[name], name)
        after = Doc(audit.contents[name], name, ValidationError)
        if name == MODEL_MEMBER:
            variable = model_skeleton(before).variable
        elif name == MODEL_RELS_MEMBER:
            variable = set(before.relationship_lines())
        else:
            variable = settings_skeleton(before).variable
        counts[name] = kept_lines(before, after, variable)
    mesh_before = Doc(template.contents[template.mesh_member], template.mesh_member)
    mesh_lines = mesh_skeleton(mesh_before).variable
    for placed in audit.objects:
        counts[placed.member] = kept_lines(mesh_before, Doc(audit.contents[placed.member], placed.member, ValidationError), mesh_lines)
    # the model_instance block is written once per object: its other lines must be there once per object
    settings_before = Doc(template.contents[SETTINGS_MEMBER], SETTINGS_MEMBER)
    settings_after = Doc(audit.contents[SETTINGS_MEMBER], SETTINGS_MEMBER, ValidationError)
    instance = settings_skeleton(settings_before)
    for index in range(instance.instance_open, instance.instance_close + 1):
        if index not in instance.variable:
            require(settings_after.body.count(settings_before.body[index]) == len(audit.objects),
                    f"{SETTINGS_MEMBER}: the model_instance line {settings_before.body[index].strip()!r} is not there once per object")
    say(f"template lines kept verbatim (mesh documents counted once, they are alike): {sum(counts.values())} "
        f"({', '.join(f'{Path(name).name} {count}' for name, count in counts.items())}); "
        f"model_instance lines {len(audit.objects)} x each")


def validate_model(audit: Audit, say: Say) -> None:
    template = audit.template
    objects = find_all(audit.roots[MODEL_MEMBER], "resources", "object")
    items = find_all(audit.roots[MODEL_MEMBER], "build", "item")
    relationships = [rel for rel in audit.roots[MODEL_RELS_MEMBER] if short_name(rel.tag) == "Relationship"]
    require(len(objects) == len(items) == len(relationships) == 5,
            f"not five objects / build items / relationships: {len(objects)} / {len(items)} / {len(relationships)}")
    for k, placed in enumerate(audit.objects):
        member = find_all(objects[k], "components", "component")
        if len(member) != 1:
            raise ValidationError(f"{MODEL_MEMBER}: object {k} has {len(member)} components, not one")
        obj, component, item, relation = attributes(objects[k]), attributes(member[0]), attributes(items[k]), attributes(relationships[k])
        require(obj.get("id") == str(placed.object_id), f"{MODEL_MEMBER}: object {k} has id {obj.get('id')}, not {placed.object_id}")
        require(component.get("objectid") == str(placed.volume_id), f"{MODEL_MEMBER}: component {k} does not point at volume {placed.volume_id}")
        require(template.path_style(placed.member) == component.get("path") == relation.get("Target"),
                f"{MODEL_MEMBER}: p:path {component.get('path')!r}, Target {relation.get('Target')!r} and member {placed.member!r} disagree")
        require(placed.member in audit.contents, f"{placed.member}: the component's document is not in the zip")
        require(relation.get("Id") == placed.rel_id and relation.get("Type") == template.rel_type,
                f"{MODEL_RELS_MEMBER}: relationship {k} is not {placed.rel_id} of the template's type")
        require(component.get("transform", IDENTITY_TRANSFORM) == IDENTITY_TRANSFORM, f"{MODEL_MEMBER}: component {k} has a transform of its own")
        require(item.get("objectid") == str(placed.object_id), f"{MODEL_MEMBER}: build item {k} does not reference object {placed.object_id}")
        require(item.get("transform") == placed.transform, f"{MODEL_MEMBER}: build item {k} has transform {item.get('transform')!r}")
        require(obj.get("UUID") == placed.object_uuid and component.get("UUID") == placed.component_uuid
                and item.get("UUID") == placed.item_uuid, f"{MODEL_MEMBER}: object {k} does not carry its derived p:UUIDs")
    say(f"{MODEL_MEMBER}: {len(objects)} objects {[attributes(o).get('id') for o in objects]}, one component each, "
        f"one build item each (p:path = Target = zip member, p:UUIDs as derived); "
        f"{MODEL_RELS_MEMBER}: {[attributes(r).get('Id') for r in relationships]}")


def validate_meshes(audit: Audit, say: Say) -> dict[int, Measured]:
    measured: dict[int, Measured] = {}
    for placed in audit.objects:
        objects = find_all(audit.roots[placed.member], "resources", "object")
        require(len(objects) == 1, f"{placed.member}: must hold exactly one object")
        found = attributes(objects[0])
        require(found.get("id") == str(placed.volume_id) and found.get("UUID") == placed.mesh_uuid,
                f"{placed.member}: object id / p:UUID are {found.get('id')} / {found.get('UUID')}, "
                f"not {placed.volume_id} / {placed.mesh_uuid}")
        vertices: list[Vertex] = []
        for element in find_all(objects[0], "mesh", "vertices", "vertex"):
            values = attributes(element)
            require(all(DECIMAL_TEXT.fullmatch(values.get(axis) or "") for axis in "xyz"),
                    f"{placed.member}: a vertex is not a plain decimal with at most 6 decimals: {values}")
            vertices.append((round(float(values["x"]) * MICRO), round(float(values["y"]) * MICRO), round(float(values["z"]) * MICRO)))
        triangles: list[Face] = []
        for element in find_all(objects[0], "mesh", "triangles", "triangle"):
            values = attributes(element)
            triangle = tuple(int_text(values.get(key), f"{placed.member} triangle index", ValidationError) for key in ("v1", "v2", "v3"))
            require(min(triangle) >= 0, f"{placed.member}: a triangle index is negative")
            triangles.append((triangle[0], triangle[1], triangle[2]))
        say(f"{placed.shape.name} ({placed.member}): mesh object id {placed.volume_id}, {len(vertices)} vertices, "
            f"{len(triangles)} triangles, every coordinate a decimal with at most 6 places")
        shells = check_mesh(placed.shape.name, vertices, triangles, placed.shape, say)
        low = (min(vertex[0] for vertex in vertices) / MICRO, min(vertex[1] for vertex in vertices) / MICRO,
               min(vertex[2] for vertex in vertices) / MICRO)
        high = (max(vertex[0] for vertex in vertices) / MICRO, max(vertex[1] for vertex in vertices) / MICRO,
                max(vertex[2] for vertex in vertices) / MICRO)
        measured[placed.object_id] = Measured(low, high, shells, len(triangles))
    return measured


def validate_settings(audit: Audit, say: Say) -> None:
    template = audit.template
    root = audit.roots[SETTINGS_MEMBER]
    before = xml_root(audit.template.contents[SETTINGS_MEMBER], SETTINGS_MEMBER, ValidationError)
    objects = find_all(root, "object")
    plates = find_all(root, "plate")
    instances = find_all(root, "plate", "model_instance")
    items = find_all(root, "assemble", "assemble_item")
    require(len(objects) == 5 and len(plates) == 1 and len(instances) == 5 and len(items) == 5,
            f"{SETTINGS_MEMBER}: not 5 objects / 1 plate / 5 model_instance / 5 assemble_item: "
            f"{len(objects)} / {len(plates)} / {len(instances)} / {len(items)}")
    template_objects = find_all(before, "object")
    template_parts = find_all(template_objects[0], "part")
    template_instances = find_all(before, "plate", "model_instance")
    template_items = find_all(before, "assemble", "assemble_item")
    if len(template_objects) != 1 or len(template_parts) != 1 or len(template_instances) != 1 or len(template_items) != 1:
        raise ValidationError(f"{SETTINGS_MEMBER}: the template's blocks are not one each")
    without = {"name", "extruder"}
    for k, placed in enumerate(audit.objects):
        meta = metadata_of(objects[k])
        parts = find_all(objects[k], "part")
        if len(parts) != 1:
            raise ValidationError(f"{SETTINGS_MEMBER}: object {k} has {len(parts)} parts, not one")
        part_meta = metadata_of(parts[0])
        require(attributes(objects[k]).get("id") == str(placed.object_id), f"{SETTINGS_MEMBER}: object {k} has another id than {placed.object_id}")
        require(meta.get("name") == placed.shape.name, f"{SETTINGS_MEMBER}: object {k} is named {meta.get('name')!r}, not {placed.shape.name!r}")
        require(meta.get("extruder") == placed.extruder, f"{SETTINGS_MEMBER}: object {k} ({placed.shape.name}) has extruder {meta.get('extruder')!r}, not {placed.extruder!r}")
        require({key: value for key, value in meta.items() if key not in without}
                == {key: value for key, value in metadata_of(template_objects[0]).items() if key not in without},
                f"{SETTINGS_MEMBER}: object {k} carries other metadata than the template")
        require(attributes(parts[0]) == dict(attributes(template_parts[0]), id=str(placed.volume_id)),
                f"{SETTINGS_MEMBER}: part of object {k} is not the template's part with id {placed.volume_id}")
        require(part_meta.get("name") == placed.shape.name
                and {key: value for key, value in part_meta.items() if key != "name"}
                == {key: value for key, value in metadata_of(template_parts[0]).items() if key != "name"},
                f"{SETTINGS_MEMBER}: part of object {k} differs from the template's apart from its name")
        require(metadata_of(instances[k]) == {**metadata_of(template_instances[0]), "object_id": str(placed.object_id),
                                               "identify_id": str(placed.identify_id)},
                f"{SETTINGS_MEMBER}: model_instance {k} is not the template's for object {placed.object_id}, identify {placed.identify_id}")
        require(attributes(items[k]) == dict(attributes(template_items[0]), object_id=str(placed.object_id), transform=placed.transform),
                f"{SETTINGS_MEMBER}: assemble_item {k} is not the template's with object {placed.object_id} and the item transform")
    require(metadata_of(plates[0]) == metadata_of(find_all(before, "plate")[0]), f"{SETTINGS_MEMBER}: the plate's metadata differ from the template's")
    names = [metadata_of(obj).get("name") for obj in objects]
    require(names == [shape.name for shape in shapes()], f"{SETTINGS_MEMBER}: the five names are {names}")
    say(f"{SETTINGS_MEMBER}: object count {len(objects)}, names {names}, "
        f"extruders {[metadata_of(obj).get('extruder') for obj in objects]}, part ids {[attributes(find_all(obj, 'part')[0]).get('id') for obj in objects]}, "
        f"model_instance (object_id, identify_id) {[(metadata_of(i).get('object_id'), metadata_of(i).get('identify_id')) for i in instances]}, "
        f"{len(items)} assemble_items with the build items' transforms")


def project_settings(contents: dict[str, bytes]) -> dict[str, object] | None:
    """The template's project settings when they are a JSON object; None when they are something else."""
    if PROJECT_SETTINGS_MEMBER not in contents:
        return None
    try:
        data = json.loads(contents[PROJECT_SETTINGS_MEMBER].decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def bed_of(project: dict[str, object]) -> tuple[float, float, float, float] | None:
    """x/y minimum and maximum of printable_area ("0x0", "270x0", ...) in mm."""
    corners = project.get("printable_area")
    if not isinstance(corners, list) or not corners:
        return None
    points = []
    for corner in corners:
        found = re.fullmatch(r"\s*(-?[0-9.]+)x(-?[0-9.]+)\s*", str(corner))
        if found is None:
            return None
        points.append((float(found.group(1)), float(found.group(2))))
    return (min(x for x, _ in points), min(y for _, y in points),
            max(x for x, _ in points), max(y for _, y in points))


def validate_layout(audit: Audit, measured: dict[int, Measured], say: Say) -> None:
    """Where the objects sit on the plate: the mesh bounding box plus the item transform, both read from the file."""
    plate: dict[int, tuple[list[float], list[float]]] = {}
    for placed in audit.objects:
        box = measured[placed.object_id]
        shift = [float(value) for value in placed.transform.split()[9:]]
        plate[placed.object_id] = ([a + s for a, s in zip(box.low, shift)], [a + s for a, s in zip(box.high, shift)])
    for k, placed in enumerate(audit.objects):
        low, high = plate[placed.object_id]
        centre = ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2)
        require(abs(centre[0] - CENTRE_X[k]) <= ABS_TOLERANCE and abs(centre[1] - PLATE_Y) <= ABS_TOLERANCE
                and abs(low[2]) <= ABS_TOLERANCE,
                f"{placed.shape.name}: sits at {centre} with its bottom at z = {low[2]}, not at ({CENTRE_X[k]}, {PLATE_Y}, 0)")
    ids = [placed.object_id for placed in audit.objects]
    gaps = [plate[following][0][0] - plate[earlier][1][0] for earlier, following in zip(ids, ids[1:])]
    require(min(gaps) >= MIN_GAP,
            f"objects closer than {MIN_GAP} mm (x gaps {gaps}): the by-object rows need the clearance")
    say(f"placement (mesh bounding box + item transform): centres x {list(CENTRE_X)} on y = {PLATE_Y}, bottoms at z = 0; "
        f"x gaps between neighbours {[number(gap) for gap in gaps]} mm, smallest {number(min(gaps))} mm")

    project = project_settings(audit.contents)
    if project is None:
        say("filaments and bed: NOT CHECKED - the template's project settings are not a JSON object")
        return
    extruders = [placed.extruder for placed in audit.objects]
    colours = project.get("filament_colour")
    if isinstance(colours, list) and all(value.isdigit() for value in extruders):
        highest = max(int(value) for value in extruders)
        require(len(colours) >= highest, f"the template has {len(colours)} filaments; the plate assigns extruder {highest}")
        say(f"filaments in the template: {len(colours)}; highest extruder assigned: {highest}")
    else:
        say(f"filaments: NOT CHECKED - filament_colour is {type(colours).__name__}, extruders {extruders}")
    bed = bed_of(project)
    if bed is None:
        say("bed: NOT CHECKED - printable_area is not a list of corners written as 'XxY'")
        return
    low = [min(plate[identifier][0][axis] for identifier in ids) for axis in range(2)]
    high = [max(plate[identifier][1][axis] for identifier in ids) for axis in range(2)]
    require(bed[0] <= low[0] and bed[1] <= low[1] and high[0] <= bed[2] and high[1] <= bed[3],
            f"the plate content {low} .. {high} leaves the bed {bed}")
    say(f"bed (printable_area) {number(bed[0])}..{number(bed[2])} x {number(bed[1])}..{number(bed[3])} mm holds the content "
        f"x {number(low[0])}..{number(high[0])}, y {number(low[1])}..{number(high[1])} mm")


def validate(output: bytes, template: Template, say: Say) -> list[Placed]:
    """Every required check, on the output read back from its bytes. Prints the numbers as it goes."""
    objects = plan(template)
    audit = Audit(template, objects, {}, {})
    validate_container(output, audit, say)
    validate_lines(audit, say)
    validate_model(audit, say)
    measured = validate_meshes(audit, say)
    validate_settings(audit, say)
    validate_layout(audit, measured, say)
    say("objects on the plate: id, name, extruder, centre (x, y), design size, measured size, z range, shells, triangles")
    for k, placed in enumerate(objects):
        box = measured[placed.object_id]
        size = tuple(b - a for a, b in zip(box.low, box.high))
        say(f"  {placed.object_id}  {placed.shape.name}  extruder {placed.extruder}  centre ({CENTRE_X[k]}, {PLATE_Y})  "
            f"design {number(placed.shape.size[0])} x {number(placed.shape.size[1])} x {number(placed.shape.size[2])}  "
            f"measured {number(size[0])} x {number(size[1])} x {number(size[2])}  z {number(box.low[2])}..{number(box.high[2])}  "
            f"shells {box.shells}  triangles {box.triangles}")
    return objects


# ---------------------------------------------------------------- entry point

def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")   # object names are Chinese; a console must not end the run
    parser = argparse.ArgumentParser(description="Derive the five-object Feishu shapes plate from a template project.")
    parser.add_argument("--template", default=str(ROOT / DEFAULT_TEMPLATE), help="the project to derive from")
    parser.add_argument("--out", default=str(ROOT / DEFAULT_OUT), help="the project to write")
    args = parser.parse_args(argv)
    template_path, out_path = Path(args.template), Path(args.out)
    lines: list[str] = []
    say: Say = lines.append
    try:
        need(out_path.resolve() != template_path.resolve(), "--out must not be the template itself")
        try:
            raw = template_path.read_bytes()
        except OSError as exc:
            raise TemplateError(f"cannot read the template {template_path}: {exc}") from exc
        say(f"template {template_path}: {len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()}")
        template = read_template(raw)
        output = build(template)
        validate(output, template, say)
        require(build(template) == output, "a second build wrote different bytes")
        say(f"double build in this process: byte-identical, sha256 {hashlib.sha256(output).hexdigest()}")
        if out_path.exists():
            try:
                previous = out_path.read_bytes()
            except OSError as exc:
                raise TemplateError(f"cannot read the existing {out_path}: {exc}") from exc
            say(f"existing {out_path.name}: " + ("byte-identical to this build" if previous == output
                 else f"DIFFERENT ({len(previous)} bytes), it is replaced"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(dir=out_path.parent, prefix=out_path.name + ".", suffix=".tmp", delete=False)
        try:
            with handle:
                handle.write(output)
            os.replace(handle.name, out_path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise
        require(out_path.read_bytes() == output, "the file read back from disk differs from what was built")
        require(template_path.read_bytes() == raw, "the template changed during the run")
        say(f"output {out_path}: {len(output)} bytes, sha256 {hashlib.sha256(output).hexdigest()}")
    except FixtureError as exc:
        if lines:
            print("\n".join(lines))
        sys.stdout.flush()
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
