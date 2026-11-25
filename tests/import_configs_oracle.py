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
LIMIT = 4 * 1024 * 1024


def _preset(data):
    if isinstance(data, dict) and data.get('type') in KINDS and isinstance(data.get('name'), str):
        return {'kind': data['type'], 'name': data['name'], 'settings': data}
    return None


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
                    preset = _preset(data)
                    if preset:
                        rows.append({**preset, 'member': entry.filename})
    except BadZipFile:
        preset = _preset(json.loads(raw.decode('utf-8-sig')))
        rows = [{**preset, 'member': path.name}] if preset else []
    return sorted(rows, key=lambda row: (row['kind'], row['name']))


def profile_presets(datadir):
    """Every preset stored in a profile directory, which is what the preset lists are built from."""
    rows = []
    for path in sorted(Path(datadir).rglob('*.json')):
        try:
            if path.stat().st_size > LIMIT:
                continue
            preset = _preset(json.loads(path.read_text(encoding='utf-8-sig')))
        except (OSError, ValueError):
            continue
        if preset:
            rows.append({**preset, 'file': path.relative_to(datadir).as_posix()})
    return sorted(rows, key=lambda row: (row['kind'], row['name']))


def _key(row):
    return row['kind'], row['name']


def verify_import(config, before, after, dialogs) -> dict:
    """Every preset of the config file must be in the profile afterwards with the
    parameters it was exported with; a name clash must bring a prompt.

    `config`, `before` and `after` are preset lists (bundle_presets, profile_presets),
    `dialogs` the [{'title', 'texts'}] the product showed after the import."""
    wanted = {_key(row): row['settings'] for row in config}
    had = {_key(row) for row in before}
    now = {_key(row): row['settings'] for row in after}
    missing = sorted('/'.join(key) for key in wanted if key not in now)
    changed = {}
    for key, settings in wanted.items():
        if key not in now:
            continue
        differing = sorted(name for name, value in settings.items() if now[key].get(name) != value)
        if differing:
            changed['/'.join(key)] = {'differing_keys': differing[:40],
                                      'extra_keys': sorted(set(now[key]) - set(settings))[:40]}
    result = next((row for row in dialogs if RESULT_TITLE in row['title']), None)
    clashes = sorted('/'.join(key) for key in wanted if key in had)
    prompts = [row for row in dialogs if any(word in ' '.join(row['texts']).casefold() for word in CLASH)]
    problems = []
    if not wanted:
        problems.append('the config file holds no preset that the reader recognises')
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
                        'missing': missing, 'changed': changed, 'clashes': clashes,
                        'prompt_dialogs': [[row['title'], *row['texts'][:12]] for row in prompts],
                        'result_dialog': None if result is None else [result['title'], *result['texts'][:12]]}}
