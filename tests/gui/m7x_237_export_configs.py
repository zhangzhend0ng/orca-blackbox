#!/usr/bin/env python3
# m7x_237_export_configs.py — Feishu #237: presets exported as a package and imported again
# feishu: baseline#237
"""Feishu #237【配置导出】导出所选预设为配置包，可被重新导入还原 (P1).

Precondition (Feishu): 存在自定义打印机/耗材/工艺预设.
Steps (Feishu): 1. 点击「文件→导出→导出配置包…」; 2. 选择要导出的预设并保存;
3. 随后用「导入配置…」重新导入核对参数一致.
Expected (Feishu): 生成配置包文件（.ini/.zip），重新导入后预设参数与导出前一致.

The custom presets are the process presets the harness seeds into every fresh
profile (<datadir>/user/default/process). Both sessions start from a profile
whose config also has the printer those presets were made for installed; with
the usual seed the export dialog lists nothing for any printer (measured: census
0d7222e7, #232 dev runs) and with the printer installed too it listed no process
row (measured: run da4ecd60).

Session 1 opens the standard cube, records what each custom preset means (its
own values over the presets it inherits from), reads what every package type of
File > Export > Export Preset Bundle lists, and exports each row listed for
"Process presets(.zip)". When that type lists nothing, it exports the first
filament name that "Filament presets(.zip)" lists instead, so that the export is
really walked; which row that was is written down. The zip is read back, its
bytes and SHA-256 recorded, the words of the result box are read from pixels,
and the lines the application wrote to its own log are kept as ``app-log.log``
(a zip and the application's log are not among the harvested files).
Session 2 starts from a profile without any user preset, imports the packages
through File > Import > Import Configs and is closed. The presets it then has
on disk are compared with the recorded ones, parameter by parameter.
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
                                    configs_expectation_gaps, failed_to_add, import_readings, importable,
                                    member_configs, package_facts, preset_table, public_attempts)
from file_export_cases import BUNDLE_FILES, BUNDLE_KINDS, bundle_survey, export_preset_bundle, import_configs  # noqa: E402
from harness import launcher, profile, winutil  # noqa: E402
from m3_common import add_common_args, ensure_gl_ready  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from m8_common import wait_arrival  # noqa: E402

FIXTURE = HERE / 'fixtures/feishu_std_cube.3mf'
LOG = '[m7x237]'
# The custom process presets of the seeded profile were made for this printer.
KIND = 'Process presets(.zip)'
FALLBACK = 'Filament presets(.zip)'
INSTALLED = {'vendor': 'Snapmaker', 'model': 'Snapmaker U1', 'nozzle_diameter': '0.4'}


def seed(datadir, with_presets=True):
    """A new profile as the harness seeds it, with the printer also installed in its application
    config; without the seeded user presets when asked. Returns how many of them were removed."""
    profile.seed_profile(datadir, fresh=False, conf_extra={'models': [dict(INSTALLED)]})
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


def custom_counts(tables):
    return {kind: len(table['presets']) for kind, table in tables.items()}


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def export_plan(listed):
    """[(zip type, row)]: every row the process type lists, or else the first filament name the
    filament type lists, so that something is exported whenever the dialog offers anything."""
    if listed[KIND]:
        return [(KIND, label, 'a printer with custom process presets') for label in listed[KIND]]
    if listed[FALLBACK]:
        return [(FALLBACK, listed[FALLBACK][0], f'"{KIND}" lists no row: the first filament name that is listed')]
    return []


def _failed_lines(attempt, failed, attempts):
    """The log lines about files that could not be added, for one export."""
    if len(attempts) == 1 or attempt['kind'] != FALLBACK:
        return list(failed)
    return [line for line in failed if attempt['row'] in line]


def export_session(args, work, analysis):
    """Session 1: record the custom presets, read the export dialog, export what it lists, and
    keep what the application said about it. Returns (the presets as seeded, the presets as
    they were at the export, the export attempts)."""
    datadir = work / 'export-profile'
    seed(datadir)
    seeded = {kind: preset_table(datadir, kind) for kind in PRESET_KINDS}
    reading = analysis['export_session'] = {'installed_printer': dict(INSTALLED),
                                            'custom_presets_on_disk': custom_counts(seeded)}
    if not any(seeded[kind]['presets'] for kind in PRESET_KINDS):
        raise ValueError('precondition not met: the profile holds no custom preset')
    reading['custom_presets'] = {kind: sorted(seeded[kind]['presets']) for kind in PRESET_KINDS}
    attempts, state = [], None
    session = boot(args, datadir, args.model)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('the fixture did not render')
        with stage(analysis, 'read_export_dialog'):
            survey = bundle_survey(session, work, analysis)
        listed = {kind: [row['label'] for row in survey['kinds'][kind]['items']] for kind in BUNDLE_KINDS}
        reading['listed'] = listed
        reading['export_plan'] = [{'kind': kind, 'row': row, 'why': why} for kind, row, why in export_plan(listed)]
        for kind, label, _why in export_plan(listed):
            folder = work / 'packages' / re.sub(r'[^A-Za-z0-9._-]+', '_', f'{kind} {label}')
            folder.mkdir(parents=True)
            attempt = {'kind': kind, 'row': label, 'directory': folder.relative_to(work).as_posix(),
                       'app_log': {'lines': []}}
            mark = app_log_mark(datadir)
            try:
                with stage(analysis, f'export_{len(attempts) + 1}'):
                    receipt = export_preset_bundle(session, kind, folder, work, analysis, tick=[label],
                                                   key=f'export_{len(attempts) + 1}')
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
            attempts.append(attempt)
            if attempt.get('error'):
                break
        attempts.extend({'kind': kind, 'row': label, 'directory': '', 'app_log': {'lines': []},
                         'error': 'not attempted: the row before it failed'}
                        for kind, label, _why in export_plan(listed)[len(attempts):])
        at_export = {kind: preset_table(datadir, kind) for kind in PRESET_KINDS}
        for attempt in attempts:
            if not attempt.get('landed'):
                continue
            package = Path(work, attempt['directory']) / BUNDLE_FILES[attempt['kind']]
            attempt['package'] = package_facts(package, at_export, kind=attempt['kind'], rows=[attempt['row']])
            attempt['package']['path'] = package.relative_to(work).as_posix()
            attempt['_members'] = member_configs(package)
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
    names = (INSTALLED['model'],) + tuple(name for kind in PRESET_KINDS for name in seeded[kind]['presets'])
    lines = app_log_lines(datadir, keywords=APP_LOG_KEYWORDS, extra=APP_LOG_LOADING, names=names)
    failed = failed_to_add(lines)
    for attempt in attempts:
        attempt['app_log']['failed_to_add'] = _failed_lines(attempt, failed, attempts)
    reading['app_log'] = {
        'file': 'app-log.log', 'lines_kept': len(lines),
        'sources': [f'log/{path.name} ({size} bytes)' for path, size in app_log_files(datadir)],
        'loaded_user_presets': [line[-200:] for line in lines if 'load config successful' in line.casefold()][-12:],
        'parents_not_found': [line[-200:] for line in lines if 'can not find parent' in line.casefold()][-12:],
        'printer_visibility': [line[-200:] for line in lines if 'is_visible set to' in line.casefold()][-12:],
        'failed_to_add': [line[-240:] for line in failed[-6:]],
        'added': [line[-200:] for line in lines if 'json add successful' in line.casefold()][-12:]}
    (work / 'app-log.log').write_text(app_log_text(datadir, [
        ('the whole log, as far as it matters here', lines[-APP_LOG_KEEP:]),
        *[(f'export {number}: {attempt["kind"]} / {attempt["row"]}', attempt['app_log']['lines'])
          for number, attempt in enumerate(attempts, 1)]]), encoding='utf-8')
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
    reading = analysis['import_session'] = {'installed_printer': dict(INSTALLED),
                                            'sources': [package.relative_to(work).as_posix() for package in packages]}
    if not packages:
        reading['note'] = 'not run: no package holding a preset was exported'
        return {kind: preset_table(datadir, kind) for kind in PRESET_KINDS}
    reading['seeded_user_presets_removed'] = seed(datadir, with_presets=False)
    reading['presets_at_start'] = custom_counts({kind: preset_table(datadir, kind) for kind in PRESET_KINDS})
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
    reading['app_log'] = {'lines': len(lines),
                         'presets_skipped': [line[-200:] for line in lines if 'skip' in line.casefold()][-12:]}
    with open(work / 'app-log.log', 'a', encoding='utf-8') as handle:
        handle.write('\n' + '\n'.join(app_log_section('the import', lines)) + '\n')
    if state != {'alive': True, 'dialog': None}:
        raise ValueError(f'the editor was left in an unexpected state after the import: {state!r}')
    return {kind: preset_table(datadir, kind) for kind in PRESET_KINDS}


def run(args, work, analysis):
    seeded, at_export, attempts, listed = export_session(args, work, analysis)
    analysis['exports'] = public_attempts(attempts)  # what was asked of the export dialog and what each row landed
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    after = import_session(args, work, analysis, attempts)
    write_json(work / 'presets-after.json', {'after': after})
    offered = '; '.join(f'{kind}: {labels or "nothing"}' for kind, labels in listed.items())
    custom = analysis['export_session']['custom_presets_on_disk']
    nothing = (f'the dialog lists no row to export, although the profile holds custom presets on disk '
               f'({custom}); it lists {offered}')
    gaps = analysis['expectation_gaps'] = configs_expectation_gaps(at_export, after, attempts, nothing_listed=nothing)
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
