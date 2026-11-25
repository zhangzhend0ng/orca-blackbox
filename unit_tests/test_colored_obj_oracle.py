"""Controls for tests/colored_obj_oracle.py (Feishu #228).

The positive controls are the files the application saved on the guest with
one thing replaced through zipfile: the #227 project (one imported 20 mm STL)
with its mesh exchanged for the fixture's two boxes and their faces painted,
and the #236 G-code with one tool change inserted in the shape the real
five-tool export 0ac8ba5d shows. Every negative control is one of those with
one thing changed, or the untouched file. The #202 project is used as it was
saved: it carries ``paint_color`` values the decoder has to read.
"""
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests' / 'gui')]
from colored_obj_cases import affirmative, write_fixture  # noqa: E402
from colored_obj_oracle import (  # noqa: E402
    decode_paint, filament_readings, GEOMETRIES, material_triangles, mesh_geometry, painted_readings,
    read_colored_project, verify_filament_change, verify_painted_import)

EVIDENCE = ROOT / 'docs/runs/evidence'
REAL_227 = EVIDENCE / 'feishu-227-2026-11-26/11858f17-run1-imported.3mf'
REAL_236 = EVIDENCE / 'feishu-236-2026-11-26/48e3aa7d-run1-plate.gcode'
REAL_PAINT = EVIDENCE / 'feishu-140-201-202-2026-11-25/row-202-hyperv/7a7a584f-after-save-as.3mf'
CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PROD = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
MAIN = '3D/3dmodel.model'
MESH = '3D/Objects/cube_20mm.stl_2.model'
SETTINGS = 'Metadata/model_settings.config'
PROJECT = 'Metadata/project_settings.config'
# A tool change as the U1 export 0ac8ba5d writes it mid-print.
CHANGE = ['; Change Tool0 -> Tool1 (layer 1)', 'G91', 'G1 Z1.5 F1800', 'G90', 'G1 F21000',
          'M109 S220 T1', 'M400', 'T1', 'G90']


def encode_state(state):
    """The paint value of an unsplit face painted with filament `state`, from the bit layout
    TriangleSelector::serialize and FacetsAnnotation::get_triangle_as_string describe."""
    if state < 3:
        return format(state << 2, 'X')
    chunks, rest = [], state - 3
    while rest >= 15:
        chunks.append('F')
        rest -= 15
    chunks.append(format(rest, 'X'))
    return ''.join(reversed(chunks)) + 'C'


def _rewrite(source, target, members):
    """Copy a saved 3MF, replacing (or adding) the members `members` maps to new bytes."""
    with ZipFile(source) as src, ZipFile(target, 'w', ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info.filename, members.get(info.filename, src.read(info.filename)))
        for name, raw in members.items():
            if name not in src.namelist():
                dst.writestr(name, raw)


def _mesh(faces, object_id='1'):
    """A mesh member whose triangles are `(corners, paint value or None)`."""
    ET.register_namespace('', CORE[1:-1])
    model = ET.Element(CORE + 'model', {'unit': 'millimeter'})
    mesh = ET.SubElement(ET.SubElement(ET.SubElement(model, CORE + 'resources'), CORE + 'object', {'id': object_id}),
                         CORE + 'mesh')
    vertices, triangles = ET.SubElement(mesh, CORE + 'vertices'), ET.SubElement(mesh, CORE + 'triangles')
    index = {}
    for corners, paint in faces:
        ids = []
        for corner in corners:
            if tuple(corner) not in index:
                index[tuple(corner)] = str(len(index))
                ET.SubElement(vertices, CORE + 'vertex', dict(zip('xyz', (str(value) for value in corner))))
            ids.append(index[tuple(corner)])
        attrs = dict(zip(('v1', 'v2', 'v3'), ids))
        if paint is not None:
            attrs['paint_color'] = paint
        ET.SubElement(triangles, CORE + 'triangle', attrs)
    return ET.tostring(model, encoding='utf-8', xml_declaration=True)


def _settings(raw, extruder='1'):
    root = ET.fromstring(raw)
    for node in (root.find('object'), root.find('object/part')):
        for row in node.findall('metadata'):
            if row.get('key') == 'extruder':
                node.remove(row)
        node.insert(0, ET.Element('metadata', {'key': 'extruder', 'value': extruder}))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _project(raw, colours):
    settings = json.loads(raw)
    assert len(settings['filament_colour']) >= 2, 'the real project names two filaments at least'
    settings['filament_colour'][:2] = list(colours)
    return json.dumps(settings).encode('utf-8')


def _default(material, _number):
    return 1 if material == 'red' else 2


def painted_project(target, painter=None, extruder='1', colours=('#FF0000', '#0000FF'), geometry='two-boxes'):
    """The real #227 project with its mesh replaced by the fixture's, each face painted as
    `painter(material, number)` says (the first material with filament 1, the second with 2)."""
    choose = painter or _default
    faces = [(face, encode_state(choose(material, number)))
             for material, triangles in material_triangles(geometry).items() for number, face in enumerate(triangles)]
    with ZipFile(REAL_227) as archive:
        old = {name: archive.read(name) for name in (MESH, SETTINGS, PROJECT)}
    _rewrite(REAL_227, target, {MESH: _mesh(faces), SETTINGS: _settings(old[SETTINGS], extruder),
                                PROJECT: _project(old[PROJECT], colours)})
    return Path(target)


# --- the paint value -----------------------------------------------------------

def test_decoder_reads_the_paint_the_application_saved():
    with ZipFile(REAL_PAINT) as archive:
        models = [ET.fromstring(archive.read(name)) for name in archive.namelist() if name.endswith('.model')]
    values = {triangle.get('paint_color') for model in models for triangle in model.iter(CORE + 'triangle')} - {None}
    assert len(values) >= 2
    states = {state for value in values for state in decode_paint(value)}
    assert len({state for state in states if state}) >= 2
    census = read_colored_project(REAL_PAINT)
    assert set(census['triangle_attributes']['paint_color']) == values


@pytest.mark.parametrize('state', [1, 2, 3, 4, 15, 16, 17, 18, 32, 33, 40])
def test_paint_value_round_trips(state):
    assert decode_paint(encode_state(state)) == [state]


@pytest.mark.parametrize('raw', ['FC', '44', '4C4', 'G4', ''])
def test_paint_value_that_is_not_one_tree_is_refused(raw):
    with pytest.raises(ValueError):
        decode_paint(raw)


# --- the fixture ---------------------------------------------------------------

def _read_obj(path):
    vertices, uvs, groups, current = [], [], {}, None
    for line in path.read_text(encoding='ascii').split('\n'):
        parts = line.split()
        if not parts or parts[0].startswith('#'):
            continue
        if parts[0] == 'v':
            vertices.append(tuple(map(float, parts[1:4])))
        elif parts[0] == 'vt':
            uvs.append(tuple(map(float, parts[1:3])))
        elif parts[0] == 'usemtl':
            current = parts[1]
            groups.setdefault(current, [])
        elif parts[0] == 'f':
            groups[current].append(tuple(tuple(vertices[int(c.split('/')[0]) - 1]) for c in parts[1:4]))
    return vertices, uvs, groups


def _png_pixels(raw):
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    chunks, pos = [], 8
    while pos < len(raw):
        size, kind = struct.unpack('>I4s', raw[pos:pos + 8])
        body = raw[pos + 8:pos + 8 + size]
        assert struct.unpack('>I', raw[pos + 8 + size:pos + 12 + size])[0] == zlib.crc32(kind + body) & 0xffffffff
        chunks.append((kind, body))
        pos += 12 + size
    return (struct.unpack('>IIBBBBB', chunks[0][1]),
            zlib.decompress(b''.join(body for kind, body in chunks if kind == b'IDAT')))


@pytest.mark.parametrize('geometry', sorted(GEOMETRIES))
def test_fixture_is_the_geometry_the_oracle_expects(tmp_path, geometry):
    reading = write_fixture(tmp_path, geometry=geometry)
    assert reading['texture_referenced'] and reading['obj_has_uv'] and reading['geometry'] == geometry
    for name, record in reading['files'].items():
        raw = (tmp_path / name).read_bytes()
        assert len(raw) == record['bytes'] and record['sha256'] == hashlib.sha256(raw).hexdigest()
        assert name.endswith('.png') or b'\r' not in raw
    vertices, uvs, groups = _read_obj(tmp_path / 'model.obj')
    assert groups == material_triangles(geometry)
    assert len(vertices) == VERTICES[geometry] and len(uvs) == 4
    corners = [corner for line in (tmp_path / 'model.obj').read_text(encoding='ascii').split('\n')
               if line.startswith('f ') for corner in line.split()[1:]]
    assert len(corners) == 6 * FACES[geometry]
    assert all(1 <= int(c.split('/')[0]) <= VERTICES[geometry] and 1 <= int(c.split('/')[1]) <= 4 for c in corners)
    assert (tmp_path / 'model.mtl').read_text(encoding='ascii').split('\n') == [
        '# Feishu #228: two materials', 'newmtl red', 'Ka 0 0 0', 'Kd 1 0 0', 'map_Kd texture.png',
        '', 'newmtl blue', 'Ka 0 0 0', 'Kd 0 0 1', '']
    header, pixels = _png_pixels((tmp_path / 'texture.png').read_bytes())
    assert header == (16, 16, 8, 2, 0, 0, 0)
    assert pixels == (b'\x00' + b'\xff\x00\x00' * 16) * 16


def test_control_fixture_has_no_texture_and_no_uv(tmp_path):
    first = write_fixture(tmp_path)
    before = (tmp_path / 'texture.png').read_bytes()
    control = write_fixture(tmp_path, 'model_kd', texture=False, uv=False)
    assert set(control['files']) == {'model_kd.obj', 'model_kd.mtl'}
    assert set(first['files']) == {'model.obj', 'model.mtl', 'texture.png'}
    assert (tmp_path / 'texture.png').read_bytes() == before
    text = (tmp_path / 'model_kd.obj').read_text(encoding='ascii')
    vertices, uvs, groups = _read_obj(tmp_path / 'model_kd.obj')
    assert 'mtllib model_kd.mtl' in text and 'map_Kd' not in text and not uvs and vertices
    assert groups == material_triangles()
    assert 'map_Kd' not in (tmp_path / 'model_kd.mtl').read_text(encoding='ascii')


def test_affirmative_button_is_found_by_id_or_by_one_name():
    def child(text, id_, enabled=True):
        return {'text': text, 'id': id_, 'enabled': enabled, 'visible': True}
    ok = child('Confirm', 5104)
    assert affirmative([child('Skip Matching', 6000), ok]) is ok
    assert affirmative([child('Skip Matching', 6000), child('Import', 7)])['text'] == 'Import'
    assert affirmative([child('Skip Matching', 6000)]) is None
    assert affirmative([child('OK', 7), child('Yes', 8)]) is None
    assert affirmative([child('OK', 7, enabled=False)]) is None


# --- clause 1 ------------------------------------------------------------------

FACES = {'two-boxes': 12, 'split-cube': 10}
VERTICES = {'two-boxes': 16, 'split-cube': 12}
# In the two-boxes fixture four triangles lie on the wall the two boxes share.
UNDER_CENTRES = {'two-boxes': {'red': {'1': 10, 'inner wall': 2}, 'blue': {'2': 10, 'inner wall': 2}},
                 'split-cube': {'red': {'1': 10}, 'blue': {'2': 10}}}


@pytest.mark.parametrize('geometry', sorted(GEOMETRIES))
def test_each_geometry_is_a_closed_outward_cube_split_at_the_origin(geometry):
    vertices, faces = mesh_geometry(geometry)
    edges = Counter(tuple(sorted((face[index], face[(index + 1) % 3]))) for face in faces for index in range(3))
    assert set(edges.values()) == {2} and len(faces) == 2 * FACES[geometry] and len(vertices) == VERTICES[geometry]
    volume = sum(_tetrahedron(vertices[index] for index in face[:3]) for face in faces)
    assert abs(volume - 8000.0) < 1e-6
    groups = material_triangles(geometry)
    assert all(corner[0] <= 0 for corner in sum(groups['red'], ())) and all(corner[0] >= 0 for corner in sum(groups['blue'], ()))
    with pytest.raises(ValueError):
        mesh_geometry('sphere')


def _tetrahedron(corners):
    a, b, c = corners
    return (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6


@pytest.mark.parametrize('geometry', sorted(GEOMETRIES))
def test_painted_project_is_accepted(tmp_path, geometry):
    reading = verify_painted_import(painted_project(tmp_path / 'painted.3mf', geometry=geometry), None,
                                    material_triangles(geometry))
    assert reading['filaments'] == {'red': 1, 'blue': 2} and reading['object_names'] == ['cube_20mm.stl']
    assert reading['parts'][0]['triangles'] == 2 * FACES[geometry] and reading['extruder_is_smallest_filament']
    assert reading['triangle_attribute_names'] == ['paint_color', 'v1', 'v2', 'v3']
    assert {name: row['faces'] for name, row in reading['paint_states'].items()} == {'1': FACES[geometry], '2': FACES[geometry]}
    assert reading['under_centres'] == UNDER_CENTRES[geometry]


def _by_material(mapping):
    return lambda material, _number: mapping[material]


def test_same_filament_on_both_materials_is_refused(tmp_path):
    with pytest.raises(ValueError, match='different_filaments'):
        verify_painted_import(painted_project(tmp_path / 'same.3mf', _by_material({'red': 1, 'blue': 1})))


def test_unpainted_faces_are_refused(tmp_path):
    with pytest.raises(ValueError, match='first_material_one_filament'):
        verify_painted_import(painted_project(tmp_path / 'bare.3mf', _by_material({'red': 0, 'blue': 0})))


def test_one_material_split_over_two_filaments_is_refused(tmp_path):
    with pytest.raises(ValueError, match='first_material_one_filament'):
        verify_painted_import(painted_project(tmp_path / 'split.3mf', lambda material, number: (
            1 + number % 2 if material == 'red' else 2)))


def test_same_colour_for_both_filaments_is_refused(tmp_path):
    with pytest.raises(ValueError, match='different_filament_colours'):
        verify_painted_import(painted_project(tmp_path / 'grey.3mf', colours=('#FFFFFF', '#FFFFFF')))


def test_real_single_volume_project_without_paint_is_refused():
    with pytest.raises(ValueError, match='faces_are_the_fixture'):
        verify_painted_import(REAL_227)


def test_object_split_in_two_parts_is_refused(tmp_path):
    target = painted_project(tmp_path / 'two.3mf')
    with ZipFile(target) as archive:
        main, settings = ET.fromstring(archive.read(MAIN)), ET.fromstring(archive.read(SETTINGS))
    ET.register_namespace('p', PROD[1:-1])
    components = main.find(f'{CORE}resources/{CORE}object/{CORE}components')
    blue = copy.deepcopy(components[0])
    blue.set('objectid', '3')
    blue.set(PROD + 'path', '/3D/Objects/blue.model')
    components.append(blue)
    part = copy.deepcopy(settings.find('object/part'))
    part.set('id', '3')
    part.find("metadata[@key='name']").set('value', 'blue')
    part.find("metadata[@key='extruder']").set('value', '2')
    settings.find('object').append(part)
    groups = material_triangles()
    _rewrite(target, tmp_path / 'two-parts.3mf', {
        MAIN: ET.tostring(main, encoding='utf-8', xml_declaration=True),
        SETTINGS: ET.tostring(settings, encoding='utf-8', xml_declaration=True),
        '3D/Objects/blue.model': _mesh([(face, encode_state(2)) for face in groups['blue']], object_id='3'),
        MESH: _mesh([(face, encode_state(1)) for face in groups['red']])})
    reading = painted_readings(tmp_path / 'two-parts.3mf')
    assert 'one part' in reading['error'] and not reading['checks']


# --- clause 2 ------------------------------------------------------------------

def gcode_with_change(target, block=CHANGE, after=20):
    """The real #236 G-code with `block` inserted before the `after`-th extruding move of layer 1."""
    lines = [line.rstrip('\r') for line in REAL_236.read_text(encoding='utf-8').split('\n')]
    first = next(number for number, line in enumerate(lines) if line.startswith(';LAYER_CHANGE'))
    count = 0
    for number in range(first, len(lines)):
        code = lines[number].split(';', 1)[0]
        if code.startswith(('G1', 'G2', 'G3')) and ' E' in code and (' X' in code or ' Y' in code):
            count += 1
            if count == after:
                lines[number:number] = block
                break
    Path(target).write_text('\n'.join(lines), encoding='utf-8')
    return Path(target)


@pytest.fixture
def imported(tmp_path):
    return painted_readings(painted_project(tmp_path / 'painted.3mf'))


def test_two_filaments_with_a_change_between_them_are_accepted(tmp_path, imported):
    reading = verify_filament_change(gcode_with_change(tmp_path / 'two.gcode'), imported)
    assert reading['tools_extruding'] == [0, 1] and reading['changes_between_them'] == 1
    assert reading['per_tool']['0']['extruding_moves'] > 0 and reading['per_tool']['1']['extruding_moves'] > 0


def test_monochrome_gcode_is_refused(imported):
    with pytest.raises(ValueError, match='two_filaments_print'):
        verify_filament_change(REAL_236, imported)
    reading = filament_readings(REAL_236, imported)
    assert reading['tools_extruding'] == [0] and reading['change_count'] == 0


def test_tool_selected_but_never_extruding_is_refused(tmp_path, imported):
    with pytest.raises(ValueError, match='two_filaments_print'):
        verify_filament_change(gcode_with_change(tmp_path / 'idle.gcode', block=['T1', 'T0']), imported)


def test_change_to_a_filament_the_model_is_not_painted_with_is_refused(tmp_path):
    painted = painted_readings(painted_project(tmp_path / 'other.3mf', _by_material({'red': 2, 'blue': 3})))
    with pytest.raises(ValueError, match='two_filaments_print'):
        verify_filament_change(gcode_with_change(tmp_path / 'other.gcode'), painted)


def test_gcode_without_project_filaments_is_not_judged(tmp_path):
    reading = filament_readings(gcode_with_change(tmp_path / 'orphan.gcode'), {'checks': {}, 'filaments': {}})
    assert reading['error'] and not reading['checks']
    with pytest.raises(ValueError):
        verify_filament_change(REAL_236, {'checks': {}})
