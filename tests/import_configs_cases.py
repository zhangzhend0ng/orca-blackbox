"""GUI helpers for Feishu #232 config import.

The Export Preset Bundle dialog is no longer driven by this case: on the guest the
product reported "add file fail" for its own export (runs c378dee0 and 8d20f5b),
and the config file is a precondition of the Feishu case, not a step of it."""
import time

import cv2

import m7_common as m7
from harness import export_util, winutil
from repair_model_cases import IMAGE_ERRORS, dialog_texts
from zip_import_cases import _comboboxes, shoot, wait_closed

IMPORT_ROW = 'Import Configs'
YES = ('Yes to all', '&Yes to all', 'Yes', '&Yes', 'OK', 'Confirm', 'Overwrite', 'Replace')


def keep(session, work, analysis, found, name):
    """Record a dialog (title, texts, image and, when its message is drawn, its OCR text)
    under analysis['dialogs']; returns its hwnd."""
    _cls, title, _rect, hwnd = found
    record = {'title': title, 'texts': dialog_texts(hwnd), 'screenshot': f'{name}.png'}
    analysis.setdefault('dialogs', []).append(record)
    try:
        frame = shoot(hwnd, work / record['screenshot'])
        if 'htmlWindow' in record['texts']:  # the message itself is drawn, it is not window text
            record['message'] = ' '.join(word[0] for word in m7.mdu.ocr_words_img(
                cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR), scale=3, psm=6))
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


def click_text(hwnd, start):
    """Click the first visible child whose text starts with `start`, the dialog as the root window."""
    rows = [(text, rect, child) for text, rect, child in export_util._children_texts(hwnd)
            if winutil.user32.IsWindowVisible(child)]
    hits = [rect for text, rect, _child in rows if text.strip().casefold().startswith(start.casefold())]
    if not hits:
        raise ValueError(f'no {start!r} in {[text for text, _rect, _child in rows]}')
    left, top, right, bottom = hits[0]
    winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)


def answer_box(hwnd, timeout_s=5):
    """Close an Info box with its own Yes button, else OK; fall back to IDOK, then WM_CLOSE."""
    for label in ('Yes', 'OK'):
        try:
            click_text(hwnd, label)
            break
        except ValueError:
            continue
    if not wait_closed(hwnd, timeout_s):
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
        if not wait_closed(hwnd, 4):
            close_dialog(hwnd)


def choose_configs(session, path, work, analysis):
    """File > Import > Import Configs..., type the config path into the chooser and confirm.
    Records the chooser (title, read-back path, type filter) under analysis['choosers']."""
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
    serial = len(analysis.setdefault('choosers', [])) + 1
    shoot(hwnd, work / f'chooser-{serial}.png')
    analysis['choosers'].append({'title': title, 'entered': entered, 'file': path.name, 'filters': filters,
                                 'ini_in_filter': any('.ini' in item.casefold() for box in filters for item in box['items'])})
    print(f'[m7x232] chooser {analysis["choosers"][-1]!r}', flush=True)
    # The chooser carries an extra, empty combo box the second time it opens (guest run
    # dev232d-67abded0), so the filter is looked for in any box, not in the last one.
    offered = [item.casefold() for box in filters for item in box['items']]
    if 'profile' not in title.lower() or not any('*.zip' in item for item in offered):
        raise ValueError(f'unexpected config chooser: {title!r} {filters}')
    if entered != str(path):
        raise ValueError(f'wrong chooser filename: {entered}')
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
    return hwnd


def import_once(session, path, work, analysis, tag, limit=8):
    """One pass of File > Import > Import Configs... with `path`.

    Returns what the product showed: whether the chooser let the path through, and
    every dialog up to the Import result box. A name-clash prompt is answered with
    its first affirmative button when there is one."""
    dialogs = analysis.setdefault('dialogs', [])
    first = len(dialogs)
    outcome = {'file': path.name}
    chooser = choose_configs(session, path, work, analysis)
    outcome['chooser_closed'] = wait_closed(chooser, 10)
    if not outcome['chooser_closed']:
        outcome['chooser_still_open'] = [text for text, _rect, child in export_util._children_texts(chooser)
                                         if winutil.user32.IsWindowVisible(child) and text][:20]
        close_dialog(chooser)
    for index in range(limit):
        found = m7.wait_dialog(session.pid, timeout_s=15 if index == 0 else 8)
        if not found:
            break
        hwnd = keep(session, work, analysis, found, f'{tag}-dialog-{index + 1}')
        record = dialogs[-1]
        record['buttons'] = sorted({text.strip() for text, _rect, child in export_util._children_texts(hwnd)
                                    if winutil.user32.IsWindowVisible(child) and text.strip()
                                    and winutil.window_class(child) in ('Button', 'wxWindowNR')
                                    and len(text.strip()) <= 24})
        if 'Import result' in record['title']:
            answer_box(hwnd)
            break
        answer = next((text for text in YES if text in record['buttons']), None)
        record['answer'] = answer
        if answer:
            click_text(hwnd, answer)
            if wait_closed(hwnd, 5):
                continue
        close_dialog(hwnd)
    outcome['dialogs'] = dialogs[first:]
    return outcome
