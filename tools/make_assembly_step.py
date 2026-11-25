#!/usr/bin/env python3
"""Write and check assembly.step: three 10 mm cubes in red, green and blue (Feishu #229).

    python tools/make_assembly_step.py fixtures/assembly.step [--side 10] [--gap 10]
    python tools/make_assembly_step.py --check fixtures/assembly.step

The Feishu row asks for "assembly.step" holding three solids, each in another
colour, and expects the application to import all three with their colours.
The file is written here from scratch in ISO 10303-21 (AP214), with the
standard library only, and the same bytes every time.

Why it is written rather than spliced from the calibration model
(resources/calib/volumetric_speed/SpeedTestStructure.step of the application,
one solid with one colour): that one is a 2.3 MB tower, so three copies would
be 7 MB and could not be kept as a fixture, while three cubes are a few
ten-thousand bytes and easy to recognise in a saved project. The wire of the
file follows that model's, which the application reads: one product, an
``ADVANCED_BREP_SHAPE_REPRESENTATION`` that holds the solids and is linked to
the product's ``SHAPE_REPRESENTATION`` by a ``SHAPE_REPRESENTATION_RELATIONSHIP``,
and a ``MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION`` that holds one
``STYLED_ITEM`` per solid (there the single styled item points at the solid
too). Each style is the chain the model uses: ``PRESENTATION_STYLE_ASSIGNMENT``,
``SURFACE_STYLE_USAGE(.BOTH., ...)``, ``SURFACE_SIDE_STYLE``,
``SURFACE_STYLE_FILL_AREA``, ``FILL_AREA_STYLE``, ``FILL_AREA_STYLE_COLOUR``,
``COLOUR_RGB``.

Each cube is a closed shell of six planar faces. Its twelve edges are shared
by two faces each, once forwards and once backwards, and every face's loop
runs counter-clockwise seen from outside (``FACE_OUTER_BOUND`` with ``.T.``
around the plane's axis, the face's ``same_sense`` being ``.T.``).

``--check`` reads a file back and does not trust the writer:

* every ``#id`` is defined once and every ``#id`` used is defined;
* there are three ``MANIFOLD_SOLID_BREP`` and three different ``COLOUR_RGB``;
  each solid has one ``STYLED_ITEM``, and no two share a colour;
* for solids made of planes and lines only: every shell is closed (each edge
  used twice, in opposite directions), every loop follows its face's normal,
  every line runs along its edge the way ``same_sense`` says, every shell has
  a positive volume and the solids' boxes do not overlap.

A file that fails prints its failures and exits with 1. What only the
application can say (whether OCCT reads one object with three parts or three
objects, and whether the colours survive) is not claimed here.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

SCHEMA = 'AUTOMOTIVE_DESIGN { 1 0 10303 214 3 1 1 }'
SOLIDS = ('cube_red', 'cube_green', 'cube_blue')
COLOURS = (('Red', (1.0, 0.0, 0.0)), ('Green', (0.0, 1.0, 0.0)), ('Blue', (0.0, 0.0, 1.0)))
TOL_MM = 1e-6
RECORD = re.compile(r'#(\d+)\s*=\s*(.+)$', re.S)
NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[Ee][-+]?\d+)?')


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    """A coordinate the way Part 21 writes it: 10, 0, 1.5, -3."""
    return f'{value:.10g}'


# --- writing -------------------------------------------------------------------

class _Writer:
    """Collects entity records under consecutive ids."""

    def __init__(self):
        self.records, self.count = [], 0

    def add(self, text):
        self.count += 1
        self.records.append(f'#{self.count}={text};')
        return self.count

    def refs(self, ids):
        return ','.join(f'#{value}' for value in ids)


def _directions(writer):
    keys = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    return {key: writer.add(f"DIRECTION('',({_number(key[0])},{_number(key[1])},{_number(key[2])}))") for key in keys}


def _cube(writer, name, origin, side, directions):
    """A closed cube from x0, y0, z0 to x0 + side, ...: one MANIFOLD_SOLID_BREP; returns its id."""
    x0, y0, z0 = origin
    corners = ((x0, y0, z0), (x0 + side, y0, z0), (x0 + side, y0 + side, z0), (x0, y0 + side, z0),
               (x0, y0, z0 + side), (x0 + side, y0, z0 + side), (x0 + side, y0 + side, z0 + side),
               (x0, y0 + side, z0 + side))
    point = [writer.add(f"CARTESIAN_POINT('',({_number(x)},{_number(y)},{_number(z)}))") for x, y, z in corners]
    vertex = [writer.add(f"VERTEX_POINT('',#{point[index]})") for index in range(8)]
    # Each edge runs from its first corner to its second, along the unit direction named third.
    edges = ((0, 1, (1, 0, 0)), (1, 2, (0, 1, 0)), (2, 3, (-1, 0, 0)), (3, 0, (0, -1, 0)),
             (4, 5, (1, 0, 0)), (5, 6, (0, 1, 0)), (6, 7, (-1, 0, 0)), (7, 4, (0, -1, 0)),
             (0, 4, (0, 0, 1)), (1, 5, (0, 0, 1)), (2, 6, (0, 0, 1)), (3, 7, (0, 0, 1)))
    edge = []
    for first, second, way in edges:
        vector = writer.add(f"VECTOR('',#{directions[way]},{_number(side)})")
        line = writer.add(f"LINE('',#{point[first]},#{vector})")
        edge.append(writer.add(f"EDGE_CURVE('',#{vertex[first]},#{vertex[second]},#{line},.T.)"))
    # For each face: the plane's axis (outward), a reference direction, a corner on it, and the
    # loop as (edge, runs forwards). Counter-clockwise seen from outside.
    faces = (((0, 0, -1), (1, 0, 0), 0, ((3, False), (2, False), (1, False), (0, False))),   # bottom
             ((0, 0, 1), (1, 0, 0), 4, ((4, True), (5, True), (6, True), (7, True))),        # top
             ((0, -1, 0), (1, 0, 0), 0, ((0, True), (9, True), (4, False), (8, False))),    # front
             ((0, 1, 0), (1, 0, 0), 3, ((2, True), (11, True), (6, False), (10, False))),   # back
             ((1, 0, 0), (0, 1, 0), 1, ((1, True), (10, True), (5, False), (9, False))),    # right
             ((-1, 0, 0), (0, 1, 0), 0, ((3, True), (8, True), (7, False), (11, False))))   # left
    face = []
    for axis, reference, corner, loop in faces:
        placement = writer.add(f"AXIS2_PLACEMENT_3D('',#{point[corner]},#{directions[axis]},#{directions[reference]})")
        plane = writer.add(f"PLANE('',#{placement})")
        oriented = [writer.add(f"ORIENTED_EDGE('',*,*,#{edge[index]},.{'T' if forwards else 'F'}.)")
                    for index, forwards in loop]
        edge_loop = writer.add(f"EDGE_LOOP('',({writer.refs(oriented)}))")
        bound = writer.add(f"FACE_OUTER_BOUND('',#{edge_loop},.T.)")
        face.append(writer.add(f"ADVANCED_FACE('',(#{bound}),#{plane},.T.)"))
    shell = writer.add(f"CLOSED_SHELL('',({writer.refs(face)}))")
    return writer.add(f"MANIFOLD_SOLID_BREP('{name}',#{shell})")


def _style(writer, solid, colour):
    """A STYLED_ITEM that paints `solid` in `colour` (a name and its red, green, blue)."""
    name, (red, green, blue) = colour
    rgb = writer.add(f"COLOUR_RGB('{name}',{_number(red)},{_number(green)},{_number(blue)})")
    fill_colour = writer.add(f"FILL_AREA_STYLE_COLOUR('{name}',#{rgb})")
    area = writer.add(f"FILL_AREA_STYLE('{name}',(#{fill_colour}))")
    surface = writer.add(f"SURFACE_STYLE_FILL_AREA(#{area})")
    side = writer.add(f"SURFACE_SIDE_STYLE('',(#{surface}))")
    usage = writer.add(f"SURFACE_STYLE_USAGE(.BOTH.,#{side})")
    assignment = writer.add(f"PRESENTATION_STYLE_ASSIGNMENT((#{usage}))")
    return writer.add(f"STYLED_ITEM('',(#{assignment}),#{solid})")


def assembly_text(side=10.0, gap=10.0, solids=SOLIDS, colours=COLOURS):
    """The whole file. The cubes stand side by side along x, `gap` apart, each resting on z = 0."""
    _need(side > 0 and gap > 0, f'side and gap must be positive, got {side!r} and {gap!r}')
    _need(len(solids) == len(colours) == 3 and len(set(solids)) == 3, 'the file names three solids')
    _need(len({rgb for _name, rgb in colours}) == 3, 'the file needs three different colours')
    writer = _Writer()
    application = writer.add("APPLICATION_CONTEXT('Core Data for Automotive Mechanical Design Process')")
    writer.add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2009,#{application})")
    product_context = writer.add(f"PRODUCT_CONTEXT('part definition',#{application},'mechanical')")
    product = writer.add(f"PRODUCT('assembly','assembly','three cubes, one red, one green, one blue',"
                         f"(#{product_context}))")
    writer.add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('assembly','assembly',(#{product}))")
    formation = writer.add(f"PRODUCT_DEFINITION_FORMATION('','',#{product})")
    definition_context = writer.add(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{application},'design')")
    definition = writer.add(f"PRODUCT_DEFINITION('assembly','assembly',#{formation},#{definition_context})")
    shape = writer.add(f"PRODUCT_DEFINITION_SHAPE('','',#{definition})")
    length = writer.add('(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))')
    angle = writer.add('(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))')
    solid_angle = writer.add('(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())')
    contexts = []
    for _ in range(2):  # one for the shape, one for the presentation, as the calibration model has
        uncertainty = writer.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#{length},"
                                 f"'distance_accuracy_value','confusion accuracy')")
        contexts.append(writer.add('(GEOMETRIC_REPRESENTATION_CONTEXT(3) '
                                   f'GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{uncertainty})) '
                                   f'GLOBAL_UNIT_ASSIGNED_CONTEXT((#{length},#{angle},#{solid_angle})) '
                                   "REPRESENTATION_CONTEXT('','3D'))"))
    directions = _directions(writer)
    cubes = [_cube(writer, name, (index * (side + gap), 0.0, 0.0), side, directions)
             for index, name in enumerate(solids)]
    styled = [_style(writer, cube, colour) for cube, colour in zip(cubes, colours)]
    origin = writer.add("CARTESIAN_POINT('',(0,0,0))")
    placement = writer.add(f"AXIS2_PLACEMENT_3D('',#{origin},#{directions[(0, 0, 1)]},#{directions[(1, 0, 0)]})")
    representation = writer.add(f"SHAPE_REPRESENTATION('',(#{placement}),#{contexts[0]})")
    brep = writer.add(f"ADVANCED_BREP_SHAPE_REPRESENTATION('',({writer.refs(cubes)}),#{contexts[0]})")
    writer.add(f"SHAPE_DEFINITION_REPRESENTATION(#{shape},#{representation})")
    writer.add(f"SHAPE_REPRESENTATION_RELATIONSHIP('SRR','None',#{representation},#{brep})")
    writer.add("MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',"
               f"({writer.refs(styled)}),#{contexts[1]})")
    return '\n'.join([
        'ISO-10303-21;', 'HEADER;',
        "FILE_DESCRIPTION(('Three cubes in red, green and blue: an assembly for Feishu #229'),'2;1');",
        f"FILE_NAME('assembly.step','2026-11-26T00:00:00+08:00',('orca-blackbox'),(),"
        "'make_assembly_step.py','orca-blackbox','');",
        f"FILE_SCHEMA(('{SCHEMA}'));", 'ENDSEC;', 'DATA;', *writer.records, 'ENDSEC;', 'END-ISO-10303-21;', ''])


def write_assembly(path, **options):
    """Write the file and return its byte count and SHA-256."""
    raw = assembly_text(**options).encode('ascii')
    Path(path).write_bytes(raw)
    return {'name': Path(path).name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


# --- reading -------------------------------------------------------------------

def _split(text, separator):
    """The parts of `text` between its top-level `separator`s (outside strings and brackets)."""
    parts, start, depth, quoted, index = [], 0, 0, False, 0
    while index < len(text):
        char = text[index]
        if quoted:
            if char == "'":
                if text[index + 1:index + 2] == "'":
                    index += 1
                else:
                    quoted = False
        elif char == "'":
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return [part.strip() for part in parts]


def read_step(text):
    """{id: (name, or COMPLEX for a compound entity; its arguments; the ids it uses)} and the schema
    of a Part 21 file. Raises ValueError when a record is not an entity."""
    text = re.sub(r'/\*.*?\*/', '', text.replace('\r\n', '\n'), flags=re.S)
    _need('DATA;' in text and 'END-ISO-10303-21;' in text, 'not a Part 21 file: no DATA section or no end mark')
    schema = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'", text)
    entities = {}
    for record in _split(text[text.index('DATA;') + 5:text.rindex('ENDSEC;')], ';'):
        if not record:
            continue
        found = RECORD.match(record)
        _need(found is not None, f'not an entity record: {record[:60]!r}')
        body = found.group(2).strip()
        if body.startswith('('):
            entities[int(found.group(1))] = ('COMPLEX', body[1:-1].strip(), re.findall(r'#(\d+)', body))
            continue
        simple = re.match(r'([A-Z0-9_]+)\s*\((.*)\)$', body, re.S)
        _need(simple is not None, f'not an entity record: {record[:60]!r}')
        entities[int(found.group(1))] = (simple.group(1), simple.group(2).strip(), re.findall(r'#(\d+)', body))
    return {'schema': schema.group(1) if schema else None}, entities


def _arguments(step, reference):
    """(name, arguments) of the entity `reference` ('#12') points to."""
    _need(reference.startswith('#'), f'not a reference: {reference!r}')
    _need(int(reference[1:]) in step, f'reference {reference} is not defined')
    name, arguments, _used = step[int(reference[1:])]
    return name, _split(arguments, ',')


def _numbers(text):
    return [float(value) for value in NUMBER.findall(text)]


def _squared(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _solid_geometry(step, solid):
    """What one solid is made of, when it is made of planes and lines: its box, its volume, and
    whether it is closed and consistently oriented. `why` says what kept it from being read."""
    reading = {'faces': 0, 'closed': True, 'loops_follow_normals': True, 'lines_follow_edges': True}
    name, arguments = _arguments(step, solid)
    shell_name, shell_arguments = _arguments(step, arguments[1])
    corners, edges, volume = [], {}, 0.0
    reading['shell'] = shell_name
    for face in _list(shell_arguments[1]):
        face_name, face_arguments = _arguments(step, face)
        bound_name, bound_arguments = _arguments(step, _inside(_split(face_arguments[1], ',')[0]))
        loop_name, loop_arguments = _arguments(step, bound_arguments[1])
        polygon = []
        for oriented in _list(loop_arguments[1]):
            _oriented_name, oriented_arguments = _arguments(step, oriented)
            edges.setdefault(oriented_arguments[3], []).append(oriented_arguments[4])
            _edge_name, edge_arguments = _arguments(step, oriented_arguments[3])
            first = _numbers(_arguments(step, _arguments(step, edge_arguments[1])[1][1])[1][1])
            second = _numbers(_arguments(step, _arguments(step, edge_arguments[2])[1][1])[1][1])
            line_name, line_arguments = _arguments(step, edge_arguments[3])
            if line_name != 'LINE':
                return {'checked': False, 'why': f'edge curve {edge_arguments[3]} is a {line_name}'}
            line_point = _numbers(_arguments(step, line_arguments[1])[1][1])
            _vector_name, vector_arguments = _arguments(step, line_arguments[2])
            way = _numbers(_arguments(step, vector_arguments[1])[1][1])
            along = [b - a for a, b in zip(first, second)]
            skew = _cross(way, along)
            # The line passes through an end of its edge, runs along it, and points the way
            # same_sense says (.T.: from the first vertex to the second).
            off_edge = min(_squared(line_point, first), _squared(line_point, second)) > TOL_MM ** 2
            if (off_edge or _dot(skew, skew) > 1e-12 * _dot(along, along)
                    or (_dot(way, along) > 0) != (edge_arguments[4] == '.T.')):
                reading['lines_follow_edges'] = False
            polygon += [first, second] if oriented_arguments[4] == '.T.' else [second, first]
            corners += [first, second]
        if bound_arguments[2] == '.F.':
            polygon.reverse()
        surface_name, surface_arguments = _arguments(step, face_arguments[2])
        if surface_name != 'PLANE':
            return {'checked': False, 'why': f'face {face} lies on a {surface_name}'}
        _placement_name, placement_arguments = _arguments(step, surface_arguments[1])
        location = _numbers(_arguments(step, placement_arguments[1])[1][1])
        normal = _numbers(_arguments(step, placement_arguments[2])[1][1])
        if face_arguments[3] == '.F.':
            normal = [-value for value in normal]
        if any(abs(_dot(normal, [q - low for q, low in zip(point, location)])) > TOL_MM for point in polygon):
            reading['loops_follow_normals'] = False  # a corner off the face's plane
        turns = (0.0, 0.0, 0.0)
        for here, there in zip(polygon, polygon[1:] + polygon[:1]):
            turns = [a + b for a, b in zip(turns, _cross(here, there))]
        if _dot(turns, normal) <= 0:
            reading['loops_follow_normals'] = False
        volume += sum(_dot(polygon[0], _cross(a, b)) for a, b in zip(polygon[1:], polygon[2:])) / 6
        reading['faces'] += 1
    reading.update(used_edges=len(edges), volume_mm3=volume,
                   box_mm=[(min(point[axis] for point in corners), max(point[axis] for point in corners)) for axis in range(3)])
    reading['closed'] = all(sorted(flags) == ['.F.', '.T.'] for flags in edges.values())
    return {'checked': True, **reading}


def _inside(text):
    """What a parenthesised list holds: '(#12)' is #12."""
    text = text.strip()
    return text[1:-1].strip() if text.startswith('(') else text


def _list(text):
    """The references inside a parenthesised list such as '(#12,#13)'."""
    return [token for token in _split(_inside(text), ',') if token]


def _colour_of(step, styled):
    """(name, (red, green, blue)) of the COLOUR_RGB a STYLED_ITEM's style chain ends in."""
    name, arguments = _arguments(step, styled)
    _assignment_name, assignment_arguments = _arguments(step, _inside(arguments[1]))
    _usage_name, usage_arguments = _arguments(step, _inside(assignment_arguments[0]))
    _side_name, side_arguments = _arguments(step, usage_arguments[1])
    _surface_name, surface_arguments = _arguments(step, _inside(side_arguments[1]))
    _area_name, area_arguments = _arguments(step, surface_arguments[0])
    _fill_name, fill_arguments = _arguments(step, _inside(area_arguments[1]))
    _rgb_name, rgb_arguments = _arguments(step, fill_arguments[1])
    return rgb_arguments[0].strip("'"), tuple(_numbers(' '.join(rgb_arguments[1:])))


def check_step(path):
    """Read a file back and hold it against what the Feishu row needs. Returns the readings with
    ``failures``, a list; empty when the file passes. Nothing here is taken from the writer."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f'{path.name}: unreadable ({type(exc).__name__})') from exc
    try:
        header, step = read_step(raw.decode('ascii'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f'{path.name}: {exc}') from exc
    failures = []
    name_of = {id_: name for id_, (name, _arguments, _used) in step.items()}
    solids = sorted(f'#{id_}' for id_, name in name_of.items() if name == 'MANIFOLD_SOLID_BREP')
    colours = sorted({tuple(_numbers(' '.join(_arguments(step, f'#{id_}')[1][1:])))
                      for id_, name in name_of.items() if name == 'COLOUR_RGB'})
    if len(solids) != 3:
        failures.append(f'MANIFOLD_SOLID_BREP: {len(solids)}, expected 3')
    if len(colours) != 3:
        failures.append(f'COLOUR_RGB: {len(colours)} different, expected 3')
    header_ids = [int(value) for value in re.findall(r'^#(\d+)\s*=', raw.decode('ascii'), re.M)]
    duplicates = sorted({value for value in header_ids if header_ids.count(value) > 1})
    if duplicates:
        failures.append(f'ids defined more than once: {duplicates[:10]}')
    missing = sorted({f'#{int(reference)}' for _name, _arguments, used in step.values() for reference in used
                      if int(reference) not in step})
    summary = {'name': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'schema': header['schema'], 'length_unit_mm': 'SI_UNIT(.MILLI.,.METRE.)' in raw.decode('ascii'),
               'entities': len(step), 'references': sum(len(used) for _name, _arguments, used in step.values()),
               'duplicates': duplicates, 'missing': missing}
    if missing:
        # Nothing that follows a reference can be read while one points nowhere.
        failures.append(f'references that are not defined: {missing[:10]}')
        return {**summary, 'solids': solids, 'colours': colours, 'styled': [],
                'geometry': ['not read: a reference points nowhere'], 'geometry_checked': False, 'failures': failures}
    styled = sorted(f'#{id_}' for id_, name in name_of.items() if name == 'STYLED_ITEM')
    painted = []
    for item in styled:
        target = _arguments(step, item)[1][2]  # STYLED_ITEM(name, (styles), item): what is painted
        painted.append((name_of[int(target[1:])] if target.startswith('#') and int(target[1:]) in name_of else '?',
                        target, _colour_of(step, item)))
    on_solids = {}
    for kind, target, colour in painted:
        if kind == 'MANIFOLD_SOLID_BREP':
            on_solids.setdefault(target, []).append(colour)
    own = [values[0] for values in on_solids.values() if len(values) == 1]
    if (len(solids) == 3 and (set(on_solids) != set(solids) or len(own) != 3)) or len(set(own)) != 3:
        failures.append('the three solids do not each carry one STYLED_ITEM of their own, in three different colours')
    geometry = [_solid_geometry(step, solid) for solid in solids]
    readings = []
    for solid, read in zip(solids, geometry):
        if read['checked']:
            box = [[round(value, 6) for value in pair] for pair in read['box_mm']]
            readings.append(f"{_arguments(step, solid)[1][0].strip(chr(39)) or solid}: {read['faces']} faces, "
                            f"volume {read['volume_mm3']:.6g} mm3, box {box}")
            if not read['closed'] or not read['loops_follow_normals'] or not read['lines_follow_edges'] or read['volume_mm3'] <= 0:
                failures.append(f'{solid} is not a closed, outward-facing shell: closed={read["closed"]}, '
                                f'loops follow normals={read["loops_follow_normals"]}, lines follow edges='
                                f'{read["lines_follow_edges"]}, volume {read["volume_mm3"]:.6g}')
        else:
            readings.append(f'{solid}: geometry not checked, {read["why"]}')
    boxes = [read['box_mm'] for read in geometry if read['checked']]
    for first in range(len(boxes)):
        for second in range(first + 1, len(boxes)):
            if all(min(a[1], b[1]) - max(a[0], b[0]) > TOL_MM for a, b in zip(boxes[first], boxes[second])):
                failures.append(f'solids {first + 1} and {second + 1} overlap in their boxes')
    return {**summary, 'solids': solids, 'colours': colours, 'styled': painted,
            'geometry': readings, 'geometry_checked': all(read['checked'] for read in geometry), 'failures': failures}


def verify_step(path):
    """check_step() for a case: raises ValueError naming the failures; returns the readings."""
    readings = check_step(path)
    if readings['failures']:
        raise ValueError(f'{readings["name"]}: ' + '; '.join(readings['failures']))
    return readings


def _report(readings):
    lines = [f"{readings['name']}: {readings['bytes']} bytes, sha256 {readings['sha256'][:16]}",
             f"schema {readings['schema']}; length in millimetres: {readings['length_unit_mm']}",
             f"entities {readings['entities']}, references {readings['references']}, ids defined twice: {readings['duplicates'] or 'none'}, "
             f"references not defined: {readings['missing'] or 'none'}",
             f"MANIFOLD_SOLID_BREP: {len(readings['solids'])} {readings['solids']}",
             f"COLOUR_RGB: {len(readings['colours'])} different {readings['colours']}",
             f"STYLED_ITEM: {len(readings['styled'])} " + ', '.join(f'{target} -> {colour[0]} {colour[1]}' for _k, target, colour in readings['styled']),
             f"geometry: {'checked' if readings['geometry_checked'] else 'not checked for every solid'}"]
    return lines + [f'  {line}' for line in readings['geometry']]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Write and check assembly.step for Feishu #229.')
    parser.add_argument('output', nargs='?', help='where to write the file')
    parser.add_argument('--side', type=float, default=10.0, help='side of each cube in mm (10)')
    parser.add_argument('--gap', type=float, default=10.0, help='space between the cubes in mm (10)')
    parser.add_argument('--check', metavar='STEP', help='read a file back and check it instead of writing')
    args = parser.parse_args(argv)
    if args.check:
        try:
            readings = check_step(args.check)
        except ValueError as exc:
            print(f'FAILED: {exc}')
            return 1
        print('\n'.join(_report(readings)))
        for failure in readings['failures']:
            print(f'FAILED: {failure}')
        return 1 if readings['failures'] else 0
    if not args.output:
        parser.error('give an output path or --check')
    try:
        written = write_assembly(args.output, side=args.side, gap=args.gap)
    except ValueError as exc:
        print(f'FAILED: {exc}')
        return 1
    print(f"{written['name']}: {written['bytes']} bytes, sha256 {written['sha256']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
