#!/usr/bin/env python3
# diag_file_menu_census.py — Read-only census of the topbar File menu and its Import/Export submenus
# feishu: none
"""Lists every File / Import / Export row with its enabled state before and after slicing, and for the file
dialogs behind the import and export rows records the dialog title, the filter texts, the proposed file name and a
screenshot. Every dialog is cancelled; nothing is imported or exported. The rows are only read, so the result is a
diagnostic record, not a verdict."""
import argparse
import ctypes
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

import m7_common as m7
from harness import export_util, topbar_util, winutil
from m2_slice_chain import click_slice_start, wait_slicing_done
from m3_common import add_common_args, boot_session
from m8_common import wait_arrival

PROBED = ('g-code', 'sliced file', 'stl', 'config', 'zip', 'generic 3mf', 'preset bundle')
SKIPPED = ('factory', 'sd card')


def rows(hmenu):
    return [{'index': index, 'label': text, 'enabled': bool(hmenu) and not flags & 3,
             'separator': bool(flags & 0x800), 'submenu': bool(flags & 0x10)}
            for index, text, flags in topbar_util.menu_items(hmenu)]


def census(session):
    menu = topbar_util.open_file_menu(session)
    if not menu:
        raise ValueError('File menu did not open')
    _, _, hmenu = menu
    out = {'file': rows(hmenu), 'submenus': {}}
    for item in out['file']:
        if 'import' in item['label'].lower() or 'export' in item['label'].lower():
            _, sub = topbar_util.item_info(hmenu, item['index'])
            out['submenus'][item['label']] = rows(sub)
    topbar_util.close_menu_windows(session.pid)
    return out


def descendants(hwnd):
    out = []
    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(child, _lp):
        text = ctypes.create_unicode_buffer(4096)
        winutil.user32.GetWindowTextW(child, text, 4096)
        cls = ctypes.create_unicode_buffer(128)
        winutil.user32.GetClassNameW(child, cls, 128)
        out.append((cls.value, text.value, child))
        return True

    winutil.user32.EnumChildWindows(ctypes.c_void_p(hwnd), callback(visit), 0)
    return out


def combobox_items(combobox):
    """Every list entry of a ComboBox child (CB_GETCOUNT / CB_GETLBTEXT); the selected text is not a window text."""
    import ctypes.wintypes as wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    count = user32.SendMessageW(combobox, 0x0146, 0, 0)
    items = []
    for index in range(count):
        length = user32.SendMessageW(combobox, 0x0149, index, 0)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.SendMessageW(combobox, 0x0148, index, ctypes.addressof(buffer))
        items.append(buffer.value)
    return {'selected': user32.SendMessageW(combobox, 0x0147, 0, 0), 'items': items}


def probe_dialog(session, work, via, label, serial):
    entry = {'via': via, 'item': label}
    dispatched, dialog = m7.file_menu_dispatch(session, label, expect_dialog=True, via=via, timeout_s=8)
    entry['dispatched'] = bool(dispatched)
    if not dialog:
        entry['dialog'] = None
        return entry
    _, title, _, hwnd = dialog
    entry['title'] = title
    children = descendants(hwnd)
    entry['texts'] = [text for _cls, text, _child in children if text]
    entry['classes'] = sorted({cls for cls, _text, _child in children})
    entry['comboboxes'] = [combobox_items(child) for cls, _text, child in children if cls == 'ComboBox']
    edit = export_util.find_edit(hwnd)
    entry['filename'] = winutil.edit_text(edit, size=1024) if edit else None
    width, height, pixels = winutil.capture_window(hwnd)
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    entry['screenshot'] = f'dialog-{serial:02d}.png'
    cv2.imwrite(str(work / entry['screenshot']), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR))
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)  # IDCANCEL
    entry['closed_by'] = 'IDCANCEL'
    for attempt in range(20):
        if not winutil.user32.IsWindowVisible(hwnd):
            break
        time.sleep(0.2)
    else:
        winutil._send_msg(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        entry['closed_by'] = 'WM_CLOSE'
        for _attempt in range(20):
            if not winutil.user32.IsWindowVisible(hwnd):
                break
            time.sleep(0.2)
    entry['dialog_closed'] = not winutil.user32.IsWindowVisible(hwnd)
    entry['app_alive'] = session.alive()
    entry['next_dialog'] = (m7.wait_dialog(session.pid, timeout_s=0.5) or [None, None])[1]
    print('[census] dialog', json.dumps(entry, ensure_ascii=False), flush=True)
    return entry


def probe_submenu(session, work, submenu, phase, serial):
    out = []
    for item in submenu or []:
        label = item['label'].split('\t')[0].rstrip('. ')
        low = label.lower()
        wanted = any(part in low for part in PROBED) and not any(part in low for part in SKIPPED)
        if not item['enabled'] or item['separator'] or not wanted:
            continue
        entry = probe_dialog(session, work, phase, label, serial)
        serial += 1
        out.append(entry)
        if entry.get('dialog_closed') is False or entry.get('app_alive') is False:
            print('[census] stopping: dialog did not close or app exited', flush=True)
            break
    return out, serial


def toplevels(pid):
    """Visible top-level windows of the process: class, title, screen rect and handle."""
    import ctypes.wintypes as wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    out = []
    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _lp):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, cls, 128)
            text = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, text, 512)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            out.append({'hwnd': hwnd, 'class': cls.value, 'title': text.value,
                        'rect': [rect.left, rect.top, rect.right, rect.bottom]})
        return True

    user32.EnumWindows(callback(visit), 0)
    return out


def describe(hwnd):
    """Every descendant with class, text, visibility and screen rect (custom-drawn wx controls)."""
    import ctypes.wintypes as wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    out = []
    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(child, _lp):
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(child, cls, 128)
        text = ctypes.create_unicode_buffer(4096)
        user32.GetWindowTextW(child, text, 4096)
        rect = wintypes.RECT()
        user32.GetWindowRect(child, ctypes.byref(rect))
        out.append({'class': cls.value, 'text': text.value, 'visible': bool(user32.IsWindowVisible(child)),
                    'rect': [rect.left, rect.top, rect.right, rect.bottom]})
        return True

    user32.EnumChildWindows(ctypes.c_void_p(hwnd), callback(visit), 0)
    return out


def zip_dialog_census(session, work, analysis):
    """Import Zip Archive shows an application-drawn file list before anything is loaded: record and close it."""
    from zipfile import ZipFile

    from m7x_251_reload_from_disk import write_cube

    archive = work / 'models.zip'
    with ZipFile(archive, 'w') as bundle:
        for name, size in (('cube_10mm.stl', 10), ('cube_20mm.stl', 20), ('cube_30mm.stl', 30)):
            member = work / name
            write_cube(member, size)
            bundle.write(member, name)
    known = {window['hwnd'] for window in toplevels(session.pid)}
    entry = {'item': 'Import Zip Archive'}
    dispatched, dialog = m7.file_menu_dispatch(session, 'Import Zip Archive', expect_dialog=True, via='Import', timeout_s=8)
    entry['dispatched'] = bool(dispatched)
    if not dialog:
        entry['file_dialog'] = None
        return entry
    entry['file_dialog'] = dialog[1]
    hwnd = dialog[3]
    edit = export_util.find_edit(hwnd)
    winutil.select_all(edit)
    winutil.msg_text(edit, str(archive))
    winutil._send_msg(hwnd, 0x0111, 1, 0)  # IDOK
    fresh = []
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        fresh = [window for window in toplevels(session.pid)
                 if window['hwnd'] not in known and window['hwnd'] != hwnd and window['class'] != '#32768']
        if fresh:
            break
        time.sleep(0.5)
    entry['new_windows'] = fresh
    if not fresh:
        entry['app_alive'] = session.alive()
        return entry
    target = max(fresh, key=lambda window: (window['rect'][2] - window['rect'][0]) * (window['rect'][3] - window['rect'][1]))
    time.sleep(1.0)
    entry['dialog'] = target
    entry['children'] = describe(target['hwnd'])
    width, height, pixels = winutil.capture_window(target['hwnd'])
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    entry['screenshot'] = 'zip-dialog.png'
    cv2.imwrite(str(work / entry['screenshot']), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR))
    winutil._send_msg(target['hwnd'], 0x0010, 0, 0)  # WM_CLOSE
    deadline = time.monotonic() + 8
    while winutil.user32.IsWindowVisible(target['hwnd']) and time.monotonic() < deadline:
        time.sleep(0.2)
    entry['dialog_closed'] = not winutil.user32.IsWindowVisible(target['hwnd'])
    entry['app_alive'] = session.alive()
    entry['windows_after_close'] = [window for window in toplevels(session.pid) if window['hwnd'] not in known]
    print('[census] zip dialog', json.dumps(entry, ensure_ascii=False)[:3000], flush=True)
    return entry


def run(args, work, analysis):
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=args.model)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('fixture did not render')
        before = census(session)
        analysis['menus_before_slice'] = before
        print('[census] before', json.dumps(before, ensure_ascii=False), flush=True)
        serial = 0
        import_submenu = next((v for k, v in before['submenus'].items() if k.lower().startswith('import')), [])
        export_submenu = next((v for k, v in before['submenus'].items() if k.lower().startswith('export')), [])
        analysis['import_dialogs'], serial = probe_submenu(session, work, import_submenu, 'Import', serial)
        analysis['export_dialogs_before_slice'], serial = probe_submenu(session, work, export_submenu, 'Export', serial)
        analysis['zip_dialog'] = zip_dialog_census(session, work, analysis)
        if not click_slice_start(session):
            raise ValueError('slice click did not take')
        done, score = wait_slicing_done(session, timeout_s=150)
        analysis['slice_done'] = {'done': done, 'score': score}
        print('[census] slicing done', done, score, flush=True)
        after = census(session)
        analysis['menus_after_slice'] = after
        print('[census] after', json.dumps(after, ensure_ascii=False), flush=True)
        export_after = next((v for k, v in after['submenus'].items() if k.lower().startswith('export')), [])
        analysis['export_dialogs_after_slice'], _serial = probe_submenu(session, work, export_after, 'Export', serial)
        analysis['print_buttons'] = [text for text, _rect, _hwnd in export_util.topbar_buttons(session.hwnd)]
    finally:
        session.close()


def main():
    parser = add_common_args(argparse.ArgumentParser(), default_model=HERE / 'fixtures/feishu_std_cube.3mf')
    parser.add_argument('--row', default='census')
    args = parser.parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / args.row
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'[census] retained work directory: {work}', flush=True)
    analysis = {'case': 'file menu census', 'results': {}}
    started = time.monotonic()
    try:
        run(args, work, analysis)
        analysis['results']['census completed with the editor alive'] = 'PASS'
    except Exception as exc:
        analysis['results']['census'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    analysis['wall_seconds'] = round(time.monotonic() - started, 3)
    (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
