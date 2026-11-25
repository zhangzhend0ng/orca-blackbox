"""GUI helpers for Feishu #232 config import.

Export Preset Bundle dialog at sm-v2.4.0 (CreatePresetsDialog.cpp): each type is a
native radio Button plus a Static label, and both take a left click (3530-3551);
the printers or presets to export are textless checkbox Buttons whose label does
not take the click (306-315); OK refuses an empty selection with an Info box
(4018-4024), then asks for a directory (4026-4028), writes the file there and
reports "Export successful" in a `Snapmaker Orca - Info` box (3392-3393)."""
import time

import m7_common as m7
from harness import export_util, winutil
from repair_model_cases import IMAGE_ERRORS, dialog_texts
from zip_import_cases import _comboboxes, describe, shoot, wait_closed
from import_configs_oracle import TYPES, checkbox_rows

EXPORT_ROW = 'Export Preset Bundle'
EXPORT_TITLE = 'Export Preset Bundle'
BUNDLE_TYPE = TYPES[0]        # the printer with the filament and process presets that belong to it
ZIP_TYPES = TYPES[2:]         # the fallback: one zip per preset kind
IMPORT_ROW = 'Import Configs'
INFO_TITLE = 'Snapmaker Orca - Info'
YES = ('Yes to all', '&Yes to all', 'Yes', '&Yes', 'OK', 'Confirm', 'Overwrite', 'Replace')
KEEP = ('.zip', '.orca_printer', '.orca_filament')


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
    """Record a dialog (title, texts, image) under analysis['dialogs']; returns its hwnd."""
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


def answer_box(hwnd, timeout_s=5):
    """Close an Info box with its own OK button; fall back to IDOK, then WM_CLOSE."""
    for label in ('OK', 'Yes'):
        try:
            click_text(hwnd, label)
            break
        except ValueError:
            continue
    if not wait_closed(hwnd, timeout_s):
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
        if not wait_closed(hwnd, 4):
            close_dialog(hwnd)


def choose_folder(session, hwnd, folder, analysis):
    """Select `folder` in the native folder picker: type its path and confirm; when the
    box only navigated into the folder, press its select button."""
    edit = export_util.find_edit(hwnd)
    analysis['folder_entered'] = None
    if edit and winutil._window_pid(edit) == session.pid:
        winutil.select_all(edit)
        winutil.msg_text(edit, str(folder))
        analysis['folder_entered'] = winutil.edit_text(edit, size=512)
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
    if wait_closed(hwnd, 4):
        return
    for label in ('Select Folder', 'OK'):
        try:
            click_text(hwnd, label)
            break
        except ValueError:
            continue
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
    row it lists, choose `folder`, answer the result box. Returns the files written there;
    none when the profile lists nothing for this type."""
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
        return []
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
        raise ValueError(f'OK was refused: {analysis["dialogs"][-1]["texts"]}')
    entry['directory_box'] = next_dialog[1]
    choose_folder(session, box, folder, analysis)
    entry['files'] = [path.name for path in wait_new_files(folder, before)]
    result = new_dialog(session, EXPORT_TITLE, timeout_s=15)
    if result:
        keep(session, work, analysis, result, f'export-result-{serial}')
        answer_box(result)
    if not wait_closed(hwnd, 10):
        close_dialog(hwnd)
    if not entry['files']:
        raise ValueError(f'{kind}: no file was written into {folder.name}')
    return [folder / name for name in entry['files']]


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
