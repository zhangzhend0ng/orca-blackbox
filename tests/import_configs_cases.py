"""GUI helpers for Feishu #232 config import.

The Export Preset Bundle dialog is no longer driven by this case: on the guest the
product reported "add file fail" for its own export (runs c378dee0 and 8d20f5b),
and the config file is a precondition of the Feishu case, not a step of it."""
import re
import time

import cv2
import numpy as np

import m7_common as m7
from harness import export_util, winutil
from harness import process_panel as pp
from m8_common import combo_text, wait_slots
from repair_model_cases import IMAGE_ERRORS, dialog_texts
from zip_import_cases import _comboboxes, shoot, wait_closed
from import_configs_oracle import arrow_steps

IMPORT_ROW = 'Import Configs'
YES = ('Yes to all', '&Yes to all', 'Yes', '&Yes', 'OK', 'Confirm', 'Overwrite', 'Replace')


def find_printer_combo(session, model):
    """The sidebar printer combo: a child whose text contains the printer model name but
    not a process-preset marker, in the sidebar's upper band (m7t84's locator)."""
    hits = [(text, rect, child) for text, rect, child in export_util._children_texts(session.hwnd)
            if model in text and 'Standard' not in text and rect[1] < 400 and rect[3] - rect[1] < 60
            and winutil.user32.IsWindowVisible(child)]
    return hits[0] if hits else None


def real_wheel(x, y, notches):
    """Wheel through the input queue with the pointer on the popup (m8_common._real_wheel):
    the preset popups do not move on a posted WM_MOUSEWHEEL."""
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    winutil.user32.mouse_event(0x0800, 0, 0, 120 * int(notches), 0)


def open_popup(session, point, root):
    """Click the combo at screen `point`; the popup's (rect, hwnd), or (None, None).
    A popup that was just dismissed can swallow the first click (process_panel)."""
    for _attempt in range(2):
        winutil.msg_click_screen(*point, root)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if popup:
            return popup[2], popup[3]
    return None, None


DIVIDER = re.compile(r'^\s*[-—=~_]{2,}')  # `------ User presets ------`, as the OCR prints a section divider


def dividers_only(words):
    """Whether a reading holds nothing but section dividers."""
    texts = [text for text, _word in row_lines(words)]
    return bool(texts) and all(DIVIDER.match(text) for text in texts)


def popup_page(popup_rect, popup_hwnd):
    """The popup window as an image and its words: OCR at scale 3 with psm 6, the reading
    that sees the rows beside the section dividers (PITFALLS 17.7, m5g). When the window
    cannot be captured a screen crop is read instead (m8_common).

    A page that comes back as dividers only is read a second time, from the inverted picture
    with psm 4, and both readings are returned. The row that has the keyboard focus has a
    thin rectangle drawn around it, and the default reading then skips it and the highlighted
    row: run dev232m-4999edf0 kept a picture of the printer list with `BB Test Printer` in it
    and read four dividers."""
    try:
        width, height, pixels = winutil.capture_window(popup_hwnd)
        image = cv2.cvtColor(np.frombuffer(pixels, np.uint8).reshape(height, width, 4), cv2.COLOR_BGRA2BGR)
    except (OSError, RuntimeError, ValueError, cv2.error):
        screen_w, screen_h, pixels = winutil.screen_grab()
        frame = np.frombuffer(pixels, np.uint8).reshape(screen_h, screen_w, 4)
        left, top, right, bottom = popup_rect
        image = cv2.cvtColor(frame[max(top, 0):bottom, max(left, 0):right], cv2.COLOR_BGRA2BGR)
    words = m7.mdu.ocr_words_img(image, scale=3, psm=6)
    if dividers_only(words):
        inverted = cv2.cvtColor(255 - cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        words = words + m7.mdu.ocr_words_img(inverted, scale=3, psm=4)
    return image, words


def row_lines(words):
    """(text, first word) of each text line; tokens are grouped by their line centre."""
    lines = []
    for word in sorted(words, key=lambda w: (w[2] + w[4] / 2, w[1])):
        middle = word[2] + word[4] / 2
        if lines and abs(lines[-1][0] - middle) <= max(6, word[4] / 2):
            lines[-1][1].append(word)
        else:
            lines.append([middle, [word]])
    return [(' '.join(word[0] for word in sorted(line, key=lambda w: w[1])), min(line, key=lambda w: w[1]))
            for _middle, line in lines]


def read_popup(session, point, root, kind, work, record, pages=10):
    """Open the preset popup and keep every row it lists, from the top down, one page at a
    time with the real wheel. The first two pages are kept as images. Returns the popup's
    (rect, hwnd) and leaves it open for the caller to close."""
    popup_rect, popup_hwnd = open_popup(session, point, root)
    if not popup_hwnd:
        record['error'] = 'the popup did not open'
        return None, None
    x, y = (popup_rect[0] + popup_rect[2]) // 2, (popup_rect[1] + popup_rect[3]) // 2
    real_wheel(x, y, 40)  # the popup opens at the current selection: back to the top first
    time.sleep(0.8)
    rows, seen, before, images = [], set(), None, 0
    for page in range(pages):
        image, words = popup_page(popup_rect, popup_hwnd)
        if images < 2:
            cv2.imwrite(str(work / (f'{kind}-list.png' if not images else f'{kind}-list-2.png')), image)
            images += 1
        texts = [text for text, _word in row_lines(words)]
        if texts == before:
            break  # the list did not move: its end
        for text in texts:
            if text not in seen:
                seen.add(text)
                rows.append(text)
        before = texts
        real_wheel(x, y, -8)
        time.sleep(0.6)
    record['rows'] = rows
    record['pages_read'] = page + 1
    print(f'[m7x232] {kind} list ({page + 1} pages): {rows!r}', flush=True)
    return popup_rect, popup_hwnd


def real_click(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)


def _centre(rect):
    return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2


def settled(verify, name, timeout_s=3.0):
    deadline = time.monotonic() + timeout_s
    while True:
        if name.casefold() in (verify() or '').casefold():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def select_row(session, point, root, kind, name, work, record, verify, pages=6):
    """Open the preset popup, keep every row it lists page by page, and select the row
    named `name` on the page where it was read, without scrolling again.

    `verify()` reads the preset row's own text and alone decides whether it took.

    The row is clicked with a message click without a root window at its first word,
    which is how m8_common and process_panel click a popup row; in run 3f55a59a that
    click, sent four times, left the filament row unchanged, so the mouse is moved to
    the row first. When the text still does not change, the row is clicked through the
    input queue, and last the arrow keys and Enter are sent to the popup window."""
    record['attempts'] = []
    state = {'popup': (None, None), 'recorded': False}

    def locate():
        """(popup rect, popup hwnd, the first word of the row named `name`), or no word."""
        if not state['popup'][1] or not winutil.user32.IsWindowVisible(state['popup'][1]):
            state['popup'] = open_popup(session, point, root)
            if not state['popup'][1]:
                return None, None, None
            x, y = _centre(state['popup'][0])
            real_wheel(x, y, 40)  # the popup opens at the current selection: back to the top first
            time.sleep(0.8)
        popup_rect, popup_hwnd = state['popup']
        x, y = _centre(popup_rect)
        rows, before, page = [], None, 0
        for page in range(pages):
            image, words = popup_page(popup_rect, popup_hwnd)
            if not state['recorded'] and page < 2:
                cv2.imwrite(str(work / (f'{kind}-list.png' if not page else f'{kind}-list-2.png')), image)
            lines = row_lines(words)
            texts = [text for text, _word in lines]
            rows += [text for text in texts if text not in rows]
            hit = next((word for text, word in lines if name.casefold() in text.casefold()), None)
            if hit is not None or texts == before:
                break
            before = texts
            real_wheel(x, y, -8)
            time.sleep(0.6)
        if not state['recorded']:
            record['rows'], record['pages_read'], state['recorded'] = rows, page + 1, True
            record['lines'] = [[word[2] + word[4] // 2, text] for text, word in lines]
            print(f'[m7x232] {kind} list ({page + 1} pages): {rows!r}', flush=True)
        return popup_rect, popup_hwnd, hit

    popup_rect, popup_hwnd, hit = locate()
    record['listed'] = hit is not None
    if hit is None:
        if popup_hwnd:
            pp.close_popup(session, popup_hwnd, point)
        return False
    for how in ('message click', 'real click', 'arrow keys'):
        if how != 'message click':
            popup_rect, popup_hwnd, hit = locate()  # the popup closed on the last try
            if hit is None:
                record['attempts'].append({'how': how, 'result': 'the row was not found again'})
                break
        sx = popup_rect[0] + hit[1] + hit[3] // 2
        sy = popup_rect[1] + hit[2] + hit[4] // 2
        steps = None
        if how == 'message click':
            under = winutil.window_from_screen_point(sx, sy)
            winutil._send_msg(under, 0x0200, 0, winutil._lparam_from_screen(under, sx, sy))  # the hovered row
            winutil.msg_click_screen(sx, sy)
        elif how == 'real click':
            real_click(sx, sy)
        else:
            steps = arrow_steps(record['lines'], record.get('before', ''), name)
            keys = [0x28] * steps if steps > 0 else [0x26] * -steps
            for key in keys + [0x0D]:
                winutil._send_msg(popup_hwnd, 0x0100, key, 0)
                winutil._send_msg(popup_hwnd, 0x0101, key, 0)
                time.sleep(0.15)
        record['attempts'].append({'how': how, 'point': [sx, sy], 'steps': steps})
        if settled(verify, name):
            record['attempts'][-1]['result'] = 'selected'
            record['after'], record['selected'] = verify(), True
            return True
        record['attempts'][-1]['result'] = f'the preset row still reads {verify()!r}'
        print(f'[m7x232] {kind} {how}: {record["attempts"][-1]["result"]}', flush=True)
    if popup_hwnd and winutil.user32.IsWindowVisible(popup_hwnd):
        pp.close_popup(session, popup_hwnd, point)
    return False


def answer_dialogs(session, work, analysis, tag, timeout_s=1.5):
    """Record and close any dialog that follows a preset selection."""
    found = m7.wait_dialog(session.pid, timeout_s=timeout_s)
    if not found:
        return []
    hwnd = keep(session, work, analysis, found, f'{tag}-dialog')
    answer_box(hwnd)
    return analysis['dialogs'][-1:]


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
