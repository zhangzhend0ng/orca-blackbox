#!/usr/bin/env python3
# m7x_229_import_step.py — Feishu #229: import a STEP file of three coloured solids through File > Import
# feishu: baseline#229
"""Feishu #229: a STEP assembly of three coloured solids imported through File > Import (P1).

Precondition (Feishu): 准备含 3 个实体的装配体 assembly.step（各实体不同颜色）.
Steps (Feishu): 1. 通过「文件→导入」导入 assembly.step; 2. 观察对象列表与盘上零件数量/颜色.
Path (Feishu): 文件 → 导入 → 导入 3MF/STL/STEP/SVG/OBJ/AMF…
Expected (Feishu): 3 个实体均被导入，对象列表可见对应零件（或拆分为多对象），颜色保留，无缺件.

The STEP is fixtures/assembly.step (tools/make_assembly_step.py): three 10 mm
cubes 10 mm apart along x, red, green and blue. The plate starts empty with
the U1 0.8 template whose first filaments are red and blue
(fixtures/agent_layer_redblue.3mf; prepare_plate reads the U1 0.8 printer from
the project it saves). The file is handed to File > Import's one model row
(#227's import_stl), then the case waits for a model on the plate and for no
dialog. A dialog that comes is surveyed first (class, title, every child
window, a picture) and written to ``import_dialogs``; a loading box is waited
for, a dialog with an affirmative button has it pressed by text and is seen
to close, and an error dialog, or any other that stays 20 s, stops the case.
The project is saved as ``imported.3mf`` and the object list is read from the
sidebar. tests/step_import_oracle.py judges the four clauses from the saved
project and the list: an entity is a part of the saved project, so one object
with three parts and three objects read the same.

The application's command line refuses STEP files on this build
(``Unknown file format``, control of 2026-11-26), so this row is only seen
through the GUI. The first guest run (dev229a-253195c) showed what File >
Import does with the file: a modal ``Step file import parameters`` dialog
with two deflection boxes (``0.003`` and ``0.50``), the facet count, a
``Don't show again`` box, and a check box ``Split compound and compsolid
into multiple objects`` that is not ticked. With it as it came, the three
cubes were saved as one object with one part of 36 triangles in the first
filament. A user who wants the parts apart ticks that box, so the case
does: it records the check box, its neighbours and its state, then
tries three ways to tick it, reading it back after each by BM_GETCHECK
and by a picture of its square against the square before (a BM_CLICK to
the box; the dialog brought to the foreground and a real click on the
square; BM_SETCHECK followed by the WM_COMMAND a click sends), and only
a box that shows a tick either way leads on to OK. A message click
inside the dialog did not tick it (run dev229b-21fa17bd), and BM_SETCHECK
read back 0 there (run dev229c), so the state is not trusted to
BM_GETCHECK alone. The deflections are left as they are and recorded,
before and after the tick. Whether a tick gives three objects or one object
with three parts, and where the colours land, is read from the saved project.
"""
import ctypes
from ctypes import wintypes

import cv2
import numpy as np
from hashlib import sha256
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from colored_obj_cases import _accept, affirmative, app_dialogs, survey_dialog  # noqa: E402
from file_export_cases import capture_window  # noqa: E402
from harness import winutil  # noqa: E402
from m7x_227_import_stl import import_stl, show_objects_tab, sidebar  # noqa: E402
from m7x_244_add_model import prepare_plate  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402
from step_import_oracle import recorded_results_match, step_import_readings, verdicts  # noqa: E402

# The U1 0.8 template with its first two filaments coloured red and blue
# (tools/make_agent_layer_redblue.py): prepare_plate reads the U1 0.8 printer from the project it saves.
FIXTURE = HERE / 'fixtures' / 'agent_layer_redblue.3mf'
STEP = HERE / 'fixtures' / 'assembly.step'
LOG = '[m7x229]'
STRANGER_WAIT_S = 20
STEP_DIALOG = 'Step file import parameters'
SPLIT_OPTION = 'Split compound and compsolid into multiple objects'
BM_GETCHECK, BM_SETCHECK, BM_CLICK = 0x00F0, 0x00F1, 0x00F5  # what a native button answers to
WM_COMMAND, BN_CLICKED = 0x0111, 0  # the notification a dialog gets when a control is clicked
COVERED_WAIT_S = 15  # the dispatcher closes a system dialog that covers the desktop within this time
BOX_PX, BOX_INSET = 13, 1  # the square of a check box in the dialog picture, and its inset from the control
# What the square must show to count as ticked: interior darker than 200 by this share, or changed from its
# first picture by more than 32 in luminance on this share. The unticked squares of guest runs dev229a and
# dev229c show 0.0 of both.
INK_LUMA, INK_SHARE, CHANGE_LUMA, CHANGE_SHARE = 200, 0.04, 32, 0.10
UNCHECKED, CHECKED = 0, 1  # what BM_GETCHECK answers for a native check box (2 is the third state)
WORDS_KEPT = 400  # the object list is read below the printer panel, well past the first words

_user32 = ctypes.WinDLL('user32', use_last_error=True)
_user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.SendMessageW.restype = wintypes.LPARAM


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives the STEP and evidence only.
    return model


def _loading(title):
    return title.casefold().startswith('loading')


def find_checkbox(children, text):
    """The one native check box of a survey (class Button) whose whole text is `text`; None when
    there is not exactly one."""
    hits = [child for child in children if child['class'] == 'Button' and child['text'].strip() == text]
    return hits[0] if len(hits) == 1 else None


def readings_of(children):
    """The numbers the dialog shows: the two deflection boxes in their order and the facet count
    that follows its label."""
    edits = [child['text'].strip() for child in children if child['class'] == 'Edit']
    counts = [children[index + 1]['text'].strip() for index in range(len(children) - 1)
              if children[index]['text'].strip().startswith('Number of triangular facets')]
    return {'linear_deflection': edits[0] if edits else None, 'angle_deflection': edits[1] if len(edits) > 1 else None,
            'triangular_facets': counts[0] if counts else None}


def check_state(hwnd):
    """What a native check box shows: CHECKED, UNCHECKED, or 2 when it is in its third state."""
    return int(_user32.SendMessageW(hwnd, BM_GETCHECK, 0, 0))


def notification_wparam(control_id):
    """MAKEWPARAM(control id, BN_CLICKED): the wParam a dialog gets when its control is clicked."""
    return (control_id & 0xFFFF) | (BN_CLICKED << 16)


def _neighbours(children, child):
    """The window before and the one after `child`, as the survey lists them."""
    index = next((step for step, other in enumerate(children) if other['hwnd'] == child['hwnd']), None)
    around = [children[step] for step in (index - 1, index + 1) if index is not None and 0 <= step < len(children)]
    return [{'class': other['class'], 'rect': other['rect'], 'text': other['text'][:60]} for other in around]


def pixel_reading(square, reference):
    """What the square of a check box looks like: ``ink`` is the share of its interior darker
    than INK_LUMA (an unticked box is an outline on a light ground; a tick or a fill is ink)
    and ``changed`` the share of the square that differs from `reference`, the square as it
    looked before any way was tried, by more than CHANGE_LUMA. Either past its share means
    ticked. `square` and `reference` are the luminances (0-255) of the square, row by row."""
    interior = [value for row in square[2:-2] for value in row[2:-2]]
    ink = sum(value < INK_LUMA for value in interior) / len(interior)
    changed = sum(abs(value - other) > CHANGE_LUMA for row, before in zip(square, reference)
                  for value, other in zip(row, before)) / (len(square) * len(square[0]))
    return {'ink': round(ink, 4), 'changed': round(changed, 4),
            'ticked': ink >= INK_SHARE or changed >= CHANGE_SHARE}


def shows_ticked(reading, checked=CHECKED):
    """Whether a reading of a check box says it is ticked: the control says so (BM_GETCHECK),
    or the picture of its square does."""
    return reading.get('check') == checked or bool(reading.get('pixels', {}).get('ticked'))


def _brief(reading):
    pixels = reading['pixels']
    return f"check {reading['check']}, ink {pixels['ink']}, changed {pixels['changed']}"


def run_tick_steps(read, steps, is_ticked=shows_ticked):
    """Give a check box `steps`, one after the other: [(how, act)]. `read()` tells the box
    before and after each step (BM_GETCHECK and the picture together), and the first step
    after which `is_ticked()` holds is the last. A step may return a note and leave the box
    alone. Returns (what was tried, as [{'how', 'before', 'after', 'note'}], and the last
    reading); assert_ticked() judges it. Nothing here touches a window: `read` and the steps
    do."""
    records, reading = [], read()
    for how, act in steps:
        if is_ticked(reading):
            break
        record = {'how': how, 'before': reading}
        note = act(record)
        reading = record['after'] = read()
        if note:
            record['note'] = note
        records.append(record)
    return records, reading


def assert_ticked(records, reading, is_ticked=shows_ticked):
    """Raises ValueError, naming every way with both readings before and after it, when no way
    made the box show that it is ticked."""
    if not is_ticked(reading):
        raise ValueError(f'the check box shows itself unticked after {len(records)} way(s): '
                         + '; '.join(f'{record["how"]}: {_brief(record["before"])} -> {_brief(record["after"])}'
                                     for record in records))


def _tick_steps(session, dialog, child, wait_s=COVERED_WAIT_S):
    """The three ways to tick a check box of a dialog, in the order they are tried. They are
    built here and touch a window only when run."""
    box = child['hwnd']
    left, top, _right, bottom = child['rect']
    x, y = left + 7, (top + bottom) // 2  # the square at the left end of the control

    def bm_click(_record):
        _user32.SendMessageW(box, BM_CLICK, 0, 0)
        time.sleep(0.6)

    def real_click(_record):
        winutil.force_set_foreground(dialog)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            # A real click goes through the OS input queue: only onto a window of the application
            # under test. A system dialog that covers the desktop is closed by the dispatcher
            # within wait_s (guest run dev229c), so the point is waited for.
            if winutil._window_pid(winutil.window_from_screen_point(x, y)) == session.pid:
                break
            time.sleep(0.5)
        else:
            return 'skipped: another window covers the box'
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.2)
        winutil.real_click_screen(x, y)
        time.sleep(0.6)
        return None

    def set_and_notify(_record):
        _user32.SendMessageW(box, BM_SETCHECK, CHECKED, 0)
        _user32.SendMessageW(dialog, WM_COMMAND, notification_wparam(child['id']), box)
        time.sleep(0.6)

    return [('BM_CLICK sent to the check box', bm_click),
            ('dialog brought to the foreground, real click on the square', real_click),
            ('BM_SETCHECK, then WM_COMMAND BN_CLICKED sent to the dialog', set_and_notify)]


def box_region(client, control_rect):
    """(x0, y0, x1, y1) of the square of a check box in the dialog's picture. The picture is the
    client area of the dialog, whose screen corner is `client`; the square is BOX_PX wide and
    BOX_INSET in from the corner of the control (the dialog pictures of guest runs dev229a and
    dev229c)."""
    x0, y0 = control_rect[0] - client[0] + BOX_INSET, control_rect[1] - client[1] + BOX_INSET
    return (x0, y0, x0 + BOX_PX, y0 + BOX_PX)


def _luminances(dialog, region):
    """The luminances (0-255) of a rectangle of the dialog's picture, row by row."""
    width, height, pixels = winutil.capture_window(dialog)
    grey = cv2.cvtColor(np.frombuffer(pixels, np.uint8).reshape(height, width, 4), cv2.COLOR_BGRA2GRAY)
    x0, y0, x1, y1 = region
    return grey[y0:y1, x0:x1].tolist()


def _picture(work, hwnd, name):
    """A PrintWindow image of the dialog, kept as `name` in `work`, or why there is none."""
    try:
        capture_window(hwnd, Path(work) / name)
    except (OSError, RuntimeError, ValueError, cv2.error) as exc:
        return f'unavailable ({exc})'
    return name


def tick_option(session, work, dialog, record, text):
    """Tick the check box `text` of a surveyed dialog and see it ticked: run_tick_steps() over
    the three ways of _tick_steps(), each read back two ways, by BM_GETCHECK and by the picture
    of the square against its picture before the first way (a drawn check box keeps its state
    out of the control: on the guest BM_SETCHECK read back 0, run dev229c). The record keeps
    the square with its class, rectangle, place in the picture and neighbours, the first
    picture, every way with both readings before and after it, a picture of the dialog once
    they are done (``import-dialog-ticked.png``) and the dialog's numbers read again. When no
    way makes it show a tick, all of that stays in the record and the error follows."""
    child = find_checkbox(record['children'], text)
    option = record['option'] = {'text': text}
    if child is None:
        option['error'] = 'no single check box with that text'
        raise ValueError(f'{record["title"]!r}: {option["error"]}')
    left, top, _right, bottom = child['rect']
    region = box_region(winutil.client_to_screen(dialog, 0, 0), child['rect'])
    reference = _luminances(dialog, region)
    option.update({'class': child['class'], 'rect': child['rect'], 'at': [left + 7, (top + bottom) // 2],
                   'square_in_picture': list(region), 'first_picture': pixel_reading(reference, reference),
                   'neighbours': _neighbours(record['children'], child)})
    if option['first_picture']['ticked']:
        # Before any way is tried the square must look unticked (0.0 of ink on the guest). Ink
        # there means the square is not where this code looks in the picture, and every reading
        # below would be that mistake; so the picture is kept and the case stops.
        option['image'] = _picture(work, dialog, 'import-dialog-ticked.png')
        option['error'] = f"the square already shows ink before any way was tried: {option['first_picture']}"
        raise ValueError(f'{record["title"]!r}: {option["error"]}')

    def read():
        try:
            pixels = pixel_reading(_luminances(dialog, region), reference)
        except (OSError, RuntimeError, ValueError, cv2.error) as exc:
            pixels = {'ink': None, 'changed': None, 'ticked': False, 'error': f'unavailable ({exc})'}
        return {'check': check_state(child['hwnd']), 'pixels': pixels}

    option['steps'], option['after'] = run_tick_steps(read, _tick_steps(session, dialog, child))
    option['before'] = option['steps'][0]['before'] if option['steps'] else option['after']
    option['image'] = _picture(work, dialog, 'import-dialog-ticked.png')
    record['readings_after_tick'] = readings_of([dict(other, text=winutil.window_title(other['hwnd']))
                                                 for other in record['children']])
    assert_ticked(option['steps'], option['after'])
    return option


def wait_step_import(session, work, analysis, baseline=0, timeout_s=150):
    """After the chooser took the STEP: wait for a model on the plate and for no dialog.

    wait_arrival is no use on the empty U1 template (#251): its coloured
    fraction already clears the gate. Here a model is a candidate the plate
    shows (m7.model_candidates), and there must be more of them than the empty
    plate showed (`baseline`); the import has settled when that holds and no
    dialog is left, twice in a row."""
    deadline = time.monotonic() + timeout_s
    met = analysis.setdefault('import_dialogs', [])
    loading_seen, answered, strangers = set(), set(), {}
    quiet, state = 0, {}
    while time.monotonic() < deadline:
        dialogs = app_dialogs(session)
        for _cls, title, _rect, hwnd in dialogs:
            if _loading(title):
                loading_seen.add(title)
                continue
            if hwnd in answered:
                continue
            record = survey_dialog(work, hwnd, f'import-dialog-{len(met)}')
            met.append(record)
            print(f'[m7x229] dialog {title!r}: {[child["text"] for child in record["children"] if child["text"]][:24]!r}',
                  flush=True)
            if 'error' in title.casefold():
                raise ValueError(f'the application showed {title!r}: '
                                 f'{[child["text"] for child in record["children"] if child["text"]][:12]!r}')
            if title.casefold() == STEP_DIALOG.casefold():
                record['readings'] = readings_of(record['children'])  # the deflections stay as they are
                tick_option(session, work, hwnd, record, SPLIT_OPTION)
            if affirmative(record['children']) is not None:
                _accept(session, work, hwnd, record)  # presses the button and sees the dialog close
                answered.add(hwnd)
        others = [(hwnd, title) for _cls, title, _rect, hwnd in dialogs if not _loading(title) and hwnd not in answered]
        now = time.monotonic()
        strangers = {hwnd: strangers.get(hwnd, now) for hwnd, _title in others}
        lingering = [title for hwnd, title in others if now - strangers[hwnd] > STRANGER_WAIT_S]
        if lingering:
            raise ValueError(f'a dialog without an affirmative button stayed open {STRANGER_WAIT_S}s: '
                             f'{lingering!r}; its survey is in import_dialogs')
        loading = [(hwnd, title) for _cls, title, _rect, hwnd in dialogs if _loading(title)]
        candidates = 0 if others or loading else len(m7.model_candidates(session, limit=10))
        state = {'candidates': candidates, 'baseline': baseline, 'dialogs': [title for _hwnd, title in others + loading]}
        quiet = quiet + 1 if candidates > baseline and not others and not loading else 0
        if quiet >= 2:
            break
        time.sleep(1.0)
    analysis['loading_dialogs'] = sorted(loading_seen)
    print(f'{LOG} import settled: {state}', flush=True)
    return state


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    source = work / 'assembly.step'
    with stage(analysis, 'copy_step'):
        shutil.copyfile(STEP, source)
        analysis['fixture'] = {'name': source.name, 'bytes': source.stat().st_size,
                               'sha256': sha256(source.read_bytes()).hexdigest(),
                               'template': {'name': args.model.name, 'bytes': args.model.stat().st_size,
                                            'sha256': sha256(args.model.read_bytes()).hexdigest()}}
    with stage(analysis, 'empty_plate'):
        center = m7.find_centroid(session)
        if center is None:
            raise ValueError('the U1 template did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
        analysis['empty_plate_candidates'] = len(m7.model_candidates(session, limit=10))
    with stage(analysis, 'import_chooser'):
        import_stl(session, source, work, analysis)
    with stage(analysis, 'observe_import'):
        settled = wait_step_import(session, work, analysis, baseline=analysis['empty_plate_candidates'])
        analysis['import_settled'] = settled
        if settled.get('candidates', 0) <= settled.get('baseline', 0):
            raise ValueError(f'the STEP did not settle on the plate: {settled!r}')
    with stage(analysis, 'save_imported'):
        imported = save_snapshot(session, work, 'imported')
        show_objects_tab(session)
        words = sidebar(session)
        analysis['object_list'] = {'words': [word[0] for word in words][:WORDS_KEPT]}
        analysis['imported'] = step_import_readings(imported, words)
        analysis['object_list'].update({key: (analysis['imported'].get('object_list') or {}).get(key)
                                        for key in ('names', 'found', 'listed')})
        print(f'{LOG} imported: {analysis["imported"].get("entity_count")} entities '
              f'{[entity["part"] for entity in analysis["imported"].get("entities", [])]!r}', flush=True)
    with stage(analysis, 'read_results'):
        analysis['results'].update(verdicts(analysis['imported']))
        # The record cannot outrun the files: the verdicts above are the ones recomputed from them.
        analysis['recorded_results_match'] = recorded_results_match(analysis, analysis['imported'])
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        analysis['editor_at_end'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
        if not session.alive() or leftover:
            raise ValueError(f'editor left in an unexpected state: {analysis["editor_at_end"]!r}')


if __name__ == '__main__':
    raise SystemExit(case_main(229, FIXTURE, prepare_fixture, steps))
