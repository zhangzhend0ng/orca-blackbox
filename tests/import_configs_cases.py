"""GUI helpers for Feishu #232 config import."""
import time

import m7_common as m7
from harness import export_util, winutil
from repair_model_cases import IMAGE_ERRORS, dialog_texts
from zip_import_cases import _comboboxes, shoot, wait_closed

EXPORT_ROW = 'Export Preset Bundle'
BUNDLE_TYPE = 'Printer config bundle'  # the printer and the filament and process presets that belong to it
IMPORT_ROW = 'Import Configs'
YES = ('Yes to all', '&Yes to all', 'Yes', '&Yes', 'OK', 'Confirm', 'Overwrite', 'Replace')


def click_text(hwnd, start):
    """Click the first visible child whose text starts with `start`, the dialog as the root window."""
    rows = [(text, rect, child) for text, rect, child in export_util._children_texts(hwnd)
            if winutil.user32.IsWindowVisible(child)]
    hits = [rect for text, rect, _child in rows if text.strip().casefold().startswith(start.casefold())]
    if not hits:
        raise ValueError(f'no {start!r} in {[text for text, _rect, _child in rows]}')
    left, top, right, bottom = hits[0]
    winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)


def keep_dialog(session, work, analysis, name, timeout_s=15):
    """Wait for any native dialog; keep its image and texts. Returns its hwnd, or None."""
    found = m7.wait_dialog(session.pid, timeout_s=timeout_s)
    if not found:
        return None
    _cls, title, _rect, hwnd = found
    record = {'title': title, 'texts': dialog_texts(hwnd), 'screenshot': f'{name}.png'}
    analysis.setdefault('dialogs', []).append(record)
    try:
        shoot(hwnd, work / record['screenshot'])
    except IMAGE_ERRORS as exc:
        record['image'] = f'unavailable ({exc})'
    print(f'[m7x232] dialog {record!r}', flush=True)
    return hwnd


def close_dialog(hwnd, timeout_s=5):
    # WM_CLOSE closes the product's own dialogs; IDCANCEL does not (measured, menu census).
    winutil._send_msg(hwnd, 0x0010, 0, 0)
    deadline = time.monotonic() + timeout_s
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    return not winutil.user32.IsWindowVisible(hwnd)


def export_bundle(session, path, work, analysis):
    """File > Export > Export Preset Bundle... > Printer config bundle, saved to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dispatched, found = m7.file_menu_dispatch(session, EXPORT_ROW, expect_dialog=True, via='Export')
    if not dispatched or not found:
        raise ValueError(f'{EXPORT_ROW} did not open its dialog')
    hwnd = found[3]
    analysis['export_dialog'] = {'title': found[1], 'texts': dialog_texts(hwnd)}
    shoot(hwnd, work / 'export-dialog.png')
    click_text(hwnd, BUNDLE_TYPE)
    time.sleep(0.5)
    click_text(hwnd, 'OK')
    if not wait_closed(hwnd, 10):
        raise ValueError('Export Preset Bundle dialog did not close after OK')
    saved = keep_dialog(session, work, analysis, 'save-dialog')
    if not saved:
        raise ValueError('no save dialog followed the bundle type')
    analysis['save_dialog_title'] = analysis['dialogs'][-1]['title']
    edit = export_util.find_edit(saved)
    if not edit or winutil._window_pid(edit) != session.pid:
        raise ValueError('save dialog has no owned filename control')
    winutil.select_all(edit)
    winutil.msg_text(edit, str(path))
    analysis['save_entered'] = winutil.edit_text(edit, size=512)
    if analysis['save_entered'] != str(path):
        raise ValueError(f'wrong save filename: {analysis["save_entered"]}')
    winutil._send_msg(saved, m7.WM_COMMAND_MSG, 1, 0)
    wait_closed(saved)
    if not export_util.wait_file(path, timeout_s=30):
        extra = keep_dialog(session, work, analysis, 'after-save')
        if extra:
            close_dialog(extra)
        raise ValueError(f'{path.name} was not written')
    for name in ('export-result',):
        extra = keep_dialog(session, work, analysis, name, timeout_s=3)
        if extra:
            close_dialog(extra)


def choose_configs(session, path, work, analysis):
    """File > Import > Import Configs..., type the config path, confirm. Returns the chooser hwnd."""
    dispatched, found = m7.file_menu_dispatch(session, IMPORT_ROW, expect_dialog=True, via='Import')
    if not dispatched or not found:
        raise ValueError(f'{IMPORT_ROW} did not open a file chooser')
    title, hwnd = found[1], found[3]
    edit = export_util.find_edit(hwnd)
    if not edit or winutil._window_pid(edit) != session.pid:
        raise ValueError(f'file chooser has no owned filename control: {title}')
    winutil.select_all(edit)
    winutil.msg_text(edit, str(path))
    entered = winutil.edit_text(edit, size=512)
    filters = _comboboxes(hwnd)
    shoot(hwnd, work / 'chooser.png')
    analysis['chooser'] = {'title': title, 'entered': entered, 'filters': filters,
                           'ini_in_filter': any('.ini' in item.casefold() for box in filters for item in box['items'])}
    print(f'[m7x232] chooser {analysis["chooser"]}', flush=True)
    if 'profile' not in title.lower() or not filters[-1]['items']:
        raise ValueError(f'unexpected config chooser: {title!r} {filters}')
    if entered != str(path):
        raise ValueError(f'wrong chooser filename: {entered}')
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
    return hwnd


def collect_import_dialogs(session, work, analysis, limit=4):
    """Keep every dialog the import brings up until the Import result box. A name-clash
    prompt is answered with its first affirmative button when there is one."""
    for index in range(limit):
        hwnd = keep_dialog(session, work, analysis, f'prompt-{index + 1}', timeout_s=20)
        if not hwnd:
            return
        record = analysis['dialogs'][-1]
        buttons = {text.strip() for text, _rect, child in export_util._children_texts(hwnd)
                   if winutil.window_class(child) == 'Button'}
        record['buttons'] = sorted(buttons)
        if 'Import result' in record['title']:
            close_dialog(hwnd)
            return
        answer = next((text for text in YES if text in buttons), None)
        record['answer'] = answer
        if answer:
            click_text(hwnd, answer)
            if wait_closed(hwnd, 5):
                continue
        close_dialog(hwnd)
