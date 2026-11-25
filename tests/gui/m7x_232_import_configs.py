#!/usr/bin/env python3
# feishu: baseline#232
# m7x_232_import_configs.py — Feishu #232: export a preset bundle, import it through File > Import and compare the presets.
"""Export one preset bundle from the U1 template project (File > Export > Export Preset Bundle..., type
Printer config bundle), import that file into a fresh profile through File > Import > Import Configs...,
and compare the presets the profile stores before and after with the presets in the file.

The Feishu precondition names an exported .ini file. The chooser of this build
offers *.json, *.zip, *.orca_printer and *.orca_filament only (MainFrame.cpp:3466-3468,
sm-v2.4.0); .ini is not offered, so the config file here is one the product
exports itself. The Import result box is MainFrame.cpp:3497-3503; a name clash
asks through ConfigsOverwriteConfirmDialog (MainFrame.cpp:3479-3484)."""
import argparse
import json
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

import m7_common as m7
from m3_common import add_common_args, boot_session
from m7x_249_add_part import capture, stage
from m8_common import wait_arrival
from zip_import_cases import wait_closed
from zip_import_oracle import digest
from import_configs_cases import collect_import_dialogs, choose_configs, export_bundle
from import_configs_oracle import bundle_presets, profile_presets, verify_import

TEMPLATE = HERE / 'fixtures/agent_layer_cube.3mf'
LOG = '[m7x232]'
BUNDLE = 'printer.orca_printer'


def boot(args, work, profile):
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / profile), model=TEMPLATE)
    m7.ensure_maximized(session)
    if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
        raise ValueError('fixture did not render')
    return session


def keep(path, rows):
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')


def run(args, work, analysis):
    bundle = work / 'inputs' / BUNDLE
    # Session 1 exports the config file with the product itself.
    with stage(analysis, 'export_bundle'):
        session = boot(args, work, 'export-profile')
        try:
            export_bundle(session, bundle, work, analysis)
            analysis['bundle'] = {'file': f'inputs/{BUNDLE}', 'not_harvested': True, **digest(bundle)}
        finally:
            session.close()
    # Session 2 starts from an empty profile and imports that file.
    with stage(analysis, 'import_configs'):
        datadir = work / 'import-profile'
        session = boot(args, work, 'import-profile')
        try:
            analysis['dialogs'] = []
            before = profile_presets(datadir)
            chooser = choose_configs(session, bundle, work, analysis)
            if not wait_closed(chooser, 10):
                raise ValueError('chooser did not close after Open')
            collect_import_dialogs(session, work, analysis)
            after = profile_presets(datadir)
            capture(session, work / 'imported.png')
        finally:
            session.close()
    with stage(analysis, 'verify'):
        keep(work / 'presets-before.json', before)
        keep(work / 'presets-after.json', after)
        config = bundle_presets(bundle)
        analysis['results'].update(verify_import(config, before, after, analysis['dialogs']))
        print(LOG, analysis['results'], flush=True)


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=TEMPLATE).parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '232'
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'{LOG} retained work directory: {work}', flush=True)
    analysis = {'case': 232, 'timings': {}, 'results': {}}
    try:
        run(args, work, analysis)
    except Exception as exc:
        analysis['results']['unfinished checks'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
