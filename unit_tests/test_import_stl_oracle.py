"""Controls for tests/import_stl_oracle.py (Feishu #227).

The positive controls are files the application saved on the guest: the #244
project that holds the imported 20 mm STL with the STL itself, and the #201
pair saved before and after a +10 mm move. Every negative control is a copy
of one of those files with one thing changed, or the wrong file.
"""
import math
from pathlib import Path
import shutil
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tests' / 'gui')]
from import_stl_oracle import (  # noqa: E402
    listed_object_names, stl_filter_label, verify_imported, verify_moved, verify_rotated)
from m7x_251_reload_from_disk import write_cube  # noqa: E402

IMPORTED = ROOT / 'docs/runs/evidence/multi-244-254-2026-11-25/win11-test'
MOVED = ROOT / 'docs/runs/evidence/feishu-140-201-202-2026-11-25/row-201-hyperv'
SAVED = IMPORTED / 'e7ba1cd2-run1-imported.3mf'
MESH_MEMBER = '3D/Objects/cube_20mm.stl_2.model'


@pytest.fixture
def source(tmp_path):
    # The application names the object after the file it was given, so the control keeps its real name.
    path = tmp_path / 'cube_20mm.stl'
    shutil.copyfile(IMPORTED / 'e7ba1cd2-run1-cube_20mm.stl', path)
    return path


def _rewrite(before, output, changes):
    """A copy of a saved project with the listed archive members replaced."""
    with ZipFile(before) as src, ZipFile(output, 'w') as dst:
        for info in src.infolist():
            dst.writestr(info, changes.get(info.filename, src.read(info.filename)))
    return output


def _resized(before, output, factor):
    """The same project with every mesh vertex scaled about the origin."""
    mesh = ET.fromstring(ZipFile(before).read(MESH_MEMBER))
    namespace = mesh.tag.split('}')[0] + '}'
    for vertex in mesh.iter(namespace + 'vertex'):
        for axis in 'xyz':
            vertex.set(axis, repr(float(vertex.get(axis)) * factor))
    return _rewrite(before, output, {MESH_MEMBER: ET.tostring(mesh)})


def _placed(before, output, matrix=None, shift=(0.0, 0.0, 0.0)):
    """The same project with its only build item turned by `matrix` (3x3) and moved by `shift`.

    The saved item places a mesh centred on the origin, so its translation is the object's centre."""
    main = ET.fromstring(ZipFile(before).read('3D/3dmodel.model'))
    namespace = main.tag.split('}')[0] + '}'
    items = main.findall(f'{namespace}build/{namespace}item')
    assert len(items) == 1
    values = [float(value) for value in items[0].get('transform').split()]
    assert len(values) == 12
    matrix = matrix or (values[0:3], values[3:6], values[6:9])
    offset = [values[9 + axis] + shift[axis] for axis in range(3)]
    items[0].set('transform', ' '.join(repr(float(value)) for value in (*matrix[0], *matrix[1], *matrix[2], *offset)))
    return _rewrite(before, output, {'3D/3dmodel.model': ET.tostring(main)})


def _turned(before, output, degrees):
    """The same project with its object turned by `degrees` about the vertical axis through its centre."""
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return _placed(before, output, ((cos, -sin, 0.0), (sin, cos, 0.0), (0.0, 0.0, 1.0)))


def test_real_import_is_accepted(source):
    reading = verify_imported(SAVED, source)
    assert reading['dimensions_mm'] == [20.0, 20.0, 20.0]
    assert reading['object_names'] == ['cube_20mm.stl'] and reading['plates'] == 1
    assert reading['printer'] == {'model': 'Snapmaker U1', 'profile': 'Snapmaker U1 (0.8 nozzle)(agent_layer_cube.3mf)'}


def test_nothing_imported_is_rejected(tmp_path, source):
    # The U1 template still carries its 27 mm cube and no imported object.
    with pytest.raises(ValueError, match='mm on each axis'):
        verify_imported(ROOT / 'fixtures/agent_layer_cube.3mf', source)


def test_wrong_size_is_rejected(tmp_path, source):
    with pytest.raises(ValueError, match='mm on each axis'):
        verify_imported(_resized(SAVED, tmp_path / 'thirty.3mf', 1.5), source)


def test_another_stl_is_rejected(tmp_path):
    thirty = tmp_path / 'cube_20mm.stl'
    write_cube(thirty, 30)
    # The saved object is still 20 mm; it no longer holds the STL's own vertices.
    with pytest.raises(ValueError, match='imported mesh'):
        verify_imported(SAVED, thirty)
    with pytest.raises(ValueError, match='unexpected imported source'):
        verify_imported(SAVED, IMPORTED / 'e7ba1cd2-run1-cube_20mm.stl')


def test_project_without_the_selected_printer_is_rejected(source):
    # An earlier #244 attempt saved the import on "Default Printer".
    with pytest.raises(ValueError, match='selected U1 0.8 printer'):
        verify_imported(IMPORTED / '5ea9ba21-run1-imported.3mf', source)


def test_turned_object_is_rejected_as_a_fresh_import(tmp_path, source):
    turned = _turned(SAVED, tmp_path / 'turned.3mf', 45)
    with pytest.raises(ValueError, match='mm on each axis'):
        verify_imported(turned, source)


def test_real_move_is_accepted():
    before, after = MOVED / '1216dc9e-run1-before-save.3mf', MOVED / '1216dc9e-run1-after-save.3mf'
    assert verify_moved(before, after)['delta_mm'] == [10.0, 0.0, 0.0]


def test_unchanged_wrong_axis_and_reversed_moves_are_rejected():
    before, after = MOVED / '1216dc9e-run1-before-save.3mf', MOVED / '1216dc9e-run1-after-save.3mf'
    with pytest.raises(ValueError, match='did not move'):
        verify_moved(before, before)
    with pytest.raises(ValueError, match='did not move'):
        verify_moved(before, after, axis='y')
    with pytest.raises(ValueError, match='did not move'):
        verify_moved(after, before)


def test_synthetic_move_and_move_with_a_resized_mesh(tmp_path, source):
    moved = _placed(SAVED, tmp_path / 'moved.3mf', shift=(10.0, 0.0, 0.0))
    assert verify_moved(SAVED, moved)['delta_mm'] == [10.0, 0.0, 0.0]
    shrunk = _placed(_resized(SAVED, tmp_path / 'small.3mf', 0.5), tmp_path / 'small-moved.3mf',
                     shift=(10.0, 0.0, 0.0))
    with pytest.raises(ValueError, match='did not move'):
        verify_moved(SAVED, shrunk)


def test_turn_by_45_degrees_is_accepted(tmp_path):
    for degrees in (45, -45):
        reading = verify_rotated(SAVED, _turned(SAVED, tmp_path / f'turned{degrees}.3mf', degrees))
        # A cube centred on its own centre looks the same after +45° and after -45° (they differ by 90°).
        assert abs(reading['degrees_about_z']) == 45
        assert reading['after_box_mm'][0][1] - reading['after_box_mm'][0][0] == pytest.approx(20 * math.sqrt(2), abs=0.001)


def test_no_turn_and_a_30_degree_turn_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='not turned by 45'):
        verify_rotated(SAVED, SAVED)
    with pytest.raises(ValueError, match='not turned by 45'):
        verify_rotated(SAVED, _turned(SAVED, tmp_path / 'thirty.3mf', 30))


def test_a_turn_that_lowers_the_object_is_rejected(tmp_path):
    sunk = _placed(_turned(SAVED, tmp_path / 'sunk.3mf', 45), tmp_path / 'sunk-lowered.3mf',
                   shift=(0.0, 0.0, -5.0))
    with pytest.raises(ValueError, match='not inside the printable area'):
        verify_rotated(SAVED, sunk)


def test_stl_filter_is_read_from_the_type_entries():
    assert stl_filter_label(['Choose one or more files', 'Supported files (*.3mf, *.stl, *.oltp)'])
    assert stl_filter_label(['Gcode 3MF files (*.gcode.3mf)']) is None
    assert stl_filter_label([]) is None


def test_object_list_names():
    words = [('Objects', 10, 90, 60, 14), ('cube_20mm.stl', 10, 120, 90, 14), ('Add', 10, 300, 30, 14)]
    assert listed_object_names(words, ['cube_20mm']) == ['cube_20mm.stl']
    assert listed_object_names([('cube', 10, 120, 40, 14), ('20mm', 54, 120, 50, 14)], ['cube_20mm']) == ['cube20mm']
    assert listed_object_names([('cube_20mn', 10, 120, 90, 14)], ['cube_20mm']) == ['cube_20mn']
    for wrong in ([('Bravo', 10, 120, 90, 14)], [('cube', 10, 120, 40, 14)], [('cube_20mm', 1, 1, 1, 1), ('cube_20mm', 1, 9, 1, 1)]):
        with pytest.raises(ValueError, match='names'):
            listed_object_names(wrong, ['cube_20mm'])
