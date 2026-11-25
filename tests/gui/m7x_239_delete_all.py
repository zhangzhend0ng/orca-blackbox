#!/usr/bin/env python3
# m7x_239_delete_all.py — Feishu #239: clear the plate from its context menu and undo.
# feishu: baseline#239
import argparse
import json
import math
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]
import m7_common as m7
from harness import winutil
from delete_object_oracle import create_fixture, objects
from m3_common import add_common_args, boot_session
from m7x_248_delete_object import sidebar, snapshot
from m7x_249_add_part import capture, focus_canvas
from m7x_250_negative_part import highlight_menu_item, send_menu_key
from m8_common import wait_arrival
from model_context_cases import open_model_menu


def patch_pixels(image, points):
    return [int(np.count_nonzero(np.ptp(image[y-12:y+12, x-12:x+12], axis=2) > 45)) for x,y in points]


def run(args, work, analysis):
    fixture = work / 'Alpha-Bravo.3mf'
    create_fixture(args.model, fixture)
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / 'profile'), model=fixture)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError('two-object fixture did not appear')
        tab = next((w for w in sidebar(session) if w[0].casefold() == 'objects'), None)
        if tab:
            _, x, y, w, h = tab
            winutil.msg_click_screen(*m7.client(session, x+w//2, y+h//2), session.hwnd)
            time.sleep(1)
        snapshot(session, work, 'before', analysis)
        initial = objects(work / 'before.3mf')
        if set(initial) != {'Alpha','Bravo'} or initial != objects(fixture):
            raise ValueError('initial plate does not match two-object fixture')
        points = m7.model_candidates(session)
        centers = [min(points, key=lambda p: math.dist(p, expected)) for expected in [(1058,521),(1284,528)]]
        if math.dist(*centers) < 80:
            raise ValueError('could not distinguish two separate printed objects')
        analysis['centers'] = centers
        before = patch_pixels(m7.capture_bgr(session), centers)
        blank = tuple((a+b)//2 for a,b in zip(*centers))
        menu = open_model_menu(session, 'Delete All', candidates=[blank])
        if not menu:
            raise ValueError('blank plate right click did not open Delete All')
        _, handle, i = menu
        if not highlight_menu_item(session, handle, i, log='[m7x239]') or not send_menu_key(session, 13, log='[m7x239]'):
            raise ValueError('could not activate Delete All')
        time.sleep(1)
        if not session.alive() or m7.wait_dialog(session.pid, timeout_s=0.5):
            raise ValueError('dialog or app exit after Delete All')
        after = patch_pixels(capture(session, work/'empty.png'), centers)
        analysis['sidebar']['empty'] = [w[0].strip('.,:;_-|[]()').casefold() for w in sidebar(session)]
        fraction = m7.model_colored_frac(session)
        analysis.update(before_pixels=before, empty_pixels=after, empty_fraction=fraction)
        if min(before)<200 or max(after)>30 or fraction >= m7.EMPTY_BED_FLOOR:
            raise ValueError(f'objects did not clear the plate: {analysis}')
        canvas = winutil.deepest_child_at(session.hwnd, *m7.client(session,*blank))
        if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
            raise ValueError('owned canvas unavailable for Ctrl+Z')
        focus_canvas(session,canvas)
        m7.mdu._send_keys([(0x11,False),(ord('Z'),False),(ord('Z'),True),(0x11,True)])
        time.sleep(1)
        snapshot(session,work,'restored',analysis)
        restored = patch_pixels(m7.capture_bgr(session),centers)
        analysis['restored_pixels'] = restored
        if objects(work/'restored.3mf') != initial or min(restored)<200:
            raise ValueError('Ctrl+Z did not restore both original meshes and positions')
        for phase, expected in [('before',{'alpha','bravo'}), ('empty',set()), ('restored',{'alpha','bravo'})]:
            if set(analysis['sidebar'][phase]) & {'alpha','bravo'} != expected:
                raise ValueError(f'object list disagrees during {phase}: {analysis["sidebar"][phase]}')
        analysis['results']['Delete All clears both objects from canvas and list; Ctrl+Z restores both meshes'] = 'PASS'
    finally:
        session.close()


def main():
    args=add_common_args(argparse.ArgumentParser(), default_model=HERE/'fixtures/feishu_std_cubesfar.3mf').parse_args()
    root=args.datadir.resolve().parent/'feishu-object-cases'/'239'
    root.mkdir(exist_ok=True,parents=True)
    work=Path(tempfile.mkdtemp(prefix='run-',dir=root))
    print(f'[m7x239] retained work directory: {work}',flush=True)
    analysis={'case':239,'sidebar':{},'results':{}}
    try:
        run(args,work,analysis)
    except Exception as exc:
        analysis['results']['#239 plate evidence']=f'FAIL ({exc})'
        traceback.print_exc()
    finally:
        (work/'analysis.json').write_text(json.dumps(analysis,indent=2),encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
