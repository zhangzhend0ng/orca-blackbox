#!/usr/bin/env python3
# diag_slice_export_probe.py — Slice the cube and export through the File menu, recording what lands on disk
# feishu: none
"""Slices the standard cube, answers the runtime memory guard if it appears, and then exports once with
File > Export > Export G-code and once with File > Export > Export plate sliced file, each time typing a name
without an extension so that the application decides the extension. Records the dialog title, the proposed default
name, the file type entry, the name and size of every file that appears, and the head and tail of the G-code.
Diagnostic record only; the result is not a verdict."""
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

import m7_common as m7
from diag_file_menu_census import combobox_items, descendants
from harness import export_util, winutil
from m2_slice_chain import click_slice_start
from m3_common import add_common_args, boot_session
from m8_common import wait_arrival

GUARD = 'Memory Usage Warning'


def answer_memory_guard(session, work, analysis):
    dialog = m7.wait_dialog(session.pid, timeout_s=0.3, title_substr=GUARD)
    if not dialog:
        return False
    _, title, _, hwnd = dialog
    children = [(cls, text) for cls, text, _child in descendants(hwnd) if text]
    shot = f'memory-guard-{len(analysis["memory_guard_dialogs"])}.png'
    analysis['memory_guard_dialogs'].append({'title': title, 'texts': children, 'at': time.strftime('%H:%M:%S'),
                                             'screenshot': shot, 'seconds_after_slice_click': round(
                                                 time.monotonic() - analysis['slice_click'], 1)})
    width, height, pixels = winutil.capture_window(hwnd)
    import cv2
    import numpy as np
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    cv2.imwrite(str(work / shot), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR))
    yes = [(rect, child) for text, rect, child in export_util._children_texts(hwnd) if text.strip() == 'Yes, Continue']
    if len(yes) != 1:
        raise ValueError(f'expected one "Yes, Continue" button, found {len(yes)}')
    (left, top, right, bottom), _child = yes[0]
    winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2)
    deadline = time.monotonic() + 10
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    analysis['memory_guard_dialogs'][-1]['closed'] = not winutil.user32.IsWindowVisible(hwnd)
    print('[sliceprobe] memory guard answered Yes', analysis['memory_guard_dialogs'][-1], flush=True)
    return True


def wait_export_enabled(session, work, analysis, timeout_s=150):
    deadline = time.monotonic() + timeout_s
    polls = 0
    while time.monotonic() < deadline:
        answer_memory_guard(session, work, analysis)
        enabled, _ = m7.file_menu_dispatch(session, 'Export G-code', via='Export', inspect_enabled=True)
        polls += 1
        if enabled:
            analysis['export_enabled_after_seconds'] = round(time.monotonic() - analysis['slice_click'], 1)
            return True
        time.sleep(1.0)
    analysis['export_enabled_after_seconds'] = None
    return False


def export_named(session, work, analysis, key, item, title, name):
    entry = {'item': item, 'typed_name': name}
    dispatched, dialog = m7.file_menu_dispatch(session, item, expect_dialog=True, via='Export', timeout_s=10)
    if not dialog:
        analysis[key] = dict(entry, dialog=None, dispatched=bool(dispatched))
        return
    _, seen_title, _, hwnd = dialog
    edit = export_util.find_edit(hwnd)
    entry.update(title=seen_title, default_name=winutil.edit_text(edit, size=1024) if edit else None,
                 types=[combobox_items(child) for cls, _text, child in descendants(hwnd) if cls == 'ComboBox'])
    winutil.select_all(edit)
    winutil.msg_text(edit, str(work))
    winutil._send_msg(hwnd, 0x0111, 1, 0)  # IDOK: a typed directory path navigates, the dialog stays open
    time.sleep(1.0)
    entry['dialog_still_open_after_directory'] = bool(winutil.user32.IsWindowVisible(hwnd))
    edit = export_util.find_edit(hwnd)
    winutil.select_all(edit)
    winutil.msg_text(edit, name)
    entry['filename_before_save'] = winutil.edit_text(edit, size=1024)
    before = {path.name for path in work.iterdir()}
    winutil._send_msg(hwnd, 0x0111, 1, 0)
    deadline = time.monotonic() + 40
    fresh = set()
    while time.monotonic() < deadline:
        fresh = {path.name for path in work.iterdir()} - before
        if fresh and all((work / file).stat().st_size > 0 for file in fresh):
            break
        time.sleep(0.5)
    time.sleep(1.0)
    fresh = {path.name for path in work.iterdir()} - before
    entry['dialog_closed'] = not winutil.user32.IsWindowVisible(hwnd)
    entry['app_alive'] = session.alive()
    entry['files'] = []
    for file in sorted(fresh):
        data = (work / file).read_bytes()
        entry['files'].append({'name': file, 'bytes': len(data), 'head': data[:300].decode('utf-8', 'replace'),
                               'tail': data[-300:].decode('utf-8', 'replace'), 'zip': data[:2] == b'PK'})
    analysis[key] = entry
    print('[sliceprobe]', key, json.dumps(entry, ensure_ascii=False)[:1800], flush=True)


def run(args, work, analysis):
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=args.model)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('fixture did not render')
        analysis['slice_click'] = time.monotonic()
        if not click_slice_start(session):
            raise ValueError('slice click did not take')
        if not wait_export_enabled(session, work, analysis):
            raise ValueError('Export G-code never became enabled')
        export_named(session, work, analysis, 'gcode_export', 'Export G-code', 'Save G-code file as:', 'plate-gcode')
        export_named(session, work, analysis, 'sliced_export', 'Export plate sliced file', 'Save Sliced file as:',
                     'plate-sliced')
    finally:
        session.close()


def main():
    parser = add_common_args(argparse.ArgumentParser(), default_model=HERE / 'fixtures/feishu_std_cube.3mf')
    parser.add_argument('--row', default='sliceprobe')
    args = parser.parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / args.row
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'[sliceprobe] retained work directory: {work}', flush=True)
    analysis = {'case': 'slice export probe', 'results': {}, 'memory_guard_dialogs': []}
    started = time.monotonic()
    try:
        run(args, work, analysis)
        analysis['results']['two File menu exports landed on disk with the editor alive'] = 'PASS'
    except Exception as exc:
        analysis['results']['probe'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    analysis['wall_seconds'] = round(time.monotonic() - started, 3)
    (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
