"""Offline checks for the Feishu row #237: presets exported as a package and imported again.

Everything here reads files; nothing drives the GUI. The shapes come from the product's
source (CreatePresetsDialog.cpp, PresetBundle.cpp import_presets and import_json_presets,
Preset.cpp load_preset and save) and from what was measured on the guest (run da4ecd60):

* ``File > Export > Export Preset Bundle`` with a zip type writes
  ``<directory>/<type>.zip`` holding one ``<preset name>.json`` per preset of each row whose
  box was ticked. A row of ``Filament presets(.zip)`` is a filament name and holds every
  preset of that name, those kept inside the project included; a row of
  ``Process presets(.zip)`` is a printer and holds the user process presets made for it.
  A failed export leaves a file that is no zip and reports "add file fail"; the application's
  own log then says which file it could not add (``<name> Failed to add file to ZIP archive``).
* ``File > Import > Import Configs`` loads every JSON of the zip. The imported preset's
  config is its parent's whole config with the file's own keys applied over it, and it is
  saved at once into the user presets folder: as what differs from the parent when the
  parent it names is there, as the whole config otherwise.
* A preset is compared by what it means: its effective parameters, which are the parameters
  of the preset it inherits from, overridden key by key by its own (``inherits`` names a
  system preset of ``<datadir>/system``, which may inherit in turn). A preset that was a
  file of the profile before the export is compared with that file; a preset that lived in
  the project is compared with what the package holds, as there is no other record of it.
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
# The preset type each zip type of the export dialog holds (the "type" key of its JSON files).
MEMBER_TYPES = {'Process presets(.zip)': 'process', 'Printer presets(.zip)': 'machine',
                'Filament presets(.zip)': 'filament'}
LISTED_DIFFERENCES = 12
# What the application's own log says about an export, and what says which presets it loaded
# and which printers it can see (CreatePresetsDialog.cpp, Preset.cpp).
APP_LOG_KEYWORDS = ('zip', 'failed', 'export', 'filament preset', 'json add successful')
APP_LOG_LOADING = ('can not find parent', 'load config successful', 'load preset: ', 'incorrect keys',
                   'parse config')
APP_LOG_VISIBILITY = 'is_visible set to'
APP_LOG_FAILED = 'failed to add file to zip archive'
APP_LOG_KEEP = 2000


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


def filament_name(preset_name):
    """The name a filament preset is listed under in the export dialog: what comes before the
    last " @" (CreatePresetsDialog.cpp get_filament_name)."""
    at = preset_name.rfind('@')
    return preset_name[:at - 1] if at > 0 else preset_name


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


def _table(tables, kind):
    """The preset table of one kind out of {kind: table}, or the one table that was given."""
    if 'presets' in tables:
        return tables
    return tables.get(kind) or {'kind': kind, 'presets': {}}


def differing_keys(first, second):
    """Keys whose values differ between two mappings of preset values, the identity keys that
    are only recorded left out."""
    return [key for key in sorted(set(first) | set(second))
            if key not in IDENTITY_KEYS and not same_value(first.get(key), second.get(key))]


def _member_problem(own, expected, rows):
    """Why a member of a package is not a preset of the rows that were ticked, or None."""
    if not isinstance(own, dict) or not str(own.get('name') or ''):
        return 'not a JSON preset'
    if expected and own.get('type') != expected:
        return f'a {own.get("type")!r} preset, not a {expected} one'
    name = str(own['name'])
    if not rows:
        return None
    if expected == 'filament' and filament_name(name) not in rows:
        return f'{filament_name(name)!r} is not a filament name that was ticked {sorted(rows)}'
    if expected == 'machine' and name not in rows:
        return f'not a printer that was ticked {sorted(rows)}'
    printers = own.get('compatible_printers')
    if expected == 'process' and isinstance(printers, list) and printers and not set(printers) & set(rows):
        return f'made for {printers}, not for a printer that was ticked {sorted(rows)}'
    return None


def package_facts(path, table=None, kind=None, rows=None):
    """What a landed package holds: its bytes, its SHA-256 and, for every member, whether it is
    the JSON of a preset of the ticked `rows` of the zip `kind`, and, when that preset is a
    file of the profile (`table`), the file as it was stored."""
    path = Path(path)
    raw = path.read_bytes()
    expected = MEMBER_TYPES.get(kind)
    facts = {'name': path.name, 'extension': ''.join(path.suffixes[-1:]).lower(), 'bytes': len(raw),
             'sha256': sha256(raw).hexdigest(), 'preset_kind': expected, 'rows': list(rows or []), 'members': {}}
    try:
        with ZipFile(BytesIO(raw)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                data = archive.read(info)
                member = {'bytes': len(data), 'sha256': sha256(data).hexdigest(), 'preset': None,
                          'stored': False, 'byte_identical': False, 'matches_preset': False, 'differs_in': []}
                try:
                    own = json.loads(data.decode('utf-8-sig'))
                except (UnicodeDecodeError, ValueError):
                    member['error'] = 'not a JSON preset'
                else:
                    member['preset'] = str(own.get('name') or Path(info.filename).stem) if isinstance(own, dict) \
                        else None
                    problem = _member_problem(own, expected, rows) if expected or rows else None
                    if problem:
                        member['error'] = problem
                    else:
                        stored = _table(table, expected)['presets'].get(member['preset']) if table is not None \
                            else None
                        if stored is not None:
                            member['stored'] = True
                            member['byte_identical'] = member['sha256'] == stored['sha256']
                            member['differs_in'] = differing_keys(own, stored['own']) + [
                                key for key in ('name', 'inherits') if key in own and key in stored['own']
                                and own[key] != stored['own'][key]]
                            member['matches_preset'] = member['byte_identical'] or not member['differs_in']
                        else:
                            member['matches_preset'] = True  # a preset of the project: nothing on disk to hold against
                facts['members'][info.filename] = member
    except (BadZipFile, EOFError, OSError, ValueError, struct.error) as exc:
        facts['error'] = f'{type(exc).__name__}: {exc}'
    return facts


def member_configs(path):
    """{preset name: what its JSON in the package says}; the record a re-import is held against
    when the preset was not a file of the profile."""
    configs = {}
    try:
        with ZipFile(Path(path)) as archive:
            for info in archive.infolist():
                try:
                    own = json.loads(archive.read(info).decode('utf-8-sig'))
                except (UnicodeDecodeError, ValueError):
                    continue
                if isinstance(own, dict) and own.get('name'):
                    configs[str(own['name'])] = own
    except (BadZipFile, EOFError, OSError, ValueError, struct.error):
        pass
    return configs


def package_gaps(package):
    """[what failed] for one landed package: a .zip or .ini whose members are the JSON of the
    presets of the rows that were ticked."""
    name = package.get('name')
    gaps = []
    if package.get('extension') not in PACKAGE_SUFFIXES:
        gaps.append(f'{name!r} is not a .zip or .ini package')
    if 'error' in package:
        left = ('left a 0-byte zip: the file was created and nothing was added to it'
                if package.get('bytes') == 0 else f'is not a readable package: {package["error"]}')
        gaps.append(f'{name!r} {left}')
        return gaps
    if not [member for member in package['members'].values() if member['preset']]:
        gaps.append(f'{name!r} holds no preset')
    for filename, member in package['members'].items():
        if member.get('error'):
            gaps.append(f'{name!r}: {filename}: {member["error"]}')
        elif member['stored'] and not member['matches_preset']:
            shown = ', '.join(member['differs_in'][:LISTED_DIFFERENCES])
            gaps.append(f'{name!r}: {member["preset"]} is not the preset as stored in the profile; it '
                        f'differs in {len(member["differs_in"])} keys: {shown}')
    return gaps


def _where(attempt):
    return f'{attempt.get("kind", "the package type")}/{attempt.get("row", "the listed row")}'


def _reported(attempt):
    words = attempt.get('result_words') or attempt.get('refusal_words')
    return f' (the dialog reported: {words})' if words else ''


def _could_not_add(line):
    """The file a "Failed to add file to ZIP archive" line names, without the log's own prefix.
    One of the application's two wordings puts the kind of preset after the name
    ("<name>.json Filament preset failed to add file to ZIP archive", run 847aa160)."""
    head = line[:line.casefold().index(APP_LOG_FAILED)].strip()
    # The application writes "[severity]<tab><time>[Thread <id>]:<message>" (utils.cpp), older
    # lines read "<time> [severity] <message>": the name is what follows the last of either.
    for tail in (']:', '] '):
        if tail in head:
            head = head.rsplit(tail, 1)[-1].strip()
    for kind in ('filament preset', 'printer preset', 'process preset'):
        if head.casefold().endswith(kind):
            head = head[:-len(kind)].rstrip()
    return head


def _said(attempt):
    """What the product itself said about the export: the words of its result box and the files
    its log says it could not add."""
    said = []
    words = attempt.get('result_words')
    if words and 'fail' in words.casefold():
        said.append(f'the dialog reported {words!r}')
    said += [f'the application log could not add {_could_not_add(line)[-120:]} to the ZIP archive'
             for line in (attempt.get('app_log') or {}).get('failed_to_add', [])[:3]]
    return said


def importable(attempts):
    """The packages of the attempts that hold at least one preset."""
    return [attempt['package'] for attempt in attempts
            if attempt.get('package') and not attempt['package'].get('error')
            and any(member['preset'] for member in attempt['package']['members'].values())]


def export_gaps(attempts, nothing_listed=None):
    """[what failed] for 生成配置包文件（.ini/.zip）: every export asked for produced a package
    of the JSON of the presets that were ticked. `attempts` are the case's records, one per
    exported row: {'kind', 'row', 'error' or None, 'package': package_facts or None,
    'result_words', 'app_log': {'failed_to_add': [lines]}}. `nothing_listed` is the sentence
    for a dialog that offered no row at all."""
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
        gaps.extend(f'{_where(attempt)}: {said}' for said in _said(attempt))
        gaps.extend(f'{_where(attempt)}: {gap}' for gap in package_gaps(package))
    return gaps


def _baseline(attempt, name, old_table):
    """(parameters before the export, where they come from) for a preset of a package."""
    old = old_table['presets'].get(name)
    if old is not None and not old.get('unresolved'):
        return old['effective'], 'as stored in the profile before the export', old
    if old is not None:  # its parent is not among the system presets: what the file itself says
        return ({key: value for key, value in old['own'].items() if key not in IDENTITY_KEYS},
                'as its own file says before the export, its parent not being among the system presets', old)
    exported = (attempt.get('_members') or {}).get(name)
    if exported is None:
        return None, None, None
    return ({key: value for key, value in exported.items() if key not in IDENTITY_KEYS},
            'as the package holds it, the preset not being a file of the profile', None)


def import_readings(before, after, attempts):
    """{preset: {'compared', 'unchanged', 'changed', 'spelled_out_only_after', 'keys_after',
    'baseline'}}: what the import did to each preset of the packages."""
    readings = {}
    for attempt in attempts:
        package = attempt.get('package')
        if not package or package not in importable(attempts):
            continue
        kind = package.get('preset_kind')
        for member in package['members'].values():
            name = member['preset']
            if not name or name in readings:
                continue
            baseline, source, _old = _baseline(attempt, name, _table(before, kind))
            new = _table(after, kind)['presets'].get(name)
            if baseline is None or new is None:
                continue
            changed = [key for key in sorted(baseline) if not same_value(baseline[key], new['effective'].get(key))]
            readings[name] = {'compared': len(baseline), 'changed': changed, 'unchanged': len(baseline) - len(changed),
                              'spelled_out_only_after': len(set(new['effective']) - set(baseline)),
                              'keys_after': len(new['effective']), 'baseline': source}
    return readings


def import_gaps(before, after, attempts):
    """[what failed] for 重新导入后预设参数与导出前一致: every preset of every package is a
    user preset of the importing profile again and means what it meant before the export.
    `before` and `after` are preset tables or {kind: table}."""
    if not importable(attempts):
        return ['not exercised: no package holding a preset was imported']
    gaps, seen = [], set()
    for attempt in attempts:
        package = attempt.get('package')
        if not package or package not in importable(attempts):
            continue
        kind = package.get('preset_kind')
        old_table, new_table = _table(before, kind), _table(after, kind)
        for member in package['members'].values():
            name = member['preset']
            if not name or name in seen:
                continue
            seen.add(name)
            baseline, _source, old = _baseline(attempt, name, old_table)
            new = new_table['presets'].get(name)
            if baseline is None:
                gaps.append(f'{name}: the package holds a preset that was not a user preset before the export')
                continue
            if new is None:
                gaps.append(f'{name}: not a user preset of the profile after the import')
                continue
            if old is not None and new.get('inherits') != old.get('inherits'):
                gaps.append(f'{name}: inherits {new.get("inherits")!r} after the import, '
                            f'{old.get("inherits")!r} before')
            if new.get('unresolved') and not (old is not None and old.get('unresolved')):
                # The parent was among the system presets before and is not now; when it never
                # was, the preset is compared by what its own file says.
                gaps.append(f'{name}: the preset it inherits from is not among the system presets after '
                            f'the import ({", ".join(new["unresolved"])})')
            changed = [key for key in sorted(baseline) if not same_value(baseline[key], new['effective'].get(key))]
            if changed:
                shown = ', '.join(f'{key}: {value_text(baseline[key])} -> '
                                  f'{value_text(new["effective"].get(key))}' for key in changed[:LISTED_DIFFERENCES])
                gaps.append(f'{name}: {len(changed)} parameters differ after the import: {shown}')
    return gaps


def configs_expectation_gaps(before, after, attempts, nothing_listed=None):
    """{clause of the Feishu #237 expectation: [what failed]}, from the preset tables before
    and after and the export attempts. Nothing raises."""
    return {CONFIGS_CLAUSES[0]: export_gaps(attempts, nothing_listed),
            CONFIGS_CLAUSES[1]: import_gaps(before, after, attempts)}


def public_attempts(attempts):
    """The attempts as they go into the analysis: without the preset files the package holds."""
    return [{key: value for key, value in attempt.items() if not key.startswith('_')} for attempt in attempts]


# --- the application's own log ---------------------------------------------------------------

def app_log_files(datadir):
    """[(path, bytes)] of the application's own logs under ``<datadir>/log``, by name. The
    application names them ``<date>-<time>.log.<N>`` (utils.cpp set_log_path_and_level)."""
    folder = Path(datadir, 'log')
    if not folder.is_dir():
        return []
    return [(path, path.stat().st_size) for path in sorted(folder.glob('*.log*')) if path.is_file()]


def app_log_mark(datadir):
    """How far each log was written when this was taken (app_log_lines reads on from there)."""
    return {path: size for path, size in app_log_files(datadir)}


def app_log_lines(datadir, mark=None, keywords=APP_LOG_KEYWORDS, extra=(), names=()):
    """Lines of the application's own log, each with the timestamp it was written with.

    Kept are the lines with any of `keywords` or `extra` in them (either case), and the lines
    that say whether a preset is visible, for the printers and presets named in `names`. `mark`
    limits the reading to what was written since it was taken."""
    wanted = tuple(word.casefold() for word in tuple(keywords) + tuple(extra))
    lines = []
    for path, size in app_log_files(datadir):
        start = (mark or {}).get(path, 0)
        try:
            with open(path, 'rb') as handle:
                if size >= start:
                    handle.seek(start)
                text = handle.read().decode('utf-8', errors='replace')
        except OSError:
            continue
        for line in text.splitlines():
            low = line.casefold()
            keep = any(word in low for word in wanted)
            if not keep and APP_LOG_VISIBILITY in low:
                keep = any(str(name).casefold() in low for name in names)
            if keep:
                lines.append(line.strip())
    return lines


def log_severities(datadir):
    """{severity: lines} over the application's whole log, read from the "[severity]" it writes
    at the start of every line (utils.cpp set_log_path_and_level). Says what the application
    wrote at all when a line that was looked for is not there."""
    counts = {}
    for path, _size in app_log_files(datadir):
        try:
            with open(path, 'rb') as handle:
                text = handle.read().decode('utf-8', errors='replace')
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith('[') and ']' in line:
                severity = line[1:line.index(']')]
                counts[severity] = counts.get(severity, 0) + 1
    return counts


def failed_to_add(lines):
    """The log lines that name a file the application could not put into the package."""
    return [line for line in lines if APP_LOG_FAILED in line.casefold()]


def app_log_section(heading, lines):
    """One part of ``app-log.log``: its heading and the lines under it."""
    return ['', f'## {heading} ({len(lines)} lines)', *lines]


def app_log_text(profile, sections):
    """What goes into ``app-log.log`` at first: the sources, then each (heading, lines) in turn."""
    out = [f'# application log of {Path(profile).name}: the lines with {", ".join(APP_LOG_KEYWORDS)} (either case),',
           '# those that say which presets were loaded and which printers are visible, and what each',
           '# export wrote. Every line keeps the timestamp the application gave it.']
    out += [f'# source: log/{path.name} ({size} bytes)' for path, size in app_log_files(profile)]
    for heading, lines in sections:
        out += app_log_section(heading, lines)
    return '\n'.join(out) + '\n'
