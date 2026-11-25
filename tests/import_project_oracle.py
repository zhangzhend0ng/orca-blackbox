"""Offline disk evidence for Feishu #230 project import.

Import menu path at sm-v2.4.0 (read-only upstream): MainFrame.cpp:2609-2611
binds "Import 3MF/STL/STEP/SVG/OBJ/AMF..." to Plater::add_model();
Plater.cpp:18004-18055 (add_model) calls GUI_App::import_model and then
load_files(paths, LoadStrategy::LoadModel, false): Plater.cpp:18054-18055 ->
19161 -> 11507. The wxArrayString overload whose Single3MF case calls
open_3mf_file (Plater.cpp:19578-19583) is not on this path.
"""
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from plate_reserve_oracle import read_project

PLATES = '盘数与对象完整还原'
CONFIG = '各对象工艺/耗材配置与导出前一致'
NOTHING_LOST = '无丢失'
MODEL_SETTINGS = 'Metadata/model_settings.config'
PROJECT_SETTINGS = 'Metadata/project_settings.config'
# Objects are matched by name, and a part's matrix is its placement (compared
# through the world triangles). The source* keys record where a part came
# from. Everything else on an object or part is a process or filament setting.
BOOKKEEPING = ('name', 'matrix')
PRESET_KEYS = ('printer_settings_id', 'print_settings_id', 'filament_settings_id')


def _is_setting(key):
    return key not in BOOKKEEPING and not key.startswith('source')


def _metadata(node):
    return {row.get('key'): row.get('value') for row in node.findall('metadata')}


def _diff(before, after):
    """Keys whose values differ or that only one side has."""
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def project_facts(path):
    """Plates, per-instance world triangles and the three setting levels of a saved project."""
    plates, instances = read_project(path)
    with ZipFile(path) as bundle:
        config = ET.fromstring(bundle.read(MODEL_SETTINGS))
        settings = json.loads(bundle.read(PROJECT_SETTINGS))
    objects, plate_rows = {}, []
    for row in config.findall('object'):
        head = _metadata(row)
        objects[head['name']] = {
            'metadata': head,
            'parts': [{'id': part.get('id'), 'subtype': part.get('subtype'), **_metadata(part)}
                      for part in row.findall('part')]}
    for plate in config.findall('plate'):
        meta = _metadata(plate)
        plate_rows.append({'name': meta.get('plater_name') or meta.get('plater_id'),
                           'settings': {key: value for key, value in meta.items() if key != 'plater_id'}})
    return {'plates': list(plates), 'names': [item.name for item in instances],
            'objects': {item.name: {'plate': item.plate, 'extruder': item.extruder,
                                    'world_triangles': item.world_faces, 'shape': item.shape}
                        for item in instances},
            'object_rows': objects, 'plate_rows': plate_rows, 'project_settings': settings}


def _object_settings(row):
    return ({key: value for key, value in row['metadata'].items() if _is_setting(key)},
            [{key: value for key, value in part.items() if _is_setting(key)} for part in row['parts']])


def _settings_diff(before, after):
    head, parts = _diff(before[0], after[0]), []
    if len(before[1]) != len(after[1]):
        parts.append(f'part count {len(before[1])} -> {len(after[1])}')
    parts += [f'part {index}: {_diff(x, y)}' for index, (x, y) in enumerate(zip(before[1], after[1])) if x != y]
    return {'object': head, 'parts': parts}


def _verdict(checks, names):
    failed = [name for name in names if not checks[name]]
    return 'PASS' if not failed else 'FAIL (' + ', '.join(failed) + ')'


def verify_restore(exported: Path, imported: Path, start: Path | None = None) -> dict:
    """Compare an imported project with the exported one, item by item.

    `start` is the project the import was made into. When its project
    settings equal the exported ones, an equal result cannot tell a restore
    from an untouched project, so the project-level check fails.
    """
    before, after = project_facts(exported), project_facts(imported)
    common = [name for name in before['names'] if name in after['objects']]
    moved = [name for name in common
             if before['objects'][name]['world_triangles'] != after['objects'][name]['world_triangles']]
    plate_diff = {}
    for row in before['plate_rows']:
        same = [other for other in after['plate_rows'] if other['name'] == row['name']]
        plate_diff[row['name']] = 'plate missing' if not same else _diff(row['settings'], same[0]['settings'])
    object_diff = {name: _settings_diff(_object_settings(before['object_rows'][name]),
                                        _object_settings(after['object_rows'][name])) for name in common}
    compared = sorted({key for name in common for key in _object_settings(before['object_rows'][name])[0]})
    project_diff = _diff(before['project_settings'], after['project_settings'])
    same_names = sorted(before['names']) == sorted(after['names'])
    checks = {
        'plate_count_equal': len(after['plates']) == len(before['plates']),
        'plate_names_equal': after['plates'] == before['plates'],
        'objects_on_same_plates': same_names and all(
            before['objects'][name]['plate'] == after['objects'][name]['plate'] for name in common),
        'world_triangles_equal': same_names and not moved,
        'object_settings_equal': same_names and not any(d['object'] or d['parts'] for d in object_diff.values()),
        'plate_settings_equal': not plate_diff or not any(plate_diff.values()),
        'project_settings_equal': not project_diff,
        'no_object_lost': all(after['names'].count(name) >= before['names'].count(name) for name in before['names']),
    }
    first_plate = [row['settings'] for row in before['plate_rows']]
    detail = {
        'plates': {'exported': before['plates'], 'imported': after['plates']},
        'object_plates': {'exported': {n: before['objects'][n]['plate'] or 'unassigned' for n in before['names']},
                          'imported': {n: after['objects'][n]['plate'] or 'unassigned' for n in after['names']}},
        'objects_with_other_world_triangles': moved,
        'objects_with_other_mesh': [name for name in common if before['objects'][name]['shape'] != after['objects'][name]['shape']],
        'extruders': {'exported': {n: before['objects'][n]['extruder'] for n in before['names']},
                      'imported': {n: after['objects'][n]['extruder'] for n in after['names']}},
        'object_setting_keys_compared': compared,
        'object_settings_differences': {name: d for name, d in object_diff.items() if d['object'] or d['parts']},
        'plate_settings_differences': {name: d for name, d in plate_diff.items() if d},
        'plate_settings_identical_across_exported_plates': len(first_plate) > 1 and all(
            {k: v for k, v in row.items() if 'file' not in k and k != 'plater_name'}
            == {k: v for k, v in first_plate[0].items() if 'file' not in k and k != 'plater_name'}
            for row in first_plate[1:]),
        'project_settings_differing_keys': len(project_diff),
        'project_settings_differing_first': project_diff[:40],
        'preset_ids': {'exported': {k: before['project_settings'].get(k) for k in PRESET_KEYS},
                       'imported': {k: after['project_settings'].get(k) for k in PRESET_KEYS}},
    }
    if start is not None:
        differing = _diff(project_facts(start)['project_settings'], before['project_settings'])
        detail['start_differs_from_export_in_project_keys'] = len(differing)
        detail['start_differs_from_export_first'] = differing[:20]
        if not differing:
            checks['project_settings_equal'] = False
            detail['project_settings_note'] = 'start project has the exported project settings; equality proves nothing'
    return {'checks': checks, 'detail': detail, 'results': {
        PLATES: _verdict(checks, ('plate_count_equal', 'plate_names_equal', 'objects_on_same_plates',
                                  'world_triangles_equal')),
        CONFIG: _verdict(checks, ('object_settings_equal', 'plate_settings_equal', 'project_settings_equal')),
        NOTHING_LOST: _verdict(checks, ('no_object_lost',)),
    }}

