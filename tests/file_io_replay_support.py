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
from pathlib import Path
import re
import shutil
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


def _faces(points):
    """Triangles as sorted rounded vertex triples, so that winding, order and indexing do not matter."""
    corners = [tuple(round(value, 6) + 0.0 for value in point) for point in points]
    return tuple(sorted(tuple(sorted(corners[index:index + 3])) for index in range(0, len(corners), 3)))


def _box(points):
    return tuple(round(value, 6) + 0.0 for axis in zip(*points) for value in (min(axis), max(axis)))


def project(raw: bytes) -> dict:
    """What a saved project holds, in world millimetres: application, settings and one entry per build item."""
    files = archive(raw)
    missing = [name for name in (MAIN, SETTINGS, OBJECT_SETTINGS) if name not in files]
    _need(not missing, f'project lacks {", ".join(missing)}')
    main = _xml(files[MAIN], MAIN)
    _need(main.tag == CORE + 'model' and main.get('unit', 'millimeter') == 'millimeter',
          'not a 3MF model in millimetres')
    settings = json.loads(files[SETTINGS].decode('utf-8-sig'))
    _need(isinstance(settings, dict), 'project settings are not an object')
    rows = _xml(files[OBJECT_SETTINGS], OBJECT_SETTINGS)
    names = {row.get('id'): _metadata(row, 'name') for row in rows.findall('object')}
    plates = {}
    for plate in rows.findall('plate'):
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
        objects.append({'name': names.get(item.get('objectid')), 'plate': plates.get(item.get('objectid')),
                        'triangles': _faces(corners), 'box': _box(corners)})
    application = main.find(CORE + 'metadata[@name="Application"]')
    return {'application': application.text if application is not None else None, 'settings': settings,
            'objects': objects}


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


# --- pictures, manifests and copies ----------------------------------------------

def png(raw: bytes) -> dict:
    """Size and tonal range of a picture."""
    from PIL import Image

    try:
        with Image.open(BytesIO(raw)) as image:
            image.load()
            gray = image.convert('L')
            histogram = gray.histogram()
            count = sum(histogram)
            mean = sum(level * n for level, n in enumerate(histogram)) / count
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f'not a readable picture ({type(exc).__name__})') from exc
    spread = sum(n * (level - mean) ** 2 for level, n in enumerate(histogram)) / count
    return {'format': image.format, 'width': gray.width, 'height': gray.height, 'mode': image.mode,
            'gray_levels': sum(1 for n in histogram if n), 'std': round(spread ** 0.5, 3)}


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
