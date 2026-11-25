#!/usr/bin/env python3
# feishu: baseline#244
"""Right-click the empty build plate, import the specified cube and inspect the saved plate."""
import argparse
import json
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'tests'))

import m7_common as m7
from harness import export_util, winutil
from import_model_oracle import selected_printer, verify_import
from m3_common import add_common_args, boot_session
from m7x_249_add_part import capture, stage
from m7x_250_negative_part import highlight_menu_item, send_menu_key
from m7x_251_reload_from_disk import write_cube
from m8_common import wait_arrival
from model_context_cases import open_model_menu


def prepare_plate(session, work, analysis):
    # File > New discards the project-embedded U1 preset and falls back to
    # Default Printer on this build. Create the new project from the U1 template.
    project = work / 'new-project.3mf'
    if project.exists() or not m7.save_project_as(session, project, timeout_s=40):
        raise ValueError('could not create new project from the U1 template')
    analysis['initial_printer'] = selected_printer(project)
    root = open_model_menu(session, 'Delete')
    if not root:
        raise ValueError('could not select Delete on the template cube')
    _, menu, index = root
    if not highlight_menu_item(session, menu, index, log='[m7x244]') or not send_menu_key(session, 0x0D, log='[m7x244]'):
        raise ValueError('could not delete the template cube')
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR and m7.find_centroid(session) is None:
            return
        time.sleep(0.3)
    raise ValueError('new project did not show an empty plate after removing its template cube')


def select_model_file(session, source, work, analysis):
    # The original cube's position is known to be inside the plate after New.
    root = open_model_menu(session, 'Add Models', candidates=[analysis['bed_point']])
    if not root:
        raise ValueError('empty plate did not show Add Models')
    _, hmenu, index = root
    if not highlight_menu_item(session, hmenu, index, log='[m7x244]') or not send_menu_key(session, 0x0D, log='[m7x244]'):
        raise ValueError('could not activate exact Add Models row')
    dialog = m7.wait_dialog(session.pid, timeout_s=15)
    if not dialog:
        raise ValueError('file chooser did not open')
    _, title, _, hwnd = dialog
    edit = export_util.find_edit(hwnd)
    if not edit or winutil._window_pid(edit) != session.pid:
        raise ValueError(f'file chooser has no owned filename control: {title}')
    winutil.select_all(edit)
    winutil.msg_text(edit, str(source))
    entered = winutil.edit_text(edit, size=512)
    width, height, pixels = winutil.capture_window(hwnd)
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    if not cv2.imwrite(str(work / 'chooser.png'), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)):
        raise ValueError('unable to retain file chooser image')
    labels = [title, *(t for t, _, child in export_util._children_texts(hwnd)
                       if winutil.user32.IsWindowVisible(child) and child != edit)]
    analysis['chooser'] = {'title': title, 'entered': entered, 'labels': labels}
    print('[m7x244] chooser', analysis['chooser'], flush=True)
    if not any({'stl','3mf','obj'} <= set(re.findall(r'[a-z0-9]+', t.lower())) for t in labels):
        raise ValueError('STL, 3MF and OBJ not observed in chooser')
    if entered != str(source):
        raise ValueError(f'wrong chooser filename: {entered}')
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
    return hwnd


def run(args, work, analysis):
    source = work / 'cube_20mm.stl'
    write_cube(source, 20)
    with stage(analysis, 'open_project'):
        session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=args.model)
    try:
        with stage(analysis, 'prepare_empty_plate'):
            m7.ensure_maximized(session)
            arrived, _ = wait_arrival(session, timeout_s=30)
            center = m7.find_centroid(session) if arrived else None
            if not center:
                raise ValueError('initial printer fixture did not open')
            analysis['bed_point'] = list(center)
            prepare_plate(session, work, analysis)
            capture(session, work / 'prepare-before.png')
        with stage(analysis, 'add_models_chooser'):
            hwnd = select_model_file(session, source, work, analysis)
            analysis['results']['blank plate Add Models opens format-aware file chooser'] = 'PASS'
        with stage(analysis, 'observe_import'):
            arrived, fraction = wait_arrival(session, timeout_s=30, min_frac=0.001)
            analysis['import_fraction'] = fraction
            if not arrived or winutil.user32.IsWindowVisible(hwnd):
                raise ValueError('chooser did not close or cube did not appear')
            capture(session, work / 'prepare-imported.png')
        with stage(analysis, 'save_and_verify'):
            project = work / 'imported.3mf'
            if not m7.save_project_as(session, project, timeout_s=40):
                raise ValueError('failed to save imported project')
            readings = verify_import(project, source)
            if Path(readings['source_file']) != source:
                raise ValueError(f'imported object came from a different run: {readings}')
            analysis['saved'] = readings
            analysis['results']['single imported object on current plate matches the 20mm STL'] = 'PASS'
            print('[m7x244] saved', readings, flush=True)
    finally:
        session.close()


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=HERE / 'fixtures/agent_layer_cube.3mf').parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '244'
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'[m7x244] retained work directory: {work}', flush=True)
    analysis = {'case': 244, 'timings': {}, 'results': {}}
    try:
        run(args, work, analysis)
    except Exception as exc:
        analysis['results']['#244 import evidence'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
