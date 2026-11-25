"""Offline checks for the Feishu row #237: presets exported as a package and imported again.

Everything here reads files; nothing drives the GUI. The shapes come from the product's
source (CreatePresetsDialog.cpp, PresetBundle.cpp import_presets and import_json_presets,
Preset.cpp load_preset and save) and from the preset files the harness seeds into a fresh
profile:

* ``File > Export > Export Preset Bundle`` with ``Process presets(.zip)`` writes
  ``<directory>/Process presets.zip`` holding one ``<preset name>.json`` per user process
  preset of each printer whose box was ticked, and that member is the preset's own file in
  the profile. A failed export leaves a file that is no zip.
* ``File > Import > Import Configs`` loads every JSON of the zip. The imported preset's
  config is its parent's whole config with the file's own keys applied over it, and it is
  saved at once into the user presets folder: as what differs from the parent when the
  parent it names is there, as the whole config otherwise.
* A user preset therefore is compared by what it means: its effective parameters, which are
  the parameters of the preset it inherits from, overridden key by key by its own
  (``inherits`` names a system preset of ``<datadir>/system``, which may inherit in turn).
  Only keys on record before the export are compared; keys a file spells out only after the
  import are counted apart.

A value counts as the same when it means the same: ``"50"``, ``["50"]`` and ``"50,50"``
are one value for every extruder, ``["55","50"]`` and ``["55","50","50"]`` agree because a
shorter list repeats its last value for the remaining extruders, and ``0.20`` is ``0.2``.
"""
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
from zipfile import BadZipFile, ZipFile

CONFIGS_CLAUSES = ('生成配置包文件（.ini/.zip）', '重新导入后预设参数与导出前一致')
# Keys that say which preset a file is, not what it sets. ``name`` and ``inherits`` still have
# to carry over unchanged; the others are recorded and not compared.
IDENTITY_KEYS = frozenset((
    'type', 'name', 'from', 'inherits', 'is_custom_defined', 'version', 'instantiation', 'setting_id',
    'print_settings_id', 'filament_settings_id', 'printer_settings_id', 'filament_id', 'print_engine_id',
    'default_print_profile', 'default_filament_profile'))
PACKAGE_SUFFIXES = ('.zip', '.ini')
PRESET_KINDS = ('process', 'filament', 'machine')
LISTED_DIFFERENCES = 12


def _token(value):
    """One value as one comparable token: yes and no words, 0 and 1 and 0.0 all agree."""
    if isinstance(value, bool):
        return '1.0' if value else '0.0'
    text = str(value).strip()
    if text.casefold() in ('true', 'yes', 'on'):
        return '1.0'
    if text.casefold() in ('false', 'no', 'off'):
        return '0.0'
    try:
        number = float(text)
    except ValueError:
        return text
    return repr(number) if math.isfinite(number) else text


def _tokens(value):
    if isinstance(value, list):
        return [_token(item) for item in value]
    if value is None:
        return []
    text = str(value).strip()
    return [_token(part) for part in text.split(',')] if ',' in text else [_token(value)]


def same_value(first, second):
    """True when two preset values mean the same; the lists are padded with their last value."""
    left, right = _tokens(first), _tokens(second)
    if not left or not right:
        return left == right
    length = max(len(left), len(right))
    return left + [left[-1]] * (length - len(left)) == right + [right[-1]] * (length - len(right))


def value_text(value):
    return ','.join(str(item).strip() for item in value) if isinstance(value, list) else str(value)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _by_name(paths):
    """{preset name: {'file', 'sha256', 'own'}}; a file whose stem is the name wins over a duplicate."""
    found = {}
    for path in sorted(paths):
        try:
            raw = Path(path).read_bytes()
            own = json.loads(raw.decode('utf-8-sig'))
        except (OSError, ValueError):
            continue
        if not isinstance(own, dict):
            continue
        name = str(own.get('name') or Path(path).stem)
        exact = Path(path).stem == name
        if name not in found or (exact and not found[name]['exact']):
            found[name] = {'file': path.name, 'sha256': sha256(raw).hexdigest(), 'own': own, 'exact': exact}
    for entry in found.values():
        del entry['exact']
    return found


def user_presets(datadir, kind='process'):
    """The user's own presets of one kind anywhere under ``<datadir>/user``, by name."""
    return _by_name(Path(datadir, 'user').rglob(f'{kind}/*.json')) if Path(datadir, 'user').is_dir() else {}


def system_presets(datadir, kind='process'):
    """The system presets of one kind under ``<datadir>/system``, by name."""
    return _by_name(Path(datadir, 'system').rglob(f'{kind}/*.json')) if Path(datadir, 'system').is_dir() else {}


def effective_parameters(own, system, seen=()):
    """(effective parameters, chain of inherited preset names, inherited names not found)."""
    parent_name = own.get('inherits')
    base, chain, unresolved = {}, [], []
    parent = system.get(parent_name) if parent_name else None
    if parent_name:
        chain.append(parent_name)
        if parent is None or parent_name in seen:
            unresolved.append(parent_name)
        else:
            base, parents_chain, unresolved = effective_parameters(parent['own'], system, seen + (parent_name,))
            chain += parents_chain
    effective = dict(base)
    effective.update({key: value for key, value in own.items() if key not in IDENTITY_KEYS})
    return effective, chain, unresolved


def preset_table(datadir, kind='process'):
    """What the user presets of one kind in a profile mean: their own values, the inherited
    chain and the effective parameters of each. Kept as JSON (``presets-before.json``,
    ``presets-after.json``); the comparison of a re-import works from two such tables alone."""
    system = system_presets(datadir, kind)
    table = {'kind': kind, 'presets': {}}
    for name, preset in sorted(user_presets(datadir, kind).items()):
        effective, chain, unresolved = effective_parameters(preset['own'], system)
        table['presets'][name] = {
            'file': preset['file'], 'sha256': preset['sha256'], 'own': preset['own'],
            'inherits': preset['own'].get('inherits'), 'chain': chain, 'unresolved': unresolved,
            'effective': effective}
    return table


def differing_keys(first, second):
    """Keys whose values differ between two mappings of preset values, the identity keys that
    are only recorded left out."""
    return [key for key in sorted(set(first) | set(second))
            if key not in IDENTITY_KEYS and not same_value(first.get(key), second.get(key))]


def package_facts(path, table):
    """What a landed package holds: its bytes, its SHA-256 and, for every member, whether it is
    the preset file of the same name as stored in the profile (byte for byte, or as JSON)."""
    path = Path(path)
    raw = path.read_bytes()
    facts = {'name': path.name, 'extension': ''.join(path.suffixes[-1:]).lower(), 'bytes': len(raw),
             'sha256': sha256(raw).hexdigest(), 'members': {}}
    try:
        with ZipFile(BytesIO(raw)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                data = archive.read(info)
                member = {'bytes': len(data), 'sha256': sha256(data).hexdigest(), 'preset': None,
                          'byte_identical': False, 'matches_preset': False, 'differs_in': []}
                try:
                    own = json.loads(data.decode('utf-8-sig'))
                except (UnicodeDecodeError, ValueError):
                    member['error'] = 'not a JSON preset'
                else:
                    member['preset'] = str(own.get('name') or Path(info.filename).stem)
                    stored = table['presets'].get(member['preset'])
                    if stored is None:
                        member['error'] = 'no such user preset in the profile'
                    else:
                        member['byte_identical'] = member['sha256'] == stored['sha256']
                        member['differs_in'] = differing_keys(own, stored['own']) + [
                            key for key in ('name', 'inherits') if key in own and key in stored['own']
                            and own[key] != stored['own'][key]]
                        member['matches_preset'] = member['byte_identical'] or not member['differs_in']
                facts['members'][info.filename] = member
    except (BadZipFile, EOFError, OSError, ValueError, struct.error) as exc:
        facts['error'] = f'{type(exc).__name__}: {exc}'
    return facts


def package_gaps(package):
    """[what failed] for one landed package: a .zip or .ini whose members are the user presets
    as they were stored in the profile."""
    name = package.get('name')
    gaps = []
    if package.get('extension') not in PACKAGE_SUFFIXES:
        gaps.append(f'{name!r} is not a .zip or .ini package')
    if 'error' in package:
        gaps.append(f'{name!r} is not a readable package: {package["error"]}')
        return gaps
    if not [member for member in package['members'].values() if member['preset']]:
        gaps.append(f'{name!r} holds no preset')
    for filename, member in package['members'].items():
        if member.get('error'):
            gaps.append(f'{name!r}: {filename}: {member["error"]}')
        elif not member['matches_preset']:
            shown = ', '.join(member['differs_in'][:LISTED_DIFFERENCES])
            gaps.append(f'{name!r}: {member["preset"]} is not the preset as stored in the profile; it '
                        f'differs in {len(member["differs_in"])} keys: {shown}')
    return gaps


def _where(attempt):
    return f'{attempt.get("kind", "the package type")}/{attempt.get("row", "the listed row")}'


def _reported(attempt):
    words = attempt.get('result_words') or attempt.get('refusal_words')
    return f' (the dialog reported: {words})' if words else ''


def importable(attempts):
    """The packages of the attempts that hold at least one preset."""
    return [attempt['package'] for attempt in attempts
            if attempt.get('package') and not attempt['package'].get('error')
            and any(member['preset'] for member in attempt['package']['members'].values())]


def export_gaps(attempts, nothing_listed=None):
    """[what failed] for 生成配置包文件（.ini/.zip）: every export asked for produced a package
    of the presets as stored. `attempts` are the case's records, one per exported row:
    {'kind', 'row', 'error' or None, 'package': package_facts or None, 'result_words'}.
    `nothing_listed` is the sentence for a dialog that offered no row at all."""
    gaps = []
    if not attempts:
        return [nothing_listed or 'no preset was listed to export, so no package was asked for']
    for attempt in attempts:
        package = attempt.get('package')
        if attempt.get('error'):
            gaps.append(f'{_where(attempt)}: {attempt["error"]}')
        if not package:
            if not attempt.get('error'):  # the error already says that nothing landed
                gaps.append(f'{_where(attempt)}: no package file landed{_reported(attempt)}')
            continue
        gaps.extend(f'{_where(attempt)}: {gap}' for gap in package_gaps(package))
    return gaps


def import_readings(before, after, attempts):
    """{preset: {'compared', 'unchanged', 'changed', 'spelled_out_only_after', 'keys_after'}}:
    what the import did to each preset of the packages."""
    readings = {}
    for package in importable(attempts):
        for member in package['members'].values():
            name = member['preset']
            if not name or name in readings:
                continue
            old, new = before['presets'].get(name), after['presets'].get(name)
            if old is None or new is None:
                continue
            changed = [key for key in sorted(old['effective'])
                       if not same_value(old['effective'][key], new['effective'].get(key))]
            readings[name] = {'compared': len(old['effective']), 'changed': changed,
                              'unchanged': len(old['effective']) - len(changed),
                              'spelled_out_only_after': len(set(new['effective']) - set(old['effective'])),
                              'keys_after': len(new['effective'])}
    return readings


def import_gaps(before, after, attempts):
    """[what failed] for 重新导入后预设参数与导出前一致: every preset of every package is a
    user preset of the importing profile again and means what it meant before the export."""
    packages = importable(attempts)
    if not packages:
        return ['not exercised: no package holding a preset was imported']
    gaps, seen = [], set()
    for package in packages:
        for member in package['members'].values():
            name = member['preset']
            if not name or name in seen:
                continue
            seen.add(name)
            old, new = before['presets'].get(name), after['presets'].get(name)
            if old is None:
                gaps.append(f'{name}: the package holds a preset that was not a user preset before the export')
                continue
            if new is None:
                gaps.append(f'{name}: not a user preset of the profile after the import')
                continue
            if new.get('inherits') != old.get('inherits'):
                gaps.append(f'{name}: inherits {new.get("inherits")!r} after the import, '
                            f'{old.get("inherits")!r} before')
            if old.get('unresolved'):
                gaps.append(f'{name}: the preset it inherits from is not among the system presets '
                            f'({", ".join(old["unresolved"])}), so its parameters cannot be followed')
            if new.get('unresolved'):
                gaps.append(f'{name}: the preset it inherits from is not among the system presets after '
                            f'the import ({", ".join(new["unresolved"])})')
            changed = [key for key in sorted(old['effective'])
                       if not same_value(old['effective'][key], new['effective'].get(key))]
            if changed:
                shown = ', '.join(f'{key}: {value_text(old["effective"][key])} -> '
                                  f'{value_text(new["effective"].get(key))}' for key in changed[:LISTED_DIFFERENCES])
                gaps.append(f'{name}: {len(changed)} parameters differ after the import: {shown}')
    return gaps


def configs_expectation_gaps(before, after, attempts, nothing_listed=None):
    """{clause of the Feishu #237 expectation: [what failed]}, from the two preset tables and
    the export attempts. Nothing raises."""
    return {CONFIGS_CLAUSES[0]: export_gaps(attempts, nothing_listed),
            CONFIGS_CLAUSES[1]: import_gaps(before, after, attempts)}
