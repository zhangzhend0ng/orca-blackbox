"""Offline disk evidence for Feishu #232 config import."""
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

IMPORTED = '导入成功，3 个预设出现在对应列表且参数正确'
DUPLICATES = '同名重复时按产品既有策略提示（覆盖/重命名）'
KINDS = ('machine', 'filament', 'process')
RESULT_TITLE = 'Import result'  # MessageDialog of MainFrame::load_config_file, sm-v2.4.0
# A prompt counts as the product's name-clash strategy when it says that the
# preset exists and offers what to do with it.
CLASH = ('already', 'exist', 'overwrite', 'rename', 'replace')
# What a preset file carries besides its parameters: its identity, its parent and
# bookkeeping. An imported preset is written back as the parent's whole config plus
# this preset's own values, so the parent, the version and the id may be rewritten.
BOOKKEEPING = ('type', 'name', 'from', 'inherits', 'is_custom_defined', 'version', 'setting_id',
               'instantiation', 'modified_time')
# The Feishu precondition: one printer, one filament and one process preset.
KIND_NAMES = {'machine': 'printer', 'filament': 'filament', 'process': 'process'}
# The five rows of the Export Preset Bundle dialog (CreatePresetsDialog.cpp:3298-3302, sm-v2.4.0).
TYPES = ('Printer config bundle(.orca_printer)', 'Filament bundle(.orca_filament)', 'Printer presets(.zip)',
         'Filament presets(.zip)', 'Process presets(.zip)')
LIMIT = 4 * 1024 * 1024


def checkbox_rows(controls):
    """Pair every small textless Button with the Static written to its right on the same row.

    `controls` is describe(hwnd) output. A type row is a native radio Button plus its label;
    a listed printer or preset is a textless checkbox Button plus the label to its right,
    and only that Button takes the click (CreatePresetsDialog.cpp:306-315, sm-v2.4.0)."""
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


# A preset file on disk has no "type" key: its kind is the folder it sits in, or
# the settings id it carries (measured on the vendored user presets).
SIGNATURE = (('machine', 'printer_settings_id'), ('filament', 'filament_settings_id'),
             ('process', 'print_settings_id'))


def _kind(data, where):
    if data.get('type') in KINDS:
        return data['type']
    folders = str(where).replace('\\', '/').lower().split('/')
    for name in folders:
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
    """Presets of an exported config file: preset JSON files inside a bundle
    (.orca_printer, .orca_filament or .zip), or one preset JSON file."""
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


def parameters(settings):
    """The parameter values of a preset: everything but its bookkeeping."""
    return {name: value for name, value in settings.items() if name not in BOOKKEEPING}


def export_failed(message):
    """The two clauses when the product itself refused the export: nothing was imported.
    `message` is what its Info box said, or None when nothing could be listed."""
    reason = f'exporting the preset bundle on this build reported "{message}"' if message else (
        'no printer, filament or process preset could be exported')
    return {IMPORTED: f'FAIL ({reason}; nothing was imported)',
            DUPLICATES: 'FAIL (not exercised: nothing was imported)'}


def _key(row):
    return row['kind'], row['name']


def verify_import(config, before, after, dialogs) -> dict:
    """Every preset of the config files must be in the profile afterwards with the
    parameter values it was exported with, each of the three kinds must be among them,
    and a name clash must bring a prompt.

    `config`, `before` and `after` are preset lists (bundle_presets, profile_presets),
    `dialogs` the [{'title', 'texts', 'message'}] the product showed after the import.
    The imported preset holds the whole inherited config, so only the exported
    parameters are compared; extra keys of the imported preset are listed, not failed."""
    wanted = {_key(row): row['settings'] for row in config}
    had = {_key(row) for row in before}
    now = {_key(row): row['settings'] for row in after}
    missing = sorted('/'.join(key) for key in wanted if key not in now)
    changed, sizes = {}, {}
    for key, settings in wanted.items():
        if key not in now:
            continue
        differing = sorted(name for name, value in parameters(settings).items() if now[key].get(name) != value)
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
                        'prompt_dialogs': [[row['title'], *row['texts'][:12]] for row in prompts],
                        'result_dialog': None if result is None else [result['title'], *result['texts'][:12]]}}
