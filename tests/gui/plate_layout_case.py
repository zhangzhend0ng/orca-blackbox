"""Save one fresh GUI session's plate geometry and inspect every case stage."""
import argparse
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'),
                str(HERE / 'tests' / 'topcap')]

import m7_common as m7
from delete_object_oracle import objects
from m3_common import add_common_args, boot_session
from m7x_249_add_part import capture
from m7x_250_negative_part import highlight_menu_item, send_menu_key
from m8_common import wait_arrival
from model_context_cases import open_model_menu
from plate_layout_fixture import create_fixture


def save_stage(session, work, phase):
    if not session.alive() or m7.wait_dialog(session.pid, timeout_s=0.5):
        raise ValueError(f'unexpected dialog or editor exit before {phase}')
    path = work / f'{phase}.3mf'
    capture(session, work / f'{phase}.png')
    if not m7.save_project_as(session, path, timeout_s=40):
        raise ValueError(f'could not save {phase} project')
    return path


def activate(session, label, candidates, log):
    menu = open_model_menu(session, label, candidates=candidates)
    if menu is None:
        raise ValueError(f'native context menu did not expose enabled {label!r}')
    _, handle, index = menu
    if not highlight_menu_item(session, handle, index, log=log) or not send_menu_key(session, 13, log=log):
        raise ValueError(f'could not activate context menu item {label!r}')
    print(f'{log} activated context menu item {label!r}', flush=True)


def activate_on_blank_plate(session, label, log):
    width = m7.capture_bgr(session).shape[1]
    center = m7.find_centroid(session)
    if not center:
        raise ValueError('missing visible models for locating blank plate space')
    x, y = center
    # Anchor at the rendered objects rather than the application window. The
    # exact plate-only item verifies a blank spot on the plate was hit.
    candidates = [(x + round(width*dx), y + round(width*dy))
                  for dx, dy in ((.09, 0), (-.09, 0), (0, .065), (0, -.065),
                                 (.11, .045), (-.11, .045))]
    activate(session, label, candidates, log)


def record_checks(analysis, report):
    analysis['geometry'] = report
    for check, passed in report['checks'].items():
        analysis['results'][check] = 'PASS' if passed else 'FAIL'


def run_case(case, operation):
    parser = add_common_args(argparse.ArgumentParser(),
                             default_model=HERE / 'fixtures/feishu_std_cubesfar.3mf')
    parser.add_argument('--save-only', action='store_true')
    args = parser.parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / str(case)
    root.mkdir(exist_ok=True, parents=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    log = f'[m7x{case}]'
    print(f'{log} retained work directory: {work}', flush=True)
    analysis = {'case': case, 'results': {}, 'phase_seconds': {}}
    started = time.monotonic()
    try:
        fixture = work / 'fixture.3mf'
        create_fixture(args.model, fixture, case)
        session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=fixture)
        try:
            m7.ensure_maximized(session)
            if not wait_arrival(session, timeout_s=30, min_frac=.001)[0]:
                raise ValueError('plate fixture objects were not visible')
            before = save_stage(session, work, 'before')
            if objects(fixture) != objects(before):
                raise ValueError('loaded project geometry differs from the fixture')
            analysis['results']['initial fixture geometry preserved'] = 'PASS'
            analysis['phase_seconds']['baseline'] = round(time.monotonic() - started, 3)
            if args.save_only:
                analysis['results']['full Feishu action chain'] = 'FAIL (baseline only)'
            else:
                operation(session, work, before, analysis, log)
        finally:
            session.close()
    except Exception as exc:
        analysis['results']['case execution'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        analysis['phase_seconds']['total'] = round(time.monotonic() - started, 3)
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
        print(f'{log} analysis {json.dumps(analysis, ensure_ascii=True)}', flush=True)
    return m7.m7_verdict(analysis['results'])
