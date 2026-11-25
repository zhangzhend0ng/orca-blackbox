"""GUI helpers for Feishu #246 Fix model."""
import ctypes
import ctypes.wintypes as wintypes
import time

import cv2
import numpy as np

import m7_common as m7
from harness import export_util, topbar_util, winutil
from m2_slice_chain import click_slice_start
from m8x_48_modal_color_header import bring_main_to_mouse
from zip_import_cases import shoot

GUARD_TITLE = 'Memory Usage Warning'
GUARD_CONTINUE = 'Yes, Continue'
IMAGE_ERRORS = (OSError, RuntimeError, ValueError, cv2.error)


def open_object_menu(session, candidates):
    """Right-click the model at one of `candidates`; the open popup as (hwnd, hmenu), or None.

    model_context_cases.open_model_menu, without its exact enabled label, so that every
    row can be read first."""
    if not bring_main_to_mouse(session.hwnd):
        raise ValueError('Orca could not own the guest foreground')
    points = [(x, y + shift) for x, y in candidates for shift in (14, 0, 26)]
    for point in points:
        sx, sy = m7.client(session, *point)
        canvas = winutil.deepest_child_at(session.hwnd, sx, sy)
        if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
            continue
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.4)
        winutil.msg_click_screen(sx, sy, session.hwnd)  # selects the model under the pointer
        time.sleep(0.4)
        known = {row[4] for row in topbar_util._enum_menu_windows(session.pid)}
        if winutil.window_from_screen_point(sx, sy) == canvas:
            winutil.real_right_click_screen(sx, sy)
            popup = topbar_util.wait_submenu(session.pid, known, timeout_s=2.0)
        else:
            popup = None
        if popup is None:
            lp = winutil._lparam_from_screen(canvas, sx, sy)
            winutil._send_msg(canvas, 0x0204, 0x0002, lp)  # WM_RBUTTONDOWN
            winutil._send_msg(canvas, 0x0205, 0, lp)       # WM_RBUTTONUP
            popup = topbar_util.wait_submenu(session.pid, known, timeout_s=3.0)
        if popup:
            return popup[1], popup[2]
    return None


def dialog_texts(hwnd):
    """Text of every descendant, read through the window handles."""
    out = []
    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(child, _lp):
        text = ctypes.create_unicode_buffer(4096)
        winutil.user32.GetWindowTextW(child, text, 4096)
        if text.value:
            out.append(text.value)
        return True

    winutil.user32.EnumChildWindows(ctypes.c_void_p(hwnd), callback(visit), 0)
    return out


def _image(hwnd, work, path, record):
    try:
        record['image'] = shoot(hwnd, path) is not None
    except IMAGE_ERRORS as exc:
        record['image'] = f'unavailable ({exc})'


def watch_dialog(session, work, analysis, timeout_s):
    """Keep the first native dialog that appears within `timeout_s` (prompt.png and its
    texts), then close it. Returns its texts, or [] when none appeared."""
    dialog = m7.wait_dialog(session.pid, timeout_s=timeout_s)
    if not dialog:
        return []
    _cls, title, _rect, hwnd = dialog
    record = {'title': title, 'texts': dialog_texts(hwnd), 'screenshot': 'prompt.png'}
    _image(hwnd, work, work / 'prompt.png', record)
    analysis.setdefault('dialogs', []).append(record)
    print(f'[m7x246] dialog: {record!r}', flush=True)
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)  # IDOK closes a message box
    deadline = time.monotonic() + 5
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    if winutil.user32.IsWindowVisible(hwnd):
        winutil._send_msg(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        time.sleep(1.0)
    record['closed'] = not winutil.user32.IsWindowVisible(hwnd)
    return record['texts']


def grab_menu(menu_hwnd, path):
    """Desktop grab around the open popup menu; PrintWindow of the main window does not show it."""
    rect = wintypes.RECT()
    winutil.user32.GetWindowRect(menu_hwnd, ctypes.byref(rect))
    width, height, pixels = winutil.screen_grab()
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    left, top = max(rect.left - 8, 0), max(rect.top - 8, 0)
    crop = cv2.cvtColor(frame[top:rect.bottom + 8, left:rect.right + 8], cv2.COLOR_BGRA2BGR)
    if not cv2.imwrite(str(path), crop):
        raise ValueError(f'unable to retain {path.name}')
    return crop


def watch_prompts(session, work, analysis, timeout_s=8):
    """Read what the product shows after the click: a native dialog (kept as prompt.png with
    its texts), else the first frame whose text mentions the repair. Returns the texts read."""
    texts = watch_dialog(session, work, analysis, timeout_s=1.0)
    if texts:
        return texts
    deadline, reads = time.monotonic() + timeout_s, []
    while time.monotonic() < deadline:
        frame = m7.capture_bgr(session)
        reads = [word[0] for word in m7.mdu.ocr_words_img(frame, scale=2, psm=11)]
        if any('repair' in word.casefold() for word in reads):
            if not cv2.imwrite(str(work / 'prompt.png'), frame):
                raise ValueError('unable to retain prompt.png')
            break
        time.sleep(0.5)
    analysis['texts_after_click'] = reads
    print(f'[m7x246] texts after the click: {reads!r}', flush=True)
    return reads


def answer_memory_guard(session, work, analysis):
    """Answer the runtime memory guard with its `Yes, Continue` button, the dialog as the
    root window. After two dialogs that would not close the case stops instead of guessing."""
    dialog = m7.wait_dialog(session.pid, timeout_s=0.3, title_substr=GUARD_TITLE)
    if not dialog:
        return False
    _cls, title, _rect, hwnd = dialog
    dialogs = analysis.setdefault('memory_guard_dialogs', [])
    record = {'title': title, 'texts': dialog_texts(hwnd)}
    dialogs.append(record)
    _image(hwnd, work, work / f'memory-guard-{len(dialogs)}.png', record)
    print(f'[m7x246] memory guard dialog: {record["texts"]!r}', flush=True)
    yes = [rect for text, rect, _child in export_util._children_texts(hwnd) if text.strip() == GUARD_CONTINUE]
    if len(yes) != 1:
        raise ValueError(f'expected one "{GUARD_CONTINUE}" button, found {len(yes)}')
    (left, top, right, bottom), = yes
    winutil.msg_click_screen((left + right) // 2, (top + bottom) // 2, hwnd)
    time.sleep(1.5)
    record['closed'] = not winutil.user32.IsWindowVisible(hwnd)
    if not record['closed']:
        analysis['guard_failures'] = analysis.get('guard_failures', 0) + 1
        if analysis['guard_failures'] >= 2:
            raise ValueError(f'"{GUARD_TITLE}" could not be answered with "{GUARD_CONTINUE}"')
    return True


def slice_until_exportable(session, work, analysis, item='Export G-code', timeout_s=150):
    """Click Slice, answer the memory guard on the way, and wait until the `item` row of
    File > Export is enabled (the completion signal on this build)."""
    if not click_slice_start(session):
        raise ValueError('slice click did not take')
    analysis['slice'] = {'clicked_at': time.strftime('%H:%M:%S')}
    started = time.monotonic()
    deadline = started + timeout_s
    while time.monotonic() < deadline:
        answer_memory_guard(session, work, analysis)
        enabled, _ = m7.file_menu_dispatch(session, item, via='Export', inspect_enabled=True)
        if enabled:
            analysis['slice'].update(export_enabled=True, after_seconds=round(time.monotonic() - started, 1))
            return True
        time.sleep(1.5)
    analysis['slice']['export_enabled'] = False
    return False
