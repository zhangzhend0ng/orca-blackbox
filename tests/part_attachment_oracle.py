"""Read-only #249 checks for the fixture, the attached project and the moved parent."""

from dataclasses import dataclass
from decimal import DecimalException
import math
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from harness.model_move_pilot import bounds, mesh_point, stl_mesh, transform_point
from harness.project_3mf import _CORE, _PROD, _archive, _numbers, _xml


MAIN = '3D/3dmodel.model'
IDENTITY = '1 0 0 0 1 0 0 0 1 0 0 0'
LIMIT = 16 * 1024 * 1024
POSITION_TOL_MM = 0.0001


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    with path.open('rb') as stream:
        raw = stream.read(LIMIT + 1)
    _need(0 < len(raw) <= LIMIT, f'{path.name}: unexpected file size')
    return raw


def _transform(node):
    return tuple(map(float, _numbers(node.get('transform', IDENTITY), 12)))


def _mesh(obj):
    mesh = obj.find(_CORE + 'mesh')
    _need(mesh is not None and obj.find(_CORE + 'components') is None,
          'each part must reference a mesh directly')
    points = [mesh_point(v.get(k) for k in 'xyz')
              for v in mesh.findall(_CORE + 'vertices/' + _CORE + 'vertex')]
    faces = [tuple(int(t.get(k)) for k in ('v1', 'v2', 'v3'))
             for t in mesh.findall(_CORE + 'triangles/' + _CORE + 'triangle')]
    _need(faces and {i for face in faces for i in face} == set(range(len(points))),
          'part mesh has invalid or unused vertex indices')
    return points, faces


def _facets(points, faces):
    # Compare all facets independently of indexing, order, winding and recentering.
    limits = bounds(points)
    _need(all(high - low > POSITION_TOL_MM for low, high in limits),
          'part geometry has no extent on one or more axes')
    normalized = [tuple(round((value - low) / POSITION_TOL_MM)
                        for value, (low, _) in zip(point, limits)) for point in points]
    triangles = [tuple(sorted(normalized[i] for i in face)) for face in faces]
    _need(all(len(set(face)) == 3 for face in triangles) and len(set(triangles)) == len(triangles),
          'part mesh has degenerate or repeated triangles')
    return tuple(sorted(triangles))


@dataclass(frozen=True)
class _Part:
    local_transform: tuple
    shape: tuple
    world_bounds: tuple
    name: str

    def reading(self):
        return {'name': self.name, 'subtype': 'normal_part',
                'triangle_count': len(self.shape), 'world_bounds_mm': self.world_bounds}


@dataclass(frozen=True)
class _Project:
    object_id: str
    parent_transform: tuple
    parts: tuple


def _metadata(node, key):
    values = [row.get('value') for row in node.findall('metadata') if row.get('key') == key]
    _need(len(values) <= 1, f'duplicate {key} metadata')
    return values[0] if values else None


def _project(path, expected_parts):
    files = _archive(_read(path), lambda: False)
    objects = {}
    models = {name: _xml(raw) for name, raw in files.items() if name.endswith('.model')}
    for name, model in models.items():
        _need(model.tag == _CORE + 'model' and model.get('unit', 'millimeter') == 'millimeter',
              'project must use 3MF millimeter models')
        for obj in model.findall(_CORE + 'resources/' + _CORE + 'object'):
            key = name, obj.get('id')
            _need(key[1] and key not in objects and obj.get('type', 'model') == 'model',
                  'project contains an invalid or duplicate model object')
            objects[key] = obj
    items = models[MAIN].findall(_CORE + 'build/' + _CORE + 'item')
    _need(len(items) == 1 and items[0].get('printable', '1') in ('1', 'true'),
          'expected exactly one printable object in the build')
    object_id = items[0].get('objectid')
    parent_key = MAIN, object_id
    parent = objects[parent_key]
    parent_transform = _transform(items[0])
    config = _xml(files['Metadata/model_settings.config'])
    configs = config.findall('object')
    _need(len(configs) == 1 and configs[0].get('id') == object_id,
          'expected one model settings object for the printed object')
    instances = config.findall('plate/model_instance')
    _need(len(instances) == 1 and _metadata(instances[0], 'object_id') == object_id,
          'plate does not reference the sole printed object')
    part_rows = configs[0].findall('part')
    part_ids = {p.get('id'): p for p in part_rows}
    _need(len(part_rows) == len(part_ids) == expected_parts and all(part_ids),
          f'expected {expected_parts} uniquely identified parts under the printed object')
    _need(all(p.get('subtype') == 'normal_part' for p in part_rows),
          'every part must be a normal_part')

    components = parent.findall(_CORE + 'components/' + _CORE + 'component')
    if expected_parts == 1 and not components:
        mesh_refs = [(parent_key, IDENTITY, part_rows[0])]
    else:
        _need(parent.find(_CORE + 'mesh') is None and len(components) == expected_parts
              and {c.get('objectid') for c in components} == set(part_ids),
              'component references do not match the printed object part settings')
        mesh_refs = [((c.get(_PROD + 'path', MAIN).lstrip('/'), c.get('objectid')),
                      c.get('transform', IDENTITY), part_ids[c.get('objectid')]) for c in components]
        _need(all(key != parent_key for key, _, _ in mesh_refs), 'component references the parent itself')
    _need(set(objects) == {parent_key, *(key for key, _, _ in mesh_refs)},
          'project contains model objects outside the printed group')

    parts = []
    for key, transform, row in mesh_refs:
        local_transform = tuple(map(float, _numbers(transform, 12)))
        points, faces = _mesh(objects[key])
        world = [transform_point(transform_point(p, local_transform), parent_transform) for p in points]
        parts.append(_Part(local_transform, _facets(world, faces), bounds(world), _metadata(row, 'name') or ''))
    return _Project(object_id, parent_transform, tuple(parts))


def _load_project(path, count):
    try:
        return _project(path, count)
    except (BadZipFile, DecimalException, LookupError, OSError, ParseError, TypeError, ValueError) as exc:
        raise ValueError(f'{path.name}: {exc}') from exc


def verify_attachment(original: Path, added: Path, part_stl: Path) -> dict:
    """Establish the sole original body's retention and the imported STL's attachment."""
    before = _load_project(original, 1)
    after = _load_project(added, 2)
    try:
        source_shape = _facets(*stl_mesh(_read(part_stl)))
    except (OSError, ValueError) as exc:
        raise ValueError(f'{part_stl.name}: {exc}') from exc
    body_shape = before.parts[0].shape
    _need(body_shape != source_shape, 'input STL must be distinguishable from the original body')
    by_shape = {part.shape: part for part in after.parts}
    _need(body_shape in by_shape, 'original body facet geometry was not retained')
    _need(source_shape in by_shape, 'attached part facet geometry does not match the source STL')
    return {'printable_object_id': after.object_id, 'printable_object_count': 1,
            'original': by_shape[body_shape].reading(), 'attachment': by_shape[source_shape].reading()}


def _close(actual, expected):
    return all(math.isclose(a, b, rel_tol=0, abs_tol=POSITION_TOL_MM)
               for a, b in zip(actual, expected, strict=True))


def verify_group_move(added: Path, moved: Path, delta_x=10) -> dict:
    """Establish that the parent transform moved both of its parts together."""
    delta = float(delta_x), 0.0, 0.0
    _need(math.isfinite(delta[0]) and abs(delta[0]) > POSITION_TOL_MM, 'expected a nonzero finite X move')
    before, after = _load_project(added, 2), _load_project(moved, 2)
    first, last = before.parent_transform, after.parent_transform
    actual_delta = tuple(b - a for a, b in zip(first[9:], last[9:]))
    _need(_close(last[:9], first[:9]) and _close(actual_delta, delta),
          f'parent transform did not move by {delta} mm; measured {actual_delta} mm')

    parts = {part.shape: part for part in after.parts}
    _need(len({p.shape for p in before.parts}) == len(parts) == 2,
          'group must retain two distinguishable part meshes')
    readings = []
    for a in before.parts:
        b = parts.get(a.shape)
        _need(b is not None and _close(a.local_transform, b.local_transform),
              'component geometry or its local transform changed during the group move')
        lower_delta, upper_delta = ((x - y for x, y in zip(new, old))
                                    for new, old in zip(zip(*b.world_bounds), zip(*a.world_bounds)))
        measured = tuple(lower_delta)
        _need(_close(measured, delta) and _close(tuple(upper_delta), delta),
              f'component {a.name!r} did not move by {delta} mm')
        readings.append({'before': a.reading(), 'after': b.reading(), 'delta_mm': measured})
    return {'parent_delta_mm': actual_delta, 'parts': readings}
