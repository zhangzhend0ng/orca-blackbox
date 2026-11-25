"""#232 checks use synthetic preset bundles and profile directories."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from import_configs_oracle import (DUPLICATES, IMPORTED, TYPES, bundle_presets, checkbox_rows, export_failed,
                                   parameters, profile_presets, verify_import)

PRINTER = {'type': 'machine', 'name': 'U1 bundle', 'printer_model': 'Snapmaker U1', 'nozzle_diameter': '0.8'}
FILAMENT = {'type': 'filament', 'name': 'PLA bundle', 'filament_type': 'PLA', 'filament_settings_id': ['PLA bundle']}
PROCESS = {'type': 'process', 'name': '0.20 bundle', 'layer_height': '0.2', 'wall_loops': '2'}
RESULT = {'title': 'Import result', 'texts': ['Import result', 'There is 1 config imported. (Only non-system and compatible configs)', 'OK']}
ALL = (PRINTER, FILAMENT, PROCESS)


def rows(*presets):
    return [{'kind': p['type'], 'name': p['name'], 'settings': p} for p in presets]


def bundle(path, presets):
    with ZipFile(path, 'w') as out:
        for index, preset in enumerate(presets):
            out.writestr(f'{preset["type"]}/preset_{index}.json', json.dumps(preset))
        out.writestr('metadata.json', json.dumps({'not': 'a preset'}))
    return path


def profile(directory, presets):
    for index, preset in enumerate(presets):
        target = directory / 'user' / 'default' / preset['type'] / f'preset_{index}.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(preset), encoding='utf-8')
    return directory


def test_bundle_and_profile_readers(tmp_path):
    file = bundle(tmp_path / 'printer.orca_printer', [PROCESS, PRINTER, FILAMENT])
    assert [(row['kind'], row['name']) for row in bundle_presets(file)] == [
        ('filament', 'PLA bundle'), ('machine', 'U1 bundle'), ('process', '0.20 bundle')]
    single = tmp_path / 'machine.json'
    single.write_text(json.dumps(PRINTER), encoding='utf-8')
    assert bundle_presets(single)[0]['member'] == 'machine.json'
    assert bundle_presets(bundle(tmp_path / 'empty.zip', [])) == []
    store = profile(tmp_path / 'profile', [PRINTER, PROCESS])
    (store / 'broken.json').write_text('{', encoding='utf-8')
    (store / 'other.json').write_text(json.dumps({'type': 'web', 'name': 'x'}), encoding='utf-8')
    read = profile_presets(store)
    assert [(row['kind'], row['file']) for row in read] == [
        ('machine', 'user/default/machine/preset_0.json'), ('process', 'user/default/process/preset_1.json')]


def test_vendored_user_presets_are_recognised():
    files = sorted((ROOT / 'resources/user/default').glob('*/*.json'))
    if not files:
        pytest.skip('no vendored user presets in this checkout')
    for path in files:
        row, = bundle_presets(path)
        assert row['kind'] == path.parent.name and row['name'] == json.loads(path.read_text(encoding='utf-8-sig'))['name']


def test_parameters_leave_out_the_bookkeeping():
    exported = {'type': 'process', 'name': 'p', 'from': 'User', 'inherits': 'parent', 'version': '2.3.1.2',
                'setting_id': 'old', 'layer_height': '0.2'}
    assert parameters(exported) == {'layer_height': '0.2'}


def test_every_preset_imported_with_its_parameters_passes_the_first_item():
    # The imported preset is written back as the whole inherited config: many more
    # keys, and a new version and id. Only the exported parameters are compared.
    full = lambda preset, extra: {**extra, **preset, 'version': '2.4.0.0', 'setting_id': 'new', 'inherits': 'parent @U1'}
    base = {'line_width': '0.42', 'top_surface_line_width': '0.42'}
    after = rows(full(PRINTER, base), full(FILAMENT, base), full(PROCESS, base))
    report = verify_import(rows(*ALL), [], after, [RESULT])
    assert report[IMPORTED] == 'PASS'
    assert report['reading']['added'] == ['filament/PLA bundle', 'machine/U1 bundle', 'process/0.20 bundle']
    assert report['reading']['key_counts']['process/0.20 bundle'] == {
        'exported_keys': 4, 'imported_keys': 9, 'exported_inherits': None, 'imported_inherits': 'parent @U1'}
    assert report[DUPLICATES] == 'FAIL (not exercised: none of the 3 presets of the config file was in the profile before the import)'


def test_name_clash_needs_a_prompt():
    config = rows(*ALL)
    before = rows({**PRINTER, 'nozzle_diameter': '0.4'})
    prompt = {'title': 'Config', 'texts': ['Preset U1 bundle already exists. Overwrite it or keep the existing one?',
                                           'Yes', 'No', 'Yes to all']}
    report = verify_import(config, before, rows(*ALL), [prompt, RESULT])
    assert report[IMPORTED] == 'PASS' and report[DUPLICATES] == 'PASS'
    assert report['reading']['clashes'] == ['machine/U1 bundle']
    report = verify_import(config, before, rows(*ALL), [RESULT])
    assert report[DUPLICATES] == 'FAIL (1 presets of the config file were already in the profile and no prompt was shown)'
    assert report[IMPORTED] == 'PASS'  # the imported parameters equal the exported ones
    drawn = {'title': 'Snapmaker Orca - Info', 'texts': ['Yes'], 'message': 'Preset U1 bundle already exists'}
    assert verify_import(config, before, rows(*ALL), [drawn, RESULT])[DUPLICATES] == 'PASS'


@pytest.mark.parametrize('after, fragment', [
    (rows(PRINTER, FILAMENT), "1 of 3 presets are not in the profile: ['process/0.20 bundle']"),
    (rows(PRINTER, FILAMENT, {**PROCESS, 'layer_height': '0.3', 'version': '2.4.0.0'}),
     "parameters differ for ['process/0.20 bundle']"),
])
def test_missing_or_changed_preset_fails(tmp_path, after, fragment):
    report = verify_import(rows(*ALL), [], after, [RESULT])
    assert report[IMPORTED].startswith('FAIL') and fragment in report[IMPORTED]


def test_a_kind_that_was_never_exported_fails():
    report = verify_import(rows(FILAMENT, PROCESS), [], rows(FILAMENT, PROCESS), [RESULT])
    assert report[IMPORTED] == 'FAIL (no printer preset was exported or imported)'


def test_result_box_and_readable_config_are_required():
    config = rows(*ALL)
    assert 'no "Import result" dialog was shown' in verify_import(config, [], config, [])[IMPORTED]
    assert 'holds no preset' in verify_import([], [], [], [RESULT])[IMPORTED]
    report = verify_import(config, [], rows(PRINTER, FILAMENT, {**PROCESS, 'wall_loops': '3'}), [RESULT])
    assert report['reading']['changed'] == {'process/0.20 bundle': {'differing_keys': ['wall_loops']}}


def test_refused_export_fails_both_clauses():
    report = export_failed('add file fail Yes')
    assert report[IMPORTED] == 'FAIL (exporting the preset bundle on this build reported "add file fail Yes"; nothing was imported)'
    assert report[DUPLICATES] == 'FAIL (not exercised: nothing was imported)'
    assert export_failed(None)[IMPORTED] == 'FAIL (no printer, filament or process preset could be exported; nothing was imported)'


def test_checkbox_rows_pair_buttons_with_their_labels():
    # Export Preset Bundle dialog as the guest census read it (bundle2-0d7222e7), abridged.
    census = [
        {'class': 'Static', 'text': 'Presets', 'visible': True, 'rect': [783, 443, 883, 459]},
        {'class': 'Button', 'text': '', 'visible': True, 'rect': [903, 443, 921, 461]},
        {'class': 'Static', 'text': TYPES[0], 'visible': True, 'rect': [926, 443, 1112, 461]},
        {'class': 'Static', 'text': 'Printer and all the filament&&process presets.\nCan be shared with others.',
         'visible': True, 'rect': [925, 467, 1309, 496]},
        {'class': 'Button', 'text': '', 'visible': True, 'rect': [903, 563, 921, 581]},
        {'class': 'Static', 'text': TYPES[2], 'visible': True, 'rect': [926, 563, 1027, 581]},
        {'class': 'wxWindowNR', 'text': 'OK', 'visible': True, 'rect': [1104, 711, 1204, 743]},
    ]
    read = checkbox_rows(census)
    assert read['items'] == []
    assert [row['label'] for row in read['types']] == [TYPES[0], TYPES[2]]
    assert [row['checkbox'] for row in read['types']] == [[903, 443, 921, 461], [903, 563, 921, 581]]
    listed = census + [
        {'class': 'Button', 'text': '', 'visible': True, 'rect': [795, 700, 813, 718]},
        {'class': 'Static', 'text': 'Snapmaker U1 (0.8 nozzle)', 'visible': True, 'rect': [820, 700, 1050, 718]},
        {'class': 'Button', 'text': '', 'visible': False, 'rect': [795, 730, 813, 748]},
        {'class': 'Static', 'text': 'scrolled out of view', 'visible': True, 'rect': [820, 730, 950, 748]},
    ]
    assert checkbox_rows(listed)['items'] == [
        {'label': 'Snapmaker U1 (0.8 nozzle)', 'checkbox': [795, 700, 813, 718]}]
