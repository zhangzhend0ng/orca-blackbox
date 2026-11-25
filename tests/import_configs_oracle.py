"""Offline disk evidence for Feishu #232 config import.

Import path at sync/softfever-20261010, the source the guest build's prompts match:
File > Import > Import Configs... is MainFrame::load_config_file (GUI/MainFrame.cpp:4273),
whose chooser offers *.json, *.zip, *.orca_printer, *.orca_bundle and *.orca_filament
and hands the chosen files to PresetBundle::import_presets (libslic3r/PresetBundle.cpp:1911).
That loads a single preset JSON file (:1926) or, for the bundle and zip suffixes, every
JSON member of the archive (:1930); any other file, an .ini included, is ignored. A preset
is read as JSON only (import_json_presets :2086; the ini line is commented out at :2083),
needs a version (:2090), and its kind comes from printer_settings_id, print_settings_id
or filament_settings_id (:2094-2102). A name clash asks through override_confirm (:2123)
and answering no skips the preset (:2126); a preset with an empty inherits becomes a
custom root preset (:2146) that is saved as a whole config (:2189).

Tag sm-v2.4.0 has the same logic: MainFrame.cpp:3461, PresetBundle.cpp:935, 944-948,
1032-1035, 1039, 1042-1047, 1058, 1060-1063, 1077-1087, 1110. It only lacks .orca_bundle.
"""
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

IMPORTED = '导入成功，3 个预设出现在对应列表且参数正确'
DUPLICATES = '同名重复时按产品既有策略提示（覆盖/重命名）'
KINDS = ('machine', 'filament', 'process')
RESULT_TITLE = 'Import result'  # MessageDialog of MainFrame::load_config_file
# A prompt counts as the product's name-clash strategy when it says that the preset
# exists and offers what to do with it.
CLASH = ('already', 'exist', 'overwrite', 'rename', 'replace')
# What a preset file carries besides its parameters: its identity, its parent and
# bookkeeping. An imported preset is written back as the whole inherited config, so
# the parent, the version and the id may be rewritten.
BOOKKEEPING = ('type', 'name', 'from', 'inherits', 'is_custom_defined', 'version', 'setting_id',
               'instantiation', 'modified_time')
KIND_NAMES = {'machine': 'printer', 'filament': 'filament', 'process': 'process'}
VENDOR = 'Snapmaker'
NAMES = {'machine': 'BB Test Printer', 'filament': 'BB Test Filament', 'process': 'BB Test Process'}
ID_KEYS = {'machine': 'printer_settings_id', 'filament': 'filament_settings_id', 'process': 'print_settings_id'}
VERSION = '2.4.0.0'
ARCHIVE = 'bb_three.zip'
INI = 'bb_three.ini'
# A preset file on disk has no "type" key: its kind is the folder it sits in, or
# the settings id it carries (measured on the vendored user presets).
SIGNATURE = (('machine', 'printer_settings_id'), ('filament', 'filament_settings_id'),
             ('process', 'print_settings_id'))
LIMIT = 4 * 1024 * 1024


def _kind(data, where):
    if data.get('type') in KINDS:
        return data['type']
    for name in str(where).replace('\\', '/').lower().split('/'):
        if name == 'printer':
            return 'machine'
        if name in KINDS:
            return name
    return next((kind for kind, key in SIGNATURE if key in data), None)


def _preset(data, where=''):
    if not isinstance(data, dict) or not isinstance(data.get('name'), str):
        return None
    kind = _kind(data, where)
    return {'kind': kind, 'name': data['name'], 'settings': data} if kind else None


def bundle_presets(path):
    """Presets of a config file: preset JSON files inside a zip, or one preset JSON file."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        rows = []
        with ZipFile(path) as bundle:
            for entry in bundle.infolist():
                if entry.filename.lower().endswith('.json'):
                    try:
                        data = json.loads(bundle.read(entry))
                    except ValueError:
                        continue
                    preset = _preset(data, entry.filename)
                    if preset:
                        rows.append({**preset, 'member': entry.filename})
    except BadZipFile:
        preset = _preset(json.loads(raw.decode('utf-8-sig')), path.parent.name)
        rows = [{**preset, 'member': path.name}] if preset else []
    return sorted(rows, key=lambda row: (row['kind'], row['name']))


def profile_presets(datadir):
    """Every preset stored in a profile directory, which is what the preset lists are built from."""
    rows = []
    for path in sorted(Path(datadir).rglob('*.json')):
        try:
            if path.stat().st_size > LIMIT:
                continue
            preset = _preset(json.loads(path.read_text(encoding='utf-8-sig')), path.relative_to(datadir).as_posix())
        except (OSError, ValueError):
            continue
        if preset:
            rows.append({**preset, 'file': path.relative_to(datadir).as_posix()})
    return sorted(rows, key=lambda row: (row['kind'], row['name']))


def template_presets(project):
    """Names of the printer, the process and the first filament preset a project 3MF is set to."""
    with ZipFile(project) as bundle:
        settings = json.loads(bundle.read('Metadata/project_settings.config'))
    first = settings['filament_settings_id']
    return {'machine': settings['printer_settings_id'], 'process': settings['print_settings_id'],
            'filament': first[0] if isinstance(first, list) else first}


def effective_preset(vendor_dir, kind, name):
    """Values of a system preset: its own over those of the presets it inherits from."""
    chain, current, seen = [], name, set()
    while current:
        if current in seen:
            raise ValueError(f'{kind}/{name}: circular inherits')
        seen.add(current)
        path = Path(vendor_dir) / kind / f'{current}.json'
        if not path.is_file():
            raise ValueError(f'missing system preset {path}')
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        chain.append(data)
        current = data.get('inherits') or ''
    values = {}
    for data in reversed(chain):
        values.update({key: value for key, value in data.items() if key not in ('name', 'inherits')})
    return values, [data.get('name') for data in chain]


def standalone_preset(vendor_dir, kind, source):
    """A user preset JSON that carries the parameters of the system preset `source`
    under a name of its own, as a custom root preset (no inherits)."""
    values, chain = effective_preset(vendor_dir, kind, source)
    body = {key: value for key, value in values.items() if key not in BOOKKEEPING and not key.endswith('_settings_id')}
    preset = {'type': kind, 'name': NAMES[kind], 'from': 'User', 'version': VERSION, 'inherits': '',
              'instantiation': 'true',
              ID_KEYS[kind]: [NAMES[kind]] if kind == 'filament' else NAMES[kind], **body}
    return preset, chain


def build_config(vendor_dir, sources, work, archive):
    """Write the three preset JSON files next to the evidence and the zip the product imports.
    Returns the presets and the inheritance chain of each."""
    built = {'chains': {}, 'presets': {}}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive, 'w', ZIP_DEFLATED) as out:
        for kind in KINDS:
            preset, chain = standalone_preset(vendor_dir, kind, sources[kind])
            built['chains'][kind] = chain
            built['presets'][kind] = preset
            loose = work / f'bb_test_{kind}.json'
            loose.write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding='utf-8')
            out.write(loose, f'{NAMES[kind]}.json')
    return built


def write_ini(work, presets):
    """The config file the Feishu text names: three sections in a traditional .ini bundle.
    sm-v2.4.0 has no code path that loads it (see the module docstring); it is kept as evidence."""
    lines = []
    for section, kind in (('print', 'process'), ('filament', 'filament'), ('printer', 'machine')):
        lines.append(f'[{section}:{NAMES[kind]}]')
        lines += [f'{key} = {json.dumps(value, ensure_ascii=False)}' for key, value in presets[kind].items()]
        lines.append('')
    (work / INI).write_text('\n'.join(lines), encoding='utf-8')


def vendor_directory(candidates, sources):
    """The first vendor directory that holds the template's printer preset."""
    for candidate in candidates:
        folder = Path(candidate) / VENDOR
        if (folder / 'machine' / f'{sources["machine"]}.json').is_file():
            return folder
    raise ValueError(f'no vendor directory with machine/{sources["machine"]}.json under {list(map(str, candidates))}')


def parameters(settings):
    """The parameter values of a preset: everything but its bookkeeping."""
    return {name: value for name, value in settings.items() if name not in BOOKKEEPING}


def _number(value):
    try:
        return float(value) if isinstance(value, (int, float, str)) and str(value).strip() else None
    except ValueError:
        return None


def _same(left, right):
    """Equal values; numbers written differently count as equal (0.40 and 0.4)."""
    if isinstance(left, list) or isinstance(right, list):
        return isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right))
    a, b = _number(left), _number(right)
    if a is not None and b is not None:
        return abs(a - b) <= 1e-9 * max(1.0, abs(a))
    return left == right


def _key(row):
    return row['kind'], row['name']


def verify_import(config, before, after, dialogs) -> dict:
    """Every preset of the config files must be in the profile afterwards with the
    parameter values it was exported with, each of the three kinds must be among them,
    and a name clash must bring a prompt.

    `config`, `before` and `after` are preset lists (bundle_presets, profile_presets),
    `dialogs` the [{'title', 'texts', 'message'}] the product showed after the import.
    The imported preset holds the whole inherited config, so only the exported
    parameters are compared; extra keys of the imported preset are counted, not failed."""
    wanted = {_key(row): row['settings'] for row in config}
    had = {_key(row) for row in before}
    now = {_key(row): row['settings'] for row in after}
    missing = sorted('/'.join(key) for key in wanted if key not in now)
    changed, sizes = {}, {}
    for key, settings in wanted.items():
        if key not in now:
            continue
        differing = sorted(name for name, value in parameters(settings).items()
                           if name not in now[key] or not _same(value, now[key][name]))
        sizes['/'.join(key)] = {'exported_keys': len(settings), 'imported_keys': len(now[key]),
                                'exported_inherits': settings.get('inherits'), 'imported_inherits': now[key].get('inherits')}
        if differing:
            changed['/'.join(key)] = {'differing_keys': differing[:40]}
    result = next((row for row in dialogs if RESULT_TITLE in row['title']), None)
    clashes = sorted('/'.join(key) for key in wanted if key in had)
    prompts = [row for row in dialogs if any(word in ' '.join(row['texts'] + [row.get('message', '')]).casefold()
                                            for word in CLASH)]
    problems = []
    if not wanted:
        problems.append('the config file holds no preset that the reader recognises')
    for kind in KINDS:
        if wanted and not any(row['kind'] == kind for row in config):
            problems.append(f'no {KIND_NAMES[kind]} preset was exported or imported')
    if result is None:
        problems.append(f'no "{RESULT_TITLE}" dialog was shown')
    if missing:
        problems.append(f'{len(missing)} of {len(wanted)} presets are not in the profile: {missing[:6]}')
    if changed:
        problems.append(f'parameters differ for {sorted(changed)[:6]}')
    if not clashes:
        second = f'FAIL (not exercised: none of the {len(wanted)} presets of the config file was in the profile before the import)'
    elif prompts:
        second = 'PASS'
    else:
        second = f'FAIL ({len(clashes)} presets of the config file were already in the profile and no prompt was shown)'
    return {IMPORTED: 'PASS' if not problems else 'FAIL (' + '; '.join(problems) + ')',
            DUPLICATES: second,
            'reading': {'config': [_key(row) for row in config],
                        'added': ['/'.join(key) for key in sorted(set(now) - had)],
                        'missing': missing, 'changed': changed, 'key_counts': sizes, 'clashes': clashes,
                        'prompt_dialogs': [[row['title'], row.get('message'), *row['texts'][:12]] for row in prompts],
                        'result_dialog': None if result is None else [result['title'], result.get('message'),
                                                                        *result['texts'][:12]]}}


def checkbox_rows(controls):
    """Pair every small textless Button with the Static written to its right on the same row.

    `controls` is describe(hwnd) output of the Export Preset Bundle dialog, which this
    case no longer drives (CreatePresetsDialog.cpp:306-315, sm-v2.4.0)."""
    boxes = [c for c in controls if c['class'] == 'Button' and not c['text'] and c['visible']
             and c['rect'][2] - c['rect'][0] <= 24 and c['rect'][3] - c['rect'][1] <= 24]
    labels = [c for c in controls if c['class'] == 'Static' and c['text'] and c['visible']]
    items, radios = [], []
    for box in boxes:
        left, top, right, bottom = box['rect']
        middle = (top + bottom) / 2
        beside = [s for s in labels if s['rect'][0] >= right - 2 and s['rect'][1] - 4 <= middle <= s['rect'][3] + 4]
        if not beside:
            continue
        label = min(beside, key=lambda s: s['rect'][0])
        row = {'label': label['text'], 'checkbox': box['rect']}
        (radios if label['text'] in TYPES else items).append(row)
    return {'items': items, 'types': radios}


TYPES = ('Printer config bundle(.orca_printer)', 'Filament bundle(.orca_filament)', 'Printer presets(.zip)',
         'Filament presets(.zip)', 'Process presets(.zip)')
