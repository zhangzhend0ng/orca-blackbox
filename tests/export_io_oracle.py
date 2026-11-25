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
import math
from pathlib import Path
import re
import struct
from zipfile import BadZipFile, ZipFile

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
        raise ValueError(f'{path.name}: unreadable G-code ({exc})') from exc
    failed = [check for check, passed in gcode_checks(facts).items() if not passed]
    if failed:
        raise ValueError(f'{path.name}: ' + '; '.join(f'{check}: {_why(check, facts)}' for check in failed))
    return facts


GCODE_EXPECTATIONS = (
    ('生成 .gcode 文件', ('extension', 'gcode_extension')),
    ('含起始/结束 G-code', ('header_block', 'config_block', 'executable_block', 'start_gcode', 'end_gcode',
                           'trailer_notes')),
    ('无空文件', ('non_empty', 'layers_present', 'extrusion_present', 'layers_printed')),
    ('层命令连续', ('declared_layer_count', 'layer_numbers_consecutive', 'layer_z_monotonic')),
)


def gcode_expectation_gaps(facts, extension):
    """{clause of the Feishu #236 expectation: [names of its failed checks]}.

    `extension` is the one the application appended when saving; `facts` comes
    from the file as it landed. Nothing raises: each clause reports its own gaps."""
    checks = dict(gcode_checks(facts), extension=extension == '.gcode')
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


def plate_object_layout(project):
    """Which objects a saved plate holds, whether they overlap and whether they fit the bed."""
    bed, items = _project(Path(project))
    pairs = _pairs(items)
    return {'objects': [item.name for item in items],
            'bounds_mm': {item.name: item.box for item in items},
            'pairs': pairs,
            'checks': {'two_objects': len(items) == 2,
                       'disjoint': not any(pair['overlap'] for pair in pairs),
                       'inside_bed': bool(items) and all(bed.contains(item) for item in items)}}


# --- sliced-file archive (#234) -----------------------------------------------

def _png_size(data):
    if len(data) >= 24 and data[:8] == PNG_SIGNATURE and data[12:16] == b'IHDR':
        return list(struct.unpack('>II', data[16:24]))
    return None


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
            gcode, recorded, previews = b'', b'', []
            if len(plates) == 1:
                gcode = archive.read(plates[0])
                if plates[0] + '.md5' in names:
                    recorded = archive.read(plates[0] + '.md5').strip()
            computed = md5(archive.read(plates[0])).hexdigest() if len(plates) == 1 else ''
            for name, size in members:
                if name.startswith('Metadata/') and name.lower().endswith('.png'):
                    previews.append((name, size))
            images = [(name, size, _png_size(archive.read(name))) for name, size in previews]
    except (BadZipFile, KeyError, OSError, struct.error, ValueError) as exc:
        raise ValueError(f'{path.name}: not a readable sliced-file archive ({exc})') from exc
    facts.update({
        'members': [{'name': name, 'bytes': size} for name, size in members],
        'gcode_member': plates[0] if len(plates) == 1 else None,
        'gcode': _gcode_facts(gcode, plates[0]) if len(plates) == 1 else None,
        'previews': [{'name': name, 'bytes': size, 'size_px': size_px} for name, size, size_px in images],
        'gcode_md5_recorded': recorded.decode('ascii', errors='replace').lower(),
        'gcode_md5_computed': computed,
        'has_slice_info': 'Metadata/slice_info.config' in names,
        'has_project_settings': 'Metadata/project_settings.config' in names,
    })
    return facts


def sliced_3mf_checks(facts):
    plate = facts['gcode_member'].replace('.gcode', '') if facts['gcode_member'] else None
    valid = {image['name'] for image in facts['previews']
             if image['size_px'] and min(image['size_px']) >= 16}
    return {
        'gcode_3mf_extension': facts['extension'] == '.gcode.3mf',
        'single_plate_gcode': plate is not None,
        'contains_gcode': facts['gcode'] is not None and all(gcode_checks(facts['gcode']).values()),
        'contains_preview': plate is not None and {plate + '.png', plate + '_small.png'} <= valid,
        'gcode_checksum_consistent': bool(facts['gcode_md5_recorded'])
        and facts['gcode_md5_recorded'] == facts['gcode_md5_computed'],
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


def compare_sliced_sizes(simple, complex_):
    """Readings for "the file grows with slicing complexity": two archives side by side."""
    rows = []
    for path in (simple, complex_):
        facts = verify_sliced_3mf(path)
        rows.append({'file_name': facts['file_name'], 'file_bytes': facts['file_bytes'],
                     'gcode_bytes': facts['gcode']['file_bytes'], 'layers': facts['gcode']['layer_count'],
                     'extruding_moves': facts['gcode']['extruding_moves'],
                     'estimated_time': facts['gcode']['trailer_notes']['estimated_time']})
    return {'simple': rows[0], 'complex': rows[1],
            'checks': {'complex_file_larger': rows[1]['file_bytes'] > rows[0]['file_bytes'],
                       'complex_gcode_larger': rows[1]['gcode_bytes'] > rows[0]['gcode_bytes']}}
