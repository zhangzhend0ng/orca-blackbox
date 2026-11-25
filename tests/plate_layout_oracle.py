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


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _same_mesh(left, right):
    # Matching the Gram matrix also rejects changes such as shear with
    # unchanged axis lengths. An XY move or a proper rotation preserves it.
    def handedness(item):
        a, b, c = item.basis
        normal = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
        return _dot(normal, c)

    return (left.shape == right.shape and handedness(left) * handedness(right) > TOL_MM
            and all(abs(_dot(a, b) - _dot(c, d)) <= TOL_MM
                    for a, c in zip(left.basis, right.basis)
                    for b, d in zip(left.basis, right.basis)))


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


def _plate_normal(item):
    lengths = _axis_lengths(item)
    if min(lengths) <= TOL_MM or any(
        abs(_dot(a, b)) > TOL_MM for a, b in combinations(item.basis, 2)
    ):
        raise ValueError('cannot recover the plate direction from a singular or sheared transform')
    return tuple(axis[2] / length for axis, length in zip(item.basis, lengths))


def _contact_area(item):
    return sum(abs(_cross(*triangle)) / 2 for triangle in item.contact_faces)


def verify_orient(before, after):
    first_bed, first = _project(before)
    last_bed, last = _project(after)
    aligned = _aligned(first, last)
    readings = {}
    for source, adjusted in aligned:
        initial, final = _plate_normal(source), _plate_normal(adjusted)
        tilt = math.degrees(math.acos(max(-1, min(1, _dot(initial, final)))))
        area_before, area_after = _contact_area(source), _contact_area(adjusted)
        readings[source.name] = {
            'before_plate_normal_in_model_axes': initial, 'after_plate_normal_in_model_axes': final,
            'tilt_deg': tilt, 'before_contact_mm2': area_before, 'after_contact_mm2': area_after,
        }
    return {
        'checks': {
            'same_two_objects': _same_named(first, last, 2)
            and all(_same_mesh(a, b) for a, b in aligned),
            'each_orientation_changed': len(readings) == 2
            and all(row['tilt_deg'] > 0.1 for row in readings.values()),
            'each_contact_area_increased': len(readings) == 2
            and all(row['after_contact_mm2'] > row['before_contact_mm2'] + AREA_TOL
                    for row in readings.values()),
            'each_grounded_and_in_printable_volume': first_bed == last_bed and len(first) == len(last) == 2
            and all(abs(item.box[2][0]) <= TOL_MM for item in first)
            and all(abs(item.box[2][0]) <= TOL_MM and last_bed.contains(item) for item in last),
        },
        'objects': readings,
    }


def _rectangle(polygon):
    if len(polygon) != 4:
        return None
    xs = sorted({point[0] for point in polygon})
    ys = sorted({point[1] for point in polygon})
    if len(xs) != 2 or len(ys) != 2:
        return None
    return xs[0], ys[0], xs[1], ys[1]


def _find_square(home, obstacles, side):
    # Forbidden centres are axis-aligned open rectangles. Test each X
    # boundary and each open interval between boundaries, where the same
    # set of rectangles block Y. Include boundaries to catch exact fits.
    inset = side / 2 - TOL_MM
    x0, y0, x1, y1 = home
    x0, y0, x1, y1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    if x0 > x1 or y0 > y1:
        return None
    blocked = [(a - inset, b - inset, c + inset, d + inset) for a, b, c, d in obstacles]
    cuts = sorted({x0, x1, *(v for a, _, c, _ in blocked for v in (a, c) if x0 < v < x1)})
    samples = [*cuts, *((a + b) / 2 for a, b in zip(cuts, cuts[1:]))]
    for x in samples:
        y = y0
        for low, high in sorted((b, d) for a, b, c, d in blocked if a < x < c):
            if low >= y:
                break
            y = max(y, high)
        if y <= y1:
            return x, y
    return None


def _fill_measurement(bed, original, copies):
    base = _rectangle(bed.polygon)
    rectangles = [_rectangle(_hull(v[:2] for v in item.vertices)) for item in copies]
    source = _rectangle(_hull(v[:2] for v in original.vertices))
    if bed.exclusion or base is None or source is None or any(rect is None for rect in rectangles):
        return {'status': 'unsupported_rectangular_fixture'}
    for item, (x0, y0, x1, y1) in zip(copies, rectangles):
        if abs(_contact_area(item) - (x1 - x0) * (y1 - y0)) > AREA_TOL:
            return {'status': 'unsupported_rectangular_contact'}
    x0, y0, x1, y1 = source
    # At every yaw the source rectangle contains this axis-aligned square
    # at its centre. If that smaller square cannot fit, no extra copy can
    # fit, even with zero clearance and freely chosen yaw.
    side = min(x1 - x0, y1 - y0) / math.sqrt(2)
    empty = _find_square(base, rectangles, side)
    return {'status': 'saturated' if empty is None else 'saturation_not_proven',
            'necessary_square_side_mm': side, 'unblocked_square_center_mm': empty}


def verify_clone(before, cloned, filled=None):
    first_bed, first = _project(before)
    cloned_bed, second = _project(cloned)
    if len(first) != 1:
        raise ValueError('expected one source object before cloning')
    source, = first
    count = len(second)
    original = second[0] if count else None
    copy = second[1] if count == 2 else None
    same_original = original is not None and source.name == original.name and _same_mesh(source, original)
    original_pose = same_original and all(math.dist(a, b) <= TOL_MM
                                          for a, b in zip(source.basis, original.basis))
    pairs = _pairs(second)
    checks = {
        'exactly_one_copy_added': count == 2 and first_bed == cloned_bed,
        'original_geometry_and_pose_preserved': original_pose,
        'copy_geometry_matches': copy is not None and _same_mesh(source, copy),
        'clone_is_separately_placed': count == 2 and len(pairs) == 1 and not pairs[0]['overlap']
        and all(cloned_bed.contains(item) for item in second),
        'fill_adds_copies': False,
        'fill_copies_match': False,
        'fill_copies_nonoverlapping_and_in_bed': False,
        'fill_saturation_verified': False,
    }
    result = {
        'checks': checks, 'clone_count': count, 'clone_pairs': pairs,
        'source_bounds_mm': source.box, 'cloned_bounds_mm': [item.box for item in second],
        'fill': {'status': 'missing_saved_fill'},
    }
    if filled is not None:
        final_bed, final = _project(filled)
        checks['fill_adds_copies'] = len(final) > count == 2
        checks['fill_copies_match'] = bool(final) and all(_same_mesh(source, item) for item in final)
        checks['fill_copies_nonoverlapping_and_in_bed'] = (
            final_bed == cloned_bed and len(final) > 2
            and all(final_bed.contains(item) for item in final)
            and not any(pair['overlap'] for pair in _pairs(final))
        )
        measurement = _fill_measurement(final_bed, source, final)
        checks['fill_saturation_verified'] = (
            checks['fill_copies_match'] and checks['fill_copies_nonoverlapping_and_in_bed']
            and measurement['status'] == 'saturated'
        )
        result['fill'] = {'count': len(final), **measurement}
    return result
