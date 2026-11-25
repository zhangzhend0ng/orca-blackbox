#!/usr/bin/env python3
# m7x_251_reload_from_disk.py — Feishu #251: import an STL, reload it from disk after the file changed and after it was deleted
# feishu: baseline#251
"""Feishu #251【从磁盘重新加载】模型右键「从磁盘重新加载」按磁盘文件重载对象 (P1).

Precondition (Feishu): 对象由外部 STL 导入，磁盘上同名文件已修改（如尺寸 20mm→30mm）.
Steps (Feishu): 1. 选中对象右键 → 点击「从磁盘重新加载」　2. 观察对象几何.
Expected (Feishu): 对象按磁盘最新文件重新加载，尺寸变为 30mm；文件被删则明确报错.

The project starts as an empty plate with the U1 0.8 printer (the #244 start).
The 20 mm cube reload_cube.stl is imported through File > Import with the #227
chooser steps and the plate is saved. The same path is then overwritten with a
30 mm cube, the object's context menu gives Reload from disk, and the plate is
saved again. Last the file is deleted and Reload from disk is invoked once
more: whatever the application shows is kept (kind of dialog, title, offered
file name, picture), a file chooser is cancelled and a message box closed, and
the plate is saved a third time.
tests/reload_oracle.py judges every saved file and the dialog; nothing is
read back from the screen for the geometry.
"""
from hashlib import sha256
from pathlib import Path
import shutil
import struct
import sys
import time

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from harness import export_util, topbar_util, winutil  # noqa: E402
from m7x_199_new_project_title import save_prompt_words  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from model_context_cases import open_model_menu  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402
from reload_oracle import (  # noqa: E402
    CLAUSE_MISSING, clauses, explicit_missing_error, is_cube, verify_cube)

FIXTURE = HERE / 'fixtures' / 'agent_layer_cube.3mf'
LOG = '[m7x251]'
MENU = "Reload from disk"
SOURCE_NAME = 'reload_cube.stl'


def prepare_fixture(model, work):
    # The repository template is loaded as it is; the run directory receives evidence only.
    return model


def write_cube(path, size):
    """Write a 12-triangle binary STL with dimensions in millimeters."""
    points = ((0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0),
              (0, 0, size), (size, 0, size), (size, size, size), (0, size, size))
    faces = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
    triangle = struct.Struct("<12fH")
    with path.open("wb") as output:
        output.write(struct.pack("<80sI", b"Orca black-box #251 cube", len(faces)))
        for face in faces:
            vertices = tuple(axis for index in face for axis in points[index])
            output.write(triangle.pack(0, 0, 0, *vertices, 0))


def reload_selected(session, screenshot):
    """Right-click the object and choose Reload from disk; False when its menu never showed the row."""
    image = capture(session, screenshot)
    height, width = image.shape[:2]
    viewport_left = m7.VIEWPORT_X0
    viewport_width = width - viewport_left
    center = viewport_left + viewport_width // 2, height // 2
    # The single STL is auto-centered on the plate. Plate-side widgets also
    # carry saturated colors, so reserve the search for the central plate area.
    candidates = [
        (x, y) for x, y in m7.model_candidates(session, limit=10)
        if viewport_left + 0.2 * viewport_width < x < viewport_left + 0.8 * viewport_width
        and 0.24 * height < y < 0.74 * height
    ]
    candidates.sort(key=lambda point: (point[0] - center[0]) ** 2 + (point[1] - center[1]) ** 2)
    candidates.extend((center, (center[0], center[1] - height // 12)))
    print(f"{LOG} central plate right-click candidates={candidates}", flush=True)
    opened = open_model_menu(session, MENU, candidates=candidates)
    if opened is None:
        return False
    _, hmenu, index = opened
    try:
        return topbar_util.activate_menu_item(session, hmenu, index)
    finally:
        topbar_util.close_menu_windows(session.pid)


def observe_missing_dialog(session, source, screenshot):
    """What the application showed for the missing `source`, then closed; returns the readings.

    The dialog's kind, title, offered file name and a picture are kept. A file
    chooser is cancelled with IDCANCEL, a message box is closed with its OK.
    The judgement of these readings is reload_oracle.explicit_missing_error."""
    facts = {'appeared': False, 'behavior': 'no dialog', 'title': '', 'filename': '', 'body': '',
             'screenshot': None, 'closed': True}
    dialog = export_util.wait_toplevel(session.pid, lambda cls, _t, _r: cls == "#32770", timeout_s=10)
    if not dialog:
        print(f"{LOG} missing source: no Orca dialog", flush=True)
        return facts
    _, title, _, hwnd = dialog
    facts.update(appeared=True, title=title)
    try:
        width, height, raw = winutil.capture_window(hwnd)
        image = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
        saved = cv2.imwrite(str(screenshot), cv2.cvtColor(image, cv2.COLOR_BGRA2BGR))
        facts['screenshot'] = screenshot.name if saved else None
    except (winutil.CaptureError, cv2.error) as exc:
        print(f"{LOG} missing-source dialog screenshot unavailable: {exc}", flush=True)
    print(f"{LOG} missing-source dialog screenshot kept={facts['screenshot'] is not None}: {screenshot}", flush=True)
    edit = export_util.find_edit(hwnd)
    if edit and "select a file" in title.casefold():
        facts.update(behavior="replacement file chooser", filename=winutil.edit_text(edit, size=260))
    else:
        facts.update(behavior="message dialog",
                     body=" ".join(word[0] for word in save_prompt_words(hwnd)))
    print(f"{LOG} missing {source}: {facts['behavior']}, title={title!r}, filename={facts['filename']!r}, "
          f"body={facts['body']!r}", flush=True)
    if edit:
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)  # IDCANCEL
    else:
        m7.click_dialog_button(hwnd, "OK", fallback_first=False)
    deadline = time.monotonic() + 8
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.25)
    facts['closed'] = not winutil.user32.IsWindowVisible(hwnd)
    print(f"{LOG} missing-source dialog closed={facts['closed']}", flush=True)
    return facts


def read(analysis, key, project, stl, **checks):
    """Keep what the oracle reads from `project`, or its refusal, under analysis[key]."""
    try:
        analysis[key] = verify_cube(project, stl, **checks)
    except (ValueError, OSError, KeyError) as exc:
        analysis[key] = {'error': f'{type(exc).__name__}: {exc}'}
    print(f"{LOG} {key}: {analysis[key]!r}", flush=True)
    return 'error' not in analysis[key]


def wait_import_settled(session, timeout_s=30):
    """Wait for the imported object and for the Loading box to go.

    wait_arrival is no use here: the empty U1 template's coloured fraction
    (0.104%) already clears its gate, so it returns at once and the first
    save met the Loading dialog (guest run dev251a-67abded0)."""
    deadline = time.monotonic() + timeout_s
    state = {'dialog': None, 'objects': 0}
    while True:
        dialog = m7.wait_dialog(session.pid, timeout_s=0.5)
        objects = [] if dialog else m7.model_candidates(session, limit=10)
        state = {'dialog': dialog[1] if dialog else None, 'objects': len(objects)}
        if (objects and not dialog) or time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    print(f"{LOG} import settled: {state}", flush=True)
    return state


def steps(session, work, analysis, args):
    # Both helpers take write_cube from this module, so they are imported here.
    from m7x_227_import_stl import import_stl
    from m7x_244_add_model import prepare_plate

    analysis.setdefault('timings', {})
    source = work / SOURCE_NAME
    original, modified = work / 'source-20mm.stl', work / 'source-30mm.stl'
    with stage(analysis, 'write_stl'):
        write_cube(original, 20)
        write_cube(modified, 30)
        shutil.copyfile(original, source)
        analysis['source'] = {'path': str(source),
                              'sha256_20mm': sha256(original.read_bytes()).hexdigest(),
                              'sha256_30mm': sha256(modified.read_bytes()).hexdigest()}
    with stage(analysis, 'empty_plate'):
        center = m7.find_centroid(session)
        if center is None:
            raise ValueError('the U1 template did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
    with stage(analysis, 'import_chooser'):
        import_stl(session, source, work, analysis)
    with stage(analysis, 'observe_import'):
        settled = wait_import_settled(session)
        analysis['import_settled'] = settled
        if not settled['objects'] or settled['dialog']:
            raise ValueError(f'the imported STL did not settle on the plate: {settled}')
    with stage(analysis, 'save_imported'):
        read(analysis, 'before', save_snapshot(session, work, 'before-reload'), source, side=20)
    with stage(analysis, 'reload_modified'):
        shutil.copyfile(modified, source)
        analysis['source']['sha256_at_reload'] = sha256(source.read_bytes()).hexdigest()
        if not reload_selected(session, work / 'prepare-import.png'):
            raise ValueError('the object menu did not offer Reload from disk after the STL changed')
    with stage(analysis, 'save_reloaded'):
        read(analysis, 'reloaded', save_snapshot(session, work, 'after-reload'), source, side=30)
    with stage(analysis, 'delete_source'):
        source.unlink()
        analysis['source']['exists_after_delete'] = source.exists()
        print(f"{LOG} deleted source={source}, source still exists={source.exists()}", flush=True)
    with stage(analysis, 'reload_missing'):
        if not reload_selected(session, work / 'prepare-reloaded.png'):
            raise ValueError('the object menu did not offer Reload from disk after the STL was deleted')
        missing = analysis['missing'] = observe_missing_dialog(session, source, work / 'missing-dialog.png')
        missing['explicit_error'] = explicit_missing_error(missing['behavior'], missing['title'], missing['body'])
    with stage(analysis, 'save_after_missing'):
        read(analysis, 'after_missing', save_snapshot(session, work, 'after-missing'), modified,
             recorded=source, side=30)
    with stage(analysis, 'read_results'):
        # A reading, not a clause: cancelling the dialog must not cost the 30 mm object.
        analysis['after_missing']['still_30mm'] = is_cube(analysis['after_missing'], 30)
        checks = clauses(analysis['before'], analysis['reloaded'],
                         missing['behavior'], missing['title'], missing['body'])
        detail = (f"{missing['behavior']} {missing['title']!r} names no missing file"
                  if missing['appeared'] else 'no dialog at all')
        for clause, passed in checks.items():
            analysis['results'][clause] = 'PASS' if passed else (f'FAIL ({detail})' if clause == CLAUSE_MISSING else 'FAIL')
        leftovers = m7.wait_dialog(session.pid, timeout_s=0.5)
        analysis['editor_at_end'] = {'alive': session.alive(), 'dialog': leftovers[1] if leftovers else None}
        if not session.alive() or leftovers:
            raise ValueError(f'editor left in an unexpected state: {analysis["editor_at_end"]!r}')


if __name__ == "__main__":
    raise SystemExit(case_main(251, FIXTURE, prepare_fixture, steps))
