#!/usr/bin/env python3
# m7x_250_negative_part.py — Feishu #250: add a negative part and measure actual slicing subtraction.
# feishu: baseline#250

import argparse
import json
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'tests'))
import m7_common as m7
from harness import export_util, topbar_util, winutil
from m3_common import add_common_args, boot_session
from m8_common import wait_arrival
from model_context_cases import open_model_menu
from negative_part_oracle import measure_difference, project_boxes

FIXTURE = HERE / 'fixtures' / 'agent_layer_cube.3mf'


def write_cutter(path):
    # Fixed object-space offset cuts through the front-right corner of the cube.
    vertices = ((18, -6, -16), (18, -18, -16), (6, -18, -16), (6, -6, -16),
                (18, -6, 16), (6, -6, 16), (6, -18, 16), (18, -18, 16))
    faces = ((0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 4, 7), (0, 7, 1),
             (1, 7, 6), (1, 6, 2), (2, 6, 5), (2, 5, 3), (4, 0, 3), (4, 3, 5))
    with path.open('wb') as stream:
        stream.write(struct.pack('<80sI', b'Feishu #250 box cutter', len(faces)))
        for a, b, c in faces:
            stream.write(struct.pack('<12fH', 0, 0, 0, *vertices[a], *vertices[b], *vertices[c], 0))


def send_menu_key(session, vk, *, log='[m7x250]'):
    fg = winutil.user32.GetForegroundWindow()
    if winutil._window_pid(fg) != session.pid:
        print(f'{log} refusing menu key {vk:#x}: foreground {fg:#x} owned elsewhere')
        return False
    m7.mdu._send_keys([(vk, False), (vk, True)])
    time.sleep(0.15)
    return True


def highlight_menu_item(session, menu, wanted, *, log='[m7x250]'):
    rows = topbar_util.menu_items(menu)
    if not any(i == wanted and flags & 0x80 for i, _, flags in rows):
        if not send_menu_key(session, 0x24, log=log):  # VK_HOME.
            return False
    for _ in range(len(rows) + 1):
        current = topbar_util.menu_items(menu)
        if any(i == wanted and flags & 0x80 for i, _, flags in current):
            print(f'{log} native highlighted row {wanted} in menu {menu:#x}')
            return True
        if not send_menu_key(session, 0x28, log=log):  # VK_DOWN.
            return False
    print(f'{log} target menu row {wanted} not highlighted: {topbar_util.menu_items(menu)!r}')
    return False


def open_part_submenu(session, *, menu_label='Add Negative Part', child_label='load', candidates=None, log='[m7x250]'):
    root = open_model_menu(session, menu_label, candidates=candidates)
    if root is None:
        return None
    root_hwnd, root_menu, parent_index = root
    _, submenu = topbar_util.item_info(root_menu, parent_index)
    if not submenu or not highlight_menu_item(session, root_menu, parent_index, log=log):
        return None
    if not send_menu_key(session, 0x27, log=log):  # VK_RIGHT.
        return None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        visible = [(row[4], topbar_util.menu_hmenu(row[4]))
                   for row in topbar_util._enum_menu_windows(session.pid)]
        child = next((hwnd for hwnd, hmenu in visible if hwnd != root_hwnd and hmenu == submenu), None)
        if child:
            rows = topbar_util.menu_items(submenu)
            print(f'{log} visible {menu_label} submenu hwnd={child:#x} hmenu={submenu:#x}: {rows!r}')
            matches = [i for i, label, flags in rows
                    if label.partition('\t')[0].rstrip('. …').strip().casefold() == child_label.casefold() and not flags & 3]
            return (child, submenu, matches[0]) if len(matches) == 1 else None
        time.sleep(0.2)
    print(f'{log} expected submenu HMENU {submenu:#x} not visible: {visible!r}')
    return None


def load_part_file(session, submenu, source, *, log='[m7x250]'):
    _, menu, index = submenu
    if not highlight_menu_item(session, menu, index, log=log) or not send_menu_key(session, 0x0D, log=log):
        return False
    dialog = m7.wait_dialog(session.pid, timeout_s=15)
    edit = export_util.find_edit(dialog[3]) if dialog else None
    if not edit or winutil._window_pid(edit) != session.pid:
        print(f'{log} Load chooser missing: {dialog!r}')
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(source))
    entered = winutil.edit_text(edit, size=260)
    print(f'{log} Load chooser={dialog[1]!r}, filename readback={entered!r}')
    if entered != str(source):
        return False
    winutil._send_msg(dialog[3], m7.WM_COMMAND_MSG, 1, 0)  # IDOK.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not winutil.user32.IsWindowVisible(dialog[3]):
            prompt = m7.wait_dialog(session.pid, timeout_s=1.0)
            if not prompt:
                time.sleep(1)
                return winutil.user32.IsWindowEnabled(session.hwnd)
            if prompt[1].strip().casefold() == 'add modifier':
                print(f'{log} closing expected tips dialog {prompt[1]!r}')
                m7.click_dialog_button(prompt[3], 'OK', fallback_first=False)
            elif 'load' not in prompt[1].casefold():
                print(f'{log} unexpected dialog after loading part: {prompt!r}')
                return False
        time.sleep(0.3)
    return False


def color_witness(before, after, centroid):
    x, y = centroid
    # Compare the corresponding scene crop. Ignore UI chrome and require a
    # connected region near the model, changed from the original background.
    p = before[y - 135:y + 135, x - 135:x + 135].astype(np.int16)
    q = after[y - 135:y + 135, x - 135:x + 135].astype(np.int16)
    if p.shape != q.shape or not p.size:
        return {'pass': False, 'reason': 'viewport geometry changed'}
    changed = np.max(np.abs(p - q), axis=2) >= 18
    body = (np.ptp(p, axis=2) >= 45) & (np.ptp(q, axis=2) >= 45) & ~changed
    body_y, body_x = np.where(body)
    if len(body_x) < 100:
        return {'pass': False, 'reason': 'original colored cube could not be matched'}
    luminance = q.mean(axis=2)
    contrasting = ((np.ptp(q, axis=2) <= 35) & changed & (np.ptp(p, axis=2) <= 35)
                   & (luminance >= 50) & (luminance <= 175))
    _, labels, stats, _ = cv2.connectedComponentsWithStats(contrasting.astype(np.uint8))
    right = int(body_x.max())
    body_top, body_bottom = int(body_y.min()), int(body_y.max())
    # The test prism protrudes past +X and is vertically adjacent to the body.
    # Exclude other changed UI pixels and the near-white selection handles.
    adjacent = [i for i, (left, top, width, height, _area) in enumerate(stats[1:], 1)
                if left <= right + 5 < left + width
                and min(top + height, body_bottom + 1) - max(top, body_top) >= 20]
    largest = max(adjacent, key=lambda i: stats[i, cv2.CC_STAT_AREA], default=0)
    pixels = int(stats[largest, cv2.CC_STAT_AREA]) if largest else 0
    body_bgr = np.median(q[body], axis=0).tolist()
    negative_bgr = np.median(q[labels == largest], axis=0).tolist() if largest else []
    return {'pass': pixels >= 100, 'negative_connected_pixels': pixels,
            'body_right_in_crop': right, 'negative_box_in_crop': stats[largest, :4].tolist() if largest else [],
            'body_bgr': body_bgr, 'negative_bgr': negative_bgr}


def load_fixture(args, work, profile_name, fixture):
    run_args = SimpleNamespace(exe=args.exe, datadir=work / profile_name)
    session = boot_session(run_args, model=fixture)
    m7.ensure_maximized(session)
    arrived, amount = wait_arrival(session, timeout_s=30)
    print(f'[m7x250] {profile_name} fixture arrived={arrived}, foreground fraction={amount:.3%}')
    return session, arrived


def slice_and_export(session, results, label, output):
    if not m7.op_slice(session, results, key=label, timeout_s=120):
        return False
    sent, _ = m7.file_menu_dispatch(session, 'Export G-code', via='Export')
    dialog = m7.wait_dialog(session.pid, timeout_s=12, title_substr='Save G-code file as') if sent else None
    edit = export_util.find_edit(dialog[3]) if dialog else None
    if not edit or winutil._window_pid(edit) != session.pid:
        print(f'[m7x250] Export G-code chooser unavailable: {dialog!r}')
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(output))
    entered = winutil.edit_text(edit, size=260)
    print(f'[m7x250] Export G-code chooser={dialog[1]!r}, filename={entered!r}')
    if entered != str(output):
        return False
    winutil._send_msg(dialog[3], m7.WM_COMMAND_MSG, 1, 0)  # IDOK.
    return (export_util.wait_file(output, timeout_s=40)
            and not winutil.user32.IsWindowVisible(dialog[3]))


def run_case(args, work):
    results = {}
    src = work / 'cutter.stl'
    write_cutter(src)
    baseline_project = work / 'baseline-fixture.3mf'
    test_project = work / 'test-fixture.3mf'
    shutil.copyfile(args.model, baseline_project)
    shutil.copyfile(args.model, test_project)
    body = project_boxes(test_project)['normal_part']
    baseline_gcode = work / 'baseline.gcode'
    negative_gcode = work / 'negative.gcode'

    session, arrived = load_fixture(args, work, 'negative-profile', test_project)
    try:
        center = m7.find_centroid(session) if arrived else None
        if not center:
            results['model A present'] = 'FAIL'
            return results
        before = m7.capture_bgr(session)
        cv2.imwrite(str(work / 'prepare-before.png'), before)
        submenu = open_part_submenu(session)
        results['Add negative part opens its second-level menu'] = 'PASS' if submenu else 'FAIL'
        if not submenu or not load_part_file(session, submenu, src):
            results['load a negative part on model A'] = 'FAIL'
            return results
        after = m7.capture_bgr(session)
        cv2.imwrite(str(work / 'prepare-negative.png'), after)
        color = color_witness(before, after, center)
        print(f'[m7x250] rendered negative against model A: {color!r}')
        results['negative part has a distinct canvas color'] = ('PASS' if color['pass'] else 'FAIL') + f' ({color})'

        snapshot = work / 'negative-project.3mf'
        if not m7.save_project_as(session, snapshot, timeout_s=40):
            results['negative part saved on the same object'] = 'FAIL (save evidence missing)'
            return results
        boxes = project_boxes(snapshot)
        attached = boxes.keys() == {'normal_part', 'negative_part'} and boxes['normal_part'] == body
        results['negative part saved on the same object'] = (
            ('PASS' if attached else 'FAIL') + f' ({boxes})')
        if not attached:
            return results
        if not slice_and_export(session, results, 'negative slice', negative_gcode):
            results['negative G-code'] = 'FAIL'
            return results
        results['negative G-code'] = 'PASS'
    finally:
        session.close()

    session, arrived = load_fixture(args, work, 'baseline-profile', baseline_project)
    try:
        if not arrived or not slice_and_export(session, results, 'baseline slice', baseline_gcode):
            results['baseline G-code'] = 'FAIL'
            return results
        results['baseline G-code'] = 'PASS'
    finally:
        session.close()

    analysis = measure_difference(baseline_gcode, negative_gcode, body, boxes['negative_part'])
    same_input = measure_difference(baseline_gcode, baseline_gcode, body, boxes['negative_part'])
    assert not same_input['pass'], 'oracle admitted unchanged G-code'
    analysis.update(color=color, unchanged_control_pass=same_input['pass'])
    (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    print(f'[m7x250] geometric difference: {json.dumps(analysis)}')
    results['slice locally subtracts only where cutter intersects'] = ('PASS' if analysis['pass'] else 'FAIL')
    return results


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=FIXTURE).parse_args()
    root = args.datadir.parent / 'feishu-object-cases' / '250'
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'[m7x250] retained work directory: {work}')
    try:
        return m7.m7_verdict(run_case(args, work))
    except (AssertionError, KeyError, ValueError) as exc:
        return m7.m7_verdict({'#250 semantic evidence': f'FAIL ({type(exc).__name__}: {exc})'})


if __name__ == '__main__':
    raise SystemExit(main())
