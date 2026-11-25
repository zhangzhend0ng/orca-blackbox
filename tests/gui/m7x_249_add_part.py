#!/usr/bin/env python3
# Feishu #249: add a model part and select the assembly by clicking its parent.
# feishu: baseline#249

import argparse
import json
import math
import shutil
import struct
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'tests'))

import m7_common as m7
from harness import winutil
from m3_common import add_common_args, boot_session
from m7x_250_negative_part import load_part_file, open_part_submenu
from m8_common import wait_arrival
from m8x_48_modal_color_header import bring_main_to_mouse, request_background_focus
from part_attachment_oracle import verify_attachment, verify_group_move

FIXTURE = HERE / 'fixtures' / 'agent_layer_cube.3mf'
LOG = '[m7x249]'


def write_part(path):
    # The part protrudes from the cube's front and right faces without covering
    # the central body surface used for the subsequent selection click.
    vertices = ((23, -3, -12), (23, -14, -12), (12, -14, -12), (12, -3, -12),
                (23, -3, -3), (12, -3, -3), (12, -14, -3), (23, -14, -3))
    faces = ((0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 4, 7), (0, 7, 1),
             (1, 7, 6), (1, 6, 2), (2, 6, 5), (2, 5, 3), (4, 0, 3), (4, 3, 5))
    with path.open('wb') as stream:
        stream.write(struct.pack('<80sI', b'Feishu #249 positive part', len(faces)))
        for a, b, c in faces:
            stream.write(struct.pack('<12fH', 0, 0, 0, *vertices[a], *vertices[b], *vertices[c], 0))


@contextmanager
def stage(analysis, name):
    timing = {'started_utc': datetime.now(timezone.utc).isoformat()}
    analysis['timings'][name] = timing
    start = time.monotonic()
    print(f'{LOG} started {name} at {timing["started_utc"]}', flush=True)
    try:
        yield
    finally:
        timing['duration_s'] = round(time.monotonic() - start, 3)
        print(f'{LOG} finished {name} in {timing["duration_s"]:.3f}s', flush=True)


def capture(session, path):
    frame = m7.capture_bgr(session)
    if frame is None or not cv2.imwrite(str(path), frame):
        raise ValueError(f'screenshot unavailable at {path}')
    return frame


def changed_fraction(first, second):
    return float(np.mean(np.max(np.abs(first.astype(np.int16) - second.astype(np.int16)), axis=2) >= 20))


def focus_canvas(session, canvas):
    focus = request_background_focus(session.hwnd, canvas)
    if not (focus and focus[1][1] == canvas and winutil.user32.GetForegroundWindow() == session.hwnd):
        raise ValueError('Prepare canvas did not hold keyboard focus')


def press(vk):
    m7.mdu._send_keys([(vk, False), (vk, True)])


def select_and_move(session, work, original_frame, center, analysis):
    with stage(analysis, 'click_parent'):
        if not bring_main_to_mouse(session.hwnd):
            raise ValueError('Orca did not acquire the guest foreground')
        x, y = center
        y += 14  # The existing context-menu probe hits the body below its centroid.
        point = m7.client(session, x, y)
        canvas = winutil.deepest_child_at(session.hwnd, *point)
        if (winutil.window_class(canvas) != 'wxGLCanvas'
                or winutil._window_pid(canvas) != session.pid
                or not winutil.user32.IsWindowEnabled(canvas)):
            raise ValueError(f'parent click point {point} did not resolve to the Prepare canvas')
        focus_canvas(session, canvas)
        press(0x1B)  # Discard the selection left by Add Part.
        time.sleep(0.6)
        unselected = m7.find_centroid(session)
        press(0x27)  # The same move must have no effect before the parent click.
        time.sleep(0.8)
        equilibrium = m7.find_centroid(session)
        before = capture(session, work / 'prepare-before-select.png')
        control_distance = math.dist(unselected, equilibrium) if unselected and equilibrium else None
        analysis['selection'] = {'click_client': [x, y], 'click_screen': list(point),
                                 'unselected_centroids': [unselected, equilibrium],
                                 'unselected_centroid_distance_px': control_distance}
        print(f'{LOG} unselected Right control centroid {unselected} -> {equilibrium}')
        if control_distance is None or control_distance > 2:
            raise ValueError('Right moved the scene before clicking the parent, or rendered model was lost')
        body_slice = np.s_[y - 12:y + 12, x - 12:x + 12]
        if before.shape != original_frame.shape:
            raise ValueError(f'Prepare frame dimensions changed: {original_frame.shape} -> {before.shape}')
        similarity = 1 - changed_fraction(original_frame[body_slice], before[body_slice])
        analysis['selection']['original_body_pixels_matched'] = similarity
        if similarity < 0.75:
            raise ValueError(f'parent click point did not match the original cube surface: {similarity:.1%}')
        winutil.user32.SetCursorPos(*point)
        hit = winutil.window_from_screen_point(*point)
        if hit != canvas:
            # The guest can place a transparent WebView host above the canvas.
            # Recreate the hover on the verified Orca canvas before its click.
            winutil._send_msg(canvas, 0x0200, 0, winutil._lparam_from_screen(canvas, *point))
        time.sleep(0.4)  # Let Orca resolve the model under the pointer.
        hover_frame = m7.capture_bgr(session)
        if hit == canvas:
            if winutil.real_click_screen(*point) != 2:
                raise ValueError('the physical parent click was not fully delivered')
            click_method = 'physical'
        else:
            if winutil.msg_click_screen(*point, session.hwnd) != canvas:
                raise ValueError('the parent click was not dispatched to the verified Prepare canvas')
            click_method = 'window message'
        time.sleep(0.8)
        selected = capture(session, work / 'prepare-selected.png')
        selection = changed_fraction(hover_frame[body_slice], selected[body_slice])
        analysis['selection']['click_method'] = click_method
        analysis['selection']['body_pixels_changed_after_click'] = selection
        print(f'{LOG} clicked original body at {point} by {click_method}, selection pixel change={selection:.1%}')

    with stage(analysis, 'move_selection'):
        focus_canvas(session, canvas)
        press(0x27)  # Orca moves the selected instance +10 mm in world X.
        time.sleep(1.2)
        press(0x1B)
        time.sleep(0.8)
        capture(session, work / 'prepare-moved.png')
        moved_center = m7.find_centroid(session)
        moved_distance = math.dist(equilibrium, moved_center) if moved_center else None
        analysis['selection']['canvas_centroids'] = [equilibrium, moved_center]
        analysis['selection']['moved_centroid_distance_px'] = moved_distance
        print(f'{LOG} canvas centroids before move={equilibrium}, after move={moved_center}')
        if moved_distance is None or moved_distance < 4:
            raise ValueError('clicking the parent then pressing Right produced no visible model displacement')


def run_case(args, work, analysis, results):
    original = work / 'original.3mf'
    source = work / 'part.stl'
    added = work / 'added.3mf'
    moved = work / 'moved.3mf'
    analysis['paths'] = {path.stem: str(path) for path in (original, source, added, moved)}
    with stage(analysis, 'prepare_inputs'):
        shutil.copyfile(args.model, original)
        write_part(source)

    session = None
    try:
        with stage(analysis, 'open_original'):
            editor_args = SimpleNamespace(exe=args.exe, datadir=work / 'edit-profile')
            session = boot_session(editor_args, model=original)
            m7.ensure_maximized(session)
            arrived, fraction = wait_arrival(session, timeout_s=30)
            center = m7.find_centroid(session) if arrived else None
            print(f'{LOG} original PID={session.pid}, foreground fraction={fraction:.3%}, centroid={center}')
            if center is None:
                raise ValueError('model A did not appear in Prepare')
            original_frame = capture(session, work / 'prepare-before.png')
        with stage(analysis, 'open_add_part_submenu'):
            submenu = open_part_submenu(session, menu_label='Add Part', log=LOG)
            if submenu is None:
                raise ValueError('native Add Part submenu or its Load... row did not appear')
            results['Add Part opens its second-level menu'] = 'PASS'
        with stage(analysis, 'load_part_stl'):
            if not load_part_file(session, submenu, source, log=LOG):
                raise ValueError(f'could not load {source.name} through Add Part > Load...')
            capture(session, work / 'prepare-added.png')
            results['Add Part > Load... accepts part.stl'] = 'PASS'
        with stage(analysis, 'save_added_project'):
            if not m7.save_project_as(session, added, timeout_s=40):
                raise ValueError(f'could not save {added.name}')
        with stage(analysis, 'verify_attached_part'):
            analysis['attachment'] = verify_attachment(original, added, source)
            print(f'{LOG} saved attachment: {analysis["attachment"]!r}')
            results['part.stl is a normal part of the existing object'] = 'PASS'

        select_and_move(session, work, original_frame, center, analysis)
        with stage(analysis, 'save_moved_project'):
            if not m7.save_project_as(session, moved, timeout_s=40):
                raise ValueError(f'could not save {moved.name}')
        with stage(analysis, 'verify_group_move'):
            analysis['group_move'] = verify_group_move(added, moved, delta_x=10)
            print(f'{LOG} group move: {analysis["group_move"]!r}')
            results['clicking model A selects and moves both parts'] = 'PASS'
    finally:
        if session is not None:
            with stage(analysis, 'close_app'):
                session.close()


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=FIXTURE).parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '249'
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'{LOG} retained work directory: {work}', flush=True)
    results = {}
    analysis = {'case': 249, 'timings': {}, 'results': results}
    try:
        run_case(args, work, analysis, results)
    except Exception as exc:
        results['#249 GUI and archive evidence'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(results)


if __name__ == '__main__':
    raise SystemExit(main())
