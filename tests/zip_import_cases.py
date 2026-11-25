"""GUI helpers for Feishu #231 Import Zip Archive and #230 project import."""
import ctypes
import ctypes.wintypes as wintypes
import time
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np

import m7_common as m7
from harness import export_util, winutil
from m7x_251_reload_from_disk import write_cube
from zip_import_oracle import MEMBERS, NOTE

PREVIEW = 'Archive preview'


def build_archive(archive, loose):
    """models.zip holds three differently sized binary STL cubes and a readme
    that the product must not list. The cubes are also kept loose as the
    retained sources; the zip and the readme are outside the harvest pattern."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name, size in MEMBERS:
        path = loose / name
        write_cube(path, size)
        sources[name] = path
    note = archive.parent / NOTE
    note.write_text('Not a model. FileArchiveDialog must not list this file.\n', encoding='ascii')
    with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
        bundle.write(note, NOTE)
        for name, path in sources.items():
            bundle.write(path, name)
    return sources


def shoot(hwnd, path):
    """Client-area capture of a dialog; returns the BGRA frame."""
    width, height, pixels = winutil.capture_window(hwnd)
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    if not cv2.imwrite(str(path), cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)):
        raise ValueError(f'unable to retain {path.name}')
    return frame


def combobox_items(combobox):
    """Every list entry of a ComboBox child (CB_GETCOUNT / CB_GETLBTEXT); the selected text is not a window text."""
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


def _comboboxes(hwnd):
    return [combobox_items(child) for _text, _rect, child in export_util._children_texts(hwnd)
            if winutil.window_class(child) == 'ComboBox']


def choose_zip(session, archive, work, analysis):
    """File > Import > Import Zip Archive, type the path, confirm; returns the chooser hwnd."""
    dispatched, dialog = m7.file_menu_dispatch(session, 'Import Zip Archive', expect_dialog=True, via='Import')
    if not dispatched or not dialog:
        raise ValueError('Import Zip Archive did not open a file chooser')
    _, title, _, hwnd = dialog
    edit = export_util.find_edit(hwnd)
    if not edit or winutil._window_pid(edit) != session.pid:
        raise ValueError(f'file chooser has no owned filename control: {title}')
    winutil.select_all(edit)
    winutil.msg_text(edit, str(archive))
    entered = winutil.edit_text(edit, size=512)
    filters = _comboboxes(hwnd)
    shoot(hwnd, work / 'chooser.png')
    analysis['chooser'] = {'title': title, 'entered': entered, 'filters': filters}
    print(f'[m7x231] chooser {analysis["chooser"]}', flush=True)
    if 'zip' not in title.lower() or not any('*.zip' in item for box in filters for item in box['items']):
        raise ValueError(f'chooser is not the ZIP filter dialog: {title!r} {filters}')
    if entered != str(archive):
        raise ValueError(f'wrong chooser filename: {entered}')
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)
    return hwnd


def wait_preview(session, timeout_s=20):
    dialog = m7.wait_dialog(session.pid, timeout_s=timeout_s, title_substr=PREVIEW)
    if not dialog:
        raise ValueError('Archive preview did not open after choosing the zip')
    return dialog[3]


def describe(hwnd):
    """Every descendant with class, text, visibility and screen rect (custom-drawn wx controls)."""
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


def _visible(dlg_hwnd, label, cls=None):
    for text, rect, child in export_util._children_texts(dlg_hwnd):
        if text == label and winutil.user32.IsWindowVisible(child) and (cls is None or winutil.window_class(child) == cls):
            return rect
    return None


def press_named(dlg_hwnd, label):
    """Click an application-drawn button by its window text, with the dialog as the root window."""
    rect = _visible(dlg_hwnd, label)
    if not rect:
        raise ValueError(f'Archive preview has no visible {label!r} button: '
                         f'{[text for text, _r, _c in export_util._children_texts(dlg_hwnd)]}')
    point = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
    winutil.msg_click_screen(*point, dlg_hwnd)
    return list(point)


def list_words(dlg_hwnd, frame, cls):
    """OCR one child control of a captured dialog; rows of a wxDataView are not windows."""
    origin = winutil.client_to_screen(dlg_hwnd, 0, 0)
    rects = [rect for _text, rect, child in export_util._children_texts(dlg_hwnd)
             if winutil.window_class(child) == cls and winutil.user32.IsWindowVisible(child)]
    if not rects:
        raise ValueError(f'Archive preview has no visible {cls} control')
    left, top, right, bottom = rects[0]
    left, top = max(left - origin[0], 0), max(top - origin[1], 0)
    right, bottom = right - origin[0], bottom - origin[1]
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        raise ValueError(f'{cls} control lies outside the captured dialog')
    return [(text, x + left, y + top, w, h)
            for text, x, y, w, h in m7.mdu.ocr_words_img(crop, scale=3, psm=6)]


def sidebar_words(session):
    return m7.mdu.ocr_words_img(m7.capture_bgr(session)[:, :410], scale=2, psm=11)


def wait_closed(hwnd, timeout_s=15):
    deadline = time.monotonic() + timeout_s
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    return not winutil.user32.IsWindowVisible(hwnd)
