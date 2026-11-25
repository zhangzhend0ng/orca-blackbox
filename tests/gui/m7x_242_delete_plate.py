#!/usr/bin/env python3
"""#242 Delete the occupied right plate from its blank area and track both meshes."""
# feishu: baseline#242
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

import m7_common as m7
from harness import winutil
from m7x_249_add_part import focus_canvas
from m8x_48_modal_color_header import bring_main_to_mouse
from model_context_cases import open_model_menu
from plate_reserve_case import activate, case_main, save_snapshot
from plate_reserve_oracle import create_delete_plate_fixture, read_project, verify_delete_plate


def prepare_fixture(template, work):
    fixture = work / 'two-plates.3mf'
    create_delete_plate_fixture(template, fixture)
    return fixture


def top_view(session):
    center = m7.find_centroid(session)
    if center is None or not bring_main_to_mouse(session.hwnd):
        raise ValueError('could not focus an occupied fixture canvas')
    canvas = winutil.deepest_child_at(session.hwnd, *m7.client(session, *center))
    if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
        raise ValueError('could not identify the owned canvas')
    focus_canvas(session, canvas)
    key = ord('1')
    m7.mdu._send_keys([(0x11, False), (key, False), (key, True), (0x11, True)])
    time.sleep(1)


def steps(session, work, analysis, _args):
    top_view(session)
    before = save_snapshot(session, work, 'before')
    plates, instances = read_project(before)
    if plates != ('Keep', 'Remove') or {i.name: i.plate for i in instances} != {'Alpha': 'Keep', 'Bravo': 'Remove'}:
        raise ValueError('app did not load both named plates with their original objects')
    analysis['results']['two occupied plates retained before the action'] = 'PASS'
    points = sorted(m7.find_centroids(session, limit=2, min_area=90))
    if len(points) != 2 or points[1][0] - points[0][0] < 100:
        raise ValueError(f'could not distinguish the two plate witnesses: {points!r}')
    left, right = points
    delta = (right[0] - left[0]) // 8
    blanks = [(right[0] + delta, right[1]), (right[0] - delta, right[1]),
              (right[0], right[1] - delta)]
    analysis['object_centers_px'] = points
    analysis['blank_candidates_px'] = blanks
    activate(session, open_model_menu(session, 'Delete Plate', candidates=blanks), '[m7x242]')
    analysis['results']['Delete Plate chosen from blank plate menu'] = 'PASS'
    time.sleep(1)
    after = save_snapshot(session, work, 'after')
    analysis['plates_and_membership'] = verify_delete_plate(before, after)
    analysis['results']['target plate gone, both original meshes retained, no modal error'] = 'PASS'


if __name__ == '__main__':
    raise SystemExit(case_main(242, HERE / 'fixtures/feishu_std_cubesfar.3mf', prepare_fixture, steps))
