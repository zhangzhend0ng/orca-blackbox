"""#246 checks use the U1 template carrying a cube mesh and explicit wrong-mesh controls."""
from pathlib import Path
import sys
from xml.dom import minidom
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from harness.model_move_pilot import stl_mesh
from repair_model_oracle import (DROPPED, FACES, cube_triangles, edge_report, fix_row, initial_state, judge,
                                 menu_rows, repair_reading, repaired, verify_digests, write_holed_cube)
from zip_import_oracle import digest

TEMPLATE = ROOT / 'fixtures/agent_layer_cube.3mf'
CORNERS = ((0, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 0), (0, 0, 20), (20, 0, 20), (20, 20, 20), (0, 20, 20))
HOLED = tuple(face for index, face in enumerate(FACES) if index != DROPPED)
ROW = {'index': 1, 'label': 'Fix model', 'enabled': True}


def project(output, points, faces):
    """The U1 template carrying one mesh with the given vertices and triangles."""
    with ZipFile(TEMPLATE) as src, ZipFile(output, 'w') as dst:
        for entry in src.infolist():
            data = src.read(entry)
            if entry.filename.startswith('3D/Objects/') and entry.filename.endswith('.model'):
                document = minidom.parseString(data)
                vertices, triangles = (document.getElementsByTagName(tag)[0] for tag in ('vertices', 'triangles'))
                for tag in ('vertex', 'triangle'):
                    for node in list(document.getElementsByTagName(tag)):
                        node.parentNode.removeChild(node)
                for point in points:
                    node = document.createElement('vertex')
                    for axis, value in zip('xyz', point):
                        node.setAttribute(axis, str(value))
                    vertices.appendChild(node)
                for face in faces:
                    node = document.createElement('triangle')
                    for key, value in zip(('v1', 'v2', 'v3'), face):
                        node.setAttribute(key, str(value))
                    triangles.appendChild(node)
                data = document.toxml(encoding='utf-8')
            dst.writestr(entry, data)


@pytest.fixture
def files(tmp_path):
    stl = write_holed_cube(tmp_path / 'cube_holed.stl')
    holed, whole = tmp_path / 'before.3mf', tmp_path / 'repaired.3mf'
    project(holed, CORNERS, HOLED)
    project(whole, CORNERS, FACES)
    return stl, holed, whole


def test_holed_stl_is_open(tmp_path):
    stl = write_holed_cube(tmp_path / 'cube_holed.stl')
    report = edge_report(*stl_mesh(stl.read_bytes()))
    assert report['triangles'] == 11 and report['open_edges'] == 3 and report['closed'] is False
    assert edge_report(CORNERS, FACES) == {'triangles': 12, 'vertices': 8, 'open_edges': 0,
                                           'nonmanifold_edges': 0, 'closed': True}


def test_initial_state_requires_the_open_cube(files):
    stl, holed, whole = files
    assert initial_state(holed, stl) == {'triangles': 11, 'vertices': 8, 'open_edges': 3,
                                         'nonmanifold_edges': 0, 'closed': False, 'missing_triangles': 1}
    with pytest.raises(ValueError, match='not the imported holed cube'):
        initial_state(whole, stl)


def test_repaired_cube_passes(files):
    stl, _holed, whole = files
    reading = repair_reading(whole, stl)
    assert repaired(reading) and reading['dimensions_mm'] == [20, 20, 20]
    assert judge(ROW, reading, True, []) == 'PASS'
    assert judge(ROW, reading, True, ['Following model object has been repaired']) == 'PASS'


def test_still_open_fails(files):
    stl, holed, _whole = files
    reading = repair_reading(holed, stl)
    assert not repaired(reading)
    assert judge(ROW, reading, True, []) == 'FAIL (hole not closed)'


SIDE = ((0, 1, 5), (0, 5, 4))  # the two triangles of the holed face
OTHER_DIAGONAL = tuple(face for face in HOLED if face not in SIDE) + ((0, 1, 4), (1, 5, 4))
DOUBLED = tuple(tuple(2 * value for value in point) for point in CORNERS)
WITH_CENTER_VERTEX = (CORNERS + ((0, 10, 0),), (*HOLED, (0, 1, 8), (1, 5, 8), (5, 0, 8)))


@pytest.mark.parametrize('points,faces', [
    (CORNERS, OTHER_DIAGONAL),  # the hole closed along the other diagonal
    (DOUBLED, FACES),           # a closed cube of another size
    WITH_CENTER_VERTEX,         # closed with an extra vertex on the face
])
def test_closed_but_not_the_original_cube_fails(tmp_path, files, points, faces):
    stl, _holed, _whole = files
    other = tmp_path / 'other.3mf'
    project(other, points, faces)
    reading = repair_reading(other, stl)
    assert reading['closed'] and not repaired(reading)
    assert judge(ROW, reading, True, []) == 'FAIL (not the original cube)'


def test_intact_template_is_not_the_repaired_hole(files):
    stl, holed, _whole = files
    template = repair_reading(TEMPLATE, stl)
    assert template['closed'] and not repaired(template)  # the template cube is another box
    assert judge(ROW, template, True, []) == 'FAIL (not the original cube)'
    assert judge(ROW, repair_reading(holed, stl), True, []) == 'FAIL (hole not closed)'


def test_explicit_failure_prompt_passes_only_when_unrepaired(files):
    stl, holed, whole = files
    prompt = ['Failed to repair following model object', 'cube_holed: The mesh cannot be repaired']
    assert judge(None, repair_reading(holed, stl), False, prompt) == 'PASS'
    # A cancel notice is not a statement that the model cannot be repaired.
    assert judge(ROW, repair_reading(holed, stl), True, ['Repairing was canceled']) == 'FAIL (hole not closed)'
    assert judge(ROW, repair_reading(whole, stl), False, prompt) == 'FAIL (did not finish slicing)'


def test_missing_disabled_or_unsliced():
    assert judge(None, None, True, []) == 'FAIL (no "Fix model" row in the context menu; not the original cube)'
    disabled = {**ROW, 'enabled': False}
    assert judge(disabled, None, True, []) == 'FAIL ("Fix model" row is disabled; not the original cube)'
    assert judge(ROW, {'closed': True, 'is_cube': True, 'same_box': True}, False, []) == (
        'FAIL (did not finish slicing)')


def test_menu_reading():
    rows = [(0, 'Clone', 0), (1, 'Fix model', 0), (2, 'Simplify Model\tCtrl+T', 0), (3, '', 0x800), (4, 'Split', 0x10)]
    read = menu_rows(rows)
    assert [(r['label'], r['enabled']) for r in read[:3]] == [('Clone', True), ('Fix model', True), ('Simplify Model\tCtrl+T', True)]
    assert read[3]['separator'] and read[4]['submenu']
    assert fix_row(rows) == {**ROW, 'separator': False, 'submenu': False}
    assert fix_row([(0, 'Clone', 0), (1, 'Fix model...', 3)])['enabled'] is False
    observed = ['Clone', 'Simplify Model', 'Mesh boolean', 'Center', 'Drop', 'Split', 'Mirror', 'Delete']
    assert fix_row([(index, label, 0) for index, label in enumerate(observed)]) is None
    with pytest.raises(ValueError, match='2 rows'):
        fix_row([(0, 'Fix model', 0), (1, 'Fix Model', 0)])


def test_digest_mismatch_is_rejected(tmp_path, files):
    stl, holed, _whole = files
    kept = {stl: digest(stl), holed: digest(holed)}
    assert verify_digests(kept) == ['before.3mf', 'cube_holed.stl']
    stl.write_bytes(stl.read_bytes()[:-50])
    with pytest.raises(ValueError, match='not the recorded'):
        verify_digests(kept)
