"""Independent readings of harvested files for the file-I/O replays.

Every reader here takes raw bytes and parses them itself. None of them reads
analysis.json or calls the GUI-side oracles, so a replay can hold an oracle's
verdict against a second reading of the same file. `copy_of` stands a
counterexample in for a harvested part on a temporary copy of a run.
"""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
import shutil
import struct
import tempfile
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED
import zlib

CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PROD = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
MAIN = '3D/3dmodel.model'
SETTINGS = 'Metadata/project_settings.config'
OBJECT_SETTINGS = 'Metadata/model_settings.config'
MEMBERS, MEMBER_BYTES, TOTAL_BYTES = 4000, 64 << 20, 512 << 20
UNIT = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
MARKS = ('; HEADER_BLOCK_START', '; HEADER_BLOCK_END', '; EXECUTABLE_BLOCK_START', '; EXECUTABLE_BLOCK_END',
         '; CONFIG_BLOCK_START', '; CONFIG_BLOCK_END')
HEATERS = ('M104', 'M109', 'M140', 'M190')
NUMBER = r'-?(?:\d+\.?\d*|\.\d+)'
WORD = re.compile(r'([XYZE])(' + NUMBER + ')')
S_WORD = re.compile(r'\bS(' + NUMBER + ')')
STATS = re.compile(r'\bSET_PRINT_STATS_INFO\b.*?\bTOTAL_LAYER=(\d+)\b.*?\bCURRENT_LAYER=(-?\d+)\b')
LAYER = re.compile(r';\s*(?:LAYER_CHANGE|CHANGE_LAYER|LAYER:\s*(-?\d+))\s*$')
Z_TAG = re.compile(r';\s*Z:\s*(' + NUMBER + r')\s*$')
PRINTED = re.compile(r';\s*printing object (.*?) id:(\S+) copy (\d+)\s*$')
DECLARED = (('total layer number', re.compile(r';\s*total layer number:\s*(\d+)\s*$')),
            ('total layers count', re.compile(r';\s*total layers count\s*=\s*(\d+)\s*$')),
            ('LAYER_COUNT', re.compile(r';\s*LAYER_COUNT:\s*(\d+)\s*$')))
CONFIG_LINE = re.compile(r';\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s?(.*)$')
DIGEST = re.compile(r'[0-9a-fA-F]{64}')


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _number(text, what):
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{what} is not a number: {text!r}') from exc


def _xml(raw, name):
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f'{name}: not readable XML ({exc})') from exc


# --- project (3MF) ---------------------------------------------------------------

def archive(raw: bytes) -> dict:
    """{member: bytes} of a project. The unpacked size is bounded by what the archive declares."""
    try:
        with ZipFile(BytesIO(raw)) as zipped_:
            infos = zipped_.infolist()
            _need(len(infos) <= MEMBERS and sum(info.file_size for info in infos) <= TOTAL_BYTES
                  and not any(info.flag_bits & 1 for info in infos),
                  'project archive has too many, too large or encrypted members')
            files = {}
            for info in infos:
                _need(info.file_size <= MEMBER_BYTES, f'{info.filename}: member too large to read')
                files[info.filename.lstrip('/')] = zipped_.read(info)
    except (BadZipFile, RuntimeError, zlib.error) as exc:
        raise ValueError(f'not a readable project archive ({exc})') from exc
    return files


def zipped(files: dict) -> bytes:
    """A 3MF holding exactly `files`; tests build projects with it and replays stand a member in."""
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as archive_:
        for name, raw in files.items():
            archive_.writestr(name, raw)
    return out.getvalue()


def _metadata(node, key):
    return next((row.get('value') for row in node.findall('metadata') if row.get('key') == key), None)


def _matrix(text):
    if not text:
        return UNIT
    values = [_number(word, 'transform') for word in text.split()]
    _need(len(values) == 12, 'a transform has twelve numbers')
    return tuple(values)


def _rows(matrix):
    """Rows of the 4x4 form of `m00 m01 m02 m10 ... m30 m31 m32`: the last column is the translation."""
    return [[matrix[3 * column + row] for column in range(3)] + [matrix[9 + row]] for row in range(3)] + [
        [0.0, 0.0, 0.0, 1.0]]


def _compose(outer, inner):
    """The transform that applies `inner` first and `outer` after it."""
    top, bottom = _rows(outer), _rows(inner)
    rows = [[sum(top[row][k] * bottom[k][column] for k in range(4)) for column in range(4)] for row in range(4)]
    return tuple(rows[row][column] for column in range(4) for row in range(3))


def _at(matrix, point):
    rows = _rows(matrix)
    return tuple(sum(rows[row][k] * point[k] for k in range(3)) + rows[row][3] for row in range(3))


def _find(files, models, object_id):
    """(model member, node) of an object, looking through every model of the project."""
    for name in [MAIN] + sorted(n for n in files if n.endswith('.model') and n != MAIN):
        if name not in models:
            models[name] = _xml(files[name], name)
        node = next((obj for obj in models[name].iter(CORE + 'object') if obj.get('id') == object_id), None)
        if node is not None:
            return node
    raise ValueError(f'object {object_id} is not in the project')


def _mesh(node):
    mesh = node.find(CORE + 'mesh')
    _need(mesh is not None and node.find(CORE + 'components') is None,
          f'object {node.get("id")} is neither a mesh nor a group of parts')
    points = [tuple(_number(vertex.get(axis), 'vertex') for axis in 'xyz')
              for vertex in mesh.findall(CORE + 'vertices/' + CORE + 'vertex')]
    faces = [tuple(int(triangle.get(k)) for k in ('v1', 'v2', 'v3'))
             for triangle in mesh.findall(CORE + 'triangles/' + CORE + 'triangle')]
    _need(points and faces, f'object {node.get("id")} has no triangles')
    _need(all(0 <= index < len(points) for face in faces for index in face),
          f'object {node.get("id")}: a triangle names a vertex that is not there')
    return points, faces


def _corners(files, models, object_id, matrix, depth=0):
    """World-space corners of the triangles one object adds to a build item: its mesh, or each of its parts."""
    _need(depth < 3, 'parts are nested more than two levels')
    node = _find(files, models, object_id)
    components = node.find(CORE + 'components')
    if components is None:
        points, faces = _mesh(node)
        return [_at(matrix, points[index]) for face in faces for index in face]
    out = []
    for component in components.findall(CORE + 'component'):
        part = _compose(matrix, _matrix(component.get('transform')))
        out += _corners(files, models, component.get('objectid'), part, depth + 1)
    return out


def faces(corners: list) -> tuple:
    """Triangles as sorted rounded vertex triples, so that winding, order and indexing do not matter."""
    rounded = [tuple(round(value, 6) + 0.0 for value in point) for point in corners]
    return tuple(sorted(tuple(sorted(rounded[index:index + 3])) for index in range(0, len(rounded), 3)))


def box(points: list) -> tuple:
    """(xmin, xmax, ymin, ymax, zmin, zmax) of the points, rounded to a millionth of a millimetre."""
    return tuple(round(value, 6) + 0.0 for axis in zip(*points) for value in (min(axis), max(axis)))


def project(raw: bytes) -> dict:
    """What a saved project holds, in world millimetres: application, settings, the plates and one
    entry per build item with its name, its plate, the file it was imported from and its triangles."""
    files = archive(raw)
    missing = [name for name in (MAIN, SETTINGS, OBJECT_SETTINGS) if name not in files]
    _need(not missing, f'project lacks {", ".join(missing)}')
    main = _xml(files[MAIN], MAIN)
    _need(main.tag == CORE + 'model' and main.get('unit', 'millimeter') == 'millimeter',
          'not a 3MF model in millimetres')
    settings = json.loads(files[SETTINGS].decode('utf-8-sig'))
    _need(isinstance(settings, dict), 'project settings are not an object')
    rows = _xml(files[OBJECT_SETTINGS], OBJECT_SETTINGS)
    rows_of = {row.get('id'): row for row in rows.findall('object')}
    plates, plate_ids = {}, []
    for plate in rows.findall('plate'):
        plate_ids.append(_metadata(plate, 'plater_id'))
        for row in plate.findall('model_instance'):
            _need(_metadata(row, 'instance_id') in (None, '0'),
                  'a project with several instances of one object is not read')
            plates[_metadata(row, 'object_id')] = _metadata(plate, 'plater_id')
    build = main.find(CORE + 'build')
    _need(build is not None, 'project has no build section')
    objects = []
    for item in build.findall(CORE + 'item'):
        corners = _corners(files, {MAIN: main}, item.get('objectid'), _matrix(item.get('transform')))
        _need(corners, f'object {item.get("objectid")} adds no triangles')
        row = rows_of.get(item.get('objectid'))
        part = row.find('part') if row is not None else None
        objects.append({'name': _metadata(row, 'name') if row is not None else None,
                        'plate': plates.get(item.get('objectid')),
                        'source_file': _metadata(part, 'source_file') if part is not None else None,
                        'triangles': faces(corners), 'box': box(corners)})
    application = main.find(CORE + 'metadata[@name="Application"]')
    return {'application': application.text if application is not None else None, 'settings': settings,
            'plates': plate_ids, 'objects': objects}


def with_settings(raw: bytes, edit) -> bytes:
    """The project with its `Metadata/model_settings.config` passed through `edit`, which receives
    the root of that member and may change it in place."""
    files = archive(raw)
    root = _xml(files[OBJECT_SETTINGS], OBJECT_SETTINGS)
    edit(root)
    files[OBJECT_SETTINGS] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return zipped(files)


def with_model(raw: bytes, edit) -> bytes:
    """The project with its `3D/3dmodel.model` passed through `edit`, which receives the root."""
    files = archive(raw)
    root = _xml(files[MAIN], MAIN)
    edit(root)
    files[MAIN] = _serialise(root)
    return zipped(files)


def at_origin(item: dict) -> tuple:
    """An object's triangles moved so that its box starts at the origin: one mesh placed twice over
    compares equal this way, whatever the plate did to it."""
    low = item['box'][0], item['box'][2], item['box'][4]
    return tuple(sorted(tuple(tuple(round(c - o + 0.0, 6) for c, o in zip(corner, low)) for corner in triangle)
                        for triangle in item['triangles']))


def printable_area(settings: dict) -> list | None:
    """The corners of the printable area, from `printable_area` or `bed_shape` ("0.5x1" or "0.5 1")."""
    try:
        corners = [tuple(float(word) for word in re.split(r'[,\s]+|x', text.strip()) if word)
                   for text in settings.get('printable_area') or settings.get('bed_shape') or []]
    except (TypeError, ValueError, AttributeError):
        return None
    return corners if len(corners) >= 3 and all(len(corner) == 2 for corner in corners) else None


def in_polygon(polygon, point) -> bool:
    """Whether a point lies in a convex polygon, whichever way its corners run."""
    turns = [(b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
             for a, b in zip(polygon, polygon[1:] + polygon[:1])]
    return all(value >= -1e-6 for value in turns) or all(value <= 1e-6 for value in turns)


def on_the_bed(settings: dict, item: dict, tol=1e-3) -> bool:
    """Whether an object rests on the bed, its low face at z = 0, and lies inside the printable area."""
    area = printable_area(settings)
    try:
        height = float(settings['printable_height'])
    except (KeyError, TypeError, ValueError):
        return False
    if area is None or abs(item['box'][4]) > tol or item['box'][5] > height + tol:
        return False
    return all(in_polygon(area, (x, y)) for x in item['box'][:2] for y in item['box'][2:4])


# --- G-code ----------------------------------------------------------------------

def head(code):
    return code.split(None, 1)[0].upper() if code else ''


def s_value(code):
    found = S_WORD.search(code)
    return float(found.group(1)) if found else None


def heat_on(code):
    return head(code) in HEATERS and s_value(code) is not None and s_value(code) > 0


def heat_off(code):
    return head(code) in HEATERS and s_value(code) == 0


def fan_off(code):
    return head(code) == 'M107' or (head(code) == 'M106' and s_value(code) == 0)


def _walk(lines, codes, starts, numbered):
    """One pass over the moves: each layer's Z, number and extruding moves, the printed object names,
    the line of the last extruding move and the box those moves cover."""
    layers = [{'line': index + 1, 'z': None, 'extruding': 0,
               'number': int(LAYER.fullmatch(lines[index].strip()).group(1)) if numbered else None}
              for index in starts]
    region, totals, printed = -1, set(), set()
    absolute, relative_e = True, False
    at, e_at = [0.0, 0.0, 0.0], 0.0
    xs, ys, last = [], [], None
    for index, code in enumerate(codes):
        if region + 1 < len(starts) and index == starts[region + 1]:
            region += 1
        current = layers[region] if region >= 0 else None
        line = lines[index].strip()
        stats = STATS.search(code)
        if stats:
            totals.add(int(stats.group(1)))
            if current is not None and current['number'] is None:
                current['number'] = int(stats.group(2))
        tag = Z_TAG.fullmatch(line)
        if tag and current is not None and current['z'] is None:
            current['z'] = float(tag.group(1))
        name = PRINTED.fullmatch(line)
        if name:
            printed.add(name.group(1))
        command = head(code)
        if command == 'M82':
            relative_e = False
        elif command == 'M83':
            relative_e = True
        elif command == 'G90':
            absolute = True
        elif command == 'G91':
            absolute = False
        words = dict(WORD.findall(code))
        if command not in ('G0', 'G1', 'G2', 'G3', 'G92') or not words:
            continue
        if command == 'G92':
            for axis, value in words.items():
                if axis == 'E':
                    e_at = float(value)
                else:
                    at['XYZ'.index(axis)] = float(value)
            continue
        e_delta = None
        for axis, value in words.items():
            value = float(value)
            if axis == 'E':
                e_delta = value if relative_e else value - e_at
                e_at = e_at + value if relative_e else value
            else:
                slot = 'XYZ'.index(axis)
                at[slot] = at[slot] + value if not absolute else value
        if current is not None and e_delta is not None and e_delta > 0 and ('X' in words or 'Y' in words):
            current['extruding'] += 1
            xs.append(at[0])
            ys.append(at[1])
            last = index
    return layers, sorted(totals), sorted(printed), last, (min(xs), min(ys), max(xs), max(ys)) if xs else None


def gcode(raw: bytes) -> dict:
    """Blocks, layers, the commands around them, trailer notes and configuration of a G-code file."""
    text = raw.decode('utf-8', errors='replace')
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    codes = [line.strip().partition(';')[0].strip() for line in lines]
    marks = {name: [index + 1 for index, line in enumerate(lines) if line.strip() == name] for name in MARKS}
    starts = [index for index, line in enumerate(lines) if LAYER.fullmatch(line.strip())]
    numbered = [index for index in starts if LAYER.fullmatch(lines[index].strip()).group(1) is not None]
    if numbered:
        starts = numbered
    layers, totals, printed, last, box = _walk(lines, codes, starts, bool(numbered))
    single = lambda name: marks[name][0] - 1 if len(marks[name]) == 1 else None  # noqa: E731
    exec_start, exec_end, config_start, config_end = (single(name) for name in MARKS[2:])
    lo = exec_start + 1 if exec_start is not None else 0
    hi = exec_end if exec_end is not None else len(lines)
    stop = starts[0] if starts else hi
    declared = {label: sorted({int(match.group(1)) for line in lines if (match := pattern.fullmatch(line.strip()))})
                for label, pattern in DECLARED}
    declared = {label: values for label, values in declared.items() if values}
    if totals:
        declared['TOTAL_LAYER='] = totals
    config, config_lines = {}, 0
    if config_start is not None and config_end is not None and config_start < config_end:
        for line in lines[config_start + 1:config_end]:
            match = CONFIG_LINE.fullmatch(line.strip())
            if match:
                config_lines += 1
                config.setdefault(match.group(1), []).append(match.group(2).strip())
    generator = next((line.split(';', 1)[1].strip()[len('generated by '):] for line in lines[:16]
                      if line.strip().startswith('; generated by ')), None)
    return {
        'bytes': len(raw), 'lines': len(lines), 'replacement_chars': text.count('\ufffd'),
        'markers': marks, 'generator': generator, 'layer_marker': ';LAYER:' if numbered else ';LAYER_CHANGE',
        'layers': layers, 'layer_count': len(layers), 'z': [layer['z'] for layer in layers],
        'layer_numbers': [layer['number'] for layer in layers],
        'layers_without_extrusion': sum(1 for layer in layers if not layer['extruding']),
        'extrusion_box': box, 'object_names': printed, 'declared': declared,
        'last_extruding_line': None if last is None else last + 1,
        'start_commands': [code for code in codes[lo:stop] if code],
        'after_last_extrusion': [code for code in codes[last + 1:hi] if code] if last is not None else [],
        'trailer': [line.strip() for line in lines[hi + 1:config_start if config_start is not None else len(lines)] if line.strip()],
        'config': config, 'config_lines': config_lines,
        'after_config': [line.strip() for line in lines[config_end + 1:] if line.strip()] if config_end is not None else None,
    }


# --- binary STL and project stand-ins --------------------------------------------

STL_RECORD = struct.Struct('<12fH')
ORDERS = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))


def stl(raw: bytes) -> tuple:
    """(header, triangles) of a binary STL: every triangle as its three (x, y, z) corners."""
    _need(len(raw) >= 84, 'STL is shorter than a header and a triangle count')
    count = struct.unpack_from('<I', raw, 80)[0]
    _need(len(raw) == 84 + STL_RECORD.size * count,
          f'not a whole binary STL: {count} triangles declared, {len(raw)} bytes held')
    return raw[:80], [(record[3:6], record[6:9], record[9:12]) for record in STL_RECORD.iter_unpack(raw[84:])]


def stl_bytes(header: bytes, triangles) -> bytes:
    """A binary STL from triangles; the normals and attributes are left zero."""
    rows = [header, struct.pack('<I', len(triangles))]
    rows += [STL_RECORD.pack(0.0, 0.0, 0.0, *triangle[0], *triangle[1], *triangle[2], 0)
             for triangle in triangles]
    return b''.join(rows)


def _gap(triangle, other):
    """Smallest largest-coordinate distance over the ways to pair the corners of two triangles."""
    return min(max(abs(a - b) for first, second in zip(order, other) for a, b in zip(first, second))
               for order in ((triangle[i], triangle[j], triangle[k]) for i, j, k in ORDERS))


def _cell(point, size):
    return tuple(math.floor(value / size) for value in point)


def paired(expected, actual, tol=1e-4, cell=1e-3):
    """Pair every expected triangle with one STL triangle of the same corners within `tol`, whatever
    the winding and the order. Returns (the STL triangle's number for each expected triangle, or None,
    and the largest coordinate distance among the pairs)."""
    _need(tol < cell, 'the search cell must be wider than the tolerance')
    lookup = {}
    for number, triangle in enumerate(actual):
        for corner in triangle:
            lookup.setdefault(_cell(corner, cell), set()).add(number)
    pairs, used, worst = [], set(), 0.0
    for triangle in expected:
        # the matching STL triangle has a corner within tol of this one's smallest corner
        x, y, z = _cell(min(triangle), cell)
        candidates = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    candidates |= lookup.get((x + dx, y + dy, z + dz), set())
        best = None
        for number in candidates - used:
            gap = _gap(triangle, actual[number])
            if gap <= tol and (best is None or gap < best[1]):
                best = number, gap
        if best is None:
            pairs.append(None)
        else:
            used.add(best[0])
            pairs.append(best[0])
            worst = max(worst, best[1])
    return pairs, worst


def moved_project(raw: bytes, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> bytes:
    """The project with every build item shifted by (dx, dy, dz): the same objects, somewhere else."""
    files = archive(raw)
    model = _xml(files[MAIN], MAIN)
    for item in model.iter(CORE + 'item'):
        values = list(_matrix(item.get('transform')))
        values[9:12] = [values[9] + dx, values[10] + dy, values[11] + dz]
        item.set('transform', ' '.join(f'{value:.9g}' for value in values))
    files[MAIN] = _serialise(model)
    return zipped(files)


def _serialise(model) -> bytes:
    """A model member as the application keeps it: the core namespace is the default one."""
    ET.register_namespace('', CORE[1:-1])
    ET.register_namespace('p', PROD[1:-1])
    return ET.tostring(model, encoding='utf-8', xml_declaration=True)


def compose(outer: tuple, inner: tuple) -> tuple:
    """The transform that applies `inner` first and `outer` after it."""
    return _compose(outer, inner)


def shift(x: float, y: float, z: float) -> tuple:
    """A pure translation."""
    return UNIT[:9] + (x, y, z)


def turn(degrees: float) -> tuple:
    """A rotation about the vertical axis through the origin."""
    cosine, sine = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (cosine, sine, 0.0, -sine, cosine, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def grow(factor: float) -> tuple:
    """A scaling about the origin."""
    return (factor, 0.0, 0.0, 0.0, factor, 0.0, 0.0, 0.0, factor, 0.0, 0.0, 0.0)


def _item(files):
    """(model, its only build item) of a project with one object."""
    model = _xml(files[MAIN], MAIN)
    items = model.findall(f'{CORE}build/{CORE}item')
    _need(len(items) == 1, f'expected a project with one object, found {len(items)}')
    return model, items[0]


def item_transform(raw: bytes) -> tuple:
    """The twelve numbers of the transform of the only build item."""
    return _matrix(_item(archive(raw))[1].get('transform'))


def with_item_transform(raw: bytes, matrix) -> bytes:
    """The project with the transform of its only build item replaced by `matrix` (twelve numbers).

    What the plate operations leave in a saved project can be stood in this way: a move is a
    translation composed after the old transform, a turn a rotation about the object's centre."""
    _need(len(matrix) == 12, 'a transform has twelve numbers')
    files = archive(raw)
    model, item = _item(files)
    item.set('transform', ' '.join(f'{value:.9g}' for value in matrix))
    files[MAIN] = _serialise(model)
    return zipped(files)


# --- pictures, manifests and copies ----------------------------------------------

def png(raw: bytes) -> dict:
    """Size and tonal range of a picture. For one with an alpha channel, `solid` describes the fully
    opaque pixels: their share, their box and whether it stays inside the picture, and how many colours
    they show. A render has a bounded body of them; a blank or an opaque background has none or all."""
    import numpy as np
    from PIL import Image

    try:
        with Image.open(BytesIO(raw)) as image:
            image.load()
            gray = image.convert('L')
            histogram = gray.histogram()
            count = sum(histogram)
            mean = sum(level * n for level, n in enumerate(histogram)) / count
            solid = None
            if 'A' in image.getbands():
                pixels = np.asarray(image.convert('RGBA'))
                body = pixels[..., 3] == 255
                rows, columns = np.nonzero(body)
                height, width = body.shape
                solid = {'fraction': float(body.mean()),
                         'inside': bool(rows.size and 0 < columns.min() and columns.max() + 1 < width
                                         and 0 < rows.min() and rows.max() + 1 < height),
                         'box': None if not rows.size else [int(columns.min()), int(rows.min()),
                                                           int(columns.max()) + 1, int(rows.max()) + 1],
                         'colors': int(np.unique(pixels[body][:, :3], axis=0).shape[0]) if rows.size else 0}
            facts = {'format': image.format, 'width': gray.width, 'height': gray.height, 'mode': image.mode,
                     'gray_levels': sum(1 for n in histogram if n), 'solid': solid}
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f'not a readable picture ({type(exc).__name__})') from exc
    spread = sum(n * (level - mean) ** 2 for level, n in enumerate(histogram)) / count
    return dict(facts, std=round(spread ** 0.5, 3))


def blank_png(width: int, height: int) -> bytes:
    """A fully transparent RGBA picture of the given size, written without Pillow."""
    rows = b''.join(b'\x00' + bytes(4 * width) for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(rows))
            + chunk(b'IEND', b''))


def screenshots(raw: dict, recorded, names: tuple, dialog: str) -> dict:
    """Two readings of retained screenshots: each is a picture with something in it, and the one of
    the dialog has the size the record gives."""
    pictures = {}
    for part in names:
        try:
            pictures[part] = png(raw[part])
        except ValueError:
            pictures[part] = None
    size = pictures[dialog] or {}
    shown = recorded.get('dialog_image') if isinstance(recorded, dict) else None
    return {
        'screenshots_are_pictures': all(
            picture and picture['format'] == 'PNG' and picture['width'] >= 640 and picture['height'] >= 400
            and picture['gray_levels'] >= 32 and picture['std'] >= 5 for picture in pictures.values()),
        'dialog_picture_matches_record': shown == {
            'width_px': size.get('width'), 'height_px': size.get('height')},
    }


def as_recorded(value):
    """A reading as the GUI's analysis.json holds it: tuples and other sequences become lists."""
    return json.loads(json.dumps(value))


def manifest(directory, prefix) -> list:
    """The run's `<prefix>-object_artifacts.json`, checked for shape: a name, a byte count and a digest per part."""
    path = Path(directory) / f'{prefix}-object_artifacts.json'
    entries = json.loads(path.read_text(encoding='utf-8-sig'))
    _need(isinstance(entries, list) and entries, f'{path.name}: expected a list of parts')
    for entry in entries:
        _need(isinstance(entry, dict) and isinstance(entry.get('part'), str) and entry['part']
              and type(entry.get('bytes')) is int and entry['bytes'] >= 0
              and isinstance(entry.get('sha256'), str) and DIGEST.fullmatch(entry['sha256']),
              f'{path.name}: a part needs a name, a byte count and a SHA-256')
    _need(len({entry['part'] for entry in entries}) == len(entries), f'{path.name}: a part is listed twice')
    return entries


@contextmanager
def copy_of(directory, prefix, replace=None, rename=None, keep_manifest=True):
    """A temporary copy of a run's `<prefix>-*` files in which some parts differ.

    `replace` maps a part to the bytes that stand in for it and `rename` maps a part to the name it is
    stored under. The manifest follows both unless `keep_manifest` is False, which is the collector that
    recorded one file and kept another."""
    replace, rename = dict(replace or {}), dict(rename or {})
    source = Path(directory)
    name = f'{prefix}-object_artifacts.json'
    entries = json.loads((source / name).read_text(encoding='utf-8-sig'))
    with tempfile.TemporaryDirectory(prefix='replay-') as temporary:
        work = Path(temporary)
        for path in source.glob(f'{prefix}-*'):
            if path.name != name:
                shutil.copyfile(path, work / path.name)
        stored = {}
        for entry in entries:
            part = entry['part']
            original = work / f'{prefix}-{part}'
            if part not in replace and not original.is_file():
                continue
            raw = replace.get(part, original.read_bytes())
            stored[part] = raw
            if part in rename and part not in replace:
                original.unlink()
            target = work / f'{prefix}-{rename.get(part, part)}'
            if target.is_file():
                target.unlink()
            target.write_bytes(raw)
            entry['part'] = rename.get(part, part)      # the manifest lists the part as it is stored now
        if keep_manifest:
            for entry in entries:
                if entry['part'] in stored:
                    raw = stored[entry['part']]
                    entry.update(bytes=len(raw), sha256=sha256(raw).hexdigest())
        (work / name).write_text(json.dumps(entries, indent=1), encoding='utf-8')
        yield work, prefix


def refused(read, positive, directory, prefix, replace=None, rename=None, keep_manifest=True) -> bool:
    """True when the run with a part stood in no longer passes every reading named in `positive`.
    `read(directory, prefix)` returns the readings, its checks first; a ValueError counts as refusal."""
    try:
        with copy_of(directory, prefix, replace, rename, keep_manifest) as (folder, altered):
            checks = read(folder, altered)[0]
    except ValueError:
        return True
    return not all(checks[key] for key in positive)


def flattering(raw: bytes, clauses, **changes) -> bytes:
    """analysis.json as a forger would write it: every clause PASS and no gaps."""
    analysis = json.loads(raw.decode('utf-8-sig'))
    analysis['results'] = {clause: 'PASS' for clause in clauses}
    analysis['expectation_gaps'] = {clause: [] for clause in clauses}
    analysis.update(changes)
    return json.dumps(analysis, indent=2, ensure_ascii=False).encode('utf-8')


def work_directories(text: str, tag: str) -> list:
    """The directories a case log says it retained: every `[tag] retained work directory: <path>` line."""
    return re.findall(r'^\[' + re.escape(tag) + r'\] retained work directory: (.+?)[ \t\r]*$', text, re.M)
