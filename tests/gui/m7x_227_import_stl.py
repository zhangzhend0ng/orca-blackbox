#!/usr/bin/env python3
# m7x_227_import_stl.py — Feishu #227: import a binary STL through File > Import, then select, move and turn it
# feishu: baseline#227
"""Feishu #227【单模型】通过「文件→导入」导入一个二进制 STL，模型正确显示在盘上 (P0).

Steps (Feishu): 1. 准备边长 20mm 立方体的二进制 STL 文件（cube_20mm.stl）;
2. 点击「文件→导入→导入 3MF/STL/STEP/SVG/OBJ/AMF…」; 3. 观察盘区与右侧对象列表.
Expected (Feishu): 1. 弹出文件选择对话框，格式筛选含 *.stl; 2. 模型出现在盘上，尺寸显示 20×20×20mm;
3. 对象列表新增 1 个对象，可选中/平移/旋转.

The project starts as an empty plate with a selected printer (the U1 template
minus its cube, the same start as #244). The one Import row that names STL
opens the native chooser: its title, visible texts, type filter entries and a
picture are kept, then the STL's path is given to it. The plate is saved and
read offline; the object is then clicked once and moved with the Right key
(+10 mm in world X), saving again, and finally turned 45° about the vertical
axis through the Rotate gizmo's Z field, saving once more.
tests/import_stl_oracle.py judges every saved file.
"""
from hashlib import sha256
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from file_export_cases import capture_window, combobox_items, descendants, row_label  # noqa: E402
from harness import export_util, topbar_util, winutil  # noqa: E402
from import_stl_oracle import (  # noqa: E402
    listed_object_names, stl_filter_label, verify_imported, verify_moved, verify_rotated)
from m8_common import wait_arrival  # noqa: E402
from m8x_48_modal_color_header import bring_main_to_mouse  # noqa: E402
from m7x_244_add_model import prepare_plate  # noqa: E402
from m7x_249_add_part import capture, focus_canvas, press, stage  # noqa: E402
from m7x_251_reload_from_disk import write_cube  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402

FIXTURE = HERE / 'fixtures' / 'agent_layer_cube.3mf'
IDOK = 1
RIGHT = 0x27


def prepare_fixture(model, work):
    # The repository template is loaded as it is; the run directory receives evidence only.
    return model


def sidebar(session):
    return m7.mdu.ocr_words_img(m7.capture_bgr(session)[:, :410], scale=2, psm=11)


def show_objects_tab(session):
    # The left panel keeps its last page; the Objects list is the page the expectation names.
    tab = next((word for word in sidebar(session) if word[0].casefold() == 'objects'), None)
    if tab:
        _text, x, y, width, height = tab[:5]
        winutil.msg_click_screen(*m7.client(session, x + width // 2, y + height // 2), session.hwnd)
        time.sleep(1)


def import_rows(session):
    """Every row of the live File > Import submenu with its enabled state; the menus are closed afterwards."""
    menu = topbar_util.open_file_menu(session)
    if not menu:
        raise ValueError('topbar File menu did not open')
    _rect, _hwnd, hmenu = menu
    index = topbar_util.find_item(hmenu, 'Import')
    rows = []
    if index is not None:
        rows = [{'label': text, 'enabled': not flags & 3}
                for _i, text, flags in topbar_util.menu_items(topbar_util.item_info(hmenu, index)[1])]
    topbar_util.close_menu_windows(session.pid)
    return rows


def import_stl(session, source, work, analysis):
    """File > Import > the one row that names STL: keep what the chooser showed, then hand it `source`."""
    rows = import_rows(session)
    names = [row_label(row['label']).casefold() for row in rows]
    hits = [i for i, name in enumerate(names) if 'stl' in name]
    if len(hits) != 1 or not rows[hits[0]]['enabled']:
        raise ValueError(f'File > Import does not offer exactly one enabled STL row: {rows!r}')
    row = rows[hits[0]]
    dispatched, dialog = m7.file_menu_dispatch(session, row['label'], expect_dialog=True, via='Import', timeout_s=10)
    if not dispatched or not dialog:
        raise ValueError(f'File > Import > {row["label"]!r} opened no chooser (dispatched={dispatched!r}, dialog={dialog!r})')
    _cls, title, _rect, hwnd = dialog
    children = descendants(hwnd)
    edit = export_util.find_edit(hwnd)
    if edit is None or winutil._window_pid(edit) != session.pid:
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)
        raise ValueError(f'{title!r} has no owned file name box')
    entry = analysis['chooser'] = {
        'import_rows': rows, 'row': row['label'], 'title': title,
        'labels': [text for _cls, text, child in children if text and winutil.user32.IsWindowVisible(child)],
        'types': [combobox_items(child) for cls, _text, child in children if cls == 'ComboBox'],
        'image': capture_window(hwnd, work / 'chooser.png'),
    }
    filters = [item for box in entry['types'] for item in box['items']]
    entry['stl_filter'] = stl_filter_label([title, *entry['labels'], *filters])
    print(f'[m7x227] chooser {title!r}: labels {entry["labels"]!r}, types {filters!r}', flush=True)
    winutil.select_all(edit)
    winutil.msg_text(edit, str(source))
    entry['entered'] = winutil.edit_text(edit, size=1024)
    if entry['entered'] != str(source):
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)
        raise ValueError(f'the chooser did not keep the path {source!r}: {entry["entered"]!r}')
    winutil._send_msg(hwnd, 0x0111, IDOK, 0)
    deadline = time.monotonic() + 15
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    entry['dialog_closed'] = not winutil.user32.IsWindowVisible(hwnd)
    if not entry['dialog_closed']:
        raise ValueError(f'{title!r} stayed open after the STL was given to it')
    return entry


def click_object_then_key(session, work, phase, key, analysis):
    """Click the object under its rendered centroid, press `key`, and keep a picture before and after."""
    center = m7.find_centroid(session)
    if center is None:
        raise ValueError('no object is visible on the plate')
    if not bring_main_to_mouse(session.hwnd):
        raise ValueError('Orca did not acquire the guest foreground')
    point = m7.client(session, *center)
    canvas = winutil.deepest_child_at(session.hwnd, *point)
    if (winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid
            or not winutil.user32.IsWindowEnabled(canvas)):
        raise ValueError(f'click point {point} did not resolve to the Prepare canvas')
    focus_canvas(session, canvas)
    capture(session, work / f'{phase}-before.png')
    winutil.user32.SetCursorPos(*point)
    time.sleep(0.4)
    if winutil.window_from_screen_point(*point) == canvas:
        if winutil.real_click_screen(*point) != 2:
            raise ValueError('the physical click on the object was not fully delivered')
        method = 'physical'
    else:
        # The guest can park a transparent host above the canvas; the click then goes to the verified canvas.
        if winutil.msg_click_screen(*point, session.hwnd) != canvas:
            raise ValueError('the click was not dispatched to the verified Prepare canvas')
        method = 'window message'
    time.sleep(0.8)
    capture(session, work / f'{phase}-selected.png')
    press(key)
    time.sleep(1.2)
    capture(session, work / f'{phase}.png')
    record = {'centroid': list(center), 'click': list(point), 'click_method': method, 'key': f'0x{key:02x}'}
    analysis.setdefault('keyboard', {})[phase] = record
    print(f'[m7x227] {phase}: {record}', flush=True)
    return record


def turn_with_gizmo(session, work, analysis):
    """Open the Rotate gizmo on the selected object and type 45 into its rightmost (Z) field.

    On tag sm-v2.4.0 the PageUp key only opens this gizmo (GLCanvas3D.cpp,
    `do_rotate(L("Tool Rotate"))`); it does not turn the object by itself,
    which a first run showed: the saved project was unchanged. The gizmo is
    opened with the Rotate tool's shortcut, R, on the selected object. Its
    window is drawn inside the canvas, so the numeric fields are found by OCR
    on the row labelled Rotate (X, Y, Z from left to right); m7e_rotate45
    types into the same fields. The saved project, not the read-back, is the judge."""
    centre = m7.find_centroid(session)
    if centre is None:
        raise ValueError('no object is visible on the plate for the Rotate gizmo')
    if not bring_main_to_mouse(session.hwnd):
        raise ValueError('Orca did not acquire the guest foreground')
    canvas = winutil.deepest_child_at(session.hwnd, *m7.client(session, *centre))
    if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
        raise ValueError('the plate did not resolve to the Prepare canvas')
    focus_canvas(session, canvas)
    capture(session, work / 'rotated-before.png')
    press(ord('R'))  # the Rotate tool's shortcut; a second guest run showed the toolbar tooltips unreadable
    time.sleep(1.5)
    capture(session, work / 'rotated-gizmo.png')
    boxes = m7.gizmo_row_boxes(session, 'rotate') or m7.gizmo_row_boxes(session, 'rotation')
    record = analysis.setdefault('gizmo', {})['rotate'] = {
        'fields': [[round(x), round(y), text] for x, y, text in boxes]}
    print(f'[m7x227] rotate gizmo fields: {record["fields"]!r}', flush=True)
    if not boxes:
        raise ValueError('the Rotate gizmo showed no numeric field')
    if len(boxes) < 3:
        raise ValueError(f'the Rotate gizmo shows {len(boxes)} numeric field(s), expected X, Y and Z')
    m7.type_into_field(session, boxes[-1][:2], '45', old_len=len(boxes[-1][2]))
    time.sleep(1.0)
    record['fields_after'] = [[round(x), round(y), text] for x, y, text in
                              (m7.gizmo_row_boxes(session, 'rotate') or m7.gizmo_row_boxes(session, 'rotation'))]
    capture(session, work / 'rotated.png')


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    analysis['sidebar'] = {}
    source = work / 'cube_20mm.stl'
    with stage(analysis, 'write_stl'):
        write_cube(source, 20)
        analysis['source'] = {'name': source.name, 'bytes': source.stat().st_size,
                              'sha256': sha256(source.read_bytes()).hexdigest()}
    with stage(analysis, 'empty_plate'):
        center = m7.find_centroid(session)
        if center is None:
            raise ValueError('the U1 template did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
    with stage(analysis, 'import_chooser'):
        entry = import_stl(session, source, work, analysis)
    with stage(analysis, 'observe_import'):
        arrived, fraction = wait_arrival(session, timeout_s=30, min_frac=0.001)
        analysis['import_fraction'] = fraction
        show_objects_tab(session)
        analysis['sidebar']['imported'] = [word[0] for word in sidebar(session)]
        print(f'[m7x227] sidebar after the import: {analysis["sidebar"]["imported"]!r}', flush=True)
    with stage(analysis, 'save_imported'):
        imported = save_snapshot(session, work, 'imported')
        analysis['imported'] = verify_imported(imported, source)
        print(f'[m7x227] imported: {analysis["imported"]!r}', flush=True)
    with stage(analysis, 'select_and_move'):
        click_object_then_key(session, work, 'moved', RIGHT, analysis)
        moved = save_snapshot(session, work, 'moved')
        analysis['moved'] = verify_moved(imported, moved)
    with stage(analysis, 'select_and_rotate'):
        turn_with_gizmo(session, work, analysis)
        rotated = save_snapshot(session, work, 'rotated')
        analysis['rotated'] = verify_rotated(moved, rotated)
    with stage(analysis, 'read_results'):
        analysis['object_list_name'] = listed_object_names(sidebar(session), [source.stem])
        leftovers = m7.wait_dialog(session.pid, timeout_s=0.5)
        analysis['editor_at_end'] = {'alive': session.alive(), 'dialog': leftovers[1] if leftovers else None}
        if not session.alive() or leftovers:
            raise ValueError(f'editor left in an unexpected state: {analysis["editor_at_end"]!r}')
        checks = {
            '弹出文件选择对话框，格式筛选含 *.stl': entry['stl_filter'] is not None,
            '模型出现在盘上，尺寸显示 20×20×20mm': arrived,
            '对象列表新增 1 个对象': len(analysis['imported']['object_names']) == 1,
            '可选中/平移': True,
            '可旋转': True,
        }
        for clause, passed in checks.items():
            analysis['results'][clause] = 'PASS' if passed else 'FAIL'


if __name__ == '__main__':
    raise SystemExit(case_main(227, FIXTURE, prepare_fixture, steps))
