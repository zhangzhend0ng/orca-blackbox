"""#232 checks use the vendored system presets and synthetic profile directories."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from import_configs_oracle import (ARCHIVE, DUPLICATES, IMPORTED, INI, NAMES, VENDOR, build_config, bundle_presets,
                                   checkbox_rows, effective_preset, profile_presets, standalone_preset,
                                   template_presets, verify_import, vendor_directory, write_ini)

TEMPLATE = ROOT / 'fixtures/agent_layer_cube.3mf'
VENDOR_DIR = ROOT / 'resources' / VENDOR
RESULT = {'title': 'Import result', 'texts': ['Import result', 'There is 1 config imported. (Only non-system and compatible configs)', 'OK']}
OWN = {'type': 'machine', 'name': 'U1 bundle', 'printer_model': 'Snapmaker U1', 'nozzle_diameter': '0.8'}
FIL = {'type': 'filament', 'name': 'PLA bundle', 'filament_type': 'PLA', 'filament_settings_id': ['PLA bundle']}
PROC = {'type': 'process', 'name': '0.20 bundle', 'layer_height': '0.2', 'wall_loops': '2'}
ALL = (OWN, FIL, PROC)


def rows(*presets):
    return [{'kind': p['type'], 'name': p['name'], 'settings': p} for p in presets]


@pytest.fixture(scope='module')
def vendored():
    if not (VENDOR_DIR / 'machine').is_dir():
        pytest.skip('no vendored Snapmaker presets in this checkout')
    return VENDOR_DIR


def test_template_names_three_system_presets():
    sources = template_presets(TEMPLATE)
    assert sources == {'machine': 'Snapmaker U1 (0.8 nozzle)', 'process': '0.40 Standard @Snapmaker U1 (0.8 nozzle)',
                       'filament': 'Generic PETG @U1 0.8 nozzle'}


def test_inheritance_chain_is_merged(vendored):
    assert vendor_directory([ROOT / 'resources'], template_presets(TEMPLATE)) == VENDOR_DIR
    values, chain = effective_preset(vendored, 'machine', 'Snapmaker U1 (0.8 nozzle)')
    assert chain == ['Snapmaker U1 (0.8 nozzle)', 'fdm_U1', 'fdm_toolchanger', 'fdm_klipper']
    assert values['printer_model'] == 'Snapmaker U1' and values['printer_variant'] == '0.8'
    root, _ = effective_preset(vendored, 'machine', 'fdm_klipper')
    assert len(root) < len(values)  # the nozzle preset adds to what its ancestors carry
    with pytest.raises(ValueError, match='missing system preset'):
        effective_preset(vendored, 'machine', 'no such printer')
    with pytest.raises(ValueError, match='no vendor directory'):
        vendor_directory([ROOT / 'docs'], template_presets(TEMPLATE))


def test_standalone_preset_is_a_root_preset_of_its_own_kind(vendored, tmp_path):
    sources = template_presets(TEMPLATE)
    for kind in ('machine', 'filament', 'process'):
        preset, _chain = standalone_preset(vendored, kind, sources[kind])
        assert preset['name'] == NAMES[kind] and preset['inherits'] == '' and preset['from'] == 'User'
        assert preset['type'] == kind and preset['version'].count('.') == 3
        assert 'setting_id' not in preset and 'instantiation' in preset
        others = {'machine': ('print_settings_id', 'filament_settings_id'), 'process': ('printer_settings_id', 'filament_settings_id'),
                  'filament': ('printer_settings_id', 'print_settings_id')}[kind]
        assert not any(key in preset for key in others)
        row, = bundle_presets(_write(tmp_path / f'loose_{kind}.json', preset))
        assert (row['kind'], row['name']) == (kind, NAMES[kind])


def _write(path, preset):
    path.write_text(json.dumps(preset), encoding='utf-8')
    return path


def test_config_zip_holds_three_presets(vendored, tmp_path):
    built = build_config(vendored, template_presets(TEMPLATE), tmp_path, tmp_path / 'inputs' / ARCHIVE)
    assert sorted(built['presets']) == ['filament', 'machine', 'process']
    with ZipFile(tmp_path / 'inputs' / ARCHIVE) as bundle:
        assert bundle.namelist() == [f'{NAMES[kind]}.json' for kind in ('machine', 'filament', 'process')]
    read = bundle_presets(tmp_path / 'inputs' / ARCHIVE)
    assert [(row['kind'], row['name']) for row in read] == sorted((kind, NAMES[kind]) for kind in NAMES)
    loose = [row for path in sorted(tmp_path.glob('bb_test_*.json')) for row in bundle_presets(path)]
    loose.sort(key=lambda row: (row['kind'], row['name']))
    assert [(row['kind'], row['name'], len(row['settings'])) for row in loose] == [
        (row['kind'], row['name'], len(row['settings'])) for row in read]
    write_ini(tmp_path, built['presets'])
    text = (tmp_path / INI).read_text(encoding='utf-8')
    assert text.startswith('[print:BB Test Process]\n') and '[printer:BB Test Printer]' in text
    assert '[filament:BB Test Filament]' in text and text.count('[') >= 3


def test_every_preset_imported_with_its_parameters_passes_the_first_item():
    # The imported preset is written back as the whole inherited config: many more
    # keys, a new version and id, and a number written differently (0.40 and 0.4).
    def full(preset, extra):
        return {**extra, **preset, 'version': '2.4.0.0', 'setting_id': 'new', 'inherits': ''}
    base = {'line_width': '0.42', 'top_surface_line_width': '0.42'}
    after = rows(full(OWN, base), full(FIL, base), full({**PROC, 'layer_height': '0.20'}, base))
    report = verify_import(rows(*ALL), [], after, [RESULT])
    assert report[IMPORTED] == 'PASS'
    assert report['reading']['added'] == ['filament/PLA bundle', 'machine/U1 bundle', 'process/0.20 bundle']
    assert report['reading']['key_counts']['process/0.20 bundle'] == {
        'exported_keys': 4, 'imported_keys': 9, 'exported_inherits': None, 'imported_inherits': ''}
    assert report[DUPLICATES] == 'FAIL (not exercised: none of the 3 presets of the config file was in the profile before the import)'


def test_second_import_needs_a_prompt():
    config, first = rows(*ALL), rows(*ALL)
    prompt = {'title': 'Config', 'texts': ['Preset U1 bundle already exists. Overwrite it or keep the existing one?',
                                           'Yes', 'No', 'Yes to all']}
    report = verify_import(config, first, first, [prompt, RESULT])
    assert report[IMPORTED] == 'PASS' and report[DUPLICATES] == 'PASS'
    assert report['reading']['clashes'] == ['filament/PLA bundle', 'machine/U1 bundle', 'process/0.20 bundle']
    report = verify_import(config, first, first, [RESULT])
    assert report[DUPLICATES] == 'FAIL (3 presets of the config file were already in the profile and no prompt was shown)'
    drawn = {'title': 'Snapmaker Orca - Info', 'texts': ['Yes'], 'message': 'Preset U1 bundle already exists'}
    assert verify_import(config, first, first, [drawn, RESULT])[DUPLICATES] == 'PASS'


@pytest.mark.parametrize('after, fragment', [
    (rows(OWN, FIL), "1 of 3 presets are not in the profile: ['process/0.20 bundle']"),
    (rows(OWN, FIL, {**PROC, 'layer_height': '0.3'}), "parameters differ for ['process/0.20 bundle']"),
])
def test_missing_or_changed_preset_fails(after, fragment):
    report = verify_import(rows(*ALL), [], after, [RESULT])
    assert report[IMPORTED].startswith('FAIL') and fragment in report[IMPORTED]


def test_a_kind_that_was_never_imported_fails():
    report = verify_import(rows(FIL, PROC), [], rows(FIL, PROC), [RESULT])
    assert report[IMPORTED] == 'FAIL (no printer preset was exported or imported)'


def test_result_box_and_readable_config_are_required():
    config = rows(*ALL)
    assert 'no "Import result" dialog was shown' in verify_import(config, [], config, [])[IMPORTED]
    assert 'holds no preset' in verify_import([], [], [], [RESULT])[IMPORTED]
    report = verify_import(config, [], rows(OWN, FIL, {**PROC, 'wall_loops': '3'}), [RESULT])
    assert report['reading']['changed'] == {'process/0.20 bundle': {'differing_keys': ['wall_loops']}}


def test_profile_reader_knows_on_disk_presets(tmp_path):
    # A preset file on disk has no type key (measured on the vendored user presets).
    files = sorted((ROOT / 'resources/user/default').glob('*/*.json'))
    if files:
        for path in files:
            row, = bundle_presets(path)
            assert row['kind'] == path.parent.name
    store = tmp_path / 'profile'
    for index, preset in enumerate((OWN, PROC)):
        target = store / 'user' / 'default' / preset['type'] / f'preset_{index}.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(preset), encoding='utf-8')
    (store / 'broken.json').write_text('{', encoding='utf-8')
    (store / 'other.json').write_text(json.dumps({'type': 'web', 'name': 'x'}), encoding='utf-8')
    assert [(row['kind'], row['file']) for row in profile_presets(store)] == [
        ('machine', 'user/default/machine/preset_0.json'), ('process', 'user/default/process/preset_1.json')]


def test_checkbox_rows_pair_buttons_with_their_labels():
    # Export Preset Bundle dialog as the guest census read it (bundle2-0d7222e7), abridged.
    census = [
        {'class': 'Static', 'text': 'Presets', 'visible': True, 'rect': [783, 443, 883, 459]},
        {'class': 'Button', 'text': '', 'visible': True, 'rect': [903, 443, 921, 461]},
        {'class': 'Static', 'text': 'Printer config bundle(.orca_printer)', 'visible': True, 'rect': [926, 443, 1112, 461]},
        {'class': 'Static', 'text': 'Printer and all the filament&&process presets.\nCan be shared with others.',
         'visible': True, 'rect': [925, 467, 1309, 496]},
        {'class': 'wxWindowNR', 'text': 'OK', 'visible': True, 'rect': [1104, 711, 1204, 743]},
    ]
    read = checkbox_rows(census)
    assert read['items'] == [] and [row['label'] for row in read['types']] == ['Printer config bundle(.orca_printer)']
    listed = census + [
        {'class': 'Button', 'text': '', 'visible': True, 'rect': [795, 700, 813, 718]},
        {'class': 'Static', 'text': 'Snapmaker U1 (0.8 nozzle)', 'visible': True, 'rect': [820, 700, 1050, 718]},
        {'class': 'Button', 'text': '', 'visible': False, 'rect': [795, 730, 813, 748]},
        {'class': 'Static', 'text': 'scrolled out of view', 'visible': True, 'rect': [820, 730, 950, 748]},
    ]
    assert checkbox_rows(listed)['items'] == [
        {'label': 'Snapmaker U1 (0.8 nozzle)', 'checkbox': [795, 700, 813, 718]}]
