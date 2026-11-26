#!/usr/bin/env python3
# diag_bundle_user_printer.py - Feishu #237 probe: what "Export Preset Bundle" lists once the current
# printer is a user preset with a user process preset of its own.
# feishu: none  (#237 probe: a precondition the case could not build before, not a verdict)
"""Imports the three presets #232 builds (a printer, a filament and a process preset), switches to
the imported printer, saves a user process preset the way a user does, and reads File > Export >
Export Preset Bundle after each step. When `Process presets(.zip)` lists a row, the package is
exported and kept. The dialog's source (CreatePresetsDialog.cpp, sync/softfever-20261010) skips
project-embedded printers when it collects the user presets of each printer, which is what every
earlier #237 session had as its printer; this records whether a user printer changes the list.
Nothing here is a verdict on the Feishu row.

    & runner/hv_go.ps1 -Cases diag_bundle_user_printer -NoSync
"""
import argparse
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine')]

import m7_common as m7  # noqa: E402
from file_export_cases import bundle_survey, export_preset_bundle, save_process_preset  # noqa: E402
from harness import profile, winutil  # noqa: E402
from import_configs_cases import answer_dialogs, find_printer_combo, import_once, select_row  # noqa: E402
from import_configs_oracle import ARCHIVE, NAMES, build_config, project_settings, template_presets  # noqa: E402
from import_configs_oracle import vendor_directory  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
from m7x_232_import_configs import TEMPLATE  # noqa: E402
from m7x_237_export_configs import KIND, SAVED_PRESET, listed_labels, survey_dialog_closed  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from m8_common import combo_text, wait_arrival  # noqa: E402

LOG = '[diag237]'
KEY = 'Process presets(.zip) lists a printer once the printer is a user preset'
FALLBACK = 'Filament presets(.zip)'


def read(session, work, analysis, key, prefix, image):
    """One reading of the export dialog, then make sure it is gone."""
    listed = listed_labels(bundle_survey(session, work, analysis, key=f'survey_{key}', prefix=prefix))
    closed = survey_dialog_closed(session, work, analysis, f'dialog_{key}', image)
    print(f'{LOG} {key}: {listed!r}; dialog closed={closed}', flush=True)
    return listed


def run(args, work, analysis):
    archive, datadir = work / 'inputs' / ARCHIVE, work / 'probe-profile'
    settings = project_settings(TEMPLATE)
    sources = template_presets(TEMPLATE)
    vendor = vendor_directory([HERE / 'resources', profile.default_presets_dir()], sources)
    build_config(vendor, sources, work, archive)
    analysis['choosers'], analysis['timings'] = [], {}
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=datadir), model=TEMPLATE)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('the fixture did not render')
        with stage(analysis, 'survey_embedded'):
            analysis['embedded'] = read(session, work, analysis, 'embedded', '', 'after-survey-embedded.png')
        with stage(analysis, 'import'):
            analysis['import'] = import_once(session, archive, work, analysis, 'zip1')
        with stage(analysis, 'switch_printer'):
            printer = find_printer_combo(session, settings['printer_model'])
            if not printer:
                raise ValueError('the printer preset list control was not found in the sidebar')
            rect, control = printer[1], printer[2]
            point = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)

            def machine_text():
                current = control
                if not winutil.user32.IsWindow(current):
                    current = None
                return combo_text(current) if current else ''

            switch = analysis['switch'] = {'target': NAMES['machine'], 'before': combo_text(control)}
            if not select_row(session, point, session.hwnd, 'machine', NAMES['machine'], work, switch, machine_text):
                raise ValueError(f'the imported printer could not be selected: {switch!r}')
            answer_dialogs(session, work, analysis, 'machine-selected')
        with stage(analysis, 'survey_user'):
            analysis['user'] = read(session, work, analysis, 'user', 'user-', 'after-survey-user.png')
        with stage(analysis, 'make_preset'):
            analysis['preset_saved'] = save_process_preset(session, SAVED_PRESET, work, analysis)
        with stage(analysis, 'survey_after'):
            analysis['after'] = read(session, work, analysis, 'after', 'after-', 'after-survey-after.png')
        listed = analysis['after'][KIND] or analysis['user'][KIND]
        analysis['results'][KEY] = 'PASS' if listed else (
            f'FAIL (listed {analysis["user"][KIND]!r} after the switch and {analysis["after"][KIND]!r} after the preset)')
        if listed or analysis['after'][FALLBACK]:
            kind = KIND if listed else FALLBACK
            folder = work / 'packages' / kind.replace(' ', '_')
            folder.mkdir(parents=True)
            with stage(analysis, 'export'):
                receipt = export_preset_bundle(session, kind, folder, work, analysis, tick='all', key='export')
            analysis['export'] = {'kind': kind, 'landed': receipt.get('landed'), 'dialog_closed': receipt.get('dialog_closed'),
                                  'result': (receipt.get('result') or {}).get('words'),
                                  'files': sorted(f'{path.name}:{path.stat().st_size}' for path in folder.rglob('*') if path.is_file())}
            print(f'{LOG} export {kind}: {analysis["export"]!r}', flush=True)
    finally:
        session.close()


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=TEMPLATE).parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '237'
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='probe-', dir=root))
    print(f'{LOG} retained work directory: {work}', flush=True)
    analysis = {'case': 237, 'timings': {}, 'results': {}}
    try:
        run(args, work, analysis)
    except Exception as exc:  # noqa: BLE001 - a probe keeps whatever happened
        analysis['results'][KEY] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    analysis['wall_seconds'] = round(sum(item.get('duration_s', 0) for item in analysis['timings'].values()), 1)
    (work / 'analysis.json').write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'{LOG} {analysis["results"]}', flush=True)
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
