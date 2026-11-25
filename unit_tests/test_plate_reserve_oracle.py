"""Negative controls for Feishu #242, #247 and #252 (without the GUI)."""
from pathlib import Path
import struct
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))

from plate_reserve_oracle import (MAIN, SETTINGS, _CORE, _connected_shells,  # noqa: E402
                                  create_delete_plate_fixture, create_split_fixture,
                                  read_project, verify_delete_plate, verify_f3d_image,
                                  verify_split, verify_split_selection, verify_stl)


def _rewrite_archive(src, dst, edits):
    with ZipFile(src) as archive, ZipFile(dst, 'w') as output:
        for item in archive.infolist():
            raw = archive.read(item)
            if item.filename in edits:
                xml = ET.fromstring(raw)
                edits[item.filename](xml)
                raw = ET.tostring(xml, encoding='utf-8')
            output.writestr(item, raw)


def test_delete_plate_requires_preserving_the_removed_plates_object(tmp_path):
    initial, kept, lost = (tmp_path / filename for filename in ('initial.3mf', 'kept.3mf', 'lost.3mf'))
    create_delete_plate_fixture(ROOT / 'fixtures/feishu_std_cubesfar.3mf', initial)

    def remove_plate(xml):
        xml.remove(xml.findall('plate')[1])

    def remove_bravo_config(xml):
        remove_plate(xml)
        xml.remove(xml.findall('object')[1])

    def remove_bravo_build(xml):
        build = xml.find(_CORE + 'build')
        build.remove(build.findall(_CORE + 'item')[1])

    _rewrite_archive(initial, kept, {SETTINGS: remove_plate})
    _rewrite_archive(initial, lost, {SETTINGS: remove_bravo_config, MAIN: remove_bravo_build})

    assert verify_delete_plate(initial, kept)['objects_after'] == {'Alpha': 'Keep', 'Bravo': 'unassigned'}
    with pytest.raises(ValueError, match='lost or duplicated'):
        verify_delete_plate(initial, lost)
    with pytest.raises(ValueError, match='wrong plate survived'):
        verify_delete_plate(initial, initial)


@pytest.fixture
def joined_shells(tmp_path):
    project = tmp_path / 'two-shells.3mf'
    create_split_fixture(ROOT / 'fixtures/feishu_std_cube.3mf', project)
    model, = read_project(project)[1]
    assert len(_connected_shells(model)) == 2
    return project, model


def test_split_rejects_two_shells_still_in_one_object(joined_shells):
    project, _ = joined_shells
    with pytest.raises(ValueError, match='two independently stored'):
        verify_split(project, project)


def test_split_color_check_rejects_changes_to_both_objects_on_first_selection(tmp_path):
    template = ROOT / 'fixtures/feishu_std_cubesfar.3mf'
    baseline, left, both, wrong = (tmp_path / name for name in ('baseline.3mf', 'left.3mf', 'both.3mf', 'wrong.3mf'))
    for project, slots in [(baseline, ('1', '1')), (left, ('2', '1')),
                           (both, ('2', '3')), (wrong, ('2', '2'))]:
        def set_slots(xml):
            for obj, slot in zip(xml.findall('object'), slots, strict=True):
                obj.find("metadata[@key='extruder']").set('value', slot)

        _rewrite_archive(template, project, {SETTINGS: set_slots})
    assert verify_split_selection(baseline, left, both)['slots_after_both'] == ['2', '3']
    with pytest.raises(ValueError, match='did not independently update'):
        verify_split_selection(baseline, wrong, both)


def _write_stl(path, points, faces):
    with path.open('wb') as file:
        file.write(struct.pack('<80sI', b'Offline geometry control', len(faces)))
        for face in faces:
            vertices = [coordinate for index in face for coordinate in points[index]]
            file.write(struct.pack('<12fH', 0.0, 0.0, 0.0, *vertices, 0))


def test_export_rejects_missing_facet_even_when_stl_has_same_bounding_box(tmp_path, joined_shells):
    project, model = joined_shells
    complete, short = tmp_path / 'complete.stl', tmp_path / 'missing-facet.stl'
    _write_stl(complete, model.points, model.faces)
    _write_stl(short, model.points, model.faces[:-1])
    assert verify_stl(project, complete)['triangle_count'] == 24
    with pytest.raises(ValueError, match='does not contain all original triangles'):
        verify_stl(project, short)


@pytest.mark.parametrize('color', [(255, 255, 255, 0), (127, 127, 127, 255)])
def test_viewer_rejects_empty_and_opaque_placeholder_images(tmp_path, color):
    path = tmp_path / 'placeholder.png'
    Image.new('RGBA', (800, 600), color).save(path)
    with pytest.raises(ValueError, match='bounded foreground mesh'):
        verify_f3d_image(path)
