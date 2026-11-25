"""Run and retain each reserve case in a fresh guest project profile."""
import argparse
import json
from pathlib import Path
import tempfile
import time
import traceback
from types import SimpleNamespace

import m7_common as m7
from m3_common import add_common_args, boot_session
from m7x_249_add_part import capture
from m7x_250_negative_part import highlight_menu_item, send_menu_key
from m8_common import wait_arrival


def case_main(number, model, prepare_fixture, steps, extra_args=None):
    parser = add_common_args(argparse.ArgumentParser(), default_model=model)
    if extra_args:
        extra_args(parser)
    args = parser.parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / str(number)
    root.mkdir(exist_ok=True, parents=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'[m7x{number}] retained work directory: {work}', flush=True)
    analysis = {'case': number, 'results': {}}
    started = time.monotonic()
    session = None
    try:
        fixture = prepare_fixture(args.model, work)
        session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=fixture)
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('fixture did not render')
        steps(session, work, analysis, args)
    except Exception as exc:
        analysis['results']['unfinished checks'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        analysis['wall_seconds'] = round(time.monotonic() - started, 3)
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
        if session is not None:
            session.close()
    return m7.m7_verdict(analysis['results'])


def save_snapshot(session, work, phase):
    if not session.alive() or m7.wait_dialog(session.pid, timeout_s=0.75):
        raise ValueError(f'unexpected dialog or closed editor during {phase}')
    capture(session, work / (phase + '.png'))
    path = work / (phase + '.3mf')
    if not m7.save_project_as(session, path, timeout_s=40):
        raise ValueError(f'failed to retain {phase} project')
    return path


def activate(session, menu, log):
    if menu is None:
        raise ValueError('expected enabled native menu item was never visible')
    _, handle, index = menu
    if not highlight_menu_item(session, handle, index, log=log) or not send_menu_key(session, 13, log=log):
        raise ValueError('could not activate the native menu item')
