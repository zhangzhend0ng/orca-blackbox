#!/usr/bin/env python3
# feishu: baseline#245
"""Confirm one arranged clone, then invoke Fill in a new Clone dialog."""
import time

import cv2
import numpy as np

from plate_layout_case import activate, record_checks, run_case, save_stage

import m7_common as m7
from harness import export_util, winutil


def open_clone_dialog(session, work, analysis, phase, log):
    candidates = m7.model_candidates(session)
    if not candidates:
        raise ValueError('could not locate a rendered object to clone')
    activate(session, 'Clone', candidates, log)
    dialog = m7.wait_dialog(session.pid, title_substr='Clone', timeout_s=12)
    if not dialog or dialog[1].strip().casefold() != 'clone':
        raise ValueError(f'expected the Clone dialog, got {dialog!r}')
    hwnd = dialog[3]
    visible = children(hwnd)
    diagnostics = [{'label': label, 'class': winutil.window_class(child), 'rect': rect}
                   for label, rect, child in visible]
    analysis.setdefault('dialogs', {})[phase] = diagnostics
    print(f'{log} {phase} Clone dialog visible controls: {diagnostics!r}', flush=True)
    frame = dialog_image(hwnd, work / f'{phase}-dialog-initial.png')
    return hwnd, visible, frame


def children(hwnd):
    return [row for row in export_util._children_texts(hwnd) if winutil.user32.IsWindowVisible(row[2])]


def click_dialog_control(hwnd, dialog):
    left, top, right, bottom = winutil.window_rect(hwnd)
    x, y = (left + right) // 2, (top + bottom) // 2
    if winutil.deepest_child_at(dialog, x, y) != hwnd:
        raise ValueError('dialog control does not own its click target')
    if winutil.real_click_screen(x, y) != 2:
        raise ValueError('could not send a complete click to the Clone dialog')
    time.sleep(.4)


def dialog_image(hwnd, path):
    width, height, data = winutil.capture_window(hwnd)
    image = np.frombuffer(data, np.uint8).reshape(height, width, 4)
    frame = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if not cv2.imwrite(str(path), frame):
        raise ValueError(f'could not save dialog screenshot {path}')
    return frame


def checkbox_handle(dialog, controls):
    labels = [rect for text, rect, _ in controls if 'auto arrange plate after cloning' in text.casefold()]
    if len(labels) != 1:
        raise ValueError(f'expected one Auto arrange plate after cloning label, found {labels}')
    _, y1, x2, y2 = labels[0]
    scale = winutil.get_dpi_for_window(dialog) / 96
    matches = [child for text, (left, top, right, bottom), child in controls
               if not text and left >= x2 and top < y2 and bottom > y1
               and 12*scale <= right-left <= 25*scale and 12*scale <= bottom-top <= 25*scale]
    if len(matches) != 1:
        raise ValueError(f'could not identify one checkbox at the Auto arrange row: {matches}')
    return matches[0]


def checkbox_checked(dialog, hwnd, image):
    # Checked and focused-checked assets have a teal fill, whereas the
    # unchecked assets only draw an outline.
    left, top, right, bottom = winutil.window_rect(hwnd)
    ox, oy = winutil.client_to_screen(dialog, 0, 0)
    if not (0 <= top-oy < bottom-oy <= image.shape[0] and 0 <= left-ox < right-ox <= image.shape[1]):
        raise ValueError('checkbox is outside the captured dialog')
    sample = image[top-oy:bottom-oy, left-ox:right-ox].astype(np.int16)
    b, g, r = sample.transpose(2, 0, 1)
    return bool(np.mean((g-r > 55) & (b-r > 45)) >= .2)


def set_one_auto_arranged(dialog, controls, original, work):
    edits = [h for _, _, h in controls if winutil.window_class(h).casefold() == 'edit']
    if len(edits) != 1:
        raise ValueError('Clone dialog did not expose exactly one native copy count field')
    edit = edits[0]
    if winutil.edit_text(edit) != '1':
        winutil.select_all(edit)
        winutil.msg_text(edit, '1')
    checkbox = checkbox_handle(dialog, controls)
    was_checked = checkbox_checked(dialog, checkbox, original)
    if not was_checked:
        click_dialog_control(checkbox, dialog)
    image = dialog_image(dialog, work / 'clone-dialog-ready.png')
    count = winutil.edit_text(edit)
    checked = checkbox_checked(dialog, checkbox, image)
    if count != '1' or not checked:
        raise ValueError(f'clone dialog prerequisites failed: count={count!r}, auto_arrange={checked}')
    return {'copies': int(count), 'auto_arrange': checked, 'auto_arrange_initial': was_checked}


def confirm_dialog(session, dialog, label, log):
    visible = [(text, handle) for text, _, handle in children(dialog) if text.strip().casefold() == label.casefold()]
    if len(visible) == 1:
        click_dialog_control(visible[0][1], dialog)
    elif label == 'OK' and not visible:
        if not m7.click_dialog_button(dialog, label, fallback_first=False):
            raise ValueError('Clone dialog did not expose its OK button')
    else:
        raise ValueError(f'Clone dialog did not expose exactly one {label} button')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and winutil.user32.IsWindowVisible(dialog):
        time.sleep(.2)
    if winutil.user32.IsWindowVisible(dialog):
        raise ValueError(f'Clone dialog remained open after {label}')
    if not session.alive():
        raise ValueError(f'editor exited after {label}')
    print(f'{log} Clone dialog executed {label!r}', flush=True)


def clone_fill(session, work, before, analysis, log):
    from plate_layout_oracle import verify_clone

    started = time.monotonic()
    dialog, controls, original = open_clone_dialog(session, work, analysis, 'clone', log)
    analysis['clone_dialog'] = set_one_auto_arranged(dialog, controls, original, work)
    analysis['results']['Clone dialog shows count 1 and Auto arrange checked'] = 'PASS'
    confirm_dialog(session, dialog, 'OK', log)
    time.sleep(6)
    cloned = save_stage(session, work, 'cloned')
    clone_report = verify_clone(before, cloned)
    record_checks(analysis, clone_report)
    analysis['phase_seconds']['clone_and_save'] = round(time.monotonic() - started, 3)
    clone_checks = {key: passed for key, passed in clone_report['checks'].items() if not key.startswith('fill_')}
    if not clone_checks or not all(clone_checks.values()):
        raise ValueError('clone geometry or placement failed before Fill')

    started = time.monotonic()
    dialog, _, _ = open_clone_dialog(session, work, analysis, 'fill', log)
    confirm_dialog(session, dialog, 'Fill', log)
    time.sleep(12)
    filled = save_stage(session, work, 'filled')
    record_checks(analysis, verify_clone(before, cloned, filled))
    analysis['phase_seconds']['fill_and_save'] = round(time.monotonic() - started, 3)


if __name__ == '__main__':
    raise SystemExit(run_case(245, clone_fill))
