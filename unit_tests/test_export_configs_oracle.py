"""Offline checks of the Feishu #237 oracle against synthetic profiles and packages (no GUI).

The profiles copy the shape of the ones the harness seeds: a user preset that lists only what
it changes and names the system preset it inherits from, system presets that inherit in turn."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))

import export_configs_oracle as oracle  # noqa: E402

KIND = 'Process presets(.zip)'
PRINTER = 'Snapmaker U1 (0.4 nozzle)'
SYSTEM = {
    'fdm_process_U1_common': {'type': 'process', 'name': 'fdm_process_U1_common', 'from': 'system',
                              'instantiation': 'false', 'layer_height': '0.30', 'line_width': '0.42',
                              'top_shell_layers': '7', 'sparse_infill_density': '15%', 'wall_loops': '2'},
    'fdm_process_U1_0.20': {'type': 'process', 'name': 'fdm_process_U1_0.20', 'from': 'system',
                            'inherits': 'fdm_process_U1_common', 'instantiation': 'false',
                            'layer_height': '0.20'},
    'fdm_process_U1_0.24': {'type': 'process', 'name': 'fdm_process_U1_0.24', 'from': 'system',
                            'inherits': 'fdm_process_U1_common', 'instantiation': 'false',
                            'layer_height': '0.24', 'top_shell_layers': '4'},
    '0.20mm Standard @Snapmaker U1 (0.4 nozzle)': {
        'type': 'process', 'name': '0.20mm Standard @Snapmaker U1 (0.4 nozzle)', 'from': 'system',
        'inherits': 'fdm_process_U1_0.20', 'instantiation': 'true', 'setting_id': 'GP004',
        'compatible_printers': [PRINTER]},
    '0.24mm Standard @Snapmaker U1 (0.4 nozzle)': {
        'type': 'process', 'name': '0.24mm Standard @Snapmaker U1 (0.4 nozzle)', 'from': 'system',
        'inherits': 'fdm_process_U1_0.24', 'instantiation': 'true', 'setting_id': 'GP005',
        'compatible_printers': [PRINTER]},
}
USER = {
    '0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST': {
        'type': 'process', 'name': '0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST', 'from': 'User',
        'inherits': '0.20mm Standard @Snapmaker U1 (0.4 nozzle)', 'is_custom_defined': '0',
        'version': '2.3.1.2', 'print_settings_id': '0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST',
        'line_width': '0.45', 'outer_wall_line_width': '0.45', 'enable_overhang_speed': '0'},
    '0.24mm Standard @Snapmaker U1 (0.4 nozzle) - FLOW-TEST': {
        'type': 'process', 'name': '0.24mm Standard @Snapmaker U1 (0.4 nozzle) - FLOW-TEST', 'from': 'User',
        'inherits': '0.24mm Standard @Snapmaker U1 (0.4 nozzle)', 'is_custom_defined': '0',
        'version': '2.3.1.2', 'print_settings_id': '0.24mm Standard @Snapmaker U1 (0.4 nozzle) - FLOW-TEST',
        'line_width': ['0.5', '0.6'], 'top_shell_layers': '6'},
}
HF, FLOW = sorted(USER)
CLAUSE_PACKAGE, CLAUSE_IMPORT = oracle.CONFIGS_CLAUSES


def write_json(path, data):
    """Written the way the product writes a preset: a byte order mark and Windows line ends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\xef\xbb\xbf' + json.dumps(data, indent=2, ensure_ascii=False).replace('\n', '\r\n').encode('utf-8'))


def profile(root, users=None, system=None):
    """<root>/system/Snapmaker/process and <root>/user/default/process filled as given."""
    for name, own in (SYSTEM if system is None else system).items():
        write_json(Path(root, 'system', 'Snapmaker', 'process', f'{name}.json'), own)
    for name, own in (USER if users is None else users).items():
        write_json(Path(root, 'user', 'default', 'process', f'{name}.json'), own)
    return Path(root)


def user_file(datadir, name):
    return Path(datadir, 'user', 'default', 'process', f'{name}.json')


def zip_bytes(files):
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return out.getvalue()


def package(path, datadir, names=None, changes=None):
    """A package as the export writes it: the stored files of the named presets, member by member."""
    files = {f'{name}.json': user_file(datadir, name).read_bytes() for name in (sorted(USER) if names is None else names)}
    for name, value in (changes or {}).items():
        own = json.loads(files[f'{name}.json'].decode('utf-8-sig'))
        own.update(value)
        files[f'{name}.json'] = json.dumps(own).encode('utf-8')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(zip_bytes(files))
    return Path(path)


def attempt(path, table, **more):
    """The case's record of one exported row for a package that already lies at `path`."""
    record = {'kind': KIND, 'row': PRINTER, 'package': oracle.package_facts(path, table)}
    record.update(more)
    return record


def exported(path, datadir, table, **more):
    """The record of a row whose export wrote the stored preset files into `path`."""
    return attempt(package(path, datadir), table, **more)


def test_values_that_mean_the_same_are_one_value():
    assert oracle.same_value('50', ['50']) and oracle.same_value('50', '50,50')
    assert oracle.same_value(['55', '50'], ['55', '50', '50'])
    assert oracle.same_value('0.20', 0.2) and oracle.same_value('true', 1) and oracle.same_value(False, 'false')
    assert not oracle.same_value('0.45', '0.5') and not oracle.same_value(['0.4', '0.6'], ['0.6', '0.4'])
    assert not oracle.same_value(None, '') and oracle.same_value(None, None)
    assert oracle.same_value('PLA', ' PLA ') and not oracle.same_value('PLA', 'PETG')


def test_preset_table_follows_the_inheritance_chain_and_names_what_it_cannot_follow(tmp_path):
    datadir = profile(tmp_path / 'export-profile')
    table = oracle.preset_table(datadir)
    hf, flow = table['presets'][HF], table['presets'][FLOW]
    assert hf['chain'] == ['0.20mm Standard @Snapmaker U1 (0.4 nozzle)', 'fdm_process_U1_0.20', 'fdm_process_U1_common']
    assert hf['inherits'] == '0.20mm Standard @Snapmaker U1 (0.4 nozzle)'
    # What it means: its own values, over its parent's, over the root's; which preset it is stays out.
    assert hf['effective'] == {'layer_height': '0.20', 'line_width': '0.45', 'top_shell_layers': '7',
                               'sparse_infill_density': '15%', 'wall_loops': '2', 'outer_wall_line_width': '0.45',
                               'enable_overhang_speed': '0', 'compatible_printers': [PRINTER]}
    assert flow['effective']['top_shell_layers'] == '6' and flow['effective']['line_width'] == ['0.5', '0.6']
    assert 'print_settings_id' not in hf['effective'] and 'setting_id' not in hf['effective']
    assert hf['sha256'] == sha256(user_file(datadir, HF).read_bytes()).hexdigest()
    assert json.loads(json.dumps(table)) == table  # it is kept as a file


def test_a_preset_whose_parent_is_missing_is_said_so(tmp_path):
    orphan = dict(USER[FLOW], inherits='0.30mm Standard @Snapmaker U1 (0.4 nozzle)')
    users = dict(USER)
    users[FLOW] = orphan
    table = oracle.preset_table(profile(tmp_path, users=users))
    assert table['presets'][FLOW]['unresolved'] == ['0.30mm Standard @Snapmaker U1 (0.4 nozzle)']
    assert table['presets'][FLOW]['effective'] == {'line_width': ['0.5', '0.6'], 'top_shell_layers': '6'}
    # A link missing further up the chain is named as well, the rest of the chain still counts.
    system = dict(SYSTEM, **{'fdm_process_U1_0.24': dict(SYSTEM['fdm_process_U1_0.24'], inherits='gone')})
    table = oracle.preset_table(profile(tmp_path / 'deep', system=system))
    assert table['presets'][FLOW]['unresolved'] == ['gone']
    assert table['presets'][FLOW]['effective']['layer_height'] == '0.24'


def test_an_empty_or_missing_user_folder_is_an_empty_table(tmp_path):
    datadir = profile(tmp_path)
    for path in Path(datadir, 'user').rglob('*.json'):
        path.unlink()
    assert oracle.preset_table(datadir)['presets'] == {}
    assert oracle.preset_table(tmp_path / 'never-made')['presets'] == {}


def test_package_facts_reads_the_package_member_by_member(tmp_path):
    datadir = profile(tmp_path)
    table = oracle.preset_table(datadir)
    facts = oracle.package_facts(package(tmp_path / 'ok' / 'Process presets.zip', datadir), table)
    assert facts['extension'] == '.zip' and facts['bytes'] > 0 and len(facts['sha256']) == 64
    assert sorted(facts['members']) == [f'{HF}.json', f'{FLOW}.json']
    for name, member in facts['members'].items():
        assert member['preset'] == name[:-5] and member['byte_identical'] and member['matches_preset']
        assert member['sha256'] == table['presets'][member['preset']]['sha256']
    # The same preset spelled another way is still that preset; a changed value is not.
    changed = package(tmp_path / 'changed' / 'Process presets.zip', datadir, changes={FLOW: {'line_width': ['0.5', '0.55']}})
    member = oracle.package_facts(changed, table)['members'][f'{FLOW}.json']
    assert not member['byte_identical'] and not member['matches_preset'] and member['differs_in'] == ['line_width']
    spelled = package(tmp_path / 'spelled' / 'Process presets.zip', datadir, changes={HF: {'line_width': '0.450'}})
    member = oracle.package_facts(spelled, table)['members'][f'{HF}.json']
    assert member['matches_preset'] and not member['byte_identical'] and member['differs_in'] == []
    # A file a failed export left is no package; a member that is no preset is said so.
    Path(tmp_path / 'broken').mkdir()
    broken = Path(tmp_path / 'broken' / 'Process presets.zip')
    broken.write_bytes(b'')
    facts = oracle.package_facts(broken, table)
    assert 'BadZipFile' in facts['error'] and facts['members'] == {}
    foreign = tmp_path / 'foreign' / 'Process presets.zip'
    foreign.parent.mkdir()
    foreign.write_bytes(zip_bytes({'someone.json': json.dumps(dict(USER[HF], name='someone else')).encode()}))
    assert oracle.package_facts(foreign, table)['members']['someone.json']['error'] == 'no such user preset in the profile'


def imported_profile(root, datadir, names=None, changes=None, system=None):
    """A profile that has imported the presets: the same system presets, the same user files."""
    users = {}
    for name in (sorted(USER) if names is None else names):
        own = json.loads(user_file(datadir, name).read_text(encoding='utf-8-sig'))
        users[name] = dict(own, **(changes or {}).get(name, {}))
    return profile(root, users=users, system=system)


def test_export_and_import_that_behave_leave_no_gap(tmp_path):
    datadir = profile(tmp_path / 'export-profile')
    at_export = oracle.preset_table(datadir)
    attempts = [exported(tmp_path / 'packages' / 'u1' / 'Process presets.zip', datadir, at_export)]
    after = oracle.preset_table(imported_profile(tmp_path / 'import-profile', datadir))
    gaps = oracle.configs_expectation_gaps(at_export, after, attempts)
    assert gaps == {CLAUSE_PACKAGE: [], CLAUSE_IMPORT: []}
    readings = oracle.import_readings(at_export, after, attempts)
    assert readings[HF] == {'compared': 8, 'changed': [], 'unchanged': 8, 'spelled_out_only_after': 0, 'keys_after': 8}
    # Keys the import spells out without there being a record of them are counted, not judged.
    spelled = imported_profile(tmp_path / 'spelled', datadir, changes={HF: {'wall_loops': '2', 'skirt_loops': 1}})
    after = oracle.preset_table(spelled)
    assert oracle.import_gaps(at_export, after, attempts) == []
    assert oracle.import_readings(at_export, after, attempts)[HF]['spelled_out_only_after'] == 1


def test_import_that_loses_or_changes_a_parameter_fails_only_the_second_clause(tmp_path):
    datadir = profile(tmp_path / 'export-profile')
    at_export = oracle.preset_table(datadir)
    attempts = [exported(tmp_path / 'packages' / 'u1' / 'Process presets.zip', datadir, at_export)]
    # A preset that did not arrive.
    after = oracle.preset_table(imported_profile(tmp_path / 'one-missing', datadir, names=[HF]))
    gaps = oracle.configs_expectation_gaps(at_export, after, attempts)
    assert gaps[CLAUSE_PACKAGE] == []
    assert gaps[CLAUSE_IMPORT] == [f'{FLOW}: not a user preset of the profile after the import']
    # A value that arrived changed.
    after = oracle.preset_table(imported_profile(tmp_path / 'changed', datadir, changes={HF: {'line_width': '0.5'}}))
    gaps = oracle.configs_expectation_gaps(at_export, after, attempts)
    assert len(gaps[CLAUSE_IMPORT]) == 1
    assert ('HF-TEST: 1 parameters differ after the import: line_width: 0.45 -> 0.5'
            in gaps[CLAUSE_IMPORT][0])
    assert gaps[CLAUSE_PACKAGE] == []
    # Another parent, or a parent that is not there, is not the same preset either.
    after = oracle.preset_table(imported_profile(tmp_path / 'reparented', datadir,
                                                 changes={FLOW: {'inherits': '0.20mm Standard @Snapmaker U1 (0.4 nozzle)'}}))
    gaps = oracle.import_gaps(at_export, after, attempts)
    assert any(gap.startswith(f'{FLOW}: inherits') for gap in gaps) and any('parameters differ' in gap for gap in gaps)
    system = {name: own for name, own in SYSTEM.items() if name != 'fdm_process_U1_0.20'}
    after = oracle.preset_table(imported_profile(tmp_path / 'no-parent', datadir, system=system))
    gaps = oracle.import_gaps(at_export, after, attempts)
    assert (f"{HF}: the preset it inherits from is not among the system presets after the import "
            "(fdm_process_U1_0.20)") in gaps
    assert any('layer_height: 0.20 -> None' in gap for gap in gaps)


def test_export_that_lands_nothing_or_a_broken_package_fails_the_first_clause(tmp_path):
    datadir = profile(tmp_path / 'export-profile')
    at_export = oracle.preset_table(datadir)
    after = oracle.preset_table(imported_profile(tmp_path / 'import-profile', datadir))
    good = exported(tmp_path / 'packages' / 'u1' / 'Process presets.zip', datadir, at_export)

    def fails(attempts, *parts):
        gaps = oracle.export_gaps(attempts)
        assert len(gaps) == len(parts), gaps
        for gap, part in zip(gaps, parts):
            assert gap.startswith(f'{KIND}/{PRINTER}: ') and part in gap, gap
        return oracle.configs_expectation_gaps(at_export, after, attempts)

    # The step itself went wrong: the dialog did not behave as measured.
    gaps = fails([{'kind': KIND, 'row': PRINTER, 'error': 'ValueError: pressing OK opened neither', 'package': None}],
                 'ValueError: pressing OK opened neither')
    assert gaps[CLAUSE_PACKAGE] and 'no package file landed' not in gaps[CLAUSE_PACKAGE][0]
    # The product refused and wrote nothing.
    gaps = fails([{'kind': KIND, 'row': PRINTER, 'error': None, 'package': None, 'result_words': 'initialize fail'}],
                 'no package file landed (the dialog reported: initialize fail)')
    assert gaps[CLAUSE_IMPORT] == ['not exercised: no package holding a preset was imported']
    # The product reported a failure and left a file that is no zip.
    broken = Path(tmp_path / 'packages' / 'broken')
    broken.mkdir(parents=True)
    (broken / 'Process presets.zip').write_bytes(b'')
    gaps = fails([attempt(broken / 'Process presets.zip', at_export, result_words='add file fail')],
                 'is not a readable package: BadZipFile')
    assert gaps[CLAUSE_IMPORT] == ['not exercised: no package holding a preset was imported']
    # A package whose member is not the preset the profile stores.
    changed = package(tmp_path / 'packages' / 'changed' / 'Process presets.zip', datadir,
                      changes={FLOW: {'line_width': '0.9'}})
    gaps = fails([attempt(changed, at_export)],
                 f'{FLOW} is not the preset as stored in the profile; it differs in 1 keys: line_width')
    # One good package does not hide a failed one.
    gaps = oracle.export_gaps([good, {'kind': KIND, 'row': 'another printer', 'error': None, 'package': None}])
    assert len(gaps) == 1 and gaps[0].startswith(f'{KIND}/another printer: no package file landed')


def test_a_dialog_that_lists_nothing_fails_both_clauses(tmp_path):
    at_export = oracle.preset_table(profile(tmp_path / 'export-profile'))
    after = oracle.preset_table(profile(tmp_path / 'import-profile', users={}))
    nothing = '"Process presets(.zip)" lists no row in this profile, although 2 custom process presets are on disk'
    gaps = oracle.configs_expectation_gaps(at_export, after, [], nothing_listed=nothing)
    assert gaps == {CLAUSE_PACKAGE: [nothing], CLAUSE_IMPORT: ['not exercised: no package holding a preset was imported']}
    assert oracle.export_gaps([]) == ['no preset was listed to export, so no package was asked for']


def test_a_package_that_is_no_zip_at_all_is_not_a_package(tmp_path):
    datadir = profile(tmp_path)
    at_export = oracle.preset_table(datadir)
    ini = Path(tmp_path / 'config.ini')
    ini.write_text('[print]\nlayer_height = 0.2\n', encoding='utf-8')
    gaps = oracle.export_gaps([attempt(ini, at_export)])
    assert len(gaps) == 1 and "is not a .zip or .ini package" not in gaps[0] and 'not a readable package' in gaps[0]
    rar = ini.with_suffix('.rar')
    rar.write_bytes(b'Rar!\x1a\x07\x00')
    assert oracle.export_gaps([attempt(rar, at_export)])[0].endswith("is not a .zip or .ini package")


@pytest.mark.parametrize('count', [1, 2])
def test_importable_selects_what_holds_a_preset(tmp_path, count):
    datadir = profile(tmp_path)
    at_export = oracle.preset_table(datadir)
    # With one preset exported the package holds one; with both, two.
    names = sorted(USER)[:count]
    good = attempt(package(tmp_path / 'good' / 'Process presets.zip', datadir, names=names), at_export)
    empty = tmp_path / 'empty' / 'Process presets.zip'
    empty.parent.mkdir()
    empty.write_bytes(zip_bytes({'readme.txt': b'nothing here'}))
    ready = oracle.importable([good, attempt(empty, at_export), {'kind': KIND, 'row': PRINTER, 'package': None}])
    assert ready == [good['package']]
