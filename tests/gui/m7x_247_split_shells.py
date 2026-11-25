#!/usr/bin/env python3
"""#247 Split two disconnected shells into separately editable objects."""
# feishu: baseline#247
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

from harness import topbar_util, winutil
import m7_common as m7
from m7x_248_delete_object import sidebar
from m7x_249_add_part import capture, focus_canvas
from m7x_250_negative_part import highlight_menu_item, open_part_submenu, send_menu_key
from m8x_48_modal_color_header import bring_main_to_mouse
from model_context_cases import open_model_menu
from plate_reserve_case import activate, case_main, save_snapshot
from plate_reserve_oracle import _split_instances, create_split_fixture, verify_split, verify_split_selection


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
    # Split selects all newly created objects. Escape on the owned Prepare
    # canvas clears that selection before we address a single object.
    if not bring_main_to_mouse(session.hwnd):
        raise ValueError('editor did not acquire foreground for clearing selection')
    canvas = winutil.deepest_child_at(session.hwnd, *m7.client(session, *point))
    if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
        raise ValueError('could not identify the owned canvas for clearing selection')
    focus_canvas(session, canvas)
    if not send_menu_key(session, 0x1B, log='[m7x247]'):  # VK_ESCAPE.
        raise ValueError('could not clear the current selection')
    print(f'[m7x247] sent Escape to owned canvas before selecting {point!r}', flush=True)
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
    rows = topbar_util.menu_items(expected_child)
    print(f'[m7x247] individual filament menu {rows!r}; requested slot {slot}', flush=True)
    # Orca lists Default at row 0, then physical filament slots in index order.
    if (len(rows) <= slot or rows[0][1].replace('&', '').strip().casefold() != 'default'
            or any(i != pos or not label.strip() for pos, (i, label, _) in enumerate(rows[:slot + 1]))
            or rows[slot][2] & 3):
        raise ValueError(f'could not establish filament slot order: {rows!r}')
    activate(session, (popup[1], expected_child, rows[slot][0]), '[m7x247]')
    time.sleep(1)


def observe_object_list(session, work, analysis):
    try:
        words = sidebar(session)
        tab = next((word for word in words if word[0].casefold() == 'objects'), None)
        if tab:
            _, x, y, w, h = tab
            winutil.msg_click_screen(*m7.client(session, x + w // 2, y + h // 2), session.hwnd)
            time.sleep(1)
            words = sidebar(session)
        capture(session, work / 'object-list.png')
        analysis['object_list_ocr'] = {'objects_tab_located': bool(tab),
                                       'words': [word[0] for word in words]}
    except Exception as exc:
        analysis['object_list_ocr'] = {'unavailable': f'{type(exc).__name__}: {exc}'}
    print(f'[m7x247] object list: {analysis["object_list_ocr"]!r}', flush=True)


def steps(session, work, analysis, _args):
    before = save_snapshot(session, work, 'before')
    left, right = object_centers(session, 'before', analysis)
    activate(session, open_part_submenu(session, menu_label='Split', child_label='To objects',
                                       candidates=[left, right], log='[m7x247]'), '[m7x247]')
    time.sleep(1)
    split = save_snapshot(session, work, 'split')
    analysis['split_geometry'] = verify_split(before, split)
    analysis['results']['Split > To objects retained both closed shells as independent objects'] = 'PASS'
    # Capture both points before the first color change adds new chromatic UI pixels.
    left, right = object_centers(session, 'split', analysis)
    set_color(session, left, 2)
    left_color = save_snapshot(session, work, 'left-color')
    original_slots = [obj.extruder for obj in _split_instances(split)]
    left_slots = [obj.extruder for obj in _split_instances(left_color)]
    analysis['first_color_readback'] = {'before': original_slots, 'after': left_slots}
    if original_slots[0] == '2' or left_slots != ['2', original_slots[1]]:
        raise ValueError(f'first color change did not affect the left object alone: {original_slots} -> {left_slots}')
    analysis['results']['the first color change updated only the left object'] = 'PASS'
    set_color(session, right, 3)
    both_colors = save_snapshot(session, work, 'both-colors')
    analysis['split_selection'] = verify_split_selection(split, left_color, both_colors)
    analysis['results']['both objects can be selected individually and assigned distinct colors'] = 'PASS'
    observe_object_list(session, work, analysis)


if __name__ == '__main__':
    raise SystemExit(case_main(247, HERE / 'fixtures/feishu_std_cube.3mf', prepare_fixture, steps))
