"""#231 checks use synthetic three-cube projects and explicit wrong-file controls."""
from copy import deepcopy
from pathlib import Path
import struct
import sys
from xml.dom import minidom
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from plate_layout_fixture import FACES, _box
from zip_import_cases import build_archive
from zip_import_oracle import (EXPECTED, MEMBERS, remove_stale, temp_collisions, verify_member_digests,
                               verify_object_list, verify_zip_import)

TEMPLATE = ROOT / 'fixtures/agent_layer_cube.3mf'
PLACED = (('cube_10mm', (10, 10, 10), (80, 135)),
          ('cube_20mm', (20, 20, 20), (135, 135)),
          ('cube_30mm', (30, 30, 30), (200, 135)))


def cube_stl(path, size):
    """The same 12 triangles write_cube writes, as a binary STL."""
    points = ((0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0),
              (0, 0, size), (size, 0, size), (size, size, size), (0, size, size))
    with Path(path).open('wb') as stream:
        stream.write(struct.pack('<80sI', b'#231 unit cube', len(FACES)))
        for face in FACES:
            stream.write(struct.pack('<12fH', 0, 0, 0, *(v for i in face for v in points[i]), 0))


def sources(directory):
    Path(directory).mkdir(parents=True, exist_ok=True)
    kept = {}
    for name, size in MEMBERS:
        kept[name] = directory / name
        cube_stl(kept[name], size)
    return kept


def make_project(template, output, specs):
    """One-plate project with one box object per (name, dimensions, centre)."""
    names = ('3D/3dmodel.model', 'Metadata/model_settings.config', '3D/_rels/3dmodel.model.rels')
    with ZipFile(template) as src, ZipFile(output, 'w') as dst:
        model, config, rels = (minidom.parseString(src.read(name)) for name in names)
        resources = model.getElementsByTagName('resources')[0]
        build = model.getElementsByTagName('build')[0]
        plate = config.getElementsByTagName('plate')[0]
        assemble = config.getElementsByTagName('assemble')[0]
        resource_seed = model.getElementsByTagName('object')[0]
        mesh_seed = src.read(resource_seed.getElementsByTagName('component')[0].getAttribute('p:path').lstrip('/'))
        object_seed = config.getElementsByTagName('object')[0]
        for parent, tag in [(resources, 'object'), (build, 'item'), (config, 'object'),
                            (plate, 'model_instance'), (assemble, 'assemble_item'), (rels, 'Relationship')]:
            for element in list(parent.getElementsByTagName(tag)):
                element.parentNode.removeChild(element)
        for index, (label, dimensions, (x, y)) in enumerate(specs, 1):
            part_id, object_id = str(index), str(index + 10)
            path = f'3D/Objects/{label}.model'
            transform = f'1 0 0 0 1 0 0 0 1 {x} {y} 0'
            resource = deepcopy(resource_seed)
            resource.setAttribute('id', object_id)
            component = resource.getElementsByTagName('component')[0]
            component.setAttribute('objectid', part_id)
            component.setAttribute('p:path', '/' + path)
            resources.appendChild(resource)
            item = model.createElement('item')
            for key, value in {'objectid': object_id, 'transform': transform, 'printable': '1'}.items():
                item.setAttribute(key, value)
            build.appendChild(item)
            obj = deepcopy(object_seed)
            obj.setAttribute('id', object_id)
            obj.getElementsByTagName('part')[0].setAttribute('id', part_id)
            for node in obj.getElementsByTagName('metadata'):
                if node.getAttribute('key') == 'name':
                    node.setAttribute('value', label)
            config.documentElement.insertBefore(obj, plate)
            instance = config.createElement('model_instance')
            for key, value in {'object_id': object_id, 'instance_id': '0', 'identify_id': str(90 + index)}.items():
                node = config.createElement('metadata')
                node.setAttribute('key', key)
                node.setAttribute('value', value)
                instance.appendChild(node)
            plate.appendChild(instance)
            assembled = config.createElement('assemble_item')
            for key, value in {'object_id': object_id, 'instance_id': '0',
                               'transform': transform, 'offset': '0 0 0'}.items():
                assembled.setAttribute(key, value)
            assemble.appendChild(assembled)
            rel = rels.createElement('Relationship')
            rel.setAttribute('Target', '/' + path)
            rel.setAttribute('Id', f'rel-{index}')
            rel.setAttribute('Type', 'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel')
            rels.documentElement.appendChild(rel)
            document = minidom.parseString(mesh_seed)
            mesh_object = document.getElementsByTagName('object')[0]
            mesh_object.setAttribute('id', part_id)
            for tag, attrs, values in [('vertex', 'xyz', _box(*dimensions)), ('triangle', ('v1', 'v2', 'v3'), FACES)]:
                for node, row in zip(document.getElementsByTagName(tag), values, strict=True):
                    for axis, value in zip(attrs, row, strict=True):
                        node.setAttribute(axis, str(value))
            dst.writestr(path, document.toxml(encoding='utf-8'))
        for entry in src.infolist():
            if not entry.filename.startswith('3D/Objects/'):
                replaced = {'3D/3dmodel.model': model, 'Metadata/model_settings.config': config,
                            '3D/_rels/3dmodel.model.rels': rels}.get(entry.filename)
                dst.writestr(entry, replaced.toxml(encoding='utf-8') if replaced else src.read(entry))


@pytest.fixture
def saved(tmp_path):
    kept = sources(tmp_path)
    project = tmp_path / 'imported.3mf'
    make_project(TEMPLATE, project, PLACED)
    return project, kept


def test_three_cubes_on_one_plate_pass(saved):
    project, kept = saved
    readings = verify_zip_import(project, kept)
    assert [row['name'] for row in readings['objects']] == ['cube_10mm', 'cube_20mm', 'cube_30mm']
    assert [row['dimensions_mm'] for row in readings['objects']] == [[10, 10, 10], [20, 20, 20], [30, 30, 30]]
    assert readings['plate'] and len(readings['pairs']) == 3 and not any(p['overlap'] for p in readings['pairs'])
    assert EXPECTED.startswith('zip 内 3 个模型全部载入')


@pytest.mark.parametrize('count', [0, 1, 2])
def test_missing_object_rejected(saved, tmp_path, count):
    _project, kept = saved
    partial = tmp_path / 'partial.3mf'
    make_project(TEMPLATE, partial, PLACED[:count])
    with pytest.raises(ValueError, match='not exactly the archive models'):
        verify_zip_import(partial, kept)


@pytest.mark.parametrize('label', ['cube_20mm(1)', 'cube_2\xfcmm', 'Cube_20mm', 'cube_21mm'])
def test_changed_or_garbled_name_rejected(saved, tmp_path, label):
    _project, kept = saved
    renamed = tmp_path / 'renamed.3mf'
    make_project(TEMPLATE, renamed, [(label if name == 'cube_20mm' else name, size, centre)
                                     for name, size, centre in PLACED])
    with pytest.raises(ValueError, match='not exactly the archive models'):
        verify_zip_import(renamed, kept)


def test_wrong_size_rejected(saved, tmp_path):
    _project, kept = saved
    resized = tmp_path / 'resized.3mf'
    make_project(TEMPLATE, resized, [(name, (25, 25, 25) if name == 'cube_20mm' else size, centre)
                                     for name, size, centre in PLACED])
    with pytest.raises(ValueError, match='instead of the source'):
        verify_zip_import(resized, kept)


def test_overlapping_objects_rejected(saved, tmp_path):
    _project, kept = saved
    stacked = tmp_path / 'stacked.3mf'
    make_project(TEMPLATE, stacked, [PLACED[0], ('cube_20mm', (20, 20, 20), (85, 135)), PLACED[2]])
    with pytest.raises(ValueError, match='overlap'):
        verify_zip_import(stacked, kept)


def test_object_outside_bed_rejected(saved, tmp_path):
    _project, kept = saved
    outside = tmp_path / 'outside.3mf'
    make_project(TEMPLATE, outside, [PLACED[0], ('cube_20mm', (20, 20, 20), (-40, 135)), PLACED[2]])
    with pytest.raises(ValueError, match='outside the printable area'):
        verify_zip_import(outside, kept)


def test_template_is_not_an_import_result(saved):
    _project, kept = saved
    with pytest.raises(ValueError, match='not exactly the archive models'):
        verify_zip_import(TEMPLATE, kept)


def test_archive_must_match_retained_sources(tmp_path):
    archive = tmp_path / 'inputs' / 'models.zip'
    kept = build_archive(archive, tmp_path)
    assert [name for name, _sha in verify_member_digests(archive, kept)] == sorted(kept)
    with ZipFile(archive) as bundle:
        assert bundle.namelist()[:1] == ['readme.txt'] and len(bundle.namelist()) == 4
    cube_stl(kept['cube_20mm.stl'], 21)
    with pytest.raises(ValueError, match='do not match the retained sources'):
        verify_member_digests(archive, kept)


def test_object_list_names():
    words = [('Object list', 20, 20, 90, 14), ('cube_10mm', 30, 200, 80, 14),
             ('cube', 30, 240, 30, 14), ('_20mm', 62, 241, 40, 14), ('cube_30mm', 30, 280, 80, 14)]
    assert verify_object_list(words, ['cube_10mm', 'cube_20mm', 'cube_30mm'])['names'] == [
        'cube_10mm', 'cube_20mm', 'cube_30mm']
    for wrong in ([('cube_10mm', 30, 200, 80, 14), ('cube_20mm', 30, 240, 80, 14)],
                  [('cube_10mm', 30, 200, 80, 14), ('cube_20mm', 30, 240, 80, 14), ('cube_31mm', 30, 280, 80, 14)],
                  [('cube_10mm', 30, 200, 80, 14), ('cube_2\xfcmm', 30, 240, 80, 14), ('cube_30mm', 30, 280, 80, 14)]):
        with pytest.raises(ValueError, match='object list does not show'):
            verify_object_list(wrong, ['cube_10mm', 'cube_20mm', 'cube_30mm'])


def test_stale_extraction_removed_only_when_identical(tmp_path):
    kept = sources(tmp_path / 'run')
    temp = tmp_path / 'temp'
    temp.mkdir()
    assert temp_collisions(temp, kept) == []
    (temp / 'cube_10mm.stl').write_bytes(kept['cube_10mm.stl'].read_bytes())
    (temp / 'cube_30mm.stl').write_bytes(b'someone else\'s file')
    assert temp_collisions(temp, kept) == ['cube_10mm.stl', 'cube_30mm.stl']
    assert remove_stale(temp, kept) == ['cube_10mm.stl']
    assert not (temp / 'cube_10mm.stl').exists() and (temp / 'cube_30mm.stl').exists()
    assert temp_collisions(temp, kept) == ['cube_30mm.stl']
