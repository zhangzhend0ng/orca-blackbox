#!/usr/bin/env python3
# feishu: baseline#232
# m7x_232_import_configs.py — Feishu #232: import a preset config file through File > Import, then import it again.
"""Build a config file holding one printer, one filament and one process preset (the parameters of the
template printer's system presets under names of their own), import it into a fresh profile through
File > Import > Import Configs..., then import the same file again to see what the product does about
the name clash. Presets are compared through the JSON files the profile stores.

The Feishu precondition names an exported .ini file. The import only loads preset
JSON files, plain or inside a zip, at sync/softfever-20261010 (PresetBundle.cpp:1926,
1930, 2083-2086) and likewise at sm-v2.4.0 (944-948, 1032-1035): an .ini is ignored and
the chooser does not offer it. So the config file here is a zip of three preset JSON
files; the .ini is still offered to the chooser once and what happens is recorded,
without taking part in the verdict."""
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
from harness import profile
from m3_common import add_common_args, boot_session
from m7x_249_add_part import capture, stage
from m8_common import wait_arrival
from zip_import_oracle import digest
from import_configs_cases import import_once
from import_configs_oracle import (ARCHIVE, DUPLICATES, IMPORTED, INI, VENDOR, build_config, bundle_presets,
                                   profile_presets, template_presets, verify_import, vendor_directory, write_ini)

TEMPLATE = HERE / 'fixtures/agent_layer_cube.3mf'
LOG = '[m7x232]'


def keep(path, rows):
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')


def run(args, work, analysis):
    archive, datadir = work / 'inputs' / ARCHIVE, work / 'import-profile'
    with stage(analysis, 'build_config'):
        sources = template_presets(TEMPLATE)
        analysis['sources'] = sources
        vendor = vendor_directory([HERE / 'resources', profile.default_presets_dir()], sources)
        analysis['vendor_directory'] = str(vendor)
        built = build_config(vendor, sources, work, archive)
        write_ini(work, built['presets'])
        analysis['inheritance'] = built['chains']
        analysis['config_file'] = {'file': f'inputs/{ARCHIVE}', 'not_harvested': True, **digest(archive)}
        config = [row for path in sorted(work.glob('bb_test_*.json')) for row in bundle_presets(path)]
        analysis['config'] = [[row['kind'], row['name']] for row in config]
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=datadir), model=TEMPLATE)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('fixture did not render')
        analysis['choosers'] = []
        with stage(analysis, 'ini_attempt'):
            # The Feishu text names an .ini file. What the chooser and the product do with it is
            # recorded only; the source shows that no code path loads it.
            try:
                analysis['ini_attempt'] = import_once(session, work / INI, work, analysis, 'ini')
            except (OSError, RuntimeError, ValueError) as exc:
                analysis['ini_attempt'] = {'error': f'{type(exc).__name__}: {exc}'}
        with stage(analysis, 'first_import'):
            start = profile_presets(datadir)
            analysis['first'] = import_once(session, archive, work, analysis, 'zip1')
            first = profile_presets(datadir)
            capture(session, work / 'imported.png')
        with stage(analysis, 'second_import'):
            # The same file again: every preset now exists, so a name clash is certain.
            analysis['second'] = import_once(session, archive, work, analysis, 'zip2')
            second = profile_presets(datadir)
            capture(session, work / 'imported-again.png')
    finally:
        session.close()
    with stage(analysis, 'verify'):
        keep(work / 'presets-start.json', start)
        keep(work / 'presets-first.json', first)
        keep(work / 'presets-second.json', second)
        ini_added = sorted({'/'.join((row['kind'], row['name'])) for row in start})
        analysis['ini_attempt']['presets_in_profile_after'] = ini_added
        one = verify_import(config, start, first, analysis['first']['dialogs'])
        two = verify_import(config, first, second, analysis['second']['dialogs'])
        analysis['first_import'], analysis['second_import'] = one['reading'], two['reading']
        analysis['results'][IMPORTED] = one[IMPORTED]
        analysis['results'][DUPLICATES] = two[DUPLICATES]
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
