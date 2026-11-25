"""#232 checks use synthetic preset bundles and profile directories."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from import_configs_oracle import DUPLICATES, IMPORTED, bundle_presets, profile_presets, verify_import

PRINTER = {'type': 'machine', 'name': 'U1 bundle', 'printer_model': 'Snapmaker U1', 'nozzle_diameter': '0.8'}
FILAMENT = {'type': 'filament', 'name': 'PLA bundle', 'filament_type': 'PLA', 'filament_settings_id': ['PLA bundle']}
PROCESS = {'type': 'process', 'name': '0.20 bundle', 'layer_height': '0.2', 'wall_loops': '2'}
RESULT = {'title': 'Import result', 'texts': ['Import result', 'There is 1 config imported. (Only non-system and compatible configs)', 'OK']}


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
        target = directory / 'user' / preset['type'] / f'preset_{index}.json'
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
        ('machine', 'user/machine/preset_0.json'), ('process', 'user/process/preset_1.json')]


def test_every_preset_imported_with_its_parameters_passes_the_first_item(tmp_path):
    config, before = rows(PRINTER, FILAMENT, PROCESS), []
    after = rows({**PRINTER, 'setting_id': 'added by the product'}, FILAMENT, PROCESS)
    report = verify_import(config, before, after, [RESULT])
    assert report[IMPORTED] == 'PASS'
    assert report['reading']['added'] == ['filament/PLA bundle', 'machine/U1 bundle', 'process/0.20 bundle']
    assert report[DUPLICATES] == 'FAIL (not exercised: none of the 3 presets of the config file was in the profile before the import)'


def test_name_clash_needs_a_prompt(tmp_path):
    config = rows(PRINTER, FILAMENT, PROCESS)
    before = rows({**PRINTER, 'nozzle_diameter': '0.4'})
    prompt = {'title': 'Config', 'texts': ['Preset U1 bundle already exists. Overwrite it or keep the existing one?',
                                           'Yes', 'No', 'Yes to all']}
    report = verify_import(config, before, rows(PRINTER, FILAMENT, PROCESS), [prompt, RESULT])
    assert report[IMPORTED] == 'PASS' and report[DUPLICATES] == 'PASS'
    assert report['reading']['clashes'] == ['machine/U1 bundle']
    report = verify_import(config, before, rows(PRINTER, FILAMENT, PROCESS), [RESULT])
    assert report[DUPLICATES] == 'FAIL (1 presets of the config file were already in the profile and no prompt was shown)'
    assert report[IMPORTED] == 'PASS'  # the imported parameters equal the exported ones


@pytest.mark.parametrize('after, fragment', [
    (rows(PRINTER, FILAMENT), "1 of 3 presets are not in the profile: ['process/0.20 bundle']"),
    (rows(PRINTER, FILAMENT, {**PROCESS, 'layer_height': '0.3'}), "parameters differ for ['process/0.20 bundle']"),
])
def test_missing_or_changed_preset_fails(tmp_path, after, fragment):
    report = verify_import(rows(PRINTER, FILAMENT, PROCESS), [], after, [RESULT])
    assert report[IMPORTED].startswith('FAIL') and fragment in report[IMPORTED]


def test_result_box_and_readable_config_are_required():
    config = rows(PRINTER)
    assert 'no "Import result" dialog was shown' in verify_import(config, [], config, [])[IMPORTED]
    assert 'holds no preset' in verify_import([], [], [], [RESULT])[IMPORTED]
    assert verify_import(config, [], rows({**PRINTER, 'nozzle_diameter': '0.4'}), [RESULT])['reading']['changed'] == {
        'machine/U1 bundle': {'differing_keys': ['nozzle_diameter'], 'extra_keys': []}}
