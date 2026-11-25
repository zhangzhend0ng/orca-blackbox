"""#230 checks compare the #242 two-plate project with edited copies and other saved projects."""
import json
from pathlib import Path
import sys
from xml.dom import minidom
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from import_project_oracle import CONFIG, NOTHING_LOST, PLATES, verify_restore

EXPORTED = ROOT / 'docs/runs/evidence/feishu-242-2026-11-25/7bed4701-run1-before.3mf'
PLATE_REMOVED = ROOT / 'docs/runs/evidence/feishu-242-2026-11-25/7bed4701-run1-after.3mf'
TEMPLATE = ROOT / 'fixtures/agent_layer_cube.3mf'
ALL = ('plate_count_equal', 'plate_names_equal', 'objects_on_same_plates', 'world_triangles_equal',
       'object_settings_equal', 'plate_settings_equal', 'project_settings_equal', 'no_object_lost')
GEOMETRY = ('plate_count_equal', 'plate_names_equal', 'objects_on_same_plates', 'world_triangles_equal',
            'plate_settings_equal', 'no_object_lost')


def edited(source, output, member, mutate):
    with ZipFile(source) as src, ZipFile(output, 'w') as dst:
        for entry in src.infolist():
            data = src.read(entry)
            dst.writestr(entry, mutate(data) if entry.filename == member else data)


def move_bravo(data):
    document = minidom.parseString(data)
    item, = [node for node in document.getElementsByTagName('item') if node.getAttribute('objectid') == '4']
    matrix = item.getAttribute('transform').split()
    matrix[9] = str(float(matrix[9]) + 5)
    item.setAttribute('transform', ' '.join(matrix))
    return document.toxml(encoding='utf-8')


def metadata(tag, key, old, new):
    def mutate(data):
        document = minidom.parseString(data)
        nodes = [node for node in document.getElementsByTagName(tag)
                 if node.getAttribute('key') == key and node.getAttribute('value') == old]
        assert nodes
        for node in nodes:
            node.setAttribute('value', new)
        return document.toxml(encoding='utf-8')
    return mutate


def project_setting(data):
    settings = json.loads(data)
    settings['print_settings_id'] = 'another print preset'
    return json.dumps(settings).encode('utf-8')


def test_identical_project_passes_every_item():
    report = verify_restore(EXPORTED, EXPORTED)
    assert all(report['checks'][name] for name in ALL)
    assert list(report['results'].values()) == ['PASS'] * 3
    assert report['detail']['plates'] == {'exported': ['Keep', 'Remove'], 'imported': ['Keep', 'Remove']}
    assert report['detail']['extruders']['exported'] == {'Alpha': '1', 'Bravo': '3'}


def test_empty_template_is_not_a_restore():
    report = verify_restore(EXPORTED, TEMPLATE, start=TEMPLATE)
    assert not any(report['checks'][name] for name in ALL)
    assert all(value.startswith('FAIL') for value in report['results'].values())
    assert report['detail']['start_differs_from_export_in_project_keys'] > 0


def test_deleted_plate_is_not_a_restore():
    # After Delete Plate the object stays in the file without a plate.
    report = verify_restore(EXPORTED, PLATE_REMOVED)
    checks = report['checks']
    assert not checks['plate_count_equal'] and not checks['plate_names_equal'] and not checks['objects_on_same_plates']
    assert checks['no_object_lost'] and checks['world_triangles_equal']
    assert report['detail']['object_plates']['imported'] == {'Alpha': 'Keep', 'Bravo': 'unassigned'}
    assert report['results'][PLATES] == 'FAIL (plate_count_equal, plate_names_equal, objects_on_same_plates)'
    assert report['results'][NOTHING_LOST] == 'PASS'


def test_moved_object_fails_the_triangle_item_only(tmp_path):
    moved = tmp_path / 'moved.3mf'
    edited(EXPORTED, moved, '3D/3dmodel.model', move_bravo)
    report = verify_restore(EXPORTED, moved)
    assert report['results'][PLATES] == 'FAIL (world_triangles_equal)'
    assert report['results'][CONFIG] == 'PASS' and report['results'][NOTHING_LOST] == 'PASS'
    assert report['detail']['objects_with_other_world_triangles'] == ['Bravo']
    assert report['detail']['objects_with_other_mesh'] == []


def test_changed_extruder_fails_the_object_settings_item(tmp_path):
    recoloured = tmp_path / 'recoloured.3mf'
    edited(EXPORTED, recoloured, 'Metadata/model_settings.config', metadata('metadata', 'extruder', '1', '2'))
    report = verify_restore(EXPORTED, recoloured)
    assert report['results'][CONFIG] == 'FAIL (object_settings_equal)'
    assert all(report['checks'][name] for name in GEOMETRY)
    assert report['detail']['object_settings_differences']['Alpha']['object'] == ['extruder']


def test_changed_plate_setting_fails_the_plate_settings_item(tmp_path):
    locked = tmp_path / 'locked.3mf'
    edited(EXPORTED, locked, 'Metadata/model_settings.config', metadata('metadata', 'locked', 'false', 'true'))
    report = verify_restore(EXPORTED, locked)
    assert report['results'][CONFIG] == 'FAIL (plate_settings_equal)'
    assert report['detail']['plate_settings_differences'] == {'Keep': ['locked'], 'Remove': ['locked']}


def test_changed_project_setting_fails_the_project_settings_item(tmp_path):
    other = tmp_path / 'other.3mf'
    edited(EXPORTED, other, 'Metadata/project_settings.config', project_setting)
    report = verify_restore(EXPORTED, other)
    assert report['results'][CONFIG] == 'FAIL (project_settings_equal)'
    assert report['detail']['project_settings_differing_keys'] == 1
    assert report['detail']['project_settings_differing_first'] == ['print_settings_id']


def test_equal_start_settings_cannot_prove_a_restore():
    report = verify_restore(EXPORTED, EXPORTED, start=EXPORTED)
    assert report['results'][CONFIG] == 'FAIL (project_settings_equal)'
    assert report['detail']['start_differs_from_export_in_project_keys'] == 0
    assert 'proves nothing' in report['detail']['project_settings_note']


def test_readings_name_what_the_fixture_does_not_cover():
    detail = verify_restore(EXPORTED, EXPORTED)['detail']
    # Both plates carry the same settings and no object holds a process override.
    assert detail['plate_settings_identical_across_exported_plates'] is True
    assert detail['object_setting_keys_compared'] == ['extruder']
