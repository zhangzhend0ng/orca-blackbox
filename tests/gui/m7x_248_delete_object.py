#!/usr/bin/env python3
# m7x_248_delete_object.py — Feishu #248: delete only Alpha and restore it with Ctrl+Z.
# feishu: baseline#248
"""Delete only the selected object and restore its geometry with Ctrl+Z."""
import argparse
import json
import math
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]
import m7_common as m7
from harness import winutil
from delete_object_oracle import create_fixture, objects, verify_sequence
from m3_common import add_common_args, boot_session
from m7x_249_add_part import capture, focus_canvas
from m7x_250_negative_part import highlight_menu_item, send_menu_key
from m8_common import wait_arrival
from model_context_cases import open_model_menu
from m8x_48_modal_color_header import bring_main_to_mouse


def sidebar(session):
    image = m7.capture_bgr(session)
    return m7.mdu.ocr_words_img(image[:, :410], scale=2, psm=11)


def snapshot(session, work, phase, analysis):
    if not session.alive() or m7.wait_dialog(session.pid, timeout_s=0.5):
        raise ValueError(f'unexpected dialog or closed editor during {phase}')
    capture(session, work / (phase + '.png'))
    words = sidebar(session)
    names = [word[0].strip('.,:;_-|[]()').casefold() for word in words]
    analysis['sidebar'][phase] = names
    print(f'[m7x248] {phase} sidebar: {names}', flush=True)
    if not m7.save_project_as(session, work / (phase + '.3mf'), timeout_s=40):
        raise ValueError(f'failed to retain {phase} project')
    print(f'[m7x248] {phase} saved objects: {list(objects(work / (phase + ".3mf")))}', flush=True)


def run(args, work, analysis):
    fixture = work / 'Alpha-Bravo.3mf'
    create_fixture(args.model, fixture)
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=fixture)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('two-object fixture did not appear')
        tab = next((word for word in sidebar(session) if word[0].casefold() == 'objects'), None)
        if tab:
            _, x, y, w, h = tab
            winutil.msg_click_screen(*m7.client(session, x+w//2, y+h//2), session.hwnd)
            time.sleep(1)
        snapshot(session, work, 'before', analysis)
        if objects(fixture) != objects(work / 'before.3mf'):
            raise ValueError('loaded objects differ from the prepared fixture')
        points = m7.model_candidates(session)
        # Alpha occupies the left of the two fixed plate sites.
        point = min(points, key=lambda p: math.dist(p, (1055, 520)))
        print(f'[m7x248] candidates={points}, Alpha hit={point}', flush=True)
        menu = open_model_menu(session, 'Delete', candidates=[point])
        if not menu:
            raise ValueError('selected model menu did not show Delete')
        _, handle, i = menu
        if not highlight_menu_item(session, handle, i, log='[m7x248]') or not send_menu_key(session, 13, log='[m7x248]'):
            raise ValueError('could not activate Delete')
        time.sleep(1)
        snapshot(session, work, 'deleted', analysis)
        if set(objects(work / 'deleted.3mf')) != {'Bravo'}:
            raise ValueError('Delete did not leave only Bravo')
        if not bring_main_to_mouse(session.hwnd):
            raise ValueError('editor did not own foreground for Ctrl+Z')
        canvas = winutil.deepest_child_at(session.hwnd, *m7.client(session, *point))
        if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
            raise ValueError('could not identify owned canvas for Ctrl+Z')
        focus_canvas(session, canvas)
        m7.mdu._send_keys([(0x11, False), (ord('Z'), False), (ord('Z'), True), (0x11, True)])
        time.sleep(1.0)
        snapshot(session, work, 'restored', analysis)
        analysis['world_bounds_mm'] = verify_sequence(*(work / (phase+'.3mf') for phase in ('before','deleted','restored')))
        analysis['results']['only Alpha removed; exact Bravo and restored world triangles'] = 'PASS'
        for phase, expected in [('before', {'alpha','bravo'}), ('deleted', {'bravo'}), ('restored', {'alpha','bravo'})]:
            observed = {'alpha','bravo'} & set(analysis['sidebar'][phase])
            if observed != expected:
                raise ValueError(f'{phase}: visible object list {observed}, expected {expected}')
        analysis['results']['visible object list agrees before/after Delete and Ctrl+Z'] = 'PASS'
    finally:
        session.close()


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=HERE / 'fixtures/feishu_std_cubesfar.3mf').parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '248'
    root.mkdir(exist_ok=True, parents=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'[m7x248] retained work directory: {work}', flush=True)
    analysis = {'case': 248, 'sidebar': {}, 'results': {}}
    try:
        run(args, work, analysis)
    except Exception as exc:
        analysis['results']['#248 deletion and undo evidence'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
