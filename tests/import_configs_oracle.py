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
# The two presets that are selected in the sidebar and compared through the project's
# effective values. The printer preset cannot be switched to in the sidebar (guest runs
# 2c32e51c, 641f1a6c, a09a066): its parameters are compared through the stored file.
EFFECTIVE_KINDS = ('filament', 'process')
MACHINE_CHECK = ('the printer preset cannot be selected in the sidebar on this build; its parameters are '
                 'compared through the stored preset file against the exported JSON')
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


def project_settings(project):
    """The effective configuration a project 3MF carries."""
    with ZipFile(project) as bundle:
        return json.loads(bundle.read('Metadata/project_settings.config'))


def template_presets(project):
    """Names of the printer, the process and the first filament preset a project 3MF is set to."""
    settings = project_settings(project)
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
    under a name of its own, as a custom root preset (no inherits).

    The filament and process presets are made compatible with every printer: an
    empty `compatible_printers` and an empty `compatible_printers_condition` (and for
    the filament an empty `compatible_prints`). is_compatible_with_printer only
    evaluates the condition when the list is empty and the condition is not, and
    then returns true for an empty list (libslic3r/Preset.cpp:1049 with :1065-1080 at
    sync/softfever-20261010; :754 with :772 and :781 at sm-v2.4.0). The system presets they come
    from name one printer, which leaves them incompatible with the printer the
    template project carries, whose name has the project file appended."""
    values, chain = effective_preset(vendor_dir, kind, source)
    body = {key: value for key, value in values.items() if key not in BOOKKEEPING and not key.endswith('_settings_id')}
    preset = {'type': kind, 'name': NAMES[kind], 'from': 'User', 'version': VERSION, 'inherits': '',
              'instantiation': 'true',
              ID_KEYS[kind]: [NAMES[kind]] if kind == 'filament' else NAMES[kind], **body}
    if kind in EFFECTIVE_KINDS:
        preset['compatible_printers'] = []
        preset['compatible_printers_condition'] = ''
    if kind == 'filament':
        preset['compatible_prints'] = []
        preset['compatible_prints_condition'] = ''
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


def normalize(value):
    """One value in one shape, so that the way it was written does not count:
    a number is a number ("0.40", 0.4), a list with one item is that item ("30" and
    ["30"]), and a new line or a quote in a G-code string is the same whether it is
    written as two characters or as itself (measured on guest run fc163e85)."""
    if isinstance(value, list):
        items = [normalize(item) for item in value]
        return items[0] if len(items) == 1 else items
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 9)
    if isinstance(value, str):
        text = value.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\"', '"').strip()
        try:
            return round(float(text), 9)
        except ValueError:
            return text
    return value


def _same(left, right):
    return normalize(left) == normalize(right)


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def same_effective(exported, effective, kind):
    """An exported parameter against the project's effective value. Filament values
    are per extruder and only the first extruder carries the imported preset, so its
    first item is compared; other values are compared item by item over the exported length."""
    if not isinstance(exported, list):
        return _same(exported, _first(effective))
    if not isinstance(effective, list) or len(effective) < len(exported):
        return False
    if kind == 'filament':
        return _same(exported[0], effective[0])
    return all(_same(a, b) for a, b in zip(exported, effective))


def list_rows(rows):
    """The rows a preset popup showed, split into the user section and the rest.
    A section starts at a row that names it (the header reads 'User presets')."""
    user, inside = [], False
    for text in rows:
        low = text.casefold()
        if 'user' in low and 'preset' in low:
            inside = True
            continue
        if 'system' in low and 'preset' in low:
            inside = False
        if inside:
            user.append(text)
    return {'user': user, 'others': [text for text in rows if text not in user]}


def missing_from_lists(dropdowns, config):
    """The config presets whose name no row of their own preset popup carried."""
    missing = []
    for row in config:
        read = (dropdowns or {}).get(row['kind']) or {}
        if not any(row['name'].casefold() in text.casefold() for text in read.get('rows', [])):
            missing.append(f'{row["kind"]}/{row["name"]}')
    return missing


def effective_report(config, settings, defined, kinds=EFFECTIVE_KINDS):
    """Every exported parameter of the presets in `kinds` that the project's effective
    configuration carries is compared with it; the selection is read from their ids.

    A key the effective configuration does not carry is inert for this build: it is
    not a parameter of the product and takes no part in the verdict. It is only listed,
    per preset, in `inert_keys`; those of them the template project writes are also
    listed in `dropped_defined_keys`. The selection is read from the settings ids
    the project carries."""
    report, inert, dropped = {}, {}, {}
    for row in config:
        if row['kind'] not in kinds:
            continue
        label = f'{row["kind"]}/{row["name"]}'
        changed, absent = {}, []
        for key, value in parameters(row['settings']).items():
            if key not in settings:
                absent.append(key)
            elif not same_effective(value, settings[key], row['kind']):
                changed[key] = [value, settings[key]]
        report[label] = {'compared': len(parameters(row['settings'])) - len(absent), 'changed': changed}
        inert[label] = {'count': len(absent), 'keys': sorted(absent)}
        dropped[label] = sorted(key for key in absent if key in defined)
    ids = settings.get('filament_settings_id')
    selected = {'machine': settings.get('printer_settings_id'), 'process': settings.get('print_settings_id'),
                'filament': ids[0] if isinstance(ids, list) and ids else ids}
    return {'by_preset': report, 'inert_keys': inert, 'dropped_defined_keys': dropped, 'selected': selected,
            'selection_ok': all(selected[kind] == NAMES[kind] for kind in kinds),
            'machine_check': MACHINE_CHECK}


def dropped_report(config, after, defined):
    """Readings for when the effective values could not be read: the exported parameters
    the import left out of the stored preset, inert ones and those the template writes.
    They are readings only; a changed value is what fails, and that is read elsewhere."""
    stored = {(row['kind'], row['name']): row['settings'] for row in after}
    inert, dropped = {}, {}
    for row in config:
        label = f'{row["kind"]}/{row["name"]}'
        gone = [key for key in parameters(row['settings']) if key not in stored.get((row['kind'], row['name']), {})]
        inert[label] = {'count': len(gone), 'keys': sorted(gone)}
        dropped[label] = sorted(key for key in gone if key in defined)
    return {'inert_keys': inert, 'dropped_defined_keys': dropped}


def _short(values, limit=4):
    return ', '.join(f'{key}: {json.dumps(value[0], ensure_ascii=False)[:40]} -> '
                     f'{json.dumps(value[1], ensure_ascii=False)[:40]}' for key, value in list(values.items())[:limit])


def _loss_text(report):
    """Only parameters whose effective value differs are named; inert keys are not."""
    return [f'{label}: {len(row["changed"])} effective values changed ({_short(row["changed"])})'
            for label, row in report.items() if row.get('changed')]


def _key(row):
    return row['kind'], row['name']


def verify_import(config, before, after, dialogs, dropdowns=None, effective=None, defined=(), reason=None) -> dict:
    """Every preset of the config files must be in the profile afterwards with the
    parameter values it was exported with, each of the three kinds must be among them,
    each name must be in its own preset list, the filament and process presets must be
    the selected ones with every exported parameter equal to its effective value, and
    a name clash must bring a prompt.

    `config`, `before` and `after` are preset lists (bundle_presets, profile_presets),
    `dialogs` the [{'title', 'texts', 'message'}] the product showed after the import,
    `dropdowns` {kind: {'rows': [...]}} what the three preset popups listed, `effective`
    the project settings saved after the selection and `defined` the keys the template
    project writes. The printer preset is compared through its stored file only."""
    wanted = {_key(row): row['settings'] for row in config}
    had = {_key(row) for row in before}
    now = {_key(row): row['settings'] for row in after}
    missing = sorted('/'.join(key) for key in wanted if key not in now)
    changed, sizes = {}, {}
    for key, settings in wanted.items():
        if key not in now:
            continue
        differing = sorted(name for name, value in parameters(settings).items()
                           if name in now[key] and not _same(value, now[key][name]))
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
    effective_reading, dropped = None, None
    # The preset lists are optional evidence: without them nothing is reported as unlisted.
    unlisted = missing_from_lists(dropdowns, config) if dropdowns is not None else []
    if unlisted:
        problems.append(f'{len(unlisted)} presets are not in their preset lists: {unlisted}')
    if effective is not None:
        effective_reading = effective_report(config, effective, set(defined or ()))
        if not effective_reading['selection_ok']:
            problems.append(f'the imported presets were not the selected ones: {effective_reading["selected"]}')
        problems += _loss_text(effective_reading['by_preset'])
    elif dropdowns is not None:
        problems.append(f'the presets were not selected in the sidebar, so the effective values were not compared '
                        f'({reason})')
        dropped = dropped_report(config, after, set(defined or ()))
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
                                                                        *result['texts'][:12]],
                        'not_in_lists': unlisted, 'effective': effective_reading, 'dropped': dropped}}


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
