"""GUI helpers for Feishu #232 config import.

Export Preset Bundle dialog at sm-v2.4.0 (CreatePresetsDialog.cpp): each type is a
native radio Button plus a Static label, and both take a left click (3530-3551);
the printers or presets to export are textless checkbox Buttons whose label does
not take the click (306-315); OK refuses an empty selection with an Info box
(4018-4024), then asks for a directory (4026-4028), writes the file there and
reports "Export successful", or a failure such as "add file fail", in a
`Snapmaker Orca - Info` box whose only button is Yes (3373-3402)."""
from pathlib import Path
import sys
import time

import cv2

import m7_common as m7
from harness import export_util, winutil
from harness import mix_dialog_util as mdu
from harness import process_panel as pp
from repair_model_cases import IMAGE_ERRORS, dialog_texts
from zip_import_cases import _comboboxes, describe, shoot, wait_closed
from import_configs_oracle import profile_presets
from import_configs_oracle import TYPES, checkbox_rows

sys.path.insert(0, str(Path(__file__).resolve().parent / 'engine'))
import m5g_preset_manage as m5g  # noqa: E402 - the proven Save preset path (PITFALLS 17.8)

EXPORT_ROW = 'Export Preset Bundle'
EXPORT_TITLE = 'Export Preset Bundle'
BUNDLE_TYPE = TYPES[0]        # the printer with the filament and process presets that belong to it
ZIP_TYPES = TYPES[2:]         # the fallback: one zip per preset kind
IMPORT_ROW = 'Import Configs'
INFO_TITLE = 'Snapmaker Orca - Info'
SUCCESS = 'Export successful'
PRINTER_NAME = 'U1 BB-TEST'
YES = ('Yes to all', '&Yes to all', 'Yes', '&Yes', 'OK', 'Confirm', 'Overwrite', 'Replace')
KEEP = ('.zip', '.orca_printer', '.orca_filament')
LOG_WORDS = ('xport', 'initial_file', 'archive', 'ZIP', 'zip', 'ailed', 'preset file')


def click_text(hwnd, start):
    """Click the first visible child whose text starts with `start`, the dialog as the root window."""
    rows = [(text, rect, child) for text, rect, child in export_util._children_texts(hwnd)
            if winutil.user32.IsWindowVisible(child)]
    hits = [rect for text, rect, _child in rows if text.strip().casefold().startswith(start.casefold())]
    if not hits:
        raise ValueError(f'no {start!r} in {[text for text, _rect, _child in rows]}')
    left, top, right, bottom = hits[0]
    winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)


def new_dialog(session, exclude, timeout_s=20):
    """The next native dialog of the app whose title does not contain `exclude`, or None."""
    return export_util.wait_toplevel(
        session.pid, lambda cls, text, _rect: cls == '#32770' and exclude.casefold() not in (text or '').casefold(),
        timeout_s)


def keep(session, work, analysis, found, name):
    """Record a dialog (title, texts, image and, when its message is drawn, its OCR text)
    under analysis['dialogs']; returns its hwnd."""
    _cls, title, _rect, hwnd = found
    record = {'title': title, 'texts': dialog_texts(hwnd), 'screenshot': f'{name}.png'}
    analysis.setdefault('dialogs', []).append(record)
    try:
        frame = shoot(hwnd, work / record['screenshot'])
        if 'htmlWindow' in record['texts']:  # the message itself is drawn, it is not window text
            image = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            record['message'] = ' '.join(word[0] for word in m7.mdu.ocr_words_img(image, scale=3, psm=6))
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


def _address(hwnd):
    return [text for text, _rect, _child in export_util._children_texts(hwnd) if text.startswith('Address')]


def choose_folder(session, hwnd, folder, work, analysis, entry, serial):
    """Select `folder` in the native folder picker and record what the box held: type the
    path, confirm; when the box only navigated, read it again and press Select Folder."""
    edit = export_util.find_edit(hwnd)
    entry['folder_owned_edit'] = bool(edit) and winutil._window_pid(edit) == session.pid
    if entry['folder_owned_edit']:
        winutil.select_all(edit)
        winutil.msg_text(edit, str(folder))
        entry['folder_typed'] = winutil.edit_text(edit, size=512)
    entry['folder_address_before'] = _address(hwnd)
    shoot(hwnd, work / f'folder-dialog-{serial}.png')
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
    if wait_closed(hwnd, 4):
        entry['folder_box'] = 'closed by the first OK after the path was typed'
        return
    entry['folder_edit_after_ok'] = winutil.edit_text(edit, size=512) if edit else None
    entry['folder_address_after_ok'] = _address(hwnd)
    shoot(hwnd, work / f'folder-dialog-{serial}-after.png')
    try:
        click_text(hwnd, 'Select Folder')
        entry['folder_box'] = 'Select Folder pressed after the first OK only navigated'
    except ValueError:
        entry['folder_box'] = 'no Select Folder button; WM_CLOSE'
        close_dialog(hwnd)
        return
    if not wait_closed(hwnd, 8):
        close_dialog(hwnd)


def wait_new_files(folder, before, timeout_s=90):
    """Files with a bundle or zip suffix that appeared in `folder` and were not there before."""
    deadline = time.monotonic() + timeout_s
    while True:
        fresh = sorted(path for path in folder.iterdir()
                       if path.is_file() and path.name not in before and path.suffix in KEEP)
        if fresh or time.monotonic() >= deadline:
            return fresh
        time.sleep(0.3)


def export_bundle(session, kind, folder, work, analysis):
    """One pass of File > Export > Export Preset Bundle...: choose `kind`, tick the first
    row it lists, choose `folder`, answer the result box.

    Returns (files, message): no files and no message when the profile lists nothing
    for this type; no files and the product's words when the export was refused."""
    folder.mkdir(parents=True, exist_ok=True)
    before = {path.name for path in folder.iterdir()}
    serial = len(analysis.setdefault('exports', [])) + 1
    dispatched, found = m7.file_menu_dispatch(session, EXPORT_ROW, expect_dialog=True, via='Export')
    if not dispatched or not found:
        raise ValueError(f'{EXPORT_ROW} did not open its dialog')
    hwnd = found[3]
    entry = {'kind': kind, 'title': found[1], 'controls': describe(hwnd)}
    analysis['exports'].append(entry)
    shoot(hwnd, work / f'export-dialog-{serial}.png')
    click_text(hwnd, kind)  # the label and the radio both take a left click
    time.sleep(1.0)
    controls = describe(hwnd)
    entry['controls_after_type'] = controls
    rows = checkbox_rows(controls)
    entry['type_rows'] = [row['label'] for row in rows['types']]
    entry['rows'] = [row['label'] for row in rows['items']]
    shoot(hwnd, work / f'export-type-{serial}.png')
    print(f'[m7x232] {kind}: rows {entry["rows"]!r}', flush=True)
    if not rows['items']:
        entry['note'] = 'nothing is listed for this type in this profile'
        close_dialog(hwnd)
        return [], None
    left, top, right, bottom = rows['items'][0]['checkbox']
    winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)
    time.sleep(0.5)
    click_text(hwnd, 'OK')
    next_dialog = new_dialog(session, EXPORT_TITLE)
    if not next_dialog:
        if wait_closed(hwnd, 3):
            raise ValueError('Export Preset Bundle closed after OK without a directory box')
        raise ValueError('nothing followed OK in the Export Preset Bundle dialog')
    box = keep(session, work, analysis, next_dialog, f'after-ok-{serial}')
    if INFO_TITLE.casefold() in next_dialog[1].casefold():
        answer_box(box)
        close_dialog(hwnd)
        raise ValueError(f'OK was refused: {analysis["dialogs"][-1].get("message") or analysis["dialogs"][-1]["texts"]}')
    entry['directory_box'] = next_dialog[1]
    choose_folder(session, box, folder, work, analysis, entry, serial)
    entry['files'] = [path.name for path in wait_new_files(folder, before)]
    result = new_dialog(session, EXPORT_TITLE, timeout_s=15)
    message = None
    if result:
        answer_box(keep(session, work, analysis, result, f'export-result-{serial}'))
        message = analysis['dialogs'][-1].get('message')
    if not wait_closed(hwnd, 10):
        close_dialog(hwnd)
    entry['result'] = message
    if message is None or SUCCESS.casefold() not in message.casefold():
        return [], message
    if not entry['files']:
        raise ValueError(f'{kind}: {message} but no file was written into {folder.name}')
    return [folder / name for name in entry['files']], message


def printer_row_buttons(session):
    """Small textless Buttons on the preset row under the 'Printer' title of the sidebar."""
    anchor = next((ly for _text, cls, rect, child, lx, ly in pp.kids(session)
                   if cls == 'Static' and _text.strip() == 'Printer' and winutil.user32.IsWindowVisible(child)
                   and lx < 100), None)
    if anchor is None:
        return []
    out = []
    for text, cls, rect, child, lx, ly in pp.kids(session):
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        if (cls == 'Button' and not text.strip() and winutil.user32.IsWindowVisible(child)
                and 10 <= width <= 40 and 8 <= height <= 32 and anchor + 8 <= ly <= anchor + 70 and lx > 250):
            out.append((rect, child))
    return sorted(out, key=lambda row: row[0][0])


def save_user_printer(session, name, work, analysis):
    """Save the current printer as a user preset named `name` (PITFALLS 17.8): the
    floppy on the Printer preset row, then the `Save preset` box: name, User Preset, OK."""
    record = analysis.setdefault('saved_printer', {'name': name})
    buttons = printer_row_buttons(session)
    record['buttons'] = [rect for rect, _child in buttons]
    target = None
    for rect, _child in buttons:
        tip = m5g.hover_tooltip(session, rect)
        record.setdefault('tooltips', []).append(tip)
        if 'save' in tip.casefold():
            target = rect
            break
    if target is None:
        if not buttons:
            raise ValueError('no buttons on the Printer preset row of the sidebar')
        target = buttons[0][0]
        record['note'] = 'the save tooltip was not read; the leftmost button was clicked'
    known = pp.top_dialog_set(session)
    m5g.real_click(target)
    dialog, title = m5g.wait_new_dialog(session, known)
    record['dialog'] = title
    if not dialog:
        raise ValueError('the Save preset dialog did not open')
    _rect, edit = m5g.dialog_edit(dialog)
    if not edit:
        close_dialog(dialog)
        raise ValueError('the Save preset dialog has no name field')
    focused = False
    for _attempt in range(4):
        winutil.force_set_foreground(session.hwnd)
        time.sleep(0.3)
        m5g.real_click(_rect)
        time.sleep(0.4)
        if pp.focus_hwnd(edit) == edit:
            focused = True
            break
    if not focused:
        close_dialog(dialog)
        raise ValueError('the preset name field did not take focus')
    mdu._send_keys([(0x11, False), (0x41, False), (0x41, True), (0x11, True)])  # Ctrl+A
    time.sleep(0.15)
    mdu._send_keys([(0x2E, False), (0x2E, True)])                                # Delete
    time.sleep(0.2)
    mdu._send_chars(name)                                                         # live text, no Enter
    record['entered'] = winutil.edit_text(edit, size=256)
    shoot(dialog, work / 'save-preset.png')
    radio, _child = m5g.dialog_child_exact(dialog, 'User Preset')
    if radio:
        m5g.real_click(radio)
    rect_ok, _child = m5g.dialog_child_exact(dialog, 'OK')
    if not rect_ok:
        close_dialog(dialog)
        raise ValueError('the Save preset dialog has no OK')
    m5g.real_click(rect_ok)
    time.sleep(2.0)
    return record


def wait_preset(datadir, kind, name, timeout_s=15):
    deadline = time.monotonic() + timeout_s
    while True:
        if any(row['kind'] == kind and row['name'] == name for row in profile_presets(datadir)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def keep_app_log(datadir, work):
    """Copy the application's own export-related log lines into the work directory."""
    lines = []
    folder = Path(datadir) / 'log'
    for path in sorted(folder.glob('*')) if folder.is_dir() else []:
        if not path.is_file():
            continue
        try:
            rows = path.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            continue
        lines += [f'{path.name}: {row}' for row in rows if any(word in row for word in LOG_WORDS)][-300:]
    (work / 'app-log.log').write_text('\n'.join(lines), encoding='utf-8')
    return len(lines)


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
    serial = len(analysis.setdefault('choosers', [])) + 1
    shoot(hwnd, work / f'chooser-{serial}.png')
    analysis['choosers'].append({'title': title, 'entered': entered, 'file': path.name, 'filters': filters,
                                 'ini_in_filter': any('.ini' in item.casefold() for box in filters for item in box['items'])})
    print(f'[m7x232] chooser {analysis["choosers"][-1]!r}', flush=True)
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
        found = m7.wait_dialog(session.pid, timeout_s=20)
        if not found:
            return
        hwnd = keep(session, work, analysis, found, f'import-dialog-{index + 1}')
        record = analysis['dialogs'][-1]
        record['buttons'] = sorted({text.strip() for text, _rect, child in export_util._children_texts(hwnd)
                                    if winutil.user32.IsWindowVisible(child) and text.strip()
                                    and winutil.window_class(child) in ('Button', 'wxWindowNR')
                                    and len(text.strip()) <= 24})
        if 'Import result' in record['title']:
            answer_box(hwnd)
            return
        answer = next((text for text in YES if text in record['buttons']), None)
        record['answer'] = answer
        if answer:
            click_text(hwnd, answer)
            if wait_closed(hwnd, 5):
                continue
        close_dialog(hwnd)
