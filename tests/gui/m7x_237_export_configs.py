#!/usr/bin/env python3
# m7x_237_export_configs.py — Feishu #237: presets exported as a package and imported again
# feishu: baseline#237
"""Feishu #237【配置导出】导出所选预设为配置包，可被重新导入还原 (P1).

Precondition (Feishu): 存在自定义打印机/耗材/工艺预设.
Steps (Feishu): 1. 点击「文件→导出→导出配置包…」; 2. 选择要导出的预设并保存;
3. 随后用「导入配置…」重新导入核对参数一致.
Expected (Feishu): 生成配置包文件（.ini/.zip），重新导入后预设参数与导出前一致.

The custom presets are the process presets the harness seeds into every fresh
profile (<datadir>/user/default/process). A profile seeded the usual way has no
printer installed in its application config; the product then sees none of its
system printers and its export dialog lists nothing to export for them
(measured: census 0d7222e7 and the #232 dev runs a2aafd3d, c378dee). Both
sessions of this case therefore start from a profile whose config also has the
printer those presets were made for installed.

Session 1 opens the standard cube, records what each custom preset means (its
own values over the presets it inherits from), reads what every package type
of File > Export > Export Preset Bundle lists, and exports each row listed for
"Process presets(.zip)" into a folder of its own; the zip is read back and its
bytes and SHA-256 are recorded, as a zip is not among the harvested files.
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
from export_configs_oracle import (PRESET_KINDS, configs_expectation_gaps, import_readings,  # noqa: E402
                                    importable, package_facts, preset_table)
from file_export_cases import BUNDLE_FILES, BUNDLE_KINDS, bundle_survey, export_preset_bundle, import_configs  # noqa: E402
from harness import launcher, profile, winutil  # noqa: E402
from m3_common import add_common_args, ensure_gl_ready  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from m8_common import wait_arrival  # noqa: E402

FIXTURE = HERE / 'fixtures/feishu_std_cube.3mf'
LOG = '[m7x237]'
# The custom process presets of the seeded profile were made for this printer.
KIND = 'Process presets(.zip)'
PRESET_KIND = 'process'
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


def custom_counts(datadir):
    return {kind: len(preset_table(datadir, kind)['presets']) for kind in PRESET_KINDS}


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def export_session(args, work, analysis):
    """Session 1: record the custom presets, read the export dialog, export each listed row of the
    process type. Returns (the presets as seeded, the presets as they were at the export, the
    export attempts)."""
    datadir = work / 'export-profile'
    seed(datadir)
    reading = analysis['export_session'] = {'installed_printer': dict(INSTALLED),
                                            'custom_presets_on_disk': custom_counts(datadir)}
    seeded = preset_table(datadir, PRESET_KIND)
    if not seeded['presets']:
        raise ValueError('precondition not met: the profile holds no custom process preset')
    reading['custom_process_presets'] = sorted(seeded['presets'])
    session = boot(args, datadir, args.model)
    attempts = []
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('the fixture did not render')
        with stage(analysis, 'read_export_dialog'):
            survey = bundle_survey(session, work, analysis)
        listed = {kind: survey['kinds'][kind]['items'] for kind in BUNDLE_KINDS}
        reading['listed'] = listed
        rows = [row['label'] for row in listed[KIND]]
        for label in rows:
            folder = work / 'packages' / re.sub(r'[^A-Za-z0-9._-]+', '_', label)
            folder.mkdir(parents=True)
            attempt = {'kind': KIND, 'row': label, 'directory': folder.relative_to(work).as_posix()}
            try:
                with stage(analysis, f'export_{len(attempts) + 1}'):
                    receipt = export_preset_bundle(session, KIND, folder, work, analysis, tick=[label],
                                                   key=f'export_{len(attempts) + 1}')
                    for name in ('result', 'refusal'):
                        if receipt.get(name):
                            attempt[f'{name}_words'] = receipt[name].get('words')
                    attempt['dialog_closed'] = receipt.get('dialog_closed')
                    attempt['landed'] = receipt['landed']
            except Exception as exc:  # noqa: BLE001 - recorded; the verdict turns red on it
                attempt['error'] = f'{type(exc).__name__}: {exc}'
                traceback.print_exc()
            attempts.append(attempt)
            if attempt.get('error'):
                break
        attempts.extend({'kind': KIND, 'row': label, 'error': 'not attempted: the row before it failed'}
                        for label in rows[len(attempts):])
        at_export = preset_table(datadir, PRESET_KIND)
        for attempt in attempts:
            if not attempt.get('landed'):
                continue
            package = Path(work, attempt['directory']) / BUNDLE_FILES[KIND]
            attempt['package'] = package_facts(package, at_export)
            attempt['package']['path'] = package.relative_to(work).as_posix()
        reading['presets_rewritten_while_open'] = sorted(
            name for name in seeded['presets']
            if name not in at_export['presets'] or at_export['presets'][name] != seeded['presets'][name])
        write_json(work / 'presets-before.json', {'kind': PRESET_KIND, 'seeded': seeded, 'at_export': at_export})
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        state = reading['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    finally:
        session.close()
    if state != {'alive': True, 'dialog': None}:
        raise ValueError(f'the editor was left in an unexpected state after the exports: {state!r}')
    return seeded, at_export, attempts


def import_session(args, work, analysis, attempts):
    """Session 2: a profile without user presets imports every package that holds a preset; the
    presets on disk after the editor is closed are returned."""
    ready = importable(attempts)
    packages = [Path(work, attempt['directory']) / BUNDLE_FILES[KIND] for attempt in attempts
                if attempt.get('package') in ready]
    datadir = work / 'import-profile'
    reading = analysis['import_session'] = {'installed_printer': dict(INSTALLED),
                                            'sources': [package.relative_to(work).as_posix() for package in packages]}
    if not packages:
        reading['note'] = 'not run: no package holding a preset was exported'
        return preset_table(datadir, PRESET_KIND)
    reading['seeded_user_presets_removed'] = seed(datadir, with_presets=False)
    reading['presets_at_start'] = custom_counts(datadir)
    session = boot(args, datadir, args.model)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('the fixture did not render')
        for number, package in enumerate(packages, 1):
            with stage(analysis, f'import_{number}'):
                import_configs(session, package, work, analysis, key=f'import_{number}')
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        state = reading['editor_after_import'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    finally:
        session.close()
    if state != {'alive': True, 'dialog': None}:
        raise ValueError(f'the editor was left in an unexpected state after the import: {state!r}')
    return preset_table(datadir, PRESET_KIND)


def run(args, work, analysis):
    seeded, at_export, attempts = export_session(args, work, analysis)
    analysis['exports'] = attempts  # what was asked of the export dialog and what each row landed
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    after = import_session(args, work, analysis, attempts)
    write_json(work / 'presets-after.json', {'kind': PRESET_KIND, 'after': after})
    nothing = (f'"{KIND}" lists no row in this profile, although {len(seeded["presets"])} custom process '
               f'presets are on disk; the dialog lists {analysis["export_session"]["listed"]!r}')
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
