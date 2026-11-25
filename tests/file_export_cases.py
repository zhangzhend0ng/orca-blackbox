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
from harness import export_util, topbar_util, winutil
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
