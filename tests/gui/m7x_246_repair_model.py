#!/usr/bin/env python3
# feishu: baseline#246
# m7x_246_repair_model.py — Feishu #246: import a cube with a hole, look for Fix model in its context menu, then slice.
"""Import cube_holed.stl (eleven triangles around a triangular hole) through File > Import into the empty U1
template plate, open the object's context menu and read every row, run Fix model when that row is enabled,
keep whatever the product shows, save the result and slice it. The expectation passes when the hole is
closed with the cube intact and the model slices, or when the product clearly says it cannot be repaired.

Menu facts at sm-v2.4.0: `Fix model` is appended to the object menu right after Clone
(GUI_Factories.cpp:882-892, 1358-1360) only when is_windows10() holds (FixModelByWin10.cpp:195-207);
it is enabled only while the selected object reports errors repaired at load time
(Plater.cpp:16783-16805), and the repair itself skips objects without such errors
(GUI_ObjectList.cpp:5549-5558)."""
from pathlib import Path
import sys
import time

import cv2

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

import m7_common as m7
from harness import topbar_util, winutil
from m7x_244_add_model import prepare_plate
from m7x_249_add_part import capture, stage
from m8_common import wait_arrival
from plate_reserve_case import activate, case_main
from repair_model_cases import grab_menu, open_object_menu, os_caption, slice_until_exportable, watch_prompts
from repair_model_oracle import (EXPECTED, fix_row, initial_state, judge, menu_rows, missing_row_verdict,
                                 repair_reading, write_holed_cube)
from zip_import_cases import choose_project
from zip_import_oracle import digest

LOG = '[m7x246]'


def prepare_fixture(template, _work):
    return template


def steps(session, work, analysis, _args):
    analysis.setdefault('timings', {})
    source, before, after = work / 'cube_holed.stl', work / 'before.3mf', work / 'repaired.3mf'
    with stage(analysis, 'prepare_empty_plate'):
        center = m7.find_centroid(session)
        if not center:
            raise ValueError('initial printer fixture did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
    with stage(analysis, 'import_holed_cube'):
        analysis['source'] = digest(write_holed_cube(source))
        chooser = choose_project(session, source, work, analysis)
        arrived, fraction = wait_arrival(session, timeout_s=30, min_frac=0.001)
        analysis['import_fraction'] = fraction
        if not arrived or winutil.user32.IsWindowVisible(chooser):
            raise ValueError('chooser did not close or the cube did not appear')
        time.sleep(2.0)
    with stage(analysis, 'save_before'):
        capture(session, work / 'before.png')
        if not m7.save_project_as(session, before, timeout_s=40):
            raise ValueError('could not save before.3mf')
        analysis['initial'] = initial_state(before, source)
        analysis['before_file'] = digest(before)
        print(f'{LOG} imported mesh: {analysis["initial"]}', flush=True)
    with stage(analysis, 'context_menu'):
        popup = open_object_menu(session, [m7.find_centroid(session)])
        if not popup:
            raise ValueError('no context menu opened on the imported model')
        menu_hwnd, hmenu = popup
        rows = topbar_util.menu_items(hmenu)
        analysis['context_menu'] = menu_rows(rows)
        print(f'{LOG} context menu: {[(r["index"], r["label"], r["enabled"]) for r in analysis["context_menu"]]}',
              flush=True)
        grab_menu(menu_hwnd, work / 'context-menu.png')
        row = fix_row(rows)
        analysis['fix_row'] = row
        prompts = []
        if row is None:
            # No row on this system: nothing was clicked, so a slice would say
            # nothing about this expectation. Keep the evidence and stop here.
            topbar_util.close_menu_windows(session.pid)
            analysis['os_caption'] = os_caption()
            analysis['results'][EXPECTED] = missing_row_verdict(
                len(rows), analysis['initial'], analysis['os_caption']['product_name'])
            print(f'{LOG} {analysis["results"][EXPECTED]}', flush=True)
            return
        if row['enabled']:
            with stage(analysis, 'fix_model'):
                activate(session, (menu_hwnd, hmenu, row['index']), LOG)
                time.sleep(1.5)
                prompts = watch_prompts(session, work, analysis)
        else:
            topbar_util.close_menu_windows(session.pid)
        capture(session, work / 'repaired.png')
    with stage(analysis, 'save_repaired'):
        if not m7.save_project_as(session, after, timeout_s=40):
            raise ValueError('could not save repaired.3mf')
        analysis['repair'] = repair_reading(after, source)
        analysis['after_file'] = digest(after)
        print(f'{LOG} saved mesh after the menu action: {analysis["repair"]}', flush=True)
    with stage(analysis, 'slice'):
        analysis['os_caption'] = os_caption()
        try:
            sliced = slice_until_exportable(session, work, analysis)
        except (OSError, RuntimeError, ValueError, cv2.error) as exc:
            # A slice that could not even be started leaves the conclusion to the judge.
            analysis['slice_error'] = f'{type(exc).__name__}: {exc}'
            sliced = False
    with stage(analysis, 'judge'):
        analysis['results'][EXPECTED] = judge(analysis['fix_row'], analysis['repair'], sliced, prompts)


def main():
    return case_main(246, HERE / 'fixtures/agent_layer_cube.3mf', prepare_fixture, steps)


if __name__ == '__main__':
    raise SystemExit(main())
