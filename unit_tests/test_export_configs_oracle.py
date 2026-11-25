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
    foreign.write_bytes(zip_bytes({'someone.json': json.dumps(dict(USER[HF], name='someone else',
                                                                  compatible_printers=['other printer'])).encode()}))
    assert oracle.package_facts(foreign, table, kind=KIND, rows=[PRINTER])['members']['someone.json']['error'] == (
        "made for ['other printer'], not for a printer that was ticked ['Snapmaker U1 (0.4 nozzle)']")


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
    assert readings[HF] == {'compared': 8, 'changed': [], 'unchanged': 8, 'spelled_out_only_after': 0, 'keys_after': 8,
                       'baseline': 'as stored in the profile before the export'}
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
    gaps = fails([attempt(broken / 'Process presets.zip', at_export, result_words='add file fail',
                         app_log={'failed_to_add': ['2026-11-26 02:52:40.9 [info] X.json Failed to add file to ZIP archive']})],
                 "the dialog reported 'add file fail'",
                 'the application log could not add X.json to the ZIP archive',
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


def test_a_package_of_a_filament_row_holds_the_presets_of_that_name(tmp_path):
    datadir = profile(tmp_path)  # process presets only: no filament preset is a file of this profile
    tables = {'process': oracle.preset_table(datadir)}
    inside = {'type': 'filament', 'name': 'Generic PLA @U1 0.4 nozzle(feishu_std_cube.3mf)', 'filament_type': 'PLA'}
    other = dict(inside, name='Snapmaker PLA Basic @U1 0.4 nozzle(cube.3mf)')
    path = tmp_path / 'p' / 'Filament presets.zip'
    path.parent.mkdir()
    path.write_bytes(zip_bytes({'a.json': json.dumps(inside).encode(), 'b.json': json.dumps(other).encode()}))
    facts = oracle.package_facts(path, tables, kind='Filament presets(.zip)', rows=['Generic PLA'])
    assert facts['preset_kind'] == 'filament' and facts['rows'] == ['Generic PLA']
    kept, stranger = facts['members']['a.json'], facts['members']['b.json']
    # A preset the project keeps has no file to hold it against; it counts when it is of the name ticked.
    assert kept['stored'] is False and kept['matches_preset'] and 'error' not in kept
    assert stranger['error'] == "'Snapmaker PLA Basic' is not a filament name that was ticked ['Generic PLA']"
    gaps = oracle.package_gaps(facts)
    assert len(gaps) == 1 and gaps[0].endswith(stranger['error'])
    both = oracle.package_facts(path, tables, kind='Filament presets(.zip)', rows=['Generic PLA', 'Snapmaker PLA Basic'])
    assert oracle.package_gaps(both) == []
    wrong = tmp_path / 'wrong' / 'Filament presets.zip'
    wrong.parent.mkdir()
    wrong.write_bytes(zip_bytes({'hf.json': user_file(datadir, HF).read_bytes()}))
    gaps = oracle.package_gaps(oracle.package_facts(wrong, tables, kind='Filament presets(.zip)', rows=[HF]))
    assert len(gaps) == 1 and "a 'process' preset, not a filament one" in gaps[0]
    assert oracle.filament_name('Generic PLA @U1 0.4 nozzle(x.3mf)') == 'Generic PLA'
    assert oracle.filament_name('no at sign') == 'no at sign'


def test_a_process_member_must_be_for_a_printer_that_was_ticked(tmp_path):
    datadir = profile(tmp_path)
    table = oracle.preset_table(datadir)
    elsewhere = tmp_path / 'elsewhere' / 'Process presets.zip'
    elsewhere.parent.mkdir()
    own = dict(USER[FLOW], compatible_printers=['Snapmaker U1 (0.6 nozzle)'])
    elsewhere.write_bytes(zip_bytes({'flow.json': json.dumps(own).encode()}))
    member = oracle.package_facts(elsewhere, table, kind=KIND, rows=[PRINTER])['members']['flow.json']
    assert member['error'] == "made for ['Snapmaker U1 (0.6 nozzle)'], not for a printer that was ticked ['Snapmaker U1 (0.4 nozzle)']"
    good = package(tmp_path / 'good' / 'Process presets.zip', datadir)
    facts = oracle.package_facts(good, table, kind=KIND, rows=[PRINTER])
    assert oracle.package_gaps(facts) == [] and all(m['stored'] for m in facts['members'].values())


def test_the_application_log_is_read_by_its_own_words(tmp_path):
    profile_dir = tmp_path / 'profile'
    log = profile_dir / 'log'
    log.mkdir(parents=True)
    (log / 'a.log').write_text(
        '2026-11-26 02:52:20.1 [info] load config successful and preset name is:X - TEST\n'
        '2026-11-26 02:52:20.2 [info] set_visible_from_appconfig: name Snapmaker U1 (0.4 nozzle), is_visible set to 0\n'
        '2026-11-26 02:52:20.3 [info] set_visible_from_appconfig: name Other printer, is_visible set to 1\n'
        '2026-11-26 02:52:20.4 [info] nothing of interest here\n', encoding='utf-8')
    mark = oracle.app_log_mark(profile_dir)
    with open(log / 'a.log', 'a', encoding='utf-8') as handle:
        handle.write('2026-11-26 02:52:40.9 [info] Generic PLA @U1.json Failed to add file to ZIP archive\n'
                     '2026-11-26 02:52:41.0 [info] archive_filament_preset_to_filestart exprot filament presets\n'
                     '2026-11-26 02:52:41.1 [info] Export filament preset: Y skip because of the filament file path is empty.\n'
                     '2026-11-26 02:52:41.2 [info] Printer preset json add successful: Z\n')
    since = oracle.app_log_lines(profile_dir, mark)
    assert since == [
        '2026-11-26 02:52:40.9 [info] Generic PLA @U1.json Failed to add file to ZIP archive',
        '2026-11-26 02:52:41.0 [info] archive_filament_preset_to_filestart exprot filament presets',
        '2026-11-26 02:52:41.1 [info] Export filament preset: Y skip because of the filament file path is empty.',
        '2026-11-26 02:52:41.2 [info] Printer preset json add successful: Z']
    assert oracle.failed_to_add(since) == since[:1]
    everything = oracle.app_log_lines(profile_dir, extra=oracle.APP_LOG_LOADING, names=('Snapmaker U1', 'X - TEST'))
    assert everything[:2] == [
        '2026-11-26 02:52:20.1 [info] load config successful and preset name is:X - TEST',
        '2026-11-26 02:52:20.2 [info] set_visible_from_appconfig: name Snapmaker U1 (0.4 nozzle), is_visible set to 0']
    assert everything[2:] == since
    text = oracle.app_log_text(profile_dir, [('export 1', since)])
    assert text.startswith('# application log of profile') and 'json add successful (either case)' in text
    assert '# source: log/a.log (' in text and f'## export 1 (4 lines)\n{since[0]}' in text
    assert oracle.app_log_section('the import', ['a']) == ['', '## the import (1 lines)', 'a']
    assert oracle.app_log_lines(tmp_path / 'nowhere') == [] and oracle.app_log_mark(tmp_path / 'nowhere') == {}


def test_what_the_product_said_about_a_failed_export_leads_the_gap():
    attempt = {'kind': 'Filament presets(.zip)', 'row': 'Generic PLA', 'result_words': 'add file fail',
               'package': {'name': 'Filament presets.zip', 'extension': '.zip', 'members': {},
                           'error': 'BadZipFile: File is not a zip file'},
               'app_log': {'failed_to_add': ['2026-11-26 02:52:40.9 [info] G.json Failed to add file to ZIP archive']}}
    assert oracle.export_gaps([attempt]) == [
        "Filament presets(.zip)/Generic PLA: the dialog reported 'add file fail'",
        'Filament presets(.zip)/Generic PLA: the application log could not add G.json to the ZIP archive',
        "Filament presets(.zip)/Generic PLA: 'Filament presets.zip' is not a readable package: BadZipFile: File is not a zip file"]
    # A success box without a failed line says nothing; a file that is no package still fails.
    attempt.update(result_words='Export successful', app_log={})
    assert oracle.export_gaps([attempt]) == [
        "Filament presets(.zip)/Generic PLA: 'Filament presets.zip' is not a readable package: BadZipFile: File is not a zip file"]


def test_a_preset_of_the_project_is_held_against_what_the_package_holds(tmp_path):
    datadir = profile(tmp_path)
    before = {'process': oracle.preset_table(datadir)}  # the filament preset was not a file of the profile
    inside = {'type': 'filament', 'name': 'Generic PLA @U1(x.3mf)', 'filament_type': 'PLA', 'nozzle_temperature': ['220', '220']}
    path = tmp_path / 'p' / 'Filament presets.zip'
    path.parent.mkdir()
    path.write_bytes(zip_bytes({'a.json': json.dumps(inside).encode()}))
    attempt = {'kind': 'Filament presets(.zip)', 'row': 'Generic PLA',
               'package': oracle.package_facts(path, before, kind='Filament presets(.zip)', rows=['Generic PLA']),
               '_members': {'Generic PLA @U1(x.3mf)': inside}}
    landed = tmp_path / 'import-profile'
    write_json(Path(landed, 'user', 'default', 'filament', 'a.json'),
               dict(inside, nozzle_temperature=['220', '220', '220', '220'], sparse_infill_density='15%'))
    after = {'filament': oracle.preset_table(landed, 'filament')}
    assert oracle.import_gaps(before, after, [attempt]) == []
    reading = oracle.import_readings(before, after, [attempt])['Generic PLA @U1(x.3mf)']
    assert reading == {'compared': 2, 'changed': [], 'unchanged': 2, 'spelled_out_only_after': 1, 'keys_after': 3,
                       'baseline': 'as the package holds it, the preset not being a file of the profile'}
    write_json(Path(landed, 'user', 'default', 'filament', 'a.json'), dict(inside, filament_type='PETG'))
    after = oracle.preset_table(landed, 'filament')
    gaps = oracle.import_gaps(before, after, [attempt])
    assert gaps == ['Generic PLA @U1(x.3mf): 1 parameters differ after the import: filament_type: PLA -> PETG']
    assert oracle.import_gaps(before, {'filament': {'kind': 'filament', 'presets': {}}}, [attempt]) == [
        'Generic PLA @U1(x.3mf): not a user preset of the profile after the import']
    without = dict(attempt, _members={})
    assert oracle.import_gaps(before, after, [without]) == [
        'Generic PLA @U1(x.3mf): the package holds a preset that was not a user preset before the export']
    public = oracle.public_attempts([attempt])
    assert '_members' not in public[0] and attempt['_members'] and public[0]['package'] is attempt['package']
