"""Offline checks for the Feishu export rows #236, #233 and #234.

Every function here reads what the application put on disk; nothing drives
the GUI. The G-code reading rules were derived from the 315 real exports
already harvested from Snapmaker Orca 2.4.0 with Snapmaker U1 (0.4 nozzle)
presets (``artifacts/windows_mcp_harvest/*/exports/0001.gcode``) and from the
guest probe ``runs/sliceprobe-b958af2b`` (standard cube, 135 layers):

* No real export carries ``;LAYER_COUNT:`` or ``;LAYER:n``. A layer starts
  with ``;LAYER_CHANGE``, followed by ``;Z:`` and ``;HEIGHT:``.
* The declared layer totals are the header line ``; total layer number: N``
  (equal to the number of ``;LAYER_CHANGE`` lines in 315/315), the trailer
  note ``; total layers count = N`` and ``TOTAL_LAYER=N`` of every
  ``SET_PRINT_STATS_INFO`` line (313/315; the two spiral-vase exports of that
  harvest carry one layer more than they declare).
* Layer numbers are the ``CURRENT_LAYER=n`` of each layer block, 1..N.
* Start G-code (before the first layer): ``PRINT_START``, a heater command
  with a positive ``S`` (``M104``/``M109``/``M140``/``M190``) and ``G28``.
* End G-code (after the last layer starts): ``PRINT_END`` and a fan-off
  command (``M106 S0`` / ``M107``). No U1 export switches a heater off in
  the end G-code (0/315): that happens inside the printer's ``PRINT_END``
  macro, so a heater-off command counts as end evidence but is not demanded.
* Trailer notes between the executable and the config block: ``; filament
  used`` and ``; estimated printing time``.
* The material lies where the plate's objects are: gcode_footprint() measures
  every extruding move of the layers against the objects of the saved project
  (see the section of the same name for the tolerances).

Scope: one plate printed layer by layer. An export that prints object by
object restarts Z for the second object and is rejected by the Z check; a
spiral-vase export whose declared totals disagree is rejected too. Both are
outside the rows these checks serve (single cube, 0.20 mm Standard). Another
machine preset needs its own derivation before these rules are applied.
"""
from bisect import bisect_right
from hashlib import md5, sha256
from io import BytesIO
from itertools import permutations
import json
import math
from pathlib import Path
import re
import struct
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from harness.model_move_pilot import bounds, stl_mesh
from part_attachment_oracle import _read
from plate_layout_oracle import _pairs, _project
from plate_reserve_oracle import read_project

HEADER = ('header', '; HEADER_BLOCK_START', '; HEADER_BLOCK_END')
EXECUTABLE = ('executable', '; EXECUTABLE_BLOCK_START', '; EXECUTABLE_BLOCK_END')
CONFIG = ('config', '; CONFIG_BLOCK_START', '; CONFIG_BLOCK_END')
BLOCKS = (HEADER, EXECUTABLE, CONFIG)
NUMBER = r'-?(?:\d+\.?\d*|\.\d+)'
LAYER_A = re.compile(r'^;\s*(?:LAYER_CHANGE|CHANGE_LAYER)\s*$')
LAYER_B = re.compile(r'^;\s*LAYER:\s*(\d+)\s*$')
DECLARED = ((';LAYER_COUNT:', re.compile(r'^;\s*LAYER_COUNT:\s*(\d+)\s*$')),
            ('; total layer number', re.compile(r'^;\s*total layer number:\s*(\d+)\s*$')),
            ('; total layers count', re.compile(r'^;\s*total layers count\s*=\s*(\d+)\s*$')))
STATS = re.compile(r'\bSET_PRINT_STATS_INFO\b[^;]*?\bTOTAL_LAYER=(\d+)\b[^;]*?\bCURRENT_LAYER=(-?\d+)\b')
Z_TAG = re.compile(r'^;\s*Z:\s*(' + NUMBER + r')\s*$')
MAX_Z = re.compile(r'^;\s*max_z(?:Height|_height):\s*(' + NUMBER + r')\s*$')
MOTION = re.compile(r'^G([0123])(?![0-9])')
WORD = re.compile(r'\b([XYZEF])(' + NUMBER + r')')
S_WORD = re.compile(r'\bS(' + NUMBER + r')')
CONFIG_LINE = re.compile(r'^;\s*[A-Za-z_][A-Za-z0-9_]*\s*=')
HEATERS = ('M104', 'M109', 'M140', 'M190')
TRAILER_NOTES = (('filament_used', '; filament used'), ('estimated_time', '; estimated printing time'))
MERGED_VERTEX_TOL_MM = 0.0001
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PLATE_GCODE = re.compile(r'^Metadata/plate_(\d+)\.gcode$')


def _head(code):
    return code.split(None, 1)[0].upper() if code else ''


def _s_value(code):
    found = S_WORD.search(code)
    return float(found.group(1)) if found else None


def _heat_on(code):
    temperature = _s_value(code)
    return _head(code) in HEATERS and temperature is not None and temperature > 0


def _heater_off(code):
    return _head(code) in HEATERS and _s_value(code) == 0


def _fan_off(code):
    return _head(code) == 'M107' or (_head(code) == 'M106' and _s_value(code) == 0)


# Each family is read in its own region: any member counts as that region's evidence.
START_FAMILY = (('machine_start_macro', lambda code: _head(code) == 'PRINT_START'),
                ('heat_on', _heat_on), ('home', lambda code: _head(code) == 'G28'))
END_FAMILY = (('machine_end_macro', lambda code: _head(code) == 'PRINT_END'),
              ('fan_off', _fan_off), ('heater_off', _heater_off))


def _lines(raw):
    """(text lines, code halves) of a G-code file: the comment of a line is dropped."""
    lines = raw.decode('utf-8', errors='replace').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    codes = []
    for line in lines:
        stripped = line.strip()
        codes.append('' if not stripped or stripped[0] == ';' else stripped.partition(';')[0].strip())
    return lines, codes


def _block_positions(lines):
    """{block: (line of its START marker, line of its END marker)}, None when absent."""
    where = {}
    for name, start, end in BLOCKS:
        first = next((i for i, line in enumerate(lines) if line.strip() == start), None)
        last = next((i for i, line in enumerate(lines) if line.strip() == end), None)
        where[name] = first, last
    return where


def _evidence(codes, family):
    """{class: the first commands of that class} among one region's code halves."""
    found = {name: [] for name, _predicate in family}
    for code in codes:
        for name, predicate in family:
            if code and len(found[name]) < 3 and predicate(code):
                found[name].append(code)
    return found


def _gcode_facts(raw, name):
    lines, codes = _lines(raw)
    where = _block_positions(lines)
    exec_start, exec_end = where['executable']
    lo = exec_start + 1 if exec_start is not None else 0
    hi = exec_end if exec_end is not None else len(lines)
    starts = [i for i in range(lo, hi) if LAYER_A.match(lines[i].strip())]
    marker = ';LAYER_CHANGE'
    if not starts and any(LAYER_B.match(lines[i].strip()) for i in range(lo, hi)):
        starts = [i for i in range(lo, hi) if LAYER_B.match(lines[i].strip())]
        marker = ';LAYER:'
    layers = [{'line': i, 'number': None, 'z': None, 'motion': 0, 'extruding': 0} for i in starts]
    start_codes, end_codes, totals = [], [], set()
    absolute_e, e_position = True, 0.0
    for i in range(lo, hi):
        code, line = codes[i], lines[i].strip()
        head = _head(code)
        region = bisect_right(starts, i) - 1
        if region < 0:
            start_codes.append(code)
        elif region == len(layers) - 1:
            end_codes.append(code)
        if head == 'M82':
            absolute_e = True
            continue
        if head == 'M83':
            absolute_e = False
            continue
        stats = STATS.search(code)
        if stats:
            totals.add(int(stats.group(1)))
        if region < 0:
            continue
        layer = layers[region]
        if i == layer['line'] and marker == ';LAYER:':
            layer['number'] = int(LAYER_B.match(line).group(1))
        tag = Z_TAG.match(line)
        if tag and layer['z'] is None:
            layer['z'] = float(tag.group(1))
        if stats and marker != ';LAYER:' and layer['number'] is None:
            layer['number'] = int(stats.group(2))
        if not MOTION.match(code):
            continue
        layer['motion'] += 1
        words = {key: float(value) for key, value in WORD.findall(code)}
        if head == 'G92':
            if 'E' in words:
                e_position = words['E']
            continue
        if 'E' in words:
            delta = words['E'] - e_position if absolute_e else words['E']
            e_position = words['E']
            layer['extruding'] += delta > 0 and ('X' in words or 'Y' in words)
        if layer['z'] is None and 'Z' in words:
            layer['z'] = words['Z']

    header_start, header_end = where['header']
    config_start, config_end = where['config']
    first_layer = layers[0]['line'] if layers else None
    config_lines = (sum(1 for line in lines[config_start:config_end] if CONFIG_LINE.match(line))
                    if config_start is not None and config_end is not None else 0)
    trailer_lo = exec_end + 1 if exec_end is not None else len(lines)
    trailer_hi = config_start if config_start is not None else len(lines)
    notes = {key: next((line for line in lines[trailer_lo:trailer_hi] if line.startswith(prefix)), None)
             for key, prefix in TRAILER_NOTES}
    declared = {}
    for label, pattern in DECLARED:
        values = sorted({int(match.group(1)) for line in lines if (match := pattern.match(line.strip()))})
        if values:
            declared[label] = values
    if totals:
        declared['TOTAL_LAYER='] = sorted(totals)
    numbers = [layer['number'] for layer in layers]
    heights = [layer['z'] for layer in layers]
    numbered = bool(numbers) and all(value is not None for value in numbers)
    measured = bool(heights) and all(value is not None for value in heights)
    max_z = next((MAX_Z.match(line.strip()) for line in lines[:16] if MAX_Z.match(line.strip())), None)
    return {
        'file_name': name,
        'extension': Path(name).suffix.lower(),
        'file_bytes': len(raw),
        'line_count': len(lines),
        'sha256': sha256(raw).hexdigest(),
        'generator': next((line[1:].strip() for line in lines[:16] if line.startswith('; generated by')), None),
        'max_z_height': float(max_z.group(1)) if max_z else None,
        'blocks': {block: [a + 1 if a is not None else None, b + 1 if b is not None else None]
                   for block, (a, b) in where.items()},
        'has_header_block': _ordered(where['header']),
        'has_config_block': _ordered(where['config']) and config_lines > 0,
        'config_lines': config_lines,
        'executable_order': (_ordered(where['header']) and _ordered(where['executable'])
                             and _ordered(where['config']) and header_end < exec_start
                             and (first_layer is None or exec_start < first_layer)
                             and (first_layer is not None or exec_start < exec_end)
                             and (first_layer is None or first_layer < exec_end) and exec_end < config_start),
        'start_gcode': {'first_line': lo + 1,
                        'last_line': first_layer if first_layer is not None else hi,
                        'command_count': sum(1 for code in start_codes if code),
                        'evidence': _evidence(start_codes, START_FAMILY)},
        'end_gcode': {'first_line': layers[-1]['line'] + 1 if layers else lo + 1, 'last_line': hi,
                      'evidence': _evidence(end_codes, END_FAMILY),
                      'tail': [code for code in end_codes if code][-6:]},
        'trailer_notes': notes,
        'trailer_notes_present': all(notes.values()),
        'start_gcode_present': any(_evidence(start_codes, START_FAMILY).values()),
        'end_gcode_present': any(_evidence(end_codes, END_FAMILY).values()),
        'layer_marker': marker if layers else None,
        'layer_count': len(layers),
        'layer_count_tag': (declared[';LAYER_COUNT:'][0] if declared.get(';LAYER_COUNT:') and len(declared[';LAYER_COUNT:']) == 1
                            else declared.get(';LAYER_COUNT:')),
        'declared_layer_counts': declared,
        'layer_numbering': 'CURRENT_LAYER' if numbered and marker != ';LAYER:' else (';LAYER:' if numbered else None),
        'layer_numbers': numbers,
        'first_layer_number': numbers[0] if numbers else None,
        'last_layer_number': numbers[-1] if numbers else None,
        'layer_numbers_consecutive': numbered and all(b == a + 1 for a, b in zip(numbers, numbers[1:])),
        'layer_z': heights,
        'z_first': heights[0] if heights else None,
        'z_last': heights[-1] if heights else None,
        'z_monotonic_nondecreasing': measured and all(b >= a for a, b in zip(heights, heights[1:])),
        'layers_with_motion': sum(1 for layer in layers if layer['motion']),
        'layers_printed': sum(1 for layer in layers if layer['extruding']),
        'extruding_moves': sum(layer['extruding'] for layer in layers),
    }


def _ordered(position):
    start, end = position
    return start is not None and end is not None and start < end


def gcode_export_facts(path):
    """What a G-code file contains, layer by layer. Nothing here judges."""
    path = Path(path)
    return _gcode_facts(path.read_bytes(), path.name)


def gcode_checks(facts):
    """Ordered {check: passed}; ``verify_gcode_export`` raises on the first failure."""
    count = facts['layer_count']
    return {
        'gcode_extension': facts['extension'] == '.gcode',
        'non_empty': facts['file_bytes'] > 0 and facts['line_count'] > 0,
        'header_block': facts['has_header_block'],
        'config_block': facts['has_config_block'],
        'executable_block': facts['executable_order'],
        'start_gcode': facts['start_gcode_present'],
        'end_gcode': facts['end_gcode_present'],
        'trailer_notes': facts['trailer_notes_present'],
        'layers_present': count > 0,
        'declared_layer_count': bool(facts['declared_layer_counts']) and all(
            values == [count] for values in facts['declared_layer_counts'].values()),
        'layer_numbers_consecutive': facts['layer_numbers_consecutive'],
        'layer_z_monotonic': facts['z_monotonic_nondecreasing'],
        'layers_printed': count > 0 and facts['layers_printed'] == count,
        'extrusion_present': facts['extruding_moves'] > 0,
    }


def _first_gap(values, holds):
    for index, (a, b) in enumerate(zip(values, values[1:]), 1):
        if not holds(a, b):
            return f'layers {index}->{index + 1} read {a} then {b}'
    return ''


def _why(check, facts):
    numbers, heights = facts['layer_numbers'], facts['layer_z']
    missing = lambda values: f'{sum(value is None for value in values)} of {len(values)} without a reading'  # noqa: E731
    reasons = {
        'gcode_extension': f'extension {facts["extension"]!r} is not .gcode',
        'non_empty': f'{facts["file_bytes"]} bytes, {facts["line_count"]} lines',
        'header_block': f'HEADER block markers on lines {facts["blocks"]["header"]}',
        'config_block': f'CONFIG block markers on lines {facts["blocks"]["config"]}, '
                        f'{facts["config_lines"]} setting lines',
        'executable_block': f'block markers on lines {facts["blocks"]} with '
                            f'{facts["layer_count"]} layers',
        'start_gcode': f'before the first layer the evidence is {facts["start_gcode"]["evidence"]}',
        'end_gcode': f'after the last layer the evidence is {facts["end_gcode"]["evidence"]}',
        'trailer_notes': f'trailer notes {facts["trailer_notes"]}',
        'layers_present': f'{facts["layer_count"]} layer markers ({facts["layer_marker"]})',
        'declared_layer_count': f'{facts["layer_count"]} layer markers but declared totals '
                                f'{facts["declared_layer_counts"]}',
        'layer_numbers_consecutive': ('no layer carries a number' if not numbers else
                                      f'{missing(numbers)}; {_first_gap(numbers, lambda a, b: a is not None and b == a + 1)}'),
        'layer_z_monotonic': 'no layer carries a Z' if not heights else
                             f'{missing(heights)}; {_first_gap(heights, lambda a, b: a is not None and b is not None and b >= a)}',
        'layers_printed': f'{facts["layer_count"] - facts["layers_printed"]} layers without an extruding move',
        'extrusion_present': 'no move extrudes while travelling in XY',
    }
    return reasons[check]


def verify_gcode_export(path):
    """Feishu #236: a printable G-code file with start and end G-code and continuous layers.
    Raises ValueError naming the first failed check; returns the readings."""
    path = Path(path)
    try:
        facts = gcode_export_facts(path)
    except OSError as exc:
        raise ValueError(_reason(path, exc) + ': unreadable G-code') from exc
    failed = [check for check, passed in gcode_checks(facts).items() if not passed]
    if failed:
        raise ValueError(f'{path.name}: ' + '; '.join(f'{check}: {_why(check, facts)}' for check in failed))
    return facts


GCODE_EXPECTATIONS = (
    ('生成 .gcode 文件', ('extension', 'gcode_extension', 'extrusion_on_objects')),
    ('含起始/结束 G-code', ('header_block', 'config_block', 'executable_block', 'start_gcode', 'end_gcode',
                           'trailer_notes')),
    ('无空文件', ('non_empty', 'layers_present', 'extrusion_present', 'layers_printed')),
    ('层命令连续', ('declared_layer_count', 'layer_numbers_consecutive', 'layer_z_monotonic')),
)


def gcode_expectation_gaps(facts, extension, footprint=None):
    """{clause of the Feishu #236 expectation: [names of its failed checks]}.

    `extension` is the one the application appended when saving; `facts` comes
    from the file as it landed. `footprint` is gcode_footprint() of the same
    file against the saved plate: its failed checks fail the first clause, as
    a file that prints somewhere else is not this plate's G-code. Without it
    the material is not located and nothing extra is judged."""
    checks = dict(gcode_checks(facts), extension=extension == '.gcode',
                  extrusion_on_objects=footprint is None or all(footprint['checks'].values()))
    return {clause: [name for name in names if not checks[name]] for clause, names in GCODE_EXPECTATIONS}


# --- merged STL (#233) --------------------------------------------------------

def _triangles(points, faces):
    vertices = [tuple(float(value) for value in point) for point in points]
    return [tuple(sorted(vertices[i] for i in face)) for face in faces]


def _cell(point, size):
    return tuple(math.floor(value / size) for value in point)


def _index(triangles, size):
    cells = {}
    for number, triangle in enumerate(triangles):
        for cell in {_cell(vertex, size) for vertex in triangle}:
            cells.setdefault(cell, []).append(number)
    return cells


def _near(cells, point, size):
    x, y, z = _cell(point, size)
    found = set()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                found.update(cells.get((x + dx, y + dy, z + dz), ()))
    return found


def _deviation(triangle, candidate, tol):
    """Largest coordinate distance under the best vertex pairing; None beyond tol."""
    def error(order):
        return max(abs(a - b) for first, second in zip(order, triangle) for a, b in zip(first, second))
    best = error(candidate)
    if best <= tol:
        return best
    for order in permutations(candidate):
        value = error(order)
        if value <= tol and (best > tol or value < best):
            best = value
    return best if best <= tol else None


def _consume(triangles, actual, cells, used, tol, size):
    """Pair every expected triangle with one unused STL triangle.
    Returns (STL triangle numbers, largest deviation) or (None, how many paired)."""
    pairs, deviation = [], 0.0
    for triangle in triangles:
        candidates = set.intersection(*(_near(cells, vertex, size) for vertex in triangle))
        best = None
        for number in candidates:
            if number in used:
                continue
            error = _deviation(triangle, actual[number], tol)
            if error is not None and (best is None or error < best[1]):
                best = number, error
        if best is None:
            return None, len(pairs)
        used.add(best[0])
        pairs.append(best[0])
        deviation = max(deviation, best[1])
    return pairs, deviation


def verify_merged_stl(project, exported):
    """Feishu #233: one STL holding every plate object's triangles at its plate position.
    Raises ValueError when an object is missing, moved, replaced or duplicated."""
    project, exported = Path(project), Path(exported)
    plates, instances = read_project(project)
    if len(plates) != 1:
        raise ValueError(f'expected one plate in {project.name}, found {len(plates)}')
    if len(instances) < 2:
        raise ValueError(f'expected at least two objects on the plate, found {len(instances)}')
    try:
        raw = _read(exported)
        points, faces = stl_mesh(raw)
    except (OSError, ValueError) as exc:
        raise ValueError(f'{exported.name}: not a readable STL mesh ({exc})') from exc
    actual = _triangles(points, faces)
    expected = [(instance, _triangles(instance.points, instance.faces)) for instance in instances]
    wanted = sum(len(triangles) for _instance, triangles in expected)
    if len(actual) != wanted:
        raise ValueError(f'facet counts differ: STL has {len(actual)}, the plate has {wanted} ('
                         + ', '.join(f'{instance.name}: {len(triangles)}' for instance, triangles in expected) + ')')
    size, used, deviation = 4 * MERGED_VERTEX_TOL_MM, set(), 0.0
    cells = _index(actual, size)
    objects = []
    for instance, triangles in expected:
        pairs, error = _consume(triangles, actual, cells, used, MERGED_VERTEX_TOL_MM, size)
        if pairs is None:
            raise ValueError(f'only {error} of {len(triangles)} triangles of {instance.name!r} are in the STL '
                             f'at their plate position: the object was left out or moved')
        deviation = max(deviation, error)
        placed = [vertex for number in pairs for vertex in actual[number]]
        objects.append({'name': instance.name, 'triangles': len(triangles), 'matched': len(pairs),
                        'plate_bounds_mm': bounds(list(instance.points)), 'stl_bounds_mm': bounds(placed)})
    return {'file_bytes': len(raw), 'file_sha256': sha256(raw).hexdigest(),
            'format': 'binary' if 84 + 50 * len(faces) == len(raw) else 'ascii',
            'triangle_count': len(faces), 'objects': objects,
            'max_vertex_deviation_mm': deviation, 'vertex_tolerance_mm': MERGED_VERTEX_TOL_MM,
            'stl_bounds_mm': bounds(points)}


def project_presets(project):
    """The printer and process a saved project names, read from its settings (no expectation attached)."""
    import json
    with ZipFile(Path(project)) as archive:
        settings = json.loads(archive.read('Metadata/project_settings.config'))
    filaments = settings.get('filament_settings_id') or []
    return {'printer_model': settings.get('printer_model'), 'printer_settings_id': settings.get('printer_settings_id'),
            'print_settings_id': settings.get('print_settings_id'),
            'filament_settings_id': filaments[0] if isinstance(filaments, list) and filaments else filaments,
            'layer_height': settings.get('layer_height'),
            'initial_layer_print_height': settings.get('initial_layer_print_height'),
            'print_sequence': settings.get('print_sequence')}


def _shape(vertices, faces):
    """'cube', 'sphere' or 'other', from the world-space mesh alone (names are not trusted)."""
    (x0, x1), (y0, y1), (z0, z1) = extents = bounds(list(vertices))
    sides = [x1 - x0, y1 - y0, z1 - z0]
    if len(faces) == 12 and max(sides) - min(sides) <= 1e-4:
        return 'cube'
    center = tuple((low + high) / 2 for low, high in extents)
    radius = max(sides) / 2
    if (min(sides) > 1 and max(sides) - min(sides) <= 1e-4
            and max(abs(math.dist(vertex, center) - radius) for vertex in vertices) <= 0.05):
        return 'sphere'
    return 'other'


def plate_object_layout(project):
    """Which objects a saved plate holds (name, triangles, bounds, shape), whether they overlap and fit the bed."""
    bed, items = _project(Path(project))
    objects = [{'name': item.name, 'triangles': len(item.faces), 'bounds_mm': item.box,
                'shape': _shape(item.vertices, item.faces)} for item in items]
    pairs = _pairs(items)
    return {'objects': objects, 'pairs': pairs,
            'checks': {'two_objects': len(items) == 2,
                       'cube_and_sphere': sorted(object_['shape'] for object_ in objects) == ['cube', 'sphere'],
                       'disjoint': not any(pair['overlap'] for pair in pairs),
                       'inside_bed': bool(items) and all(bed.contains(item) for item in items)}}


def merged_stl_expectation_gaps(project, exported, extension):
    """{clause of the Feishu #233 expectation: [what failed]} for the STL as it landed.

    `extension` is the one the application appended when saving. The clause
    "可正常打开" is judged by the third-party viewer in the GUI case, not here."""
    clauses = ('生成 .stl 文件', '包含两个模型的合并几何', '文件非 0 字节')
    gaps = {clause: [] for clause in clauses}
    if extension != '.stl':
        gaps['生成 .stl 文件'].append(f'extension {extension!r}')
    try:
        raw = _read(Path(exported))
        points, faces = stl_mesh(raw)
    except (OSError, ValueError) as exc:
        unreadable = f'not a readable STL mesh ({_reason(exported, exc)})'
        gaps['生成 .stl 文件'].append(unreadable)
        gaps['包含两个模型的合并几何'].append(unreadable)
        gaps['文件非 0 字节'].append('empty file' if Path(exported).is_file() and not Path(exported).stat().st_size
                                    else _reason(exported, exc))
        return gaps
    try:
        verify_merged_stl(project, exported)
    except ValueError as exc:
        gaps['包含两个模型的合并几何'].append(str(exc))
    return gaps


def _reason(path, exc):
    """A file error without the machine's path or locale in it."""
    name = Path(path).name
    if isinstance(exc, FileNotFoundError):
        return f'{name}: missing file'
    if isinstance(exc, OSError):
        return f'{name}: {type(exc).__name__}'
    return str(exc) if str(exc).startswith(name) else f'{name}: {exc}'


def viewer_gaps(receipt):
    """[what failed] for "可正常打开": the viewer opened the exact file, rendered it and rejected a broken STL."""
    gaps = []
    if receipt.get('version_rc') != 0:
        gaps.append('viewer did not identify itself')
    if receipt.get('positive_rc') != 0:
        gaps.append(f'viewer exit code {receipt.get("positive_rc")!r} on the exported file')
    if not receipt.get('image'):
        gaps.append('viewer rendered no bounded foreground mesh')
    if 'negative_rc' not in receipt:
        gaps.append('malformed control STL was not run')
    elif receipt['negative_rc'] == 0:
        gaps.append('viewer accepted the malformed control STL')
    return gaps


# --- sliced-file archive (#234) -----------------------------------------------

# The two plate previews of the real guest export carry 17 and 9 colours that cover at
# least 8 pixels each; a blank image carries one. Three asks for a picture, not for that model.
PREVIEW_MIN_COLORS = 3
PREVIEW_MIN_SIDE_PX = 16
SLICED_EXPECTATIONS = ('生成 .gcode.3mf 文件', '内含 G-code 与预览信息', '文件大小随切片复杂度合理增大')
# Which archive checks carry which clause of the expectation. The third clause is the size comparison.
SLICED_CLAUSES = (
    ('内含 G-code 与预览信息', ('single_plate_gcode', 'contains_gcode', 'contains_preview',
                           'gcode_checksum_consistent')),
)


def _png_size(data):
    if len(data) >= 24 and data[:8] == PNG_SIGNATURE and data[12:16] == b'IHDR':
        return list(struct.unpack('>II', data[16:24]))
    return None


def _png_colors(data):
    """[width, height, colours covering at least 8 pixels each], or None when not a decodable PNG."""
    size = _png_size(data)
    if not size:
        return None
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(data)) as image:
            rgba = image.convert('RGBA')
            width, height = rgba.size
            colors = sum(1 for count, _rgba in rgba.getcolors(maxcolors=width * height) if count >= 8)
    except Exception:  # noqa: BLE001 - a preview that does not decode is not a preview
        return None
    return size + [colors]


def sliced_3mf_facts(path):
    """What a ``.gcode.3mf`` archive holds: the plate G-code, the previews and the records."""
    path = Path(path)
    raw = _read(path)
    facts = {'file_name': path.name, 'extension': ''.join(path.suffixes[-2:]).lower(),
             'file_bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
    try:
        with ZipFile(BytesIO(raw)) as archive:
            members = [(info.filename, info.file_size) for info in archive.infolist()]
            names = [name for name, _size in members]
            plates = sorted(name for name in names if PLATE_GCODE.match(name))
            gcode, recorded = b'', b''
            if len(plates) == 1:
                gcode = archive.read(plates[0])
                if plates[0] + '.md5' in names:
                    recorded = archive.read(plates[0] + '.md5').strip()
            previews = []
            for name, size in members:
                if name.startswith('Metadata/') and name.lower().endswith('.png'):
                    image = _png_colors(archive.read(name))
                    previews.append({'name': name, 'bytes': size,
                                     'size_px': image[:2] if image else None,
                                     'colors': image[2] if image else None})
    except (BadZipFile, KeyError, OSError, struct.error, ValueError) as exc:
        raise ValueError(f'{path.name}: not a readable sliced-file archive ({exc})') from exc
    facts.update({
        'members': [{'name': name, 'bytes': size} for name, size in members],
        'gcode_member': plates[0] if len(plates) == 1 else None,
        'plate': plates[0][:-len('.gcode')] if len(plates) == 1 else None,
        'gcode': _gcode_facts(gcode, plates[0]) if len(plates) == 1 else None,
        'previews': previews,
        'gcode_md5_recorded': recorded.decode('ascii', errors='replace').lower(),
        'gcode_md5_computed': md5(gcode).hexdigest() if len(plates) == 1 else '',
        'has_slice_info': 'Metadata/slice_info.config' in names,
        'has_project_settings': 'Metadata/project_settings.config' in names,
    })
    return facts


def _shows_picture(preview):
    return (preview['size_px'] is not None and min(preview['size_px']) >= PREVIEW_MIN_SIDE_PX
            and preview['colors'] is not None and preview['colors'] >= PREVIEW_MIN_COLORS)


def sliced_3mf_checks(facts):
    """Ordered {check: passed}; ``verify_sliced_3mf`` raises on the first failure.

    The checksum record and slice_info are part of a complete archive on this
    build; whether the Feishu expectation holds is decided by SLICED_CLAUSES."""
    plate = facts['plate']
    pictures = {preview['name'] for preview in facts['previews'] if _shows_picture(preview)}
    return {
        'gcode_3mf_extension': facts['extension'] == '.gcode.3mf',
        'single_plate_gcode': plate is not None,
        'contains_gcode': facts['gcode'] is not None and all(gcode_checks(facts['gcode']).values()),
        'contains_preview': plate is not None and {plate + '.png', plate + '_small.png'} <= pictures,
        'gcode_checksum_recorded': bool(facts['gcode_md5_recorded']),
        # A record that contradicts the G-code member is a broken archive; no record is none to compare.
        'gcode_checksum_consistent': facts['gcode_md5_recorded'] in ('', facts['gcode_md5_computed']),
        'has_slice_info': facts['has_slice_info'],
    }


def verify_sliced_3mf(path):
    """Feishu #234: a ``.gcode.3mf`` archive holding the plate G-code and its previews."""
    facts = sliced_3mf_facts(path)
    failed = [check for check, passed in sliced_3mf_checks(facts).items() if not passed]
    if failed:
        raise ValueError(f'{facts["file_name"]}: failed {failed}; extension {facts["extension"]!r}, '
                         f'G-code member {facts["gcode_member"]!r}, previews {facts["previews"]}, '
                         f'recorded MD5 {facts["gcode_md5_recorded"]!r}')
    return facts


def _size_row(facts):
    """Size and content readings of a sliced archive (its G-code member) or of a plain G-code export."""
    gcode = facts.get('gcode') or facts
    return {'file_name': facts['file_name'], 'file_bytes': facts['file_bytes'],
            'gcode_bytes': gcode['file_bytes'], 'layers': gcode['layer_count'],
            'extruding_moves': gcode['extruding_moves'],
            'estimated_time': gcode['trailer_notes']['estimated_time']}


def _size_comparison(simple, complex_):
    """The simple and the complex plate side by side; both must have passed verify_sliced_3mf."""
    rows = {'simple': _size_row(simple), 'complex': _size_row(complex_)}
    return {'simple': rows['simple'], 'complex': rows['complex'],
            'file_ratio': round(rows['complex']['file_bytes'] / rows['simple']['file_bytes'], 3),
            'gcode_ratio': round(rows['complex']['gcode_bytes'] / rows['simple']['gcode_bytes'], 3),
            'checks': {'complex_file_larger': rows['complex']['file_bytes'] > rows['simple']['file_bytes'],
                       'complex_gcode_larger': rows['complex']['gcode_bytes'] > rows['simple']['gcode_bytes']}}


def compare_sliced_sizes(simple, complex_):
    """Readings for "the file grows with slicing complexity": two archives side by side."""
    return _size_comparison(verify_sliced_3mf(simple), verify_sliced_3mf(complex_))


def sliced_expectation_gaps(samples, projects=None):
    """({clause of the Feishu #234 expectation: [what failed]}, readings, size comparison).

    `samples` maps 'simple' and 'complex' to (path, extension) of the two sliced
    files as the application saved them: a bare name was typed, the extension
    is its own. `projects` maps the same labels to the project that was on the
    plate when it was sliced; where it is given, the G-code inside the archive
    must deposit its material on that plate's objects (gcode_footprint) or the
    clause about the G-code fails. Nothing raises; each clause reports its own gaps."""
    projects = projects or {}
    gaps = {clause: [] for clause in SLICED_EXPECTATIONS}
    readings = {}
    for label, (path, extension) in samples.items():
        if extension != '.gcode.3mf':
            gaps['生成 .gcode.3mf 文件'].append(f'{label}: extension {extension!r}')
        try:
            readings[label] = sliced_3mf_facts(path)
        except ValueError as exc:
            readings[label] = None
            gaps['生成 .gcode.3mf 文件'].append(f'{label}: {exc}')
            gaps['内含 G-code 与预览信息'].append(f'{label}: {exc}')
        else:
            checks = sliced_3mf_checks(readings[label])
            for clause, names in SLICED_CLAUSES:
                failed = [name for name in names if not checks[name]]
                if failed:
                    gaps[clause].append(f'{label}: {failed}')
            readings[label]['checks'] = checks
            if label in projects:
                try:
                    with ZipFile(path) as archive:
                        member = archive.read(readings[label]['gcode_member'])
                    plate = _footprint(member, readings[label]['gcode_member'], projects[label])
                except (OSError, ValueError, KeyError, TypeError, BadZipFile, ParseError) as exc:
                    gaps['内含 G-code 与预览信息'].append(f'{label}: extrusion_on_objects {exc}')
                else:
                    readings[label]['footprint'] = plate
                    failed = [name for name, passed in plate['checks'].items() if not passed]
                    if failed:
                        gaps['内含 G-code 与预览信息'].append(f'{label}: extrusion_on_objects {failed}')
    comparison = None
    ready = {label: facts is not None and facts['gcode'] is not None for label, facts in readings.items()}
    if ready.get('simple') and ready.get('complex'):
        comparison = _size_comparison(readings['simple'], readings['complex'])
        gaps['文件大小随切片复杂度合理增大'] = [name for name, grown in comparison['checks'].items() if not grown]
    else:
        missing = [label for label in ('simple', 'complex') if not ready.get(label)]
        gaps['文件大小随切片复杂度合理增大'].append(
            f'no readable plate G-code for {missing}: the two files cannot be compared')
    return gaps, readings, comparison


def harvested_readings(entries):
    """{label: size readings} of exports collected earlier, for a side-by-side look.

    Each entry is (label, path, kind) with kind 'gcode' for a plain G-code
    export or 'sliced' for a ``.gcode.3mf`` archive. A file that is not on
    this machine is reported as absent, not skipped."""
    out = {}
    for label, path, kind in entries:
        path = Path(path)
        if not path.is_file():
            out[label] = {'present': False, 'file_name': path.name}
            continue
        try:
            facts = sliced_3mf_facts(path) if kind == 'sliced' else gcode_export_facts(path)
            if kind == 'sliced':
                failed = [check for check, passed in sliced_3mf_checks(facts).items() if not passed]
                if failed:
                    raise ValueError(f'{path.name}: failed {failed}')
            out[label] = dict(_size_row(facts), present=True)
        except (OSError, ValueError) as exc:
            out[label] = {'present': True, 'error': _reason(path, exc)}
    return out


# --- G-code footprint (#236, #234) --------------------------------------------

# Where the G-code deposits material, against the plate it was sliced from.
#
# Read off the same real exports (plain single-colour runs, each compared with its own input project):
# * Every wall, infill, surface and bridge move lies inside its object's box. The outermost
#   centreline sits 0.41 mm (0.8 nozzle) or 0.21 mm (0.4 nozzle) inside it, and no plain run has a
#   model move beyond the box. 1.0 mm therefore leaves room for the extrusion width and still
#   rejects a whole-file shift of 1.5 mm or more on either nozzle.
# * ``; printing object <name> id:<id> copy <n>`` ... ``; stop printing object`` wraps each object's
#   moves of a layer (135 pairs in the standard cube export). Brim and raft moves sit inside those
#   blocks and leave the object's box: 4.24 mm for a 5 mm brim (run f6dc29a8), 7.63 mm for a raft
#   with raft_first_layer_expansion 5 and raft_expansion 1.5 (run daf3216f). Skirt moves sit outside
#   the blocks and reached 6.84 mm beyond all objects for skirt_distance 5 and three 0.82 mm loops
#   (run 749da439). Each of those three allowances rests on one run.
# * The start G-code extrudes the machine's own purge line at the front edge of the bed (315/315);
#   it is counted, not judged.
# * Prime tower and custom G-code may stand anywhere on the bed.
# The allowances are read from the saved project, never from the G-code, so that a file cannot
# widen them itself.
FOOTPRINT_TOL_MM = 1.0
SUPPORT_TYPES = frozenset(('Support', 'Support interface'))
CATEGORIES = ('model', 'support', 'brim', 'skirt', 'tower', 'custom')
PRINTING = re.compile(r'^; printing object (.*) id:\d+ copy \d+\s*$')


def _extrusions(raw):
    """(moves, purges): every extruding XY move from the first layer on as
    (type, object name or None, x0, y0, x1, y1), and how many such moves precede it."""
    lines, codes = _lines(raw)
    exec_start, exec_end = _block_positions(lines)['executable']
    lo = exec_start + 1 if exec_start is not None else 0
    hi = exec_end if exec_end is not None else len(lines)
    first = next((i for i in range(lo, hi) if LAYER_A.match(lines[i].strip()) or LAYER_B.match(lines[i].strip())), hi)
    absolute_e, e_position, x, y = True, 0.0, None, None
    current, kind, moves, purges = None, None, [], 0
    for i in range(lo, hi):
        line, code = lines[i].strip(), codes[i]
        if line.startswith('; printing object '):
            found = PRINTING.match(line)
            current = found.group(1) if found else None
            continue
        if line.startswith('; stop printing object'):
            current = None
            continue
        if line.startswith(';TYPE:'):
            kind = line[6:].strip()
            continue
        if not code:
            continue
        head = _head(code)
        if head == 'M82':
            absolute_e = True
            continue
        if head == 'M83':
            absolute_e = False
            continue
        if not MOTION.match(code):
            continue
        words = {key: float(value) for key, value in WORD.findall(code)}
        nx, ny = words.get('X', x), words.get('Y', y)
        if 'E' in words:
            delta = words['E'] - e_position if absolute_e else words['E']
            e_position = words['E']
            if delta > 0 and ('X' in words or 'Y' in words) and None not in (x, y, nx, ny):
                if i < first:
                    purges += 1
                else:
                    moves.append((kind, current, x, y, nx, ny))
        x, y = nx, ny
    return moves, purges


def _outside(point, box):
    """How far a point lies beyond ((x0, x1), (y0, y1)); 0 when inside."""
    return max(0.0, box[0][0] - point[0], point[0] - box[0][1], box[1][0] - point[1], point[1] - box[1][1])


def _category(kind):
    if kind == 'Brim':
        return 'brim'
    if kind == 'Skirt':
        return 'skirt'
    if kind in ('Prime tower', 'Wipe tower'):
        return 'tower'
    if not kind or kind == 'Custom':
        return 'custom'
    return 'support' if kind in SUPPORT_TYPES else 'model'


def _setting(settings, key, default=0.0):
    """The first number of a project setting ('5', '0.82', '5,5'); the default when absent or not a number."""
    value = settings.get(key)
    if value is None:
        return default
    try:
        return float(str(value).split(',')[0].strip().strip('"'))
    except ValueError:
        return default


def _footprint(raw, name, project):
    """The readings and checks of one G-code file against the plate of a saved project."""
    project = Path(project)
    try:
        bed, items = _project(project)
        with ZipFile(project) as archive:
            settings = json.loads(archive.read('Metadata/project_settings.config'))
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, ParseError) as exc:
        raise ValueError(f'{project.name}: unreadable project ({exc})') from exc
    boxes = {item.name: ((min(v[0] for v in item.vertices), max(v[0] for v in item.vertices)),
                         (min(v[1] for v in item.vertices), max(v[1] for v in item.vertices))) for item in items}

    def flat(axis):
        return min(box[axis][0] for box in boxes.values()), max(box[axis][1] for box in boxes.values())

    union = (flat(0), flat(1)) if boxes else ((0.0, 0.0), (0.0, 0.0))
    area = ((min(p[0] for p in bed.polygon), max(p[0] for p in bed.polygon)),
            (min(p[1] for p in bed.polygon), max(p[1] for p in bed.polygon)))
    line_width = _setting(settings, 'line_width', 0.42)
    raft = 0.0
    if _setting(settings, 'raft_layers') > 0:
        raft = _setting(settings, 'raft_first_layer_expansion') + _setting(settings, 'raft_expansion') + line_width
    allowances = {
        'model': FOOTPRINT_TOL_MM,
        'support': FOOTPRINT_TOL_MM + raft,
        'brim': FOOTPRINT_TOL_MM + _setting(settings, 'brim_width') + _setting(settings, 'brim_object_gap'),
        'skirt': FOOTPRINT_TOL_MM + _setting(settings, 'skirt_distance') + _setting(settings, 'skirt_loops') * line_width,
    }
    moves, purges = _extrusions(raw)
    objects = {label: {'box_mm': [box[0][0], box[0][1], box[1][0], box[1][1]], 'moves': 0, 'model_moves': 0,
                       'extruded_mm': None, 'max_excursion_mm': 0.0} for label, box in boxes.items()}
    counts = dict.fromkeys(CATEGORIES, 0)
    worst = dict.fromkeys(CATEGORIES, 0.0)
    named, unknown, unassigned = set(), set(), 0
    for kind, label, x0, y0, x1, y1 in moves:
        category = _category(kind)
        points = ((x0, y0), (x1, y1))
        counts[category] += 1
        if category in ('tower', 'custom'):
            far = max(_outside(point, area) for point in points)
        else:
            if category == 'skirt' or label not in boxes:
                box = union
                if category != 'skirt':
                    unassigned += 1
                    if label:
                        unknown.add(label)
            else:
                box = boxes[label]
                named.add(label)
                record = objects[label]
                record['moves'] += 1
                record['model_moves'] += category == 'model'
                span = record['extruded_mm'] or [x0, x0, y0, y0]
                record['extruded_mm'] = [min(span[0], x0, x1), max(span[1], x0, x1),
                                         min(span[2], y0, y1), max(span[3], y0, y1)]
            far = max(_outside(point, box) for point in points)
            if label in boxes and category != 'skirt':
                objects[label]['max_excursion_mm'] = max(objects[label]['max_excursion_mm'], far)
        worst[category] = max(worst[category], far)
    printed = {label for label, record in objects.items() if record['model_moves']}
    checks = {
        'objects_named': not unknown,
        'every_object_printed': printed == set(boxes) if named else counts['model'] > 0,
        'model_inside_object_blocks': unassigned == 0,
        'model_on_objects': worst['model'] <= allowances['model'],
        'support_on_objects': worst['support'] <= allowances['support'],
        'brim_near_objects': worst['brim'] <= allowances['brim'],
        'skirt_near_objects': worst['skirt'] <= allowances['skirt'],
        'ancillary_on_bed': worst['tower'] <= FOOTPRINT_TOL_MM and worst['custom'] <= FOOTPRINT_TOL_MM,
    }
    return {
        'file_name': name,
        'tolerance_mm': FOOTPRINT_TOL_MM,
        'allowances_mm': allowances,
        'plate_objects': {label: record['box_mm'] for label, record in objects.items()},
        'plate_box_mm': [union[0][0], union[0][1], union[1][0], union[1][1]],
        'printable_area_mm': [area[0][0], area[0][1], area[1][0], area[1][1]],
        'names_in_gcode': sorted(named),
        'moves': dict(counts, unassigned=unassigned, start_gcode=purges),
        'max_excursion_mm': worst,
        'objects': objects,
        'checks': checks,
    }


def gcode_footprint(path, project):
    """Where the G-code deposits material, against the objects of the saved plate. Nothing here judges
    beyond `checks`; `project` is the project as it was on the plate when the plate was sliced."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(_reason(path, exc) + ': unreadable G-code') from exc
    return _footprint(raw, path.name, project)


def verify_gcode_footprint(path, project):
    """Raises ValueError naming the failed footprint checks; returns the readings."""
    footprint = gcode_footprint(path, project)
    failed = [check for check, passed in footprint['checks'].items() if not passed]
    if failed:
        raise ValueError(f'{footprint["file_name"]}: {failed}; excursions {footprint["max_excursion_mm"]} mm '
                         f'against allowances {footprint["allowances_mm"]} mm')
    return footprint
