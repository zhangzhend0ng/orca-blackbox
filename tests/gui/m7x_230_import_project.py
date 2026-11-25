#!/usr/bin/env python3
# feishu: baseline#230
# m7x_230_import_project.py — Feishu #230: import an exported two-plate project through File > Import and compare it.
"""Open the #242 two-plate project and save it again as this run's project.3mf, import that file into an
empty plate through File > Import > Import 3MF/STL/STEP/SVG/OBJ/AMF..., and compare plates, objects and
settings item by item. No check is relaxed when the product behaves differently from the expectation."""
import argparse
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

import m7_common as m7
from harness import winutil
from m3_common import add_common_args, boot_session
from m7x_244_add_model import prepare_plate
from m7x_249_add_part import capture, stage
from m8_common import wait_arrival
from zip_import_cases import choose_project, wait_closed
from zip_import_oracle import digest
from import_project_oracle import verify_restore

SOURCE = HERE / 'docs/runs/evidence/feishu-242-2026-11-25/7bed4701-run1-before.3mf'
TEMPLATE = HERE / 'fixtures/agent_layer_cube.3mf'
LOG = '[m7x230]'


def boot(args, work, model, profile):
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / profile), model=model)
    m7.ensure_maximized(session)
    if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
        raise ValueError('fixture did not render')
    return session


def export_project(args, work, analysis, project):
    # Session 1 opens the #242 GUI-saved two-plate project (plates Keep and
    # Remove, Alpha on extruder 1 and Bravo on extruder 3) and saves it again,
    # so project.3mf is a file this software exported in this run.
    session = boot(args, work, SOURCE, 'export-profile')
    try:
        if m7.wait_dialog(session.pid, timeout_s=1.0) or not session.alive():
            raise ValueError('a dialog is still open in the two-plate project')
        if not m7.save_project_as(session, project, timeout_s=40):
            raise ValueError('could not save project.3mf from the opened two-plate project')
        analysis['export'] = digest(project)
    finally:
        session.close()


def import_project(args, work, analysis, project, imported):
    # Session 2 starts from the empty U1 template plate, the same start as #244 and #231.
    session = boot(args, work, TEMPLATE, 'import-profile')
    try:
        with stage(analysis, 'prepare_empty_plate'):
            center = m7.find_centroid(session)
            if not center:
                raise ValueError('initial printer fixture did not open')
            analysis['bed_point'] = list(center)
            prepare_plate(session, work, analysis)
            capture(session, work / 'prepare-before.png')
        with stage(analysis, 'import_project_chooser'):
            chooser = choose_project(session, project, work, analysis)
        with stage(analysis, 'observe_import'):
            arrived, fraction = wait_arrival(session, timeout_s=30, min_frac=0.001)
            analysis['import_fraction'] = fraction
            if not arrived or winutil.user32.IsWindowVisible(chooser):
                raise ValueError('chooser did not close or no model appeared after the import')
            time.sleep(3.0)  # Let the imported objects finish their automatic placement.
            capture(session, work / 'imported.png')
        with stage(analysis, 'save_imported'):
            blocking = m7.wait_dialog(session.pid, timeout_s=1.0)
            analysis['dialog_after_import'] = blocking[1] if blocking else None
            if blocking:
                raise ValueError(f'unexpected dialog after the import: {blocking[1]}')
            if not m7.save_project_as(session, imported, timeout_s=40):
                raise ValueError('could not save imported.3mf')
        with stage(analysis, 'verify_restore'):
            analysis['restore'] = verify_restore(project, imported, start=work / 'new-project.3mf')
            analysis['results'].update(analysis['restore']['results'])
            print(LOG, 'restore', analysis['restore']['checks'], flush=True)
    finally:
        session.close()


def run(args, work, analysis):
    project, imported = work / 'project.3mf', work / 'imported.3mf'
    with stage(analysis, 'export_project'):
        export_project(args, work, analysis, project)
    with stage(analysis, 'import_project'):
        import_project(args, work, analysis, project, imported)


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=SOURCE).parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '230'
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'{LOG} retained work directory: {work}', flush=True)
    analysis = {'case': 230, 'timings': {}, 'results': {}}
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
