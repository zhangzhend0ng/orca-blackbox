#!/usr/bin/env python3
# m7x_243_add_primitive.py — Feishu #243: add an editable on-bed cube from Add Primitive.
# feishu: baseline#243
import argparse
import itertools
import json
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
from delete_object_oracle import objects
from m3_common import add_common_args, boot_session
from m7x_244_add_model import prepare_plate
from m7x_249_add_part import capture, focus_canvas
from m7x_250_negative_part import open_part_submenu, highlight_menu_item, send_menu_key
from m8_common import wait_arrival
from m8x_48_modal_color_header import bring_main_to_mouse


def cube_faces(path):
    group = objects(path)
    if len(group) != 1:
        raise ValueError(f'expected exactly one added primitive, got {list(group)}')
    faces, = group.values()
    verts = {v for f in faces for v in f}
    axes = [sorted({v[i] for v in verts}) for i in range(3)]
    if (len(faces) != 12 or any(len(axis) != 2 for axis in axes)
            or set(itertools.product(*axes)) != verts or abs(axes[2][0]) > 0.0001):
        raise ValueError(f'not an eight-corner cube resting on the plate: {axes}')
    sizes = [hi-lo for lo,hi in axes]
    if max(sizes)-min(sizes)>0.0001 or min(sizes)<0.1:
        raise ValueError(f'expected positive equal side lengths: {sizes}')
    for axis in range(3):
        for limit in axes[axis]:
            if sum(all(v[axis] == limit for v in face) for face in faces) != 2:
                raise ValueError('missing a pair of triangles on one face of the cube')
    return faces, axes


def run(args, work, analysis):
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work/'profile'), model=args.model)
    try:
        m7.ensure_maximized(session)
        ok, _ = wait_arrival(session, timeout_s=30)
        point = m7.find_centroid(session) if ok else None
        if not point:
            raise ValueError('printer fixture not visible')
        analysis['bed_point'] = point
        prepare_plate(session, work, analysis)
        capture(session, work/'empty.png')
        choice = open_part_submenu(session, menu_label='Add Primitive', child_label='Cube',
                                   candidates=[point], log='[m7x243]')
        if not choice:
            raise ValueError('empty plate did not open the Add Primitive submenu with Cube')
        _, handle, index = choice
        if not highlight_menu_item(session, handle, index, log='[m7x243]') or not send_menu_key(session,13,log='[m7x243]'):
            raise ValueError('could not select Cube')
        if not wait_arrival(session, timeout_s=30,min_frac=0.001)[0]:
            raise ValueError('added primitive did not render')
        capture(session,work/'cube.png')
        if not m7.save_project_as(session,work/'cube.3mf',timeout_s=40):
            raise ValueError('could not save added primitive')
        faces, analysis['before_bounds_mm'] = cube_faces(work/'cube.3mf')
        if not bring_main_to_mouse(session.hwnd):
            raise ValueError('could not focus editor for edit')
        point = m7.find_centroid(session)
        canvas = winutil.deepest_child_at(session.hwnd,*m7.client(session,*point)) if point else None
        if not canvas or winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
            raise ValueError('no owned canvas for cube editing')
        focus_canvas(session,canvas)
        m7.mdu._send_keys([(0x11,False),(ord('A'),False),(ord('A'),True),(0x11,True)])
        time.sleep(.5)
        m7.mdu._send_keys([(0x27,False),(0x27,True)])
        time.sleep(1)
        capture(session,work/'edited.png')
        if not m7.save_project_as(session,work/'edited.3mf',timeout_s=40):
            raise ValueError('could not save edited primitive')
        edited, analysis['after_bounds_mm'] = cube_faces(work/'edited.3mf')
        expected = tuple(tuple((round(x+10,5),y,z) for x,y,z in f) for f in faces)
        if expected != edited:
            raise ValueError('saved cube does not show the intended +10 mm X edit')
        analysis['results']['Cube from native Add Primitive submenu rests on plate and accepts X edit'] = 'PASS'
    finally:
        session.close()


def main():
    args=add_common_args(argparse.ArgumentParser(),default_model=HERE/'fixtures/agent_layer_cube.3mf').parse_args()
    root=args.datadir.resolve().parent/'feishu-object-cases'/'243'
    root.mkdir(exist_ok=True,parents=True)
    work=Path(tempfile.mkdtemp(prefix='run-',dir=root))
    print(f'[m7x243] retained work directory: {work}',flush=True)
    analysis={'case':243,'results':{}}
    try:
        run(args,work,analysis)
    except Exception as exc:
        analysis['results']['#243 primitive evidence']=f'FAIL ({exc})'
        traceback.print_exc()
    finally:
        (work/'analysis.json').write_text(json.dumps(analysis,indent=2),encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
