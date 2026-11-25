"""Offline checks for Feishu #228: an OBJ with two materials imported through File > Import.

Every function here reads what the application put on disk; nothing drives the
GUI. The ``*_readings`` functions never raise for a failed expectation: they
return their readings with ``checks``. The ``verify_*`` functions raise
ValueError on the first failed check.

What the application does with such an OBJ, as the guest showed (Snapmaker
Orca 2.4.0, run dev228b-2c32e51c on 2026-11-26) and as the tag ``sm-v2.4.0``
(b1831e5d) says, which is the ref the guest behaved like:

* One object with one mesh: ``load_obj`` ends in ``model->add_object(name,
  path, mesh)`` and does not split by ``usemtl``
  (src/libslic3r/Format/OBJ.cpp:211-228). A face takes its material's colour
  when every component of ``Ka + Kd`` is at most 1, else ``Kd``
  (OBJ.cpp:141-157).
* A material with ``map_Kd`` sets ``has_uv_png`` (OBJ.cpp:158-163), which
  turns the face-colour branch of ``Model::read_from_file`` off
  (Model.cpp:282); the textured branch is commented out (Model.cpp:290-296).
  The guest loaded that form as plain geometry: no dialog, 24 faces without
  any paint attribute, one tool in the G-code.
* Without ``map_Kd`` the GUI shows ``Obj file Import color``
  (GUI/Plater.cpp:12175-12183) and ``obj_import_face_color_deal`` sets the
  extruder of the object and of its one volume to the filament of the first
  colour cluster, then paints every face whose filament is above 1 and leaves
  the faces of filament 1 to that extruder (Model.cpp:3255-3280, the skip at
  3271). A face therefore prints with its paint where it carries one and with
  its part's extruder otherwise, which is how painted_readings() reads it.

The ref ``sync/softfever-20261010`` (813784a9d0) describes another importer,
which would show ``Import Model`` for both forms (Model.cpp:356-365 and
398-415, GUI/Plater.cpp:24060). The guest did not behave that way; that
dialog's title is answered all the same.

The paint on a triangle is read as saved, never assumed:

* The attribute is ``paint_color`` (Format/bbs_3mf.cpp:372 on the sync ref;
  the tracked project docs/runs/evidence/feishu-140-201-202-2026-11-25/
  row-202-hyperv/7a7a584f-after-save-as.3mf, saved by the same application,
  carries it). The same field under its older name ``slic3rpe:mmu_segmentation``
  (Format/3mf.cpp:142) is read as well, and every triangle attribute there is
  goes into ``triangle_attributes``.
* The value is a bit stream packed four bits to a hexadecimal digit, last
  digit first (Model.cpp:4063-4085 FacetsAnnotation::get_triangle_as_string
  on the sync ref). A node is two bits for the number of split sides, then
  for a split node two bits for the special side and one node per child, else
  two bits of state, where 3 says that one or more four-bit chunks of
  ``state - 3`` follow and a chunk of 15 says another chunk follows
  (TriangleSelector.cpp:1722-1788, TriangleSelector::serialize). An unsplit
  face painted with the first filament is ``4``, with the second ``8``, with
  the third ``0C``: state n is the n-th filament (CONST_FILAMENTS in
  Model.cpp:48-50 on the tag says the same: "", "4", "8", "0C", ...).
* The unit tests decode the values of that tracked project with the same
  function.

Tool changes: a Snapmaker U1 export selects a tool with a ``T<n>`` line, n
being the filament's index from zero. The real five-tool export 0ac8ba5d
(artifacts/windows_mcp_harvest) changes with ``; Change Tool1 -> Tool2
(layer 2)``, ``M109 S230 T2``, ``M400``, ``T2``.
"""
import json
from pathlib import Path
import re
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from export_io_oracle import MOTION, NUMBER, WORD
from harness.model_move_pilot import transform_point
from harness.project_3mf import _CORE, _PROD, _archive, _xml
from part_attachment_oracle import _metadata, _mesh, _read, _transform

CLAUSE_COLORS = '模型导入成功，两种颜色按面片正确显示'
CLAUSE_FILAMENTS = '切片后按颜色生成对应耗材/换料'
MATERIALS = ('red', 'blue')
SIDE_MM = 20.0
MAIN = '3D/3dmodel.model'
SETTINGS = 'Metadata/model_settings.config'
PROJECT = 'Metadata/project_settings.config'
EXTRUDER_KEY = 'extruder'
DEFAULT_EXTRUDER = 1  # what a part prints with that names no extruder, nor does its object
PAINT_ATTRS = ('paint_color', 'slic3rpe:mmu_segmentation')
VERTEX_TOL_MM = 0.001  # the same tolerance as tests/import_stl_oracle.py
TOOL = re.compile(r'^T(\d+)(?:\D|$)')
LAYER_START = re.compile(r'^;\s*(?:LAYER_CHANGE|LAYER:\s*\d+)\s*$')
PRINTING = re.compile(r'^; printing object (.*) id:\d+ copy \d+\s*$')
HEX = re.compile(r'^[0-9A-Fa-f]+$')
CENSUS_LIMIT = 60


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _leaf(path):
    return str(path).replace('\\', '/').rsplit('/', 1)[-1]


# --- the fixture's geometry ----------------------------------------------------

def _box(x0, x1):
    half = SIDE_MM / 2
    corners = ((x0, -half, -half), (x1, -half, -half), (x1, half, -half), (x0, half, -half),
               (x0, -half, half), (x1, -half, half), (x1, half, half), (x0, half, half))
    # Outward faces, three corners counter-clockwise seen from outside.
    faces = ((0, 3, 2), (0, 2, 1), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
    return [tuple(corners[index] for index in face) for face in faces]


def _two_boxes():
    """(vertices, faces): two closed 10 x 20 x 20 boxes side by side, each with its own vertices.
    16 vertices, 24 faces. The two boxes share the wall at x = 0 as geometry: two coincident
    faces there, one facing each way."""
    vertices, faces = [], []
    for material, x0 in zip(MATERIALS, (-SIDE_MM / 2, 0.0)):
        local = sorted({corner for face in _box(x0, x0 + SIDE_MM / 2) for corner in face})
        base = len(vertices)
        vertices += local
        faces += [(*(base + local.index(corner) for corner in face), material) for face in _box(x0, x0 + SIDE_MM / 2)]
    return vertices, faces


def _split_cube():
    """(vertices, faces): one closed 20 mm cube cut at x = 0: 12 vertices, 20 faces, every edge in
    two faces. The left half of each face is the first material, the right half the second."""
    h = SIDE_MM / 2
    vertices = [(-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h), (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
                (0, -h, -h), (0, h, -h), (0, -h, h), (0, h, h)]  # the last four bisect the edges that cross x = 0
    red = [(0, 3, 9), (0, 9, 8), (4, 10, 11), (4, 11, 7), (0, 8, 10), (0, 10, 4), (9, 3, 7), (9, 7, 11),
           (3, 0, 4), (3, 4, 7)]
    blue = [(8, 9, 2), (8, 2, 1), (10, 5, 6), (10, 6, 11), (8, 1, 5), (8, 5, 10), (2, 9, 11), (2, 11, 6),
            (1, 2, 6), (1, 6, 5)]
    return vertices, [(*face, 'red') for face in red] + [(*face, 'blue') for face in blue]


GEOMETRIES = {'two-boxes': _two_boxes, 'split-cube': _split_cube}


def mesh_geometry(name='two-boxes'):
    """(vertices, [(i, j, k, material)]) of a fixture geometry in OBJ coordinates; the faces come
    material by material, in the order MATERIALS names them."""
    if name not in GEOMETRIES:
        raise ValueError(f'unknown fixture geometry {name!r}; known: {sorted(GEOMETRIES)}')
    return GEOMETRIES[name]()


def material_triangles(name='two-boxes'):
    """{'red': the triangles of the first material, 'blue': those of the second} in OBJ coordinates.
    ``two-boxes``: 12 + 12 faces of two closed boxes making a 20 mm cube split at x = 0;
    ``split-cube``: 10 + 10 faces of one closed cube cut at x = 0."""
    vertices, faces = mesh_geometry(name)
    return {material: [tuple(vertices[index] for index in face[:3]) for face in faces if face[3] == material]
            for material in MATERIALS}


# --- the paint on one triangle -------------------------------------------------

def decode_paint(raw):
    """Leaf states of one paint value, in the order TriangleSelector::serialize emits them
    (0 is a leaf that is not painted). Raises ValueError when the digits do not form
    exactly one complete tree."""
    _need(isinstance(raw, str) and raw and HEX.match(raw), f'not a hexadecimal paint value: {raw!r}')
    bits = [(int(char, 16) >> bit) & 1 for char in reversed(raw) for bit in range(4)]
    pos = 0

    def pair():
        nonlocal pos
        _need(pos + 2 <= len(bits), f'paint value {raw!r} ends inside a node')
        value = bits[pos] | (bits[pos + 1] << 1)
        pos += 2
        return value

    def node():
        nonlocal pos
        split = pair()
        if split:
            pair()  # the special side: which side is kept or split; not read here
            states = []
            for _ in range(split + 1):
                states.extend(node())
            return states
        state = pair()
        if state < 3:
            return [state]
        while True:
            _need(pos + 4 <= len(bits), f'paint value {raw!r} ends inside a state chunk')
            chunk = sum(bits[pos + bit] << bit for bit in range(4))
            pos += 4
            if chunk != 15:
                return [state + chunk]
            state += 15

    states = node()
    _need(pos == len(bits), f'paint value {raw!r} has {len(bits) - pos} bits outside its tree')
    return states


def face_filament(raw):
    """The filament a triangle is painted with, 0 when it is not, None when its leaves disagree
    (they are in ``decode_paint(raw)``)."""
    if raw is None:
        return 0
    states = decode_paint(raw)
    return states[0] if len(states) == 1 and len(set(states)) == 1 else None


# --- the saved project ---------------------------------------------------------

def _number(value):
    return int(value) if value and value.isdigit() else None


def _paint(triangle):
    found = {key.split('}')[-1]: value for key, value in triangle.attrib.items()
             if key.split('}')[-1] in PAINT_ATTRS}
    _need(len(found) <= 1, 'a triangle carries more than one paint attribute')
    return next(iter(found.items())) if found else (None, None)


def _part_faces(obj, local, world):
    points, faces = _mesh(obj)
    triangles = obj.find(_CORE + 'mesh/' + _CORE + 'triangles')
    _need(triangles is not None and len(triangles) == len(faces), 'a part lists other than its own triangles')
    placed = [transform_point(transform_point(point, local), world) for point in points]
    out = []
    for triangle, face in zip(triangles, faces):
        key, raw = _paint(triangle)
        face_ = {'corners': tuple(placed[index] for index in face), 'attribute': key, 'paint': raw,
                 'leaves': [], 'filament': 0, 'decode_error': None}
        if raw is not None:
            try:
                face_['leaves'] = decode_paint(raw)
            except ValueError as exc:
                face_['decode_error'] = str(exc)
            else:
                face_['filament'] = face_['leaves'][0] if len(set(face_['leaves'])) == 1 else None
        out.append(face_)
    return out


def read_colored_project(project):
    """What a saved project holds, object by object and part by part, with every triangle
    attribute name and value it carries. Raises ValueError when the file cannot be read;
    nothing here compares with an expectation."""
    project = Path(project)
    try:
        files = _archive(_read(project), lambda: False)
        models = {name: _xml(raw, allow_colour_paint=True) for name, raw in files.items() if name.endswith('.model')}
        config = _xml(files[SETTINGS])
        settings = json.loads(files[PROJECT])
        resources = {(name, obj.get('id')): obj for name, model in models.items()
                     for obj in model.findall(_CORE + 'resources/' + _CORE + 'object')}
        items = {item.get('objectid'): item for item in models[MAIN].findall(_CORE + 'build/' + _CORE + 'item')}
        on_plate = {_metadata(row, 'object_id') for plate in config.findall('plate') for row in plate.findall('model_instance')}
        colours = settings.get('filament_colour')
        _need(isinstance(colours, list) and all(isinstance(value, str) for value in colours),
              'filament_colour is not a list of colours')
        census = {}
        for model in models.values():
            for triangle in model.iter(_CORE + 'triangle'):
                for key, value in triangle.attrib.items():
                    values = census.setdefault(key.split('}')[-1], {})
                    values[value] = values.get(value, 0) + 1
        objects, volumes = [], []
        for row in config.findall('object'):
            item = items.get(row.get('id'))
            if item is None or item.get('printable', '1') not in ('1', 'true'):
                continue
            parent = resources[(MAIN, row.get('id'))]
            world = _transform(item)
            parts = {part.get('id'): part for part in row.findall('part')}
            entry = {'id': row.get('id'), 'name': _metadata(row, 'name'), 'on_plate': row.get('id') in on_plate,
                     'extruder': _number(_metadata(row, EXTRUDER_KEY)), 'volumes': []}
            for component in parent.findall(_CORE + 'components/' + _CORE + 'component'):
                part_id = component.get('objectid')
                part = parts.get(part_id)
                path = component.get(_PROD + 'path', MAIN).lstrip('/')
                volume = {'object': row.get('id'), 'id': part_id, 'name': _metadata(part, 'name') if part is not None else None,
                          'subtype': part.get('subtype') if part is not None else None,
                          'extruder': _number(_metadata(part, EXTRUDER_KEY)) if part is not None else None,
                          'source_file': _metadata(part, 'source_file') if part is not None else None,
                          'faces': _part_faces(resources[(path, part_id)], _transform(component), world)}
                entry['volumes'].append(volume)
                volumes.append(volume)
            objects.append(entry)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, ParseError, ArithmeticError) as exc:
        raise ValueError(f'{project.name}: unreadable project ({exc})') from exc
    return {'object_names': [entry['name'] for entry in objects], 'plates': len(config.findall('plate')),
            'objects': objects, 'volumes': volumes, 'filament_colour': colours,
            'printer': settings.get('printer_settings_id'),
            'triangle_attributes': {name: dict(sorted(values.items(), key=lambda pair: -pair[1])[:CENSUS_LIMIT])
                                    for name, values in census.items()},
            'triangle_attribute_names': sorted(census)}


# --- clause 1: the colours as saved --------------------------------------------

def _distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _same_triangle(actual, expected):
    """True when every expected corner has its own actual corner within the tolerance."""
    remaining = list(actual)
    for point in expected:
        hit = next((i for i, other in enumerate(remaining) if _distance(other, point) <= VERTEX_TOL_MM), None)
        if hit is None:
            return False
        remaining.pop(hit)
    return True


def _extents(points):
    return [[min(point[axis] for point in points), max(point[axis] for point in points)] for axis in range(3)]


def _corner_offset(faces, expected):
    """Where the part lies against the fixture: from the lowest corners of one to those of the other.
    It is read from the outermost corners, so it also serves a part saved with other triangles."""
    corners = [corner for face in faces for corner in face['corners']]
    flat = [corner for group in expected.values() for face in group for corner in face]
    if not corners or not flat:
        return [0.0, 0.0, 0.0]
    return [low - other for (low, _high), (other, _high) in zip(_extents(corners), _extents(flat))]


def _part_faces_placed(faces, expected):
    """(offset in mm, [(index of a face of the part, material whose triangle it is)]): the part's
    faces as the fixture's triangles moved onto the plate; (None, []) when the part is not
    the fixture's geometry."""
    corners = [corner for face in faces for corner in face['corners']]
    if not corners or sum(len(group) for group in expected.values()) != len(faces):
        return None, []
    offset = _corner_offset(faces, expected)
    pairs, used = [], set()
    for group, triangles in expected.items():
        for triangle in triangles:
            moved = [tuple(corner[axis] + offset[axis] for axis in range(3)) for corner in triangle]
            hits = [index for index, face in enumerate(faces)
                    if index not in used and _same_triangle(face['corners'], moved)]
            if len(hits) != 1:
                return None, pairs
            used.add(hits[0])
            pairs.append((hits[0], group))
    return offset, pairs


def _paint_states(faces):
    """{what a face is painted with: how many faces carry it and where they lie}."""
    out = {}
    for face in faces:
        key = ('unpainted' if not face['paint'] else
               'split' if face['decode_error'] or face['filament'] is None else str(face['filament']))
        row = out.setdefault(key, {'faces': 0, 'box_mm': None, 'paint_values': {}})
        row['faces'] += 1
        row['paint_values'][face['paint']] = row['paint_values'].get(face['paint'], 0) + 1
        box = _extents(face['corners'])
        row['box_mm'] = box if row['box_mm'] is None else [[min(a[0], b[0]), max(a[1], b[1])] for a, b in zip(row['box_mm'], box)]
    return out


def _colour(colours, filament):
    return colours[filament - 1].casefold() if 0 < filament <= len(colours) else None


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _contains(corners, point):
    """True when `point` lies inside the triangle `corners` (within a hundredth of a millimetre
    of its plane): on the same side of each of its three edges as the triangle's inside."""
    first, second, third = corners
    u = [y - x for x, y in zip(first, second)]
    v = [y - x for x, y in zip(first, third)]
    w = [y - x for x, y in zip(first, point)]
    normal = _cross(u, v)
    length = sum(value * value for value in normal) ** 0.5
    if length < 1e-12 or abs(_dot(normal, w)) / length > 0.01:
        return False
    return (_dot(_cross(u, w), normal) >= -1e-12
            and _dot(_cross([y - x for x, y in zip(u, v)], [y - x for x, y in zip(v, w)]), normal) >= -1e-12
            and _dot(_cross(w, v), normal) >= -1e-12)


def _centre(triangle, offset=(0.0, 0.0, 0.0)):
    return [sum(corner[axis] for corner in triangle) / 3 + offset[axis] for axis in range(3)]


def _under_centres(faces, expected, offset):
    """{material: {what the saved face under the centre of each fixture triangle is painted with:
    count}}. A reading that holds also when the application saved the mesh divided into other
    triangles. A triangle that lies on another material's triangle (the wall between two boxes)
    has no single face under its centre and is counted as ``inner wall``."""
    out = {}
    for material, triangles in expected.items():
        others = [other for name, group in expected.items() if name != material for other in group]
        counts = {}
        for triangle in triangles:
            if any(_contains(other, _centre(triangle)) for other in others):
                key = 'inner wall'
            else:
                hit = next((face for face in faces if _contains(face['corners'], _centre(triangle, offset))), None)
                key = ('no face' if hit is None else 'unpainted' if not hit['paint']
                       else str(hit['filament']) if hit['filament'] is not None else 'split')
            counts[key] = counts.get(key, 0) + 1
        out[material] = counts
    return out


def _part_reading(volume):
    corners = [corner for face in volume['faces'] for corner in face['corners']]
    return {'name': volume['name'], 'subtype': volume['subtype'], 'extruder': volume['extruder'],
            'source_file': _leaf(volume['source_file']) if volume['source_file'] else None,
            'triangles': len(volume['faces']), 'box_mm': _extents(corners) if corners else None}


def _prints_with(face, extruder):
    """The filament a face prints with: its paint where it carries one, else `extruder`, the one
    its part prints with. None when a face is split between leaves of different filaments."""
    if face['decode_error'] or (face['paint'] and face['filament'] is None):
        return None
    return face['filament'] if face['paint'] else extruder


def painted_readings(project, object_name=None, groups=None):
    """Feishu #228, first clause. The saved project holds the fixture as one object with one
    normal part on the plate, its faces each where the fixture has it, every face of the first
    material printing with one filament, every face of the second with another, and the two
    filaments differ in ``filament_colour``. A face prints with its paint where it carries one
    and with its part's extruder otherwise, which is how an OBJ import leaves the faces of the
    first filament (Model.cpp:3271 on the tag sm-v2.4.0 skips them). ``object_name`` picks the
    object when the plate holds more than one. Nothing raises for a failed expectation;
    ``error`` when the file cannot be read."""
    expected = {name: [tuple(map(tuple, face)) for face in faces]
                for name, faces in (groups or material_triangles()).items()}
    names = list(expected)
    try:
        saved = read_colored_project(project)
        _need(len(names) == 2, 'the expectation names two materials')
        wanted = [entry for entry in saved['objects']
                  if object_name is None or entry['name'] in (object_name, object_name.rsplit('.', 1)[0])]
        _need(len(wanted) == 1, f'expected one object named {object_name!r}, the project names {saved["object_names"]!r}')
        _need(len(wanted[0]['volumes']) == 1, f'expected one part, the object has {len(wanted[0]["volumes"])}')
        entry, part = wanted[0], wanted[0]['volumes'][0]
        offset, placed = _part_faces_placed(part['faces'], expected)
        # A part without an extruder of its own follows its object's, and without that the first
        # filament: the textured project of run dev228b-2c32e51c names none and printed with T0.
        base = next((value for value in (part['extruder'], entry['extruder']) if value), DEFAULT_EXTRUDER)
        values = {name: sorted({_prints_with(part['faces'][index], base) for index, group in placed if group == name},
                               key=lambda value: (value is None, value is not None, value))
                  for name in names}
        filaments = [values[name][0] if len(values[name]) == 1 else None for name in names]
        colours = saved['filament_colour']
        painted = [value for value in filaments if value is not None]
        checks = {
            'one_object_one_part_on_plate': len(saved['object_names']) == 1 and saved['plates'] == 1
            and entry['on_plate'] and part['subtype'] == 'normal_part',
            'faces_are_the_fixture': offset is not None,
            'first_material_one_filament': offset is not None and filaments[0] is not None and filaments[0] > 0,
            'second_material_one_filament': offset is not None and filaments[1] is not None and filaments[1] > 0,
            'different_filaments': None not in filaments and filaments[0] != filaments[1],
            'different_filament_colours': None not in filaments and filaments[0] != filaments[1]
            and None not in (_colour(colours, filaments[0]), _colour(colours, filaments[1]))
            and _colour(colours, filaments[0]) != _colour(colours, filaments[1]),
        }
        return {'checks': checks, 'object_names': saved['object_names'], 'plates': saved['plates'],
                'object_extruder': entry['extruder'], 'parts': [_part_reading(part)],
                'placement_offset_mm': [round(value, 6) for value in offset] if offset is not None else None,
                'filaments': dict(zip(names, filaments)), 'filament_values': dict(zip(names, values)),
                'faces_without_paint_print_with': base,
                'filament_colours': {str(value): _colour(colours, value) for value in painted},
                'filament_colour': colours, 'printer': saved['printer'],
                # What the extruders are against the filaments the faces print with (a reading).
                'extruder_is_smallest_filament': bool(painted) and entry['extruder'] == part['extruder'] == min(painted),
                'paint_states': _paint_states(part['faces']), 'triangle_attributes': saved['triangle_attributes'],
                'triangle_attribute_names': saved['triangle_attribute_names'],
                # Not a check: the same colours read under the centre of each fixture triangle.
                'under_centres': _under_centres(part['faces'], expected, offset or _corner_offset(part['faces'], expected))}
    except (OSError, ValueError) as exc:
        return {'checks': {}, 'error': str(exc)}


def verify_painted_import(project, object_name=None, groups=None):
    """Raises ValueError naming the first failed check of painted_readings; returns its readings."""
    readings = painted_readings(project, object_name, groups)
    if 'error' in readings:
        raise ValueError(readings['error'])
    failed = [name for name, passed in readings['checks'].items() if not passed]
    if failed:
        raise ValueError(f'{_leaf(project)}: ' + '; '.join(f'{name} failed' for name in failed)
                         + f'; filaments {readings["filaments"]}, paint {readings["paint_states"]}')
    return readings


# --- clause 2: the filaments in the G-code ------------------------------------

def _codes(raw):
    """(lines, code halves) of a G-code file: the comment of a line is dropped."""
    lines = raw.decode('utf-8', errors='replace').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    codes = []
    for line in lines:
        stripped = line.strip()
        codes.append('' if not stripped or stripped[0] == ';' else stripped.partition(';')[0].strip())
    return lines, codes


def _walk(raw):
    """What a G-code file does with its tools, line by line: ``('select', tool)`` at every
    ``T<n>``, ``('change', from, to, line, after the first layer starts)`` whenever the tool
    changes, and ``('extrude', object being printed or None, tool, filament length)`` at every
    move that extrudes while travelling in XY. ``M82``, ``M83`` and ``G92 E`` are followed."""
    lines, codes = _codes(raw)
    first_layer = next((i for i, line in enumerate(lines) if LAYER_START.match(line.strip())), len(lines))
    tool, absolute_e, e_position, printed = None, True, None, None
    for number, (line, code) in enumerate(zip(lines, codes), 1):
        head = code.split(None, 1)[0].upper() if code else ''
        if line.startswith('; printing object '):
            found = PRINTING.match(line.strip())
            printed = found.group(1) if found else None
            continue
        if line.startswith('; stop printing object'):
            printed = None
            continue
        found = TOOL.match(code)
        if found:
            new = int(found.group(1))
            if tool is not None and new != tool:
                yield 'change', tool, new, number, number - 1 >= first_layer
            tool, e_position = new, None
            yield 'select', new
        elif head == 'M82':
            absolute_e, e_position = True, None
        elif head == 'M83':
            absolute_e = False
        elif MOTION.match(code):
            words = {key: float(value) for key, value in WORD.findall(code)}
            if head == 'G92':
                e_position = words.get('E', e_position)
            elif 'E' in words:
                if absolute_e:
                    delta = None if e_position is None else words['E'] - e_position
                    e_position = words['E']
                else:
                    delta = words['E']
                if delta is not None and delta > 0 and ('X' in words or 'Y' in words) and tool is not None:
                    yield 'extrude', printed, tool, delta


def _per_tool(events):
    """{tool: its selects, extruding moves and filament length} over the ``select`` and
    ``extrude`` events of `events`."""
    tools = {}
    for event in events:
        if event[0] == 'select':
            tools.setdefault(event[1], {'selects': 0, 'extruding_moves': 0, 'e': 0.0})['selects'] += 1
        elif event[0] == 'extrude':
            row = tools.setdefault(event[2], {'selects': 0, 'extruding_moves': 0, 'e': 0.0})
            row['extruding_moves'] += 1
            row['e'] += event[3]
    return {str(tool): {**row, 'e': round(row['e'], 5)} for tool, row in sorted(tools.items())}


def _extruding(per_tool):
    return sorted(int(tool) for tool, row in per_tool.items() if row['extruding_moves'])


def _filament_used(raw):
    return [line for line in _codes(raw)[0] if line.startswith('; filament used')]


def _printed_in(event, keys):
    return event[0] == 'extrude' and event[1] is not None and event[1].casefold() in keys


def gcode_tools(path, object_name=None):
    """The tools a G-code file prints with: those that extrude, each tool's extruding moves and
    filament length, and how often the tool changes. With ``object_name`` the moves inside that
    object's ``; printing object`` blocks are read once more on their own (``object_...``), which
    tells one object's filaments from another's on a plate that holds both. A reading: nothing
    is compared with an expectation. ``error`` when the file cannot be read."""
    path = Path(path)
    try:
        raw = _read(path)
        events = list(_walk(raw))
        whole = _per_tool(events)
        reading = {'tools_extruding': _extruding(whole), 'per_tool': whole,
                   'change_count': sum(1 for event in events if event[0] == 'change'),
                   'filament_used': _filament_used(raw), 'file_bytes': len(raw),
                   'objects_printed': sorted({str(event[1]) for event in events if event[0] == 'extrude' and event[1]})}
        if object_name is not None:
            keys = {str(object_name).casefold(), str(object_name).rsplit('.', 1)[0].casefold()}
            inside = _per_tool([event for event in events if _printed_in(event, keys)])
            reading.update(object=str(object_name), object_printed=any(_printed_in(event, keys) for event in events),
                           object_tools_extruding=_extruding(inside),
                           object_per_tool={tool: {key: value for key, value in row.items() if key != 'selects'}
                                             for tool, row in inside.items()})
        return reading
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'error': f'{path.name}: unreadable G-code ({exc})'}


def filament_readings(path, imported):
    """Feishu #228, second clause. The G-code prints with the two filaments the saved project
    painted the model with (``imported`` is painted_readings() of that project) and changes
    between them. A tool ``T<n>`` is the (n + 1)-th filament. Nothing raises for a failed
    expectation; ``error`` when the file cannot be read."""
    path = Path(path)
    try:
        raw = _read(path)
        wanted = sorted({value for value in imported.get('filaments', {}).values() if value})
        _need(imported.get('checks'), 'the project readings name no painted filaments')
        events = list(_walk(raw))
        per_tool = _per_tool(events)
        used = _extruding(per_tool)
        changes = [{'line': event[3], 'from': event[1], 'to': event[2], 'after_first_layer': event[4]}
                   for event in events if event[0] == 'change']
        printed = [filament for filament in wanted if filament - 1 in used]
        swaps = [change for change in changes
                 if change['from'] + 1 in wanted and change['to'] + 1 in wanted and change['to'] != change['from']]
        colours = imported.get('filament_colour') or []
        checks = {
            'two_filaments_print': len(wanted) == 2 and len(printed) == 2,
            'change_between_them': bool(swaps),
            'filaments_have_distinct_colours': len({_colour(colours, filament) for filament in wanted}) == 2
            and None not in {_colour(colours, filament) for filament in wanted},
        }
        return {'checks': checks, 'filaments': wanted, 'tools': [filament - 1 for filament in wanted],
                'tools_extruding': used, 'per_tool': per_tool, 'printed_filaments': printed,
                'changes': changes[:12], 'change_count': len(changes), 'changes_between_them': len(swaps),
                'filament_used': _filament_used(raw), 'file_bytes': len(raw)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'checks': {}, 'error': f'{path.name}: unreadable G-code ({exc})'}


def verify_filament_change(path, imported):
    """Raises ValueError naming the first failed check of filament_readings; returns its readings."""
    readings = filament_readings(path, imported)
    if 'error' in readings:
        raise ValueError(readings['error'])
    failed = [name for name, passed in readings['checks'].items() if not passed]
    if failed:
        raise ValueError(f'{Path(path).name}: ' + '; '.join(f'{name} failed' for name in failed)
                         + f'; tools extruding {readings["tools_extruding"]}, filaments {readings["filaments"]}')
    return readings
