#!/usr/bin/env python3
"""#247 Split two disconnected shells into separately editable objects."""
# feishu: baseline#247
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

from harness import topbar_util
import m7_common as m7
from m7x_250_negative_part import highlight_menu_item, open_part_submenu, send_menu_key
from model_context_cases import open_model_menu
from plate_reserve_case import activate, case_main, save_snapshot
from plate_reserve_oracle import create_split_fixture, verify_split, verify_split_selection


def prepare_fixture(template, work):
    fixture = work / 'twin-shell.3mf'
    create_split_fixture(template, fixture)
    return fixture


def object_centers(session, phase, analysis):
    points = sorted(m7.find_centroids(session, limit=2, min_area=70))
    analysis.setdefault('shell_centers_px', {})[phase] = points
    print(f'[m7x247] {phase} centers: {points!r}', flush=True)
    if len(points) != 2 or points[1][0] - points[0][0] < 30:
        raise ValueError(f'could not address both visible mesh shells: {points!r}')
    return points


def set_color(session, point, slot):
    menu = open_model_menu(session, 'Change Filament', candidates=[point])
    if not menu:
        raise ValueError('object was not selectable with an individual filament menu')
    hwnd, handle, index = menu
    _, expected_child = topbar_util.item_info(handle, index)
    if not expected_child or not highlight_menu_item(session, handle, index, log='[m7x247]'):
        raise ValueError('expected a nested Change Filament menu')
    if not send_menu_key(session, 0x27, log='[m7x247]'):
        raise ValueError('could not focus available colors')
    popup = topbar_util.wait_submenu(session.pid, {hwnd}, timeout_s=5)
    if not popup or popup[2] != expected_child:
        raise ValueError('Change Filament submenu did not open')
    rows = [(i, label) for i, label, flags in topbar_util.menu_items(expected_child)
            if label.strip() and not flags & 3]
    if len(rows) <= slot or rows[0][1].strip().casefold() != 'default':
        raise ValueError(f'could not establish filament slot order: {rows!r}')
    print(f'[m7x247] individual filament menu {rows!r}; requested slot {slot}', flush=True)
    activate(session, (popup[1], expected_child, rows[slot][0]), '[m7x247]')
    time.sleep(1)


def steps(session, work, analysis, _args):
    before = save_snapshot(session, work, 'before')
    left, right = object_centers(session, 'before', analysis)
    activate(session, open_part_submenu(session, menu_label='Split', child_label='To objects',
                                       candidates=[left, right], log='[m7x247]'), '[m7x247]')
    time.sleep(1)
    split = save_snapshot(session, work, 'split')
    analysis['split_geometry'] = verify_split(before, split)
    analysis['results']['Split > To objects retained both closed shells as independent objects'] = 'PASS'
    left, _ = object_centers(session, 'split', analysis)
    set_color(session, left, 2)
    left_color = save_snapshot(session, work, 'left-color')
    _, right = object_centers(session, 'left-color', analysis)
    set_color(session, right, 3)
    both_colors = save_snapshot(session, work, 'both-colors')
    analysis['split_selection'] = verify_split_selection(split, left_color, both_colors)
    analysis['results']['both objects can be selected individually and assigned distinct colors'] = 'PASS'


if __name__ == '__main__':
    raise SystemExit(case_main(247, HERE / 'fixtures/feishu_std_cube.3mf', prepare_fixture, steps))
