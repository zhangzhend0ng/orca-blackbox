#!/usr/bin/env python3
"""GUI helpers shared by the File > Export cases (Feishu #236, #233, #234).

Everything here drives the application from outside: menus are read through
their HMENU, dialogs through their child windows, and the result is whatever
file lands in the run directory. Nothing in this module judges the product.

Measured on the guest (Snapmaker Orca 2.4.0, en_US), see the coordinator's
probes diag_file_menu_census and diag_slice_export_probe:

* File > Export is a submenu. Its rows are ``Export all objects as one
  STL...``, ``Export all objects as STLs...``, ``Export Generic 3MF...``,
  ``Export plate sliced file...`` (Ctrl+G), ``Export all plate sliced
  file...``, ``Export G-code...`` and ``Export Preset Bundle...``. The three
  slice rows stay disabled until the plate has a slice result; the slice
  button's done badge is NOT that signal, because the runtime memory guard can
  hold the rows disabled while the badge already shows.
* The file dialog's type filter is the selected entry of a ComboBox, not a
  window text.
* A directory path typed into the file name box plus IDOK navigates the dialog
  and keeps it open; a name typed afterwards plus IDOK saves, and the
  application appends the extension. A full path typed at once saves too
  (m7x_250), but then the extension is the caller's, not the product's.
* ``Memory Usage Warning`` (RichMessageDialog, #32770) pops when the guest
  runs low on memory during slicing. Its default button is ``No, Stop``; the
  only accepted answer is a click on the child whose text is exactly
  ``Yes, Continue``. A message click without a root window does not close it;
  the same click resolved inside the dialog's own window tree does
  (runs hogprobe-f5572f61 against hogprobe2-e3ce6f8b). Never send Enter or a
  default-button command here.
"""
import ctypes
from ctypes import wintypes
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import struct
import time
from zipfile import ZipFile

import cv2
import numpy as np

import m7_common as m7
from harness import export_util, mixing_util, topbar_util, winutil
from m2_slice_chain import click_slice_start

LOG = '[export]'
GUARD_TITLE = 'Memory Usage Warning'
GUARD_CONTINUE = 'Yes, Continue'
GUARD_CLICK_TIERS = ('message click', 'message click inside dialog', 'real click')
IDOK, IDCANCEL = 1, 2


def descendants(hwnd):
    """[(class name, window text, hwnd)] of every child of a dialog, top to bottom."""
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
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    items = []
    for index in range(user32.SendMessageW(combobox, 0x0146, 0, 0)):
        length = user32.SendMessageW(combobox, 0x0149, index, 0)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.SendMessageW(combobox, 0x0148, index, ctypes.addressof(buffer))
        items.append(buffer.value)
    return {'selected': user32.SendMessageW(combobox, 0x0147, 0, 0), 'items': items}


def row_label(text):
    """A menu label without its accelerator and trailing dots."""
    return text.partition('\t')[0].rstrip('. …').strip()


def _rows(hmenu):
    return [{'index': index, 'label': text, 'enabled': bool(hmenu) and not flags & 3, 'submenu': bool(flags & 0x10)}
            for index, text, flags in topbar_util.menu_items(hmenu)]


def read_export_menu(session):
    """Every row of the live File menu and of its Export submenu, with the enabled state; the menus are closed."""
    menu = topbar_util.open_file_menu(session)
    if not menu:
        raise ValueError('topbar File menu did not open')
    _rect, _hwnd, hmenu = menu
    file_rows = _rows(hmenu)
    index = topbar_util.find_item(hmenu, 'Export')
    submenu = topbar_util.item_info(hmenu, index)[1] if index is not None else None
    export_rows = _rows(submenu)
    topbar_util.close_menu_windows(session.pid)
    print(f'{LOG} file menu: {[row["label"] for row in file_rows]}', flush=True)
    print(f'{LOG} Export menu: {[(row["index"], row["label"], row["enabled"]) for row in export_rows]}', flush=True)
    return {'file': file_rows, 'export': export_rows}


def dismiss_menus(session):
    """Close the application's open popup menus, also one whose submenu was expanded.

    A menu whose submenu opened for the real cursor ignores WM_CANCELMODE (PITFALLS 17.10). It
    closes for real Escape keys, and those go to the foreground window: they are only sent while
    the application under test is that window. Returns True once no menu is left."""
    for _attempt in range(3):
        if not topbar_util._enum_menu_windows(session.pid):
            break
        if winutil._window_pid(winutil.user32.GetForegroundWindow()) == session.pid:
            m7.mdu._send_keys([(0x1B, False), (0x1B, True)])  # VK_ESCAPE
        time.sleep(0.5)
    topbar_util.close_menu_windows(session.pid)
    deadline = time.monotonic() + 5
    while topbar_util._enum_menu_windows(session.pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    return not topbar_util._enum_menu_windows(session.pid)


def _row_ink(frame, menu_hwnd, hmenu, index):
    """Luminance of the brightest pixels of one menu row in a desktop frame (its text), or None
    when the row has no rectangle on the screen. A reading for the picture, not a check."""
    rect = wintypes.RECT()
    try:
        if not winutil.user32.GetMenuItemRect(menu_hwnd, hmenu, index, ctypes.byref(rect)):
            return None
        region = frame[max(rect.top, 0):max(rect.bottom, 0), max(rect.left, 0):max(rect.right, 0), :3]
        if region.size == 0:
            return None
        return int(np.percentile(region.max(axis=2), 99))
    except (OSError, ValueError, cv2.error):
        return None


def _menu_row_rect(menu_hwnd, hmenu, index):
    """Screen rectangle of one row of an open popup menu, or None. The popup's own window has to
    be passed: with a NULL window the call fails on the guest (PITFALLS 20)."""
    rect = wintypes.RECT()
    if winutil.user32.GetMenuItemRect(menu_hwnd, hmenu, index, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def _wait_submenu(pid, known, expected, timeout_s):
    """(rect, hwnd, hmenu) of the popup menu whose HMENU is `expected`, among the menus of `pid`
    that are not in `known`; other new menus are noted in `known` and passed over."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for left, top, right, bottom, hwnd in topbar_util._enum_menu_windows(pid):
            if hwnd in known:
                continue
            if topbar_util.menu_hmenu(hwnd) == expected:
                return (left, top, right, bottom), hwnd, expected
            known.add(hwnd)
        time.sleep(0.2)
    return None


def expand_submenu(session, menu_hwnd, hmenu, rect, count, index, record=None):
    """Open the submenu of a native menu row; returns (rect, hwnd, hmenu) of the submenu or None.

    A native menu follows the real pointer: the cursor is parked on the row and jogged so that
    the menu sees it arrive. The row's own rectangle is tried first, then the places an even row
    pitch puts it at and a few pixels around them (separators are lower than rows), then the
    Right arrow key, which opens the submenu of the highlighted row and is sent only while the
    application under test has the keyboard. The submenu is accepted only when its HMENU is the
    one the row leads to, so Import is never taken for Export. What was tried goes to `record`."""
    record = [] if record is None else record
    expected = topbar_util.item_info(hmenu, index)[1]
    left, top, right, bottom = rect
    even = top + 2 + int((index + 0.5) * (bottom - top - 4) / max(count, 1))
    tried = []
    row = _menu_row_rect(menu_hwnd, hmenu, index)
    if row:
        tried.append(('row rectangle', (row[0] + row[2]) // 2, (row[1] + row[3]) // 2))
    for step in (0, 6, -6, 12, -12, 18, -18):
        if top < even + step < bottom and all(abs(even + step - y) > 2 for _how, _x, y in tried):
            tried.append(('even pitch' if not step else f'even pitch {step:+d}', (left + right) // 2, even + step))
    known = {menu_hwnd}
    for how, x, y in tried:
        winutil.user32.SetCursorPos(x, y - 4)
        time.sleep(0.08)
        winutil.user32.SetCursorPos(x, y)
        entry = {'how': how, 'point': [x, y]}
        record.append(entry)
        sub = _wait_submenu(session.pid, known, expected, timeout_s=2.5)
        if sub:
            entry['opened'] = True
            return sub
    entry = {'how': 'Right arrow key'}
    record.append(entry)
    if winutil._window_pid(winutil.user32.GetForegroundWindow()) == session.pid:
        m7.mdu._send_keys([(0x27, False), (0x27, True)])
        sub = _wait_submenu(session.pid, known, expected, timeout_s=3.0)
        if sub:
            entry['opened'] = True
            return sub
    else:
        entry['skipped'] = 'another window has the keyboard'
    return None


def _pointer_state(session):
    """Where the real cursor is and whether the application under test has the keyboard."""
    point = wintypes.POINT()
    winutil.user32.GetCursorPos(ctypes.byref(point))
    foreground = winutil.user32.GetForegroundWindow()
    return {'cursor': [point.x, point.y],
            'foreground_is_orca': winutil._window_pid(foreground) == session.pid}


def export_menu_reading(session, work, image, margin=12):
    """Read File > Export, then try to keep a picture of the two menus open on screen.

    The rows are read from the menus' handles while the File menu is open. That needs no
    pointer and is what a case judges by. The picture is tried afterwards and never decides
    anything: the window is brought to the foreground (so the real keys that close the menus
    again reach it), the real cursor is parked on the Export row, and the picture is cut from
    the desktop around both menus once the submenu shows. When it does not show, `menu_picture`
    says so together with where the cursor went, which menu windows were open and who had the
    keyboard. The menus are closed before returning; only a menu that refuses to close raises.
    #238's first guest run had the picture decide and said no more than that."""
    from m8x_48_modal_color_header import bring_main_to_mouse

    menu = topbar_util.open_file_menu(session)
    if not menu:
        raise ValueError('topbar File menu did not open')
    rect, hwnd, hmenu = menu
    file_rows = _rows(hmenu)
    index = topbar_util.find_item(hmenu, 'Export')
    sub_menu = topbar_util.item_info(hmenu, index)[1] if index is not None else None
    if not sub_menu:
        topbar_util.close_menu_windows(session.pid)
        raise ValueError('the File menu has no Export submenu')
    export_rows = _rows(sub_menu)
    picture = {'image': None, 'file_menu_px': list(rect)}
    try:
        foreground = bring_main_to_mouse(session.hwnd)
        picture['foreground'] = bool(foreground)
        if not foreground:
            picture['unavailable'] = 'Orca could not come to the foreground; the submenu was not opened for a picture'
        else:
            time.sleep(0.2)  # let the menu finish opening
            record = []
            sub = expand_submenu(session, hwnd, hmenu, rect, len(file_rows), index, record)
            if not sub:
                picture.update(unavailable='the Export submenu did not open on screen', tried=record,
                               pointer=_pointer_state(session),
                               menu_windows=[list(found[:4]) for found in topbar_util._enum_menu_windows(session.pid)])
            else:
                sub_rect, sub_hwnd, sub_menu = sub
                try:
                    time.sleep(0.5)  # let the submenu finish painting
                    width, height, pixels = winutil.screen_grab()
                    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
                    left = max(0, min(rect[0], sub_rect[0]) - margin)
                    top = max(0, min(rect[1], sub_rect[1]) - margin)
                    right = min(width, max(rect[2], sub_rect[2]) + margin)
                    bottom = min(height, max(rect[3], sub_rect[3]) + margin)
                    crop = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGRA2BGR)
                    if right <= left or bottom <= top or not cv2.imwrite(str(Path(work) / image), crop):
                        raise ValueError(f'could not keep a picture of the open menus as {image}')
                except (OSError, RuntimeError, ValueError, cv2.error) as exc:
                    picture['unavailable'] = f'the desktop picture failed ({exc})'
                else:
                    picture.update(image=image, screen_px=[width, height], opened_by=record,
                                   menus_px={'file': list(rect), 'export': list(sub_rect)})
                    for row in export_rows:
                        row['text_luminance'] = _row_ink(frame, sub_hwnd, sub_menu, row['index'])
    finally:
        closed = dismiss_menus(session)
    if not closed:
        raise ValueError(f'the File menu stayed open: '
                         f'{[list(found[:4]) for found in topbar_util._enum_menu_windows(session.pid)]!r}')
    print(f'{LOG} File > Export read: {[(row["index"], row["label"], row["enabled"]) for row in export_rows]}; '
          f'picture {picture.get("image") or "unavailable: " + picture.get("unavailable", "?")}', flush=True)
    return {'file': file_rows, 'export': export_rows, 'menu_picture': picture}


# --- the application's own dialogs: preset packages ----------------------------

# File > Export > Export Preset Bundle... opens the application's own #32770 dialog "Export
# Preset Bundle" (CreatePresetsDialog.cpp). Measured on the guest (census 0d7222e7 and the
# #232 dev runs a2aafd3d and c378dee):
# * A package type is a text-less native Button of 18 x 18 with its Static label 5 px to the
#   right; a click on the label chooses the type.
# * What can be exported is listed under the types: a text-less check box with its Static
#   label to the right on the same row, and only the box takes the click. The list depends on
#   the type and on the profile; a type with nothing to list shows no control at all.
# * OK with nothing ticked brings "Snapmaker Orca - Info" ("Please select at least one
#   printer or filament.") whose one button reads "Yes". OK with a box ticked opens "Choose a
#   directory" (a "Folder:" box and "Select Folder"); the package lands in that directory
#   under a name the application picks, and an Info box reports the outcome in an html window,
#   which has no window text: its words are in pixels only.
# * A failed export leaves the dialog open. WM_CLOSE is what closes it; IDCANCEL is not.
BUNDLE_ROW = 'Export Preset Bundle'
BUNDLE_DIALOG = 'Export Preset Bundle'
BUNDLE_KINDS = ('Printer config bundle(.orca_printer)', 'Filament bundle(.orca_filament)',
                'Printer presets(.zip)', 'Filament presets(.zip)', 'Process presets(.zip)')
BUNDLE_FILES = {'Printer presets(.zip)': 'Printer presets.zip', 'Filament presets(.zip)': 'Filament presets.zip',
                'Process presets(.zip)': 'Process presets.zip'}
BUNDLE_BUTTONS = ('wxWindowNR', 'Button')
DIRECTORY_DIALOG = 'Choose a directory'
IMPORT_ROW = 'Import Configs'
IMPORT_DIALOG = 'Select profile to load:'
OVERWRITE_DIALOG = 'Overwrite config'
IMPORT_RESULT = 'Import result'
INFO_BUTTONS = ('Yes', 'OK')
WM_CLOSE = 0x0010


def dialog_controls(hwnd):
    """Every child of a dialog in enumeration order: class, text, rectangle, handle, visibility."""
    classes = {child: cls for cls, _text, child in descendants(hwnd)}
    return [{'cls': classes.get(child, ''), 'text': text, 'rect': [left, top, right, bottom], 'hwnd': child,
             'visible': bool(winutil.user32.IsWindowVisible(child))}
            for text, (left, top, right, bottom), child in export_util._children_texts(hwnd)]


def plain(text):
    """Window text as it is shown: the ampersands of accelerators dropped."""
    return text.replace('&', '').strip()


def click_dialog_text(hwnd, text, classes=('wxWindowNR', 'Button')):
    """Click the one control of a dialog whose text is `text` as shown.

    The click is a window message to the control under the point, looked up inside the
    dialog's own window tree (the dialog is the root of the hit test), so a layer above the
    dialog cannot take it. Returns what was clicked; raises when the text is not there exactly
    once. No key and no default-button command is ever sent."""
    wanted = plain(text).casefold()
    controls = dialog_controls(hwnd)
    found = [control for control in controls
             if plain(control['text']).casefold() == wanted and control['cls'] in classes]
    if len(found) != 1:
        shown = [control['text'] for control in controls if control['text']]
        raise ValueError(f'the control {text!r} is in the dialog {len(found)} times; it shows {shown!r}')
    left, top, right, bottom = found[0]['rect']
    hit = winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)
    return {'text': found[0]['text'], 'class': found[0]['cls'], 'rect': [left, top, right, bottom],
            'hit': hex(hit) if hit else None}


def _picture(hwnd, work, image):
    """A PrintWindow picture of a dialog under `image`, or why there is none."""
    try:
        return {'image': capture_window(hwnd, Path(work) / image), 'image_name': image}
    except (OSError, RuntimeError, ValueError, cv2.error) as exc:
        return {'image': f'unavailable ({exc})', 'image_name': image}


def dialog_receipt(hwnd, work=None, image=None):
    """A dialog's title, its controls with class and rectangle, and a PrintWindow picture."""
    controls = dialog_controls(hwnd)
    receipt = {'title': winutil.window_title(hwnd),
               'texts': [control['text'] for control in controls if control['text']],
               'controls': [[control['cls'], control['text'], list(control['rect'])] for control in controls]}
    if image:
        receipt.update(_picture(hwnd, work, image))
    return receipt


def press_dialog_button(hwnd, buttons, receipt):
    """Press the first of `buttons` the dialog shows exactly once, by its text. Returns whether
    one was pressed; what was pressed goes to receipt['pressed']. Nothing is ever sent as a
    default key."""
    for text in buttons:
        try:
            receipt['pressed'] = click_dialog_text(hwnd, text)
        except ValueError:
            continue
        return True
    receipt['pressed'] = None
    return False


def _wait_other_dialog(pid, exclude, timeout_s):
    """The next #32770 of the application other than the windows in `exclude`, or None.

    Every visible top-level window is looked at on every poll: a wait for the first dialog
    of a class would hand back the dialog that is already open and known, over and over."""
    deadline = time.monotonic() + timeout_s
    while True:
        found = next((window for window in mixing_util.toplevel(pid)
                      if window[0] == '#32770' and window[3] not in exclude), None)
        if found or time.monotonic() >= deadline:
            return found
        time.sleep(0.25)


def _read_pixels(hwnd):
    """(the words a window shows in pixels, why they could not be read or None). The Info
    boxes of the application write their message into an html window, which carries no
    window text. The reading is evidence; no step depends on it."""
    try:
        from harness import ocr_util
        return ' '.join(ocr_util.ocr_hwnd(hwnd).split()) or None, None
    except Exception as exc:  # noqa: BLE001 - a reading in pixels is extra evidence only
        return None, f'{type(exc).__name__}: {exc}'


def _leave_dialog(hwnd, button='Cancel'):
    """Close one of the application's dialogs by its own `button`; WM_CLOSE when it stays."""
    try:
        click_dialog_text(hwnd, button)
    except ValueError:
        pass
    if _wait_closed(hwnd, 5):
        return True
    winutil._send_msg(hwnd, WM_CLOSE, 0, 0)
    return _wait_closed(hwnd, 5)


def app_dialogs(session, title=None):
    """Visible #32770 top-level windows of the application: [(title, rectangle, handle)], only
    those whose title contains `title` when it is given. Looked up anew on every call, so a
    dialog is found whatever became of the handle it had before."""
    found = [(text, rect, hwnd) for cls, text, rect, hwnd in mixing_util.toplevel(session.pid)
             if cls == '#32770']
    return [row for row in found if title is None or title.casefold() in (row[0] or '').casefold()]


def leave_no_dialog(session, work, analysis, title, key='dialog_left', image='after-dialog.png'):
    """Make sure no dialog of the application is left over, and write down what was done.

    A dialog whose title contains `title` is closed by its own Cancel (a click resolved inside
    that dialog), and by WM_CLOSE when it stays; then it is waited for until no dialog of the
    application is visible any more. The receipt in analysis[key] keeps what was found, what
    was pressed, what is left, whether the main window is enabled, and a picture of the whole
    screen afterwards. Returns the receipt; 'closed' says whether nothing is left."""
    receipt = analysis[key] = {'title': title}
    handles = [row[2] for row in app_dialogs(session, title)]
    receipt['found'] = [[text, list(rect)] for text, rect, _hwnd in app_dialogs(session, title)]
    for hwnd in handles:
        try:
            receipt['cancel'] = click_dialog_text(hwnd, 'Cancel')
        except ValueError as exc:
            receipt['cancel'] = str(exc)
        if not _gone(session, hwnd, 5):
            winutil._send_msg(hwnd, WM_CLOSE, 0, 0)  # a failed export leaves the dialog open
            receipt['wm_close'] = _gone(session, hwnd, 5)
    receipt['left'] = [[text, list(rect)] for text, rect, _hwnd in app_dialogs(session)]
    receipt['main_enabled'] = bool(winutil.user32.IsWindowEnabled(session.hwnd))
    receipt.update(_screen_picture(work, image))
    receipt['closed'] = not receipt['left']
    return receipt


def _gone(session, hwnd, timeout_s):
    deadline = time.monotonic() + timeout_s
    while hwnd in [row[2] for row in app_dialogs(session)] and time.monotonic() < deadline:
        time.sleep(0.2)
    return hwnd not in [row[2] for row in app_dialogs(session)]


def open_dialog_record(session, work, image):
    """What dialogs of the application are open now, with a picture of the whole screen and the
    window in front: the record a step leaves when it must not click with a dialog open."""
    front = winutil.user32.GetForegroundWindow()
    record = {'dialogs': [[text, list(rect)] for text, rect, _hwnd in app_dialogs(session)],
              'main_enabled': bool(winutil.user32.IsWindowEnabled(session.hwnd)),
              'foreground': {'title': winutil.window_title(front) if front else None,
                             'class': winutil.window_class(front) if front else None}}
    record.update(_screen_picture(work, image) if image else {'image_name': None})
    return record


def bundle_rows(controls):
    """The check boxes of the Export Preset Bundle dialog, each paired with its label.

    A box is a small text-less control with a Static written to its right on the same row. A
    box whose label is a package type is a type ('types'); every other one is something to
    export ('items'). 'hint' is the line the dialog writes under the list; 'rows' keeps the
    rectangles of both."""
    boxes = [control for control in controls
             if control['cls'] in BUNDLE_BUTTONS and not control['text'] and control['visible']
             and control['rect'][2] - control['rect'][0] <= 24 and control['rect'][3] - control['rect'][1] <= 24]
    labels = [control for control in controls if control['cls'] == 'Static' and control['text'] and control['visible']]
    rows, paired = [], set()
    for box in boxes:
        left, top, right, bottom = box['rect']
        middle = (top + bottom) / 2
        beside = [label for label in labels if label['hwnd'] not in paired and label['rect'][0] >= right - 2
                  and label['rect'][1] - 4 <= middle <= label['rect'][3] + 4]
        if not beside:
            continue
        label = min(beside, key=lambda candidate: candidate['rect'][0])
        paired.add(label['hwnd'])
        rows.append({'label': label['text'], 'group': 'type' if label['text'] in BUNDLE_KINDS else 'item',
                     'box': list(box['rect']), 'box_class': box['cls'], 'label_rect': list(label['rect'])})
    rest = [control for control in labels if control['hwnd'] not in paired
            and 'shared with others' not in control['text'].casefold()]
    hint = max(rest, key=lambda control: control['rect'][3])['text'] if rest else None
    return {'types': [row['label'] for row in rows if row['group'] == 'type'],
            'items': [row['label'] for row in rows if row['group'] == 'item'], 'hint': hint, 'rows': rows}


def _choose_bundle_kind(hwnd, kind, hint_before, work=None, image=None):
    """Click the label of the package type `kind` and read what the dialog lists afterwards."""
    entry = {'clicked': click_dialog_text(hwnd, kind, classes=('Static', 'wxWindowNR', 'Button'))}
    started = time.monotonic()
    rows = bundle_rows(dialog_controls(hwnd))
    while not rows['items'] and time.monotonic() - started < 6:
        if rows['hint'] != hint_before and time.monotonic() - started >= 1.0:
            break  # the dialog answered with a new hint, and the list under it is empty
        time.sleep(0.25)
        rows = bundle_rows(dialog_controls(hwnd))
    time.sleep(0.5)  # the list finishes its layout after the hint changes
    rows = bundle_rows(dialog_controls(hwnd))
    entry['hint'] = rows['hint']
    entry['items'] = [{'label': row['label'], 'box': row['box'], 'box_class': row['box_class']}
                      for row in rows['rows'] if row['group'] == 'item']
    if work is not None and image:
        entry.update(_picture(hwnd, work, image))
    return entry


def bundle_survey(session, work, analysis, key='bundle_survey', prefix=''):
    """Open File > Export > Export Preset Bundle once and read, for every package type, what it
    lists; then close the dialog without exporting.

    The receipt goes to analysis[key] and is returned: the dialog as opened, and per type the
    rows listed, the hint under the list and a picture (`prefix` keeps the pictures of a second
    reading apart from the first). Raises when the dialog does not open, is not the one
    measured, or will not close."""
    receipt = analysis[key] = {'order': list(BUNDLE_KINDS), 'kinds': {}}
    dispatched, dialog = m7.file_menu_dispatch(session, BUNDLE_ROW, expect_dialog=True, via='Export', timeout_s=10)
    if not dispatched or not dialog:
        raise ValueError(f'File > Export > {BUNDLE_ROW} opened no dialog (dispatched={dispatched!r})')
    _cls, title, _rect, hwnd = dialog
    if BUNDLE_DIALOG.casefold() not in title.casefold():
        raise ValueError(f'File > Export > {BUNDLE_ROW} opened {title!r}')
    receipt['title'] = title
    try:
        receipt['dialog'] = dialog_receipt(hwnd, work, f'{prefix}bundle-dialog.png')
        hint = bundle_rows(dialog_controls(hwnd))['hint']
        for number, kind in enumerate(BUNDLE_KINDS, 1):
            receipt['kinds'][kind] = _choose_bundle_kind(hwnd, kind, hint, work, f'{prefix}bundle-type-{number}.png')
    finally:
        receipt['closed'] = _leave_dialog(hwnd)
    if not receipt['closed']:
        raise ValueError('the Export Preset Bundle dialog would not close')
    return receipt


def _box_beside(dialog, labels):
    """The Edit to the right of the Static that names it (`labels`, without the colon), else the
    first Edit of the dialog. A file chooser has more than one Edit; the one the confirmation
    reads is the one with the label."""
    wanted = {label.casefold() for label in labels}
    controls = dialog_controls(dialog)
    marks = [control for control in controls
             if control['cls'] == 'Static' and plain(control['text']).rstrip(':').casefold() in wanted]
    edits = [control for control in controls if control['cls'] == 'Edit']
    for mark in marks:
        for edit in edits:
            if edit['rect'][0] >= mark['rect'][2] - 4 and edit['rect'][1] < mark['rect'][3] \
                    and edit['rect'][3] > mark['rect'][1]:
                return edit['hwnd']
    return export_util.find_edit(dialog)


def _give_directory(session, chooser, directory, entry):
    """Type `directory` into the folder box of a directory chooser and confirm; the chooser's own
    select button ends it when the confirmation only moved it."""
    edit = _box_beside(chooser, ('Folder',))
    if edit is None or winutil._window_pid(edit) != session.pid:
        raise ValueError('the directory chooser has no owned folder box')
    winutil.select_all(edit)
    winutil.msg_text(edit, str(directory))
    entry['typed'] = winutil.edit_text(edit, size=1024)
    if entry['typed'] != str(directory):
        raise ValueError(f'the directory chooser did not take the directory: {entry["typed"]!r}')
    winutil._send_msg(chooser, 0x0111, IDOK, 0)
    if _wait_closed(chooser, 8):
        return
    entry['select_pressed'] = click_dialog_text(chooser, 'Select Folder')
    if not _wait_closed(chooser, 10):
        raise ValueError('the directory chooser stayed open')


def export_preset_bundle(session, kind, directory, work, analysis, tick='all', key='preset_export'):
    """File > Export > Export Preset Bundle: choose the zip `kind`, tick the listed rows named in
    `tick` ('all' for every row), press OK, give `directory` to the chooser and answer the
    result box.

    `kind` is one of the three zip types by its exact row text (BUNDLE_FILES). The receipt
    goes to analysis[key] and is returned: the rows listed and ticked, the chooser, the result
    box with its words read from pixels, and what landed (`landed`, and for a landed file its
    path, name, bytes and SHA-256). A step that does not behave as measured raises ValueError
    with the receipt kept and leaves no dialog open. Whether what landed is a package of the
    presets is not judged here."""
    if BUNDLE_FILES.get(kind) is None:
        raise ValueError(f'{kind!r} is not one of the zip types this helper exports: {sorted(BUNDLE_FILES)}')
    directory = Path(directory)
    target = directory / BUNDLE_FILES[kind]
    receipt = analysis[key] = {'kind': kind, 'directory': str(directory), 'package_name': target.name}
    if target.exists():
        receipt['error'] = 'a file of that name is already in the directory'
        raise ValueError(f'{target} exists: the application would ask whether to replace it')
    directory.mkdir(parents=True, exist_ok=True)  # the chooser only accepts a directory that is there
    dispatched, dialog = m7.file_menu_dispatch(session, BUNDLE_ROW, expect_dialog=True, via='Export', timeout_s=10)
    if not dispatched or not dialog:
        raise ValueError(f'File > Export > {BUNDLE_ROW} opened no dialog (dispatched={dispatched!r})')
    _cls, title, _rect, hwnd = dialog
    if BUNDLE_DIALOG.casefold() not in title.casefold():
        raise ValueError(f'File > Export > {BUNDLE_ROW} opened {title!r}')
    receipt['title'] = title
    try:
        receipt['dialog'] = dialog_receipt(hwnd, work, 'export-dialog.png')
        hint = bundle_rows(dialog_controls(hwnd))['hint']
        receipt['listed'] = _choose_bundle_kind(hwnd, kind, hint)
        listed = receipt['listed']['items']
        wanted = [row['label'] for row in listed] if tick in (None, 'all') else list(tick)
        unknown = [label for label in wanted if label not in [row['label'] for row in listed]]
        if unknown:
            raise ValueError(f'{kind!r} does not list {unknown!r}; it lists {[row["label"] for row in listed]!r}')
        if not wanted:
            raise ValueError(f'{kind!r} lists nothing to export in this profile '
                             f'(hint: {receipt["listed"]["hint"]!r})')
        receipt['ticked'] = []
        for row in listed:
            if row['label'] not in wanted:
                continue
            left, top, right, bottom = row['box']
            hit = winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)
            receipt['ticked'].append({'label': row['label'], 'box': list(row['box']), 'hit': hex(hit) if hit else None})
        receipt['after_ticking'] = dialog_receipt(hwnd, work, 'export-dialog-ticked.png')
        receipt['ok'] = click_dialog_text(hwnd, 'OK')
        following = _wait_other_dialog(session.pid, {hwnd}, 20)
        if not following:
            raise ValueError('pressing OK opened neither a directory chooser nor a message')
        if DIRECTORY_DIALOG.casefold() not in following[1].casefold():
            refusal = receipt['refusal'] = dialog_receipt(following[3], work, 'result-dialog.png')
            refusal['words'], refusal['words_error'] = _read_pixels(following[3])
            press_dialog_button(following[3], INFO_BUTTONS, refusal)
            raise ValueError(f'pressing OK did not open a directory chooser but {following[1]!r}: '
                             f'{refusal["words"] or refusal["texts"]!r}')
        chooser = following[3]
        receipt['directory_dialog'] = dialog_receipt(chooser, work, 'directory-dialog.png')
        _give_directory(session, chooser, directory, receipt['directory_dialog'])
        result = _wait_other_dialog(session.pid, {hwnd}, 60)
        if result:
            box = receipt['result'] = dialog_receipt(result[3], work, 'result-dialog.png')
            box['words'], box['words_error'] = _read_pixels(result[3])
            press_dialog_button(result[3], INFO_BUTTONS, box)
            if not _wait_closed(result[3], 10):
                raise ValueError('the result message stayed open')
        receipt['dialog_closed'] = _wait_closed(hwnd, 15)
    finally:
        if winutil.user32.IsWindowVisible(hwnd):
            winutil._send_msg(hwnd, WM_CLOSE, 0, 0)  # a failed export leaves the dialog open
    receipt['landed'] = target.is_file()
    if receipt['landed']:
        raw = target.read_bytes()
        receipt.update(saved_path=str(target), saved_name=target.name, bytes=len(raw),
                       sha256=sha256(raw).hexdigest())
        print(f'{LOG} {target.name} of kind {kind!r}: {len(raw)} bytes in {directory}', flush=True)
    return receipt


SAVE_PRESET_DIALOG = 'Save preset'
# The scope switch on the title row of the sidebar's Process panel, and the tab that is a
# child of the main window only while that panel's page is up (run c378dee0, before.png).
PROCESS_PAGE = ('Global', 'Objects')
PROCESS_TAB = 'Quality'
SIDEBAR_TREE = 300


def _screen_picture(work, image):
    """A picture of the whole screen under `image`, or why there is none."""
    try:
        width, height, pixels = winutil.screen_grab()
        frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)[:, :, :3]
        if not cv2.imwrite(str(Path(work) / image), frame):
            return {'image': 'unavailable (not written)', 'image_name': image}
        return {'image': {'width_px': int(width), 'height_px': int(height)}, 'image_name': image}
    except Exception as exc:  # noqa: BLE001 - a picture is evidence; no step depends on it
        return {'image': f'unavailable ({exc})', 'image_name': image}


def window_tree(hwnd, limit=SIDEBAR_TREE):
    """[[class, text, rectangle]] of a window's children, the ones with a text first."""
    classes = {child: cls for cls, _text, child in descendants(hwnd)}
    rows = [[classes.get(child, ''), text[:80], [left, top, right, bottom]]
            for text, (left, top, right, bottom), child in export_util._children_texts(hwnd)]
    rows.sort(key=lambda row: not row[1].strip())
    return rows[:limit]


def show_process_page(session, work, receipt, panel):
    """Bring the page of the sidebar's Process panel forward, and write down what is there.

    The page is up when its "Quality" tab is a child of the main window. When it is not, the
    "Global" side of the scope switch on the panel's title row is clicked, a window message
    resolved inside the main window, and the tab is looked for again. A picture of the whole
    screen is taken first; when the page is still not up, the sidebar's windows (class, text,
    rectangle) go into the receipt. Returns whether the page is up."""
    receipt['before'] = _screen_picture(work, 'preset-before.png')
    row, tab = panel.process_row_y(session), panel.tab_button(session, PROCESS_TAB)
    found = {'process_row_y': row, 'quality_tab': list(tab[0]) if tab else None}
    if tab is None:
        switch = [control for control in dialog_controls(session.hwnd)
                  if control['visible'] and plain(control['text']) in PROCESS_PAGE
                  and 0 < control['rect'][2] - control['rect'][0] <= 160
                  and 12 <= control['rect'][3] - control['rect'][1] <= 40]
        found['scope_switch'] = [[control['cls'], control['text'], control['rect']] for control in switch]
        target = next((control for control in switch if plain(control['text']) == PROCESS_PAGE[0]), None)
        if target is not None:
            left, top, right, bottom = target['rect']
            hit = winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, session.hwnd)
            found['clicked'] = [PROCESS_PAGE[0], [left, top, right, bottom], hex(hit) if hit else None]
            time.sleep(2.0)
            row, tab = panel.process_row_y(session), panel.tab_button(session, PROCESS_TAB)
    found.update(process_row_y_after=row, quality_tab_after=list(tab[0]) if tab else None)
    receipt['page'] = found
    receipt['page_up'] = tab is not None
    if tab is None:
        receipt['sidebar_tree'] = window_tree(session.hwnd)
    return tab is not None


def save_process_preset(session, name, work, analysis, key='preset_saved', value='0.3'):
    """Make the process preset of the moment a user preset named `name`, the way a user does.

    This is the path tests/engine/m5g_preset_manage.py measured, with its helpers. First the
    page of the sidebar's Process panel is brought forward (show_process_page), with a picture
    of the whole screen taken before anything is touched. Then the Advanced switch, the Quality
    page and its first field (the layer height) are driven with real input until the preset is
    changed; the save button of the preset row is found by its tooltip; in
    the application's own "Save preset" box the name is typed without Enter (the box lives on
    its text events), and "User Preset" and "OK" are clicked by their exact text. The receipt
    goes to analysis[key] and is returned: what each step saw, the box's texts and a picture.
    A step that does not behave as measured raises ValueError with the receipt kept and leaves
    no box open. The preset is written by the application under
    ``<datadir>/user/default/process/<name>.json``; whether it is, is for the caller to look at."""
    from harness import host_guard
    if not (host_guard.real_execution_allowed() or host_guard.allow_host()):
        # Real keystrokes and clicks belong on the guest. A test that reaches this line on a
        # host without the opt-in must stop here (one once let keys reach the host's
        # foreground window, 2026-11-26).
        raise ValueError('save_process_preset drives real input: the guest, or ORCA_BB_ALLOW_TESTBOX / ORCA_BB_ALLOW_HOST')
    import m5g_preset_manage as m5g
    from harness import mix_dialog_util as mdu
    from harness import process_panel as pp
    receipt = analysis[key] = {'name': name, 'value': value, 'steps': {}}
    steps = receipt['steps']
    if app_dialogs(session):
        # Nothing is clicked while one of the application's own dialogs is open: the dialog is
        # modal, and a click meant for the sidebar lands nowhere (run f9e9922).
        receipt.update(open_dialog_record(session, work, 'preset-dialog-open.png'))
        raise ValueError(f'the application has a dialog open: {[row[0] for row in app_dialogs(session)]!r}; '
                         'nothing is clicked while it is')
    receipt['at_start'] = open_dialog_record(session, work, None)
    dialog = None
    try:
        if not show_process_page(session, work, receipt, pp):
            raise ValueError('the process page of the sidebar is not up: no "Quality" tab under the '
                             'Process title (preset-before.png holds the whole screen, sidebar_tree '
                             'the sidebar\'s windows)')
        steps['advanced_on'] = bool(pp.ensure_advanced(session, want=True))
        if not steps['advanced_on']:
            raise ValueError('the Advanced switch of the process page did not turn on')
        steps['quality_page'] = bool(pp.click_tab(session, 'Quality', 'height'))
        field = pp.wait_float_edit(session, timeout_s=60) if steps['quality_page'] else None
        if not field:
            raise ValueError('the Quality page shows no field to change')
        rect, handle, before = field
        after = pp.real_edit_set(session, rect, handle, value)
        pp.neutralize_focus(session)
        steps.update(layer_height_before=before, layer_height_after=after)
        if not (after and str(after).startswith(value)):
            raise ValueError(f'the layer height did not take {value!r}: {after!r}')
        time.sleep(6.0)
        steps['preset_row_before_save'] = m5g.preset_row_text(session)
        rect, handle, tooltip = m5g.find_button_by_tooltip(session, 'save')
        steps['save_button'] = {'rect': list(rect) if rect else None, 'tooltip': tooltip}
        if handle is None:
            raise ValueError('the preset row shows no button whose tooltip says save')
        known = pp.top_dialog_set(session)  # what is open now, so that the box stands out
        m5g.real_click(rect)
        box, title = m5g.wait_new_dialog(session, known)
        if not box:
            raise ValueError('pressing the save button opened no "Save preset" box')
        dialog = box
        receipt['dialog'] = dialog_receipt(box, work, 'save-preset-dialog.png')
        if SAVE_PRESET_DIALOG.casefold() not in (title or '').casefold():
            raise ValueError(f'pressing the save button opened {title!r}')
        edit_rect, edit = m5g.dialog_edit(box)
        if not edit:
            raise ValueError('the "Save preset" box has no field for the name')
        focused = False
        for _attempt in range(4):
            winutil.force_set_foreground(session.hwnd)
            time.sleep(0.3)
            m5g.real_click(edit_rect)
            time.sleep(0.4)
            if pp.focus_hwnd(edit) == edit:
                focused = True
                break
        if not focused:
            raise ValueError('the field for the name did not take the focus')
        mdu._send_keys([(0x11, False), (0x41, False), (0x41, True), (0x11, True)])  # Ctrl+A and Delete, never Enter
        time.sleep(0.15)
        mdu._send_keys([(0x2E, False), (0x2E, True)])
        time.sleep(0.2)
        mdu._send_chars(name)
        time.sleep(0.4)
        receipt['typed'] = mdu.edit_value(edit)
        if receipt['typed'] != name:
            raise ValueError(f'the "Save preset" box holds {receipt["typed"]!r}, not {name!r}')
        user, _handle = m5g.dialog_child_exact(box, 'User Preset')
        if not user:
            raise ValueError('the "Save preset" box shows no "User Preset"')
        receipt['user_preset'] = list(user)
        m5g.real_click(user)
        time.sleep(0.5)
        receipt['filled'] = _picture(box, work, 'save-preset-filled.png')
        ok_rect, _handle = m5g.dialog_child_exact(box, 'OK')
        if not ok_rect:
            raise ValueError('the "Save preset" box shows no OK')
        receipt['ok'] = list(ok_rect)
        m5g.real_click(ok_rect)
        time.sleep(3.0)
        receipt['closed'] = not winutil.user32.IsWindowVisible(box)
        receipt['preset_row_after_save'] = m5g.preset_row_text(session)
    finally:
        if dialog is not None and winutil.user32.IsWindowVisible(dialog):
            winutil._send_msg(dialog, WM_CLOSE, 0, 0)
    return receipt


def import_configs(session, sources, work, analysis, key='config_import'):
    """File > Import > Import Configs: give the file chooser the path(s), then answer by their
    text the dialogs that follow.

    An "Overwrite config" question gets its Yes (it only comes for a preset of the same name);
    the "Import result" message gets OK. Both are read in pixels as well, as their text may be
    an html window. Any other dialog is closed and raised. The receipt in analysis[key] lists
    every dialog; a step that does not behave that way raises ValueError and leaves no dialog
    open."""
    sources = [Path(source) for source in (sources if isinstance(sources, (list, tuple)) else [sources])]
    for source in sources:
        if not source.is_file():
            raise ValueError(f'{source} is not a file to import')
    receipt = analysis[key] = {'sources': [source.name for source in sources], 'dialogs': []}
    dispatched, dialog = m7.file_menu_dispatch(session, IMPORT_ROW, expect_dialog=True, via='Import', timeout_s=10)
    if not dispatched or not dialog:
        raise ValueError(f'File > Import > {IMPORT_ROW} opened no dialog (dispatched={dispatched!r})')
    _cls, title, _rect, hwnd = dialog
    if IMPORT_DIALOG.casefold() not in title.casefold():
        raise ValueError(f'File > Import > {IMPORT_ROW} opened {title!r}')
    typed = ' '.join(f'"{source}"' for source in sources) if len(sources) > 1 else str(sources[0])
    seen = {hwnd}
    try:
        receipt['dialog'] = dialog_receipt(hwnd, work, 'import-dialog.png')
        edit = _box_beside(hwnd, ('File name',))
        if edit is None or winutil._window_pid(edit) != session.pid:
            raise ValueError(f'{title!r} has no owned file name box')
        winutil.select_all(edit)
        winutil.msg_text(edit, typed)
        receipt['typed'] = winutil.edit_text(edit, size=2048)
        if receipt['typed'] != typed:
            raise ValueError(f'{title!r} did not take the path: {receipt["typed"]!r}')
        winutil._send_msg(hwnd, 0x0111, IDOK, 0)
        if not _wait_closed(hwnd, 15):
            raise ValueError(f'{title!r} stayed open')
        for number in range(1, 9):
            current = _wait_other_dialog(session.pid, seen, 40)
            if not current:
                raise ValueError('nothing followed the file chooser: no "Import result" message')
            seen.add(current[3])
            entry = dialog_receipt(current[3], work, f'import-{number}-dialog.png')
            entry['words'], entry['words_error'] = _read_pixels(current[3])
            receipt['dialogs'].append(entry)
            heading = entry['title'].casefold()
            if IMPORT_RESULT.casefold() in heading:
                if not press_dialog_button(current[3], ('OK',), entry):
                    raise ValueError(f'the "Import result" message shows no OK: {entry["texts"]!r}')
                if not _wait_closed(current[3], 10):
                    raise ValueError(f'{entry["title"]!r} stayed open')
                break
            if OVERWRITE_DIALOG.casefold() not in heading:
                raise ValueError(f'an unexpected dialog followed the import: {entry["title"]!r} '
                                 f'{entry["words"] or entry["texts"]!r}')
            if not press_dialog_button(current[3], ('Yes',), entry):
                raise ValueError(f'the overwrite question shows no Yes: {entry["texts"]!r}')
            if not _wait_closed(current[3], 10):
                raise ValueError(f'{entry["title"]!r} stayed open')
        else:
            raise ValueError('the import ended without an "Import result" message')
    finally:
        for handle in seen:  # after a failure nothing of this flow may stay over the editor
            if winutil.user32.IsWindowVisible(handle):
                winutil._send_msg(handle, WM_CLOSE, 0, 0)
    return receipt


def export_row_in(rows, item):
    """The one Export submenu row whose label (without accelerator and dots) is `item`, or None."""
    wanted = row_label(item).casefold()
    found = [row for row in rows if row_label(row['label']).casefold() == wanted]
    if len(found) > 1:
        raise ValueError(f'{item!r} names {len(found)} Export rows')
    return found[0] if found else None


def topbar_labels(session):
    return [text for text, _rect, _hwnd in export_util.topbar_buttons(session.hwnd)]


def capture_window(hwnd, path):
    """Keep a PrintWindow image of a native dialog."""
    width, height, pixels = winutil.capture_window(hwnd)
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    if not cv2.imwrite(str(path), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)):
        raise ValueError(f'could not keep the dialog image {Path(path).name}')
    return {'width_px': width, 'height_px': height}


def answer_memory_guard(session, work, analysis):
    """Answer the runtime memory guard with its `Yes, Continue` button.

    The dialog's text and image go to the analysis first. Only the child whose
    text is exactly `Yes, Continue` is clicked, tier by tier; after two dialogs
    that would not close the case stops with an error instead of guessing."""
    dialog = m7.wait_dialog(session.pid, timeout_s=0.3, title_substr=GUARD_TITLE)
    if not dialog:
        return False
    _cls, title, _rect, hwnd = dialog
    dialogs = analysis.setdefault('memory_guard_dialogs', [])
    record = {'title': title, 'at': time.strftime('%H:%M:%S'),
              'texts': [text for _cls, text, _child in descendants(hwnd) if text],
              'screenshot': f'memory-guard-{len(dialogs)}.png'}
    dialogs.append(record)
    try:
        record['image'] = capture_window(hwnd, work / record['screenshot'])
    except (OSError, RuntimeError, ValueError, cv2.error) as exc:
        record['image'] = f'unavailable ({exc})'
    print(f'{LOG} memory guard dialog: {record["texts"]!r}', flush=True)
    yes = [(rect, child) for text, rect, child in export_util._children_texts(hwnd) if text.strip() == GUARD_CONTINUE]
    if len(yes) != 1:
        raise ValueError(f'expected one "{GUARD_CONTINUE}" button, found {len(yes)}: {record["texts"]!r}')
    (left, top, right, bottom), _child = yes[0]
    cx, cy = (left + right) // 2, (top + bottom) // 2
    record['button'] = [left, top, right, bottom]
    record['tiers'] = []
    for how in GUARD_CLICK_TIERS:
        if how == 'message click':
            winutil.msg_click_screen(cx, cy)
        elif how == 'message click inside dialog':
            winutil.msg_click_screen(cx, cy, hwnd)
        elif winutil._window_pid(winutil.window_from_screen_point(cx, cy)) == session.pid:
            # A real click goes through the OS input queue: only when the point
            # really is a window of the application under test.
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            winutil.real_click_screen(cx, cy)
        else:
            record['tiers'].append({'how': how, 'skipped': 'another window covers the button'})
            break
        time.sleep(1.5)
        record['tiers'].append({'how': how, 'closed': not winutil.user32.IsWindowVisible(hwnd)})
        if not winutil.user32.IsWindowVisible(hwnd):
            break
    record['closed'] = not winutil.user32.IsWindowVisible(hwnd)
    print(f'{LOG} memory guard answered: {record["tiers"]!r}', flush=True)
    if not record['closed']:
        analysis['guard_failures'] = analysis.get('guard_failures', 0) + 1
        if analysis['guard_failures'] >= 2:
            raise ValueError(f'"{GUARD_TITLE}" could not be answered with "{GUARD_CONTINUE}"')
    return True


def wait_export_enabled(session, work, analysis, item, timeout_s=150):
    """Wait until the `item` row of File > Export is enabled, answering the memory guard on the way.

    The row's enabled state is gated on the slice result being ready for
    export (MainFrame::can_export_gcode), so it is the completion signal."""
    started = analysis['slice']['clicked_at']
    deadline = time.monotonic() + timeout_s
    polls = 0
    while time.monotonic() < deadline:
        answer_memory_guard(session, work, analysis)
        enabled, _ = m7.file_menu_dispatch(session, item, via='Export', inspect_enabled=True)
        polls += 1
        if enabled:
            analysis['slice'].update(export_enabled_after_seconds=round(time.monotonic() - started, 1), polls=polls)
            print(f'{LOG} {item!r} enabled {analysis["slice"]["export_enabled_after_seconds"]}s after the Slice click', flush=True)
            return True
        time.sleep(1.5)
    try:
        rows = read_export_menu(session)['export']
    except ValueError as exc:
        rows = f'unavailable ({exc})'
    analysis['slice'].update(export_enabled_after_seconds=None, polls=polls, export_menu_at_timeout=rows)
    raise ValueError(f'{item!r} stayed disabled {timeout_s}s after the Slice click')


def slice_until_exportable(session, work, analysis, item, timeout_s=150, key='slice', click=None):
    """Click Slice once, then wait for the `item` export row.

    The readings land in analysis[key]; the memory guard records stay in the
    analysis itself so that a case which slices twice keeps both sets.
    `click` replaces the plate's own Slice button (click_slice_start), for
    example with click_slice_all."""
    analysis['slice'] = {'topbar_before': topbar_labels(session), 'clicked_at': time.monotonic()}
    # Every run records whether the guest's memory guard came up, also when it did not.
    analysis.setdefault('memory_guard_dialogs', [])
    analysis.setdefault('guard_failures', 0)
    try:
        if not (click or click_slice_start)(session):
            raise ValueError('the Slice click did not take')
        wait_export_enabled(session, work, analysis, item, timeout_s)
    finally:
        analysis['slice'].pop('clicked_at', None)
        if key != 'slice':
            analysis[key] = analysis.pop('slice')
    slice_reading = analysis[key]
    slice_reading['topbar_after'] = topbar_labels(session)
    slice_reading['export_menu_after'] = read_export_menu(session)['export']
    return slice_reading


def choose_slice_all(session, record):
    """Select `Slice all` in the slice dropdown; True once the slice button reads `Slice all`.

    The dropdown is a SidePopup: a top-level window of its own, outside the main window tree.
    Its row is clicked with the popup as the root of the hit test, so that the click lands on
    the row whatever transparent layer sits above the popup; the un-rooted click that
    m3f_multi_plate uses is the second try. #235's first guest run stopped here: the rows were
    read and the un-rooted click left the button reading `Slice plate`. Every click, where it
    landed and which label followed goes to `record`."""
    def label():
        _opt, main = export_util.find_slice_buttons(session.hwnd)
        return main[0] if main else None

    for attempt in range(2):
        if 'Slice all' in (label() or ''):
            return True
        opt, _main = export_util.find_slice_buttons(session.hwnd)
        if not opt:
            record.append({'attempt': attempt, 'error': 'the slice button has no dropdown'})
            return False
        x0, y0, x1, y1 = opt[1]
        winutil.msg_click_screen((x0 + x1) // 2, (y0 + y1) // 2, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=5.0)
        if not popup:
            record.append({'attempt': attempt, 'error': 'the slice dropdown did not open'})
            continue
        popup_hwnd = popup[3]
        time.sleep(0.3)  # let the popup finish opening
        shown = export_util._children_texts(popup_hwnd)
        rows = [row for row in shown if 'Slice all' in row[0]]
        if len(rows) != 1:
            record.append({'attempt': attempt, 'error': f'the dropdown shows Slice all {len(rows)} times',
                           'rows': [[text, rect] for text, rect, _child in shown]})
            winutil.close_window(popup_hwnd)
            continue
        _text, (left, top, right, bottom), _child = rows[0]
        x, y = (left + right) // 2, (top + bottom) // 2
        for how, root in (('inside the popup', popup_hwnd), ('un-rooted', None)):
            if not winutil.user32.IsWindow(popup_hwnd):
                break  # the popup is gone: open it again rather than click where it was
            hit = winutil.msg_click_screen(x, y, root)
            entry = {'attempt': attempt, 'click': how, 'row': [left, top, right, bottom],
                     'hit': hex(hit) if hit else None}
            record.append(entry)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if 'Slice all' in (label() or ''):
                    entry['label'] = label()
                    return True
                time.sleep(0.3)
            entry['label'] = label()
    return False


def click_slice_all(session, record=None):
    """Choose Slice all in the slice dropdown and press the slice button once.

    Returns True when the button read `Slice all` and took the click. Whether
    slicing then finished is for the export row to say: the application slices
    the plates one after another, and File > Export > Export all plate sliced
    file stays disabled until every plate has its result."""
    record = [] if record is None else record
    if not choose_slice_all(session, record):
        return False
    _opt, main = export_util.find_slice_buttons(session.hwnd)
    if not main or 'Slice all' not in main[0] or not winutil.user32.IsWindowEnabled(main[2]):
        record.append({'error': 'the slice button is not an enabled Slice all button',
                       'label': main[0] if main else None})
        return False
    x0, y0, x1, y1 = main[1]
    hit = winutil.msg_click_screen((x0 + x1) // 2, (y0 + y1) // 2, session.hwnd)
    record.append({'button': [x0, y0, x1, y1], 'label': main[0], 'hit': hex(hit) if hit else None})
    return True


def complete_file(path, kind):
    """True once a landed file of `kind` ('gcode', 'stl' or 'archive') carries its end marker."""
    raw = Path(path).read_bytes()
    if kind == 'gcode':
        return raw.rstrip().endswith(b'; CONFIG_BLOCK_END')
    if kind == 'stl':
        return len(raw) >= 84 and 84 + 50 * struct.unpack_from('<I', raw, 80)[0] == len(raw)
    if kind == 'archive':
        if raw[:2] != b'PK':
            return False
        try:
            with ZipFile(BytesIO(raw)) as archive:
                return archive.testzip() is None
        except Exception:  # noqa: BLE001 - an unfinished archive is simply not readable yet
            return False
    raise ValueError(f'unknown file kind {kind!r}')


def wait_landed_file(directory, name, known, kind, timeout_s=60):
    """The one file the application wrote for `name`, once it is complete and its size has held still for a second."""
    deadline = time.monotonic() + timeout_s
    previous, stable_since, seen = None, None, []
    while time.monotonic() < deadline:
        seen = sorted(path for path in Path(directory).iterdir()
                      if path.is_file() and path.name not in known
                      and (path.name == name or path.name.startswith(name + '.')))
        sizes = [path.stat().st_size for path in seen]
        now = time.monotonic()
        if len(seen) == 1 and sizes[0] and sizes[0] == previous and complete_file(seen[0], kind):
            stable_since = stable_since or now
            if now - stable_since >= 1.0:
                return seen[0]
        else:
            stable_since = None
        previous = sizes[0] if len(seen) == 1 else None
        time.sleep(0.25)
    raise ValueError(f'no complete file for {name!r} landed within {timeout_s}s; new files: {[p.name for p in seen]}')


def _wait_closed(hwnd, timeout_s):
    deadline = time.monotonic() + timeout_s
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    return not winutil.user32.IsWindowVisible(hwnd)


def cancel_dialog(hwnd):
    """IDCANCEL on a native file dialog."""
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, IDCANCEL, 0)


def export_via_file_menu(session, item, directory, name, work, analysis, title_substr, kind, timeout_s=60,
                         image='export-dialog.png', key='export'):
    """File > Export > `item`: navigate the dialog to `directory`, save under `name`, return what landed.

    The name is typed without an extension so that the application decides it.
    The receipt carries the Export rows seen, the dialog title, the proposed
    name, the type filter entries and the name and size of the file. A dialog
    with another title is left untouched: it may be the memory guard.
    `image` names the kept dialog picture and `key` the analysis entry of the
    receipt; a case that exports more than once gives each its own."""
    directory, name = Path(directory), str(name)
    if not directory.is_dir():
        raise ValueError(f'{directory} is not a directory')
    rows = read_export_menu(session)['export']
    row = export_row_in(rows, item)
    if row is None:
        raise ValueError(f'File > Export has no row {item!r}: {rows!r}')
    if not row['enabled']:
        raise ValueError(f'File > Export > {item} is disabled')
    known = {path.name for path in directory.iterdir()}
    if name in known or any(entry.startswith(name + '.') for entry in known):
        raise ValueError(f'{name!r} already exists in {directory}')
    receipt = analysis[key] = {'item': item, 'export_rows': rows, 'typed_name': name}
    dispatched, dialog = m7.file_menu_dispatch(session, item, expect_dialog=True, via='Export', timeout_s=10)
    if not dispatched or not dialog:
        raise ValueError(f'File > Export > {item} opened no dialog (dispatched={dispatched!r}, dialog={dialog!r})')
    _cls, title, _rect, hwnd = dialog
    receipt['title'] = title
    if title_substr.casefold() not in title.casefold():
        raise ValueError(f'File > Export > {item} opened {title!r}, expected a dialog titled {title_substr!r}')
    children = descendants(hwnd)
    edit = export_util.find_edit(hwnd)
    if edit is None or winutil._window_pid(edit) != session.pid:
        cancel_dialog(hwnd)
        raise ValueError(f'{title!r} has no owned file name box')
    receipt['default_name'] = winutil.edit_text(edit, size=1024)
    receipt['types'] = [combobox_items(child) for cls, _text, child in children if cls == 'ComboBox']
    receipt['labels'] = [text for _cls, text, _child in children if text]
    # Step 1 (measured on the guest): a directory path plus IDOK navigates and keeps the dialog open.
    winutil.select_all(edit)
    winutil.msg_text(edit, str(directory))
    winutil._send_msg(hwnd, 0x0111, IDOK, 0)
    time.sleep(1.0)
    if not winutil.user32.IsWindowVisible(hwnd):
        raise ValueError(f'{title!r} closed after the directory was entered')
    receipt['directory'] = str(directory)
    # Step 2: the bare name plus IDOK saves; the application appends the extension.
    edit = export_util.find_edit(hwnd)
    winutil.select_all(edit)
    winutil.msg_text(edit, name)
    receipt['filename_before_save'] = winutil.edit_text(edit, size=1024)
    if receipt['filename_before_save'] != name:
        cancel_dialog(hwnd)
        raise ValueError(f'{title!r} did not accept the name {name!r}: {receipt["filename_before_save"]!r}')
    receipt['dialog_image'] = capture_window(hwnd, work / image)
    winutil._send_msg(hwnd, 0x0111, IDOK, 0)
    receipt['dialog_closed'] = _wait_closed(hwnd, 15)
    if not receipt['dialog_closed']:
        raise ValueError(f'{title!r} stayed open after the save; dialog texts {[t for t in receipt["labels"]][:24]!r}')
    landed = wait_landed_file(directory, name, known, kind, timeout_s)
    raw = landed.read_bytes()
    receipt.update(saved_name=landed.name, saved_extension=''.join(landed.suffixes),
                   file_bytes=len(raw), file_sha256=sha256(raw).hexdigest(), app_alive=session.alive())
    print(f'{LOG} {item} -> {landed.name} ({len(raw)} bytes), extension {receipt["saved_extension"]!r}', flush=True)
    return receipt
