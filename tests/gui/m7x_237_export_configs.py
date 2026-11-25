#!/usr/bin/env python3
# m7x_237_export_configs.py — Feishu #237: presets exported as a package and imported again
# feishu: baseline#237
"""Feishu #237【配置导出】导出所选预设为配置包，可被重新导入还原 (P1).

Precondition (Feishu): 存在自定义打印机/耗材/工艺预设.
Steps (Feishu): 1. 点击「文件→导出→导出配置包…」; 2. 选择要导出的预设并保存;
3. 随后用「导入配置…」重新导入核对参数一致.
Expected (Feishu): 生成配置包文件（.ini/.zip），重新导入后预设参数与导出前一致.

The precondition has to be made true by the product itself. The process presets the
harness seeds into a fresh profile are not presets the application saved, and the
export dialog listed no process row for them (measured: runs da4ecd60 and ff55c9d8,
with and without the printer installed in the application config). So when
"Process presets(.zip)" lists nothing, this case first makes a user process preset
the way a user does (layer height changed, the preset row's save button, the
"Save preset" box: the path tests/engine/m5g_preset_manage.py measured), looks
for the file the application writes under <datadir>/user/default/process/, and
reads the dialog again. Each process row it lists then is exported. The first
filament name of "Filament presets(.zip)" is exported once more, as a second
reading kept apart from the verdict: its presets are the project's, and the two
runs above ended in "add file fail" and a 0-byte zip.

The zip is read back, its bytes and SHA-256 recorded, the words of the result box
are read from pixels, and the lines the application wrote to its own log are
kept as ``app-log.log`` (a zip and that log are not among the harvested files).
The application's config carries ``app.log_severity_level = debug`` so that its
info lines are written. Session 2 starts from a profile without any user preset,
imports the packages through File > Import > Import Configs and is closed; the
presets it then has on disk are compared with the recorded ones, parameter by
parameter.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import traceback

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from export_configs_oracle import (APP_LOG_KEEP, APP_LOG_KEYWORDS, APP_LOG_LOADING, PRESET_KINDS,  # noqa: E402
                                    app_log_files, app_log_lines, app_log_mark, app_log_section, app_log_text,
                                    configs_expectation_gaps, export_gaps, failed_to_add, import_readings,
                                    importable, log_severities, member_configs, package_facts, preset_table,
                                    public_attempts)
from file_export_cases import (BUNDLE_FILES, BUNDLE_KINDS, bundle_survey, export_preset_bundle,  # noqa: E402
                               import_configs, save_process_preset)
from harness import launcher, profile, winutil  # noqa: E402
from m3_common import add_common_args, ensure_gl_ready  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from m8_common import wait_arrival  # noqa: E402

FIXTURE = HERE / 'fixtures/feishu_std_cube.3mf'
LOG = '[m7x237]'
KIND = 'Process presets(.zip)'
FALLBACK = 'Filament presets(.zip)'
# The custom process presets of the seeded profile were made for this printer.
INSTALLED = {'vendor': 'Snapmaker', 'model': 'Snapmaker U1', 'nozzle_diameter': '0.4'}
# What the application is told when it starts: the printer is installed, and its log takes
# debug lines (the key lives in the "app" section: AppConfig.hpp get(key) reads "app", the
# level is applied by GUI_App.cpp set_logging_level(level_string_to_boost(get("log_severity_level")))).
LOG_LEVEL = 'debug'
APP_CONFIG = {'models': [INSTALLED], 'app': {'log_severity_level': LOG_LEVEL}}
# The user process preset this case makes itself when the dialog lists none.
SAVED_PRESET = 'BB Export Test'


def seed(datadir, with_presets=True):
    """A new profile as the harness seeds it, with the printer installed in its application
    config and the log level raised; without the seeded user presets when asked. Returns how
    many of them were removed."""
    profile.seed_profile(datadir, fresh=False, conf_extra=json.loads(json.dumps(APP_CONFIG)))
    removed = 0
    if not with_presets:
        for path in sorted(Path(datadir, 'user').rglob('*')):
            if path.is_file() and path.suffix in ('.json', '.info'):
                path.unlink()
                removed += 1
    return removed


def boot(args, datadir, model):
    """What m3_common.boot_session does, for a profile this case seeded itself."""
    session = launcher.launch(exe=args.exe, datadir=datadir, model=model, dismiss_wizard=True)
    time.sleep(12.0)  # hands-off: early interference kills the automatic loading of the fixture
    try:
        winutil.user32.ShowWindow(session.hwnd, 3)  # SW_MAXIMIZE
        time.sleep(1.0)
    except Exception:  # noqa: BLE001 - the window state is cosmetic here
        pass
    ensure_gl_ready(session)
    winutil.demote_window(session.hwnd)
    return session


def tables_of(datadir):
    return {kind: preset_table(datadir, kind) for kind in PRESET_KINDS}


def custom_counts(tables):
    return {kind: len(table['presets']) for kind, table in tables.items()}


def listed_labels(survey):
    return {kind: [row['label'] for row in survey['kinds'][kind]['items']] for kind in BUNDLE_KINDS}


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def wait_for_file(path, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return False


def export_row(session, datadir, kind, label, work, analysis, number):
    """One pass of File > Export > Export Preset Bundle for one listed row: the attempt record,
    with what landed, what the dialog said and what the application logged meanwhile."""
    folder = work / 'packages' / re.sub(r'[^A-Za-z0-9._-]+', '_', f'{kind} {label}') / str(number)
    folder.mkdir(parents=True)
    attempt = {'kind': kind, 'row': label, 'directory': folder.relative_to(work).as_posix(),
               'app_log': {'lines': []}}
    mark = app_log_mark(datadir)
    try:
        with stage(analysis, f'export_{number}'):
            receipt = export_preset_bundle(session, kind, folder, work, analysis, tick=[label],
                                           key=f'export_{number}')
            for name in ('result', 'refusal'):
                if receipt.get(name):
                    attempt[f'{name}_words'] = receipt[name].get('words')
                    attempt[f'{name}_words_error'] = receipt[name].get('words_error')
            attempt['dialog_closed'] = receipt.get('dialog_closed')
            attempt['landed'] = receipt['landed']
    except Exception as exc:  # noqa: BLE001 - recorded; the verdict turns red on it
        attempt['error'] = f'{type(exc).__name__}: {exc}'
        traceback.print_exc()
    attempt['app_log']['lines'] = app_log_lines(datadir, mark)[-60:]
    if attempt.get('landed'):
        package = folder / BUNDLE_FILES[kind]
        attempt['package'] = package_facts(package, tables_of(datadir), kind=kind, rows=[label])
        attempt['package']['path'] = package.relative_to(work).as_posix()
        attempt['_members'] = member_configs(package)
    return attempt


def attribute_log_lines(records, failed):
    """Give every export the log lines about files it could not add: its own when it wrote
    some, else those of the whole session when it was the only export."""
    for record in records:
        own = failed_to_add(record['app_log']['lines'])
        record['app_log']['failed_to_add'] = own if own or len(records) > 1 else list(failed)


def export_session(args, work, analysis):
    """Session 1: make the precondition true when it is not, read the export dialog, export
    what it lists, and keep what the application said about it. Returns (the presets as
    seeded, the presets as they were at the export, the export attempts, what was listed)."""
    datadir = work / 'export-profile'
    seed(datadir)
    seeded = tables_of(datadir)
    reading = analysis['export_session'] = {'app_config': APP_CONFIG,
                                            'custom_presets_on_disk': custom_counts(seeded)}
    reading['custom_presets'] = {kind: sorted(seeded[kind]['presets']) for kind in PRESET_KINDS}
    attempts, second, state = [], None, None
    session = boot(args, datadir, args.model)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('the fixture did not render')
        with stage(analysis, 'read_export_dialog'):
            listed = listed_labels(bundle_survey(session, work, analysis))
        reading['listed_before'] = listed
        if not listed[KIND]:
            # The presets the harness seeds are not the product's own: make one the way a user
            # does, look for the file the application writes, and read the dialog again.
            try:
                with stage(analysis, 'make_user_preset'):
                    made = save_process_preset(session, SAVED_PRESET, work, analysis)
                    file = Path(datadir, 'user', 'default', 'process', f'{SAVED_PRESET}.json')
                    made['file'] = file.relative_to(work).as_posix() if wait_for_file(file, 20) else None
            except Exception as exc:  # noqa: BLE001 - recorded; the verdict below turns red on it
                made = {'error': f'{type(exc).__name__}: {exc}'}
                traceback.print_exc()
            reading['made_preset'] = {key: made.get(key) for key in
                                      ('file', 'typed', 'closed', 'preset_row_before_save',
                                       'preset_row_after_save', 'error')}
            if made.get('file'):
                with stage(analysis, 'read_export_dialog_again'):
                    listed = listed_labels(bundle_survey(session, work, analysis, key='bundle_survey_after',
                                                         prefix='after-'))
        reading['listed'] = listed
        for label in listed[KIND]:
            attempts.append(export_row(session, datadir, KIND, label, work, analysis, len(attempts) + 1))
            if attempts[-1].get('error'):
                break
        attempts.extend({'kind': KIND, 'row': label, 'directory': '', 'app_log': {'lines': []},
                         'error': 'not attempted: the row before it failed'}
                        for label in listed[KIND][len(attempts):])
        if listed[FALLBACK]:
            # A second reading only, kept apart from the verdict: a filament name, whose presets
            # are the project's.
            with stage(analysis, 'filament_reading'):
                second = export_row(session, datadir, FALLBACK, listed[FALLBACK][0], work, analysis,
                                    len(attempts) + 1)
            analysis['filament_reading'] = public_attempts([second])[0]
        at_export = tables_of(datadir)
        reading['presets_rewritten_while_open'] = sorted(
            (kind, name) for kind in PRESET_KINDS for name in seeded[kind]['presets']
            if at_export[kind]['presets'].get(name) != seeded[kind]['presets'][name])
        write_json(work / 'presets-before.json', {'seeded': seeded, 'at_export': at_export})
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        state = reading['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    finally:
        session.close()
    # What the application itself wrote: which presets it loaded, which printers it can see, and
    # what it did about the export. Kept as a file, as the log itself is not harvested.
    names = (INSTALLED['model'], SAVED_PRESET) + tuple(
        name for kind in PRESET_KINDS for name in seeded[kind]['presets'])
    lines = app_log_lines(datadir, keywords=APP_LOG_KEYWORDS, extra=APP_LOG_LOADING, names=names)
    failed = failed_to_add(lines)
    records = attempts + ([second] if second else [])
    attribute_log_lines(records, failed)
    if second is not None:
        analysis['filament_reading']['gaps'] = export_gaps([second])
    reading['app_log'] = {
        'file': 'app-log.log', 'lines_kept': len(lines),
        'sources': [f'log/{path.name} ({size} bytes)' for path, size in app_log_files(datadir)],
        'severities': log_severities(datadir),
        'loaded_user_presets': [line[-200:] for line in lines if 'load config successful' in line.casefold()][-12:],
        'parents_not_found': [line[-200:] for line in lines if 'can not find parent' in line.casefold()][-12:],
        'printer_visibility': [line[-200:] for line in lines if 'is_visible set to' in line.casefold()][-12:],
        'failed_to_add': [line[-240:] for line in failed[-6:]],
        'added': [line[-200:] for line in lines if 'json add successful' in line.casefold()][-12:]}
    (work / 'app-log.log').write_text(app_log_text(datadir, [
        ('the whole log, as far as it matters here', lines[-APP_LOG_KEEP:]),
        *[(f'export {number}: {record["kind"]} / {record["row"]}', record['app_log']['lines'])
          for number, record in enumerate(records, 1)]]), encoding='utf-8')
    if state != {'alive': True, 'dialog': None}:
        raise ValueError(f'the editor was left in an unexpected state after the exports: {state!r}')
    return seeded, at_export, attempts, listed


def import_session(args, work, analysis, attempts):
    """Session 2: a profile without user presets imports every package that holds a preset; the
    presets on disk after the editor is closed are returned, by kind."""
    ready = importable(attempts)
    packages = [Path(work, attempt['directory']) / BUNDLE_FILES[attempt['kind']] for attempt in attempts
                if attempt.get('package') in ready]
    datadir = work / 'import-profile'
    reading = analysis['import_session'] = {'app_config': APP_CONFIG,
                                            'sources': [package.relative_to(work).as_posix() for package in packages]}
    if not packages:
        reading['note'] = 'not run: no package holding a preset was exported'
        return tables_of(datadir)
    reading['seeded_user_presets_removed'] = seed(datadir, with_presets=False)
    reading['presets_at_start'] = custom_counts(tables_of(datadir))
    session, mark, state = None, None, None
    try:
        session = boot(args, datadir, args.model)
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('the fixture did not render')
        mark = app_log_mark(datadir)  # the import's own lines, apart from what the start-up wrote
        for number, package in enumerate(packages, 1):
            with stage(analysis, f'import_{number}'):
                import_configs(session, package, work, analysis, key=f'import_{number}')
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        state = reading['editor_after_import'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    finally:
        if session is not None:
            session.close()
    lines = app_log_lines(datadir, mark, keywords=(), extra=('import', 'can not find parent', 'failed'))[-120:]
    reading['app_log'] = {'lines': len(lines), 'severities': log_severities(datadir),
                          'presets_skipped': [line[-200:] for line in lines if 'skip' in line.casefold()][-12:]}
    with open(work / 'app-log.log', 'a', encoding='utf-8') as handle:
        handle.write('\n' + '\n'.join(app_log_section('the import', lines)) + '\n')
    if state != {'alive': True, 'dialog': None}:
        raise ValueError(f'the editor was left in an unexpected state after the import: {state!r}')
    return tables_of(datadir)


def nothing_listed(reading, listed):
    """The sentence for a dialog that offers no process row."""
    offered = '; '.join(f'{kind}: {labels or "nothing"}' for kind, labels in listed.items())
    made = reading.get('made_preset') or {}
    if made.get('file'):
        return (f'"{KIND}" lists no row although the application itself just saved the user preset '
                f'"{SAVED_PRESET}" under user/default/process; it lists {offered}')
    custom = reading['custom_presets_on_disk']
    why = f'; making a user preset through the application failed: {made.get("error")}' if made.get('error') else ''
    return (f'the dialog lists no row to export, although the profile holds custom presets on disk '
            f'({custom}){why}; it lists {offered}')


def run(args, work, analysis):
    seeded, at_export, attempts, listed = export_session(args, work, analysis)
    analysis['exports'] = public_attempts(attempts)  # what was asked of the export dialog and what each row landed
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    after = import_session(args, work, analysis, attempts)
    write_json(work / 'presets-after.json', {'after': after})
    gaps = analysis['expectation_gaps'] = configs_expectation_gaps(
        at_export, after, attempts, nothing_listed=nothing_listed(analysis['export_session'], listed))
    analysis['import_readings'] = import_readings(at_export, after, attempts)
    for clause, failed in gaps.items():
        analysis['results'][clause] = 'PASS' if not failed else f'FAIL ({"; ".join(failed)[:400]})'
    print(f'{LOG} gaps {gaps!r}', flush=True)


def main():
    parser = add_common_args(argparse.ArgumentParser(), default_model=FIXTURE)
    args = parser.parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '237'
    root.mkdir(exist_ok=True, parents=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'{LOG} retained work directory: {work}', flush=True)
    analysis = {'case': 237, 'results': {}, 'timings': {}}
    started = time.monotonic()
    try:
        run(args, work, analysis)
    except Exception as exc:  # noqa: BLE001 - recorded; the verdict turns red on it
        analysis['results']['unfinished checks'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        analysis['wall_seconds'] = round(time.monotonic() - started, 3)
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
