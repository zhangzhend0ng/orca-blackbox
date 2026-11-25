"""Read saved 3MF geometry to check the plate arrangement and object menu cases."""

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
import json
import math
from pathlib import Path

from harness.model_move_pilot import bounds, transform_point
from harness.project_3mf import _archive, _CORE, _PROD, _xml
from part_attachment_oracle import _facets, _mesh, _metadata, _read, _transform


MAIN = '3D/3dmodel.model'
TOL_MM = 0.0001
AREA_TOL = 0.001


@dataclass(frozen=True)
class Instance:
    name: str
    shape: tuple
    basis: tuple
    vertices: tuple
    faces: tuple

    @property
    def box(self):
        return bounds(self.vertices)

    @property
    def contact_faces(self):
        return tuple(face for face in self.faces if all(abs(vertex[2]) <= TOL_MM for vertex in face))


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _hull(points):
    points = sorted(set(points))
    sides = []
    for traversal in (points, reversed(points)):
        side = []
        for p in traversal:
            while len(side) >= 2 and _cross(*side[-2:], p) <= 0:
                side.pop()
            side.append(p)
        sides += side[:-1]
    return tuple(sides)


def _edges(polygon):
    return zip(polygon, (*polygon[1:], polygon[0]))


def _overlap(left, right):
    """True if two convex polygons overlap with positive depth across every axis."""
    for a, b in (*_edges(left), *_edges(right)):
        nx, ny = a[1] - b[1], b[0] - a[0]
        scale = math.hypot(nx, ny)
        p = [nx * x + ny * y for x, y in left]
        q = [nx * x + ny * y for x, y in right]
        if min(max(p), max(q)) - max(min(p), min(q)) <= TOL_MM * scale:
            return False
    return True


def _footprint(faces):
    return tuple(triangle for face in faces
                 if len(triangle := _hull(v[:2] for v in face)) == 3)


def _mesh_overlap(left, right):
    # Hull separation is sufficient to reject overlap. For crossing hulls,
    # use the actual projected facets, which can leave empty corners and holes.
    if not left or not right:
        return False
    if not _overlap(_hull(p for triangle in left for p in triangle),
                    _hull(p for triangle in right for p in triangle)):
        return False
    return any(_overlap(a, b) for a in left for b in right)


def _polygon(corners):
    points = tuple(tuple(map(float, corner.split('x'))) for corner in corners)
    if not all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('non-finite or malformed plate coordinates')
    polygon = _hull(points)
    if len(polygon) < 3 or len(polygon) != len(points):
        raise ValueError('expected a convex printable area')
    return polygon


@dataclass(frozen=True)
class Bed:
    polygon: tuple
    exclusion: tuple
    height: float
    printer: str

    def contains(self, item):
        if item.box[2][0] < -TOL_MM or item.box[2][1] > self.height + TOL_MM:
            return False
        footprint = _hull(v[:2] for v in item.vertices)
        if len(footprint) < 3:
            return False
        for edge in _edges(self.polygon):
            if any(_cross(*edge, point) < -TOL_MM * math.dist(*edge) for point in footprint):
                return False
        return not self.exclusion or not _mesh_overlap(_footprint(item.faces), (self.exclusion,))


def _project(path):
    files = _archive(_read(Path(path)), lambda: False)
    models = {}
    for member, raw in files.items():
        if not member.endswith('.model'):
            continue
        model = _xml(raw)
        if model.tag != _CORE + 'model' or model.get('unit', 'millimeter') != 'millimeter':
            raise ValueError('expected 3MF millimeter models')
        models[member] = model

    config = _xml(files['Metadata/model_settings.config'])
    settings = json.loads(files['Metadata/project_settings.config'])
    height = float(settings['printable_height'])
    if not math.isfinite(height) or height <= 0:
        raise ValueError('invalid printable height')
    excluded = settings.get('bed_exclude_area', [])
    bed = Bed(_polygon(settings['printable_area']),
              _polygon(excluded) if excluded and excluded != ['0x0'] else (),
              height, settings['printer_model'])
    main = models[MAIN]
    items = main.findall(_CORE + 'build/' + _CORE + 'item')
    ids = [item.get('objectid') for item in items]
    plate_instances = config.findall('plate/model_instance')
    plate_ids = [_metadata(i, 'object_id') for i in plate_instances]
    part_ids = [(_metadata(i, 'object_id'), _metadata(i, 'instance_id')) for i in plate_instances]
    object_rows = config.findall('object')
    resources = {row.get('id'): row for row in object_rows}
    if (len(config.findall('plate')) != 1 or Counter(ids) != Counter(plate_ids)
            or len(set(part_ids)) != len(part_ids) or len(resources) != len(object_rows)
            or set(ids) != resources.keys()):
        raise ValueError('model settings must identify each build instance on one plate')

    result = []
    for item in items:
        obj_id = item.get('objectid')
        settings_row = resources[obj_id]
        name = _metadata(settings_row, 'name')
        parent = main.find(f"./{_CORE}resources/{_CORE}object[@id='{obj_id}']")
        part, = settings_row.findall('part')
        component, = parent.findall(_CORE + 'components/' + _CORE + 'component')
        mesh_id = part.get('id')
        if (not name or item.get('printable', '1') not in ('1', 'true')
                or mesh_id != component.get('objectid') or part.get('subtype') != 'normal_part'):
            raise ValueError('expected one normal mesh part per printable object')
        model = models[component.get(_PROD + 'path', MAIN).lstrip('/')]
        mesh = model.find(f"./{_CORE}resources/{_CORE}object[@id='{mesh_id}']")
        points, triangles = _mesh(mesh)
        local, world = _transform(component), _transform(item)
        basis = tuple(transform_point(axis, world[:9] + (0, 0, 0)) for axis in
                      (local[:3], local[3:6], local[6:9]))
        vertices = tuple(transform_point(transform_point(p, local), world) for p in points)
        faces = tuple(tuple(vertices[i] for i in triangle) for triangle in triangles)
        result.append(Instance(name, _facets(points, triangles), basis, vertices, faces))
    return bed, tuple(result)


def _pairs(objects, *, contact=False):
    projections = [_footprint(item.contact_faces if contact else item.faces) for item in objects]
    return [{'objects': [objects[i].name, objects[j].name],
             'overlap': _mesh_overlap(projections[i], projections[j])}
            for i, j in combinations(range(len(objects)), 2)]


def _axis_lengths(item):
    return tuple(math.hypot(*axis) for axis in item.basis)


def _same_mesh(left, right):
    return left.shape == right.shape and all(
        abs(a - b) <= TOL_MM for a, b in zip(_axis_lengths(left), _axis_lengths(right)))


def _aligned(before, after):
    return [(first, second) for first in before for second in after if first.name == second.name]


def _same_named(before, after, number):
    names = {instance.name for instance in before}
    return len(before) == len(after) == len(names) == number and names == {i.name for i in after}


def verify_arrange(before, after):
    first_bed, first = _project(before)
    last_bed, last = _project(after)
    # Intersecting coplanar bottom faces prove the overlaps in the grounded
    # starting fixture. The final check covers the entire XY projected meshes.
    initial = _pairs(first, contact=True)
    final = _pairs(last)
    return {
        'checks': {
            'same_three_objects': _same_named(first, last, 3)
            and all(_same_mesh(a, b) for a, b in _aligned(first, last)),
            'every_pair_overlapped_before': len(initial) == 3 and all(p['overlap'] for p in initial),
            'every_pair_disjoint_after': len(final) == 3 and not any(p['overlap'] for p in final),
            'all_inside_printable_bed_after': first_bed == last_bed and len(last) == 3
            and all(last_bed.contains(item) for item in last),
        },
        'printable_area_mm': last_bed.polygon, 'before_pairs': initial, 'after_pairs': final,
        'before_bounds_mm': {item.name: item.box for item in first},
        'after_bounds_mm': {item.name: item.box for item in last},
    }
