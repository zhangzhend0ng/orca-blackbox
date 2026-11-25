#!/usr/bin/env python3
# m7x_238_export_disabled.py — Feishu #238: the slice export rows of File > Export are disabled until the plate is sliced
# feishu: baseline#238
"""Feishu #238【状态置灰】盘上有模型但未切片时，G-code 导出条目置灰 (P1).

Precondition (Feishu): 盘上有模型，但未执行切片.
Steps (Feishu): 1. 观察导出菜单中切片类条目的状态; 2. 执行切片后再次观察.
Expected (Feishu): 切片导出类条目置灰；切片完成后恢复可用.

The standard cube is loaded and saved as `before` (a project without a plate
G-code: nothing is sliced). File > Export is then opened and its rows are
read from the menus' handles; a desktop picture of the two menus on screen
is tried as evidence and kept apart from the reading. The plate is sliced
(the File > Export > Export G-code row is the completion signal, the memory
guard is answered on the way) and the menu is read a second time. The three
slice export rows must be disabled before slicing and enabled after it; two
rows that do not need a slice result must be enabled both times, which shows
the menu was readable and only the slice rows were disabled.
"""
from hashlib import sha256
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from export_io_oracle import export_rows_expectation_gaps, project_has_gcode, project_presets  # noqa: E402
from file_export_cases import export_menu_reading, slice_until_exportable  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402
from plate_reserve_oracle import read_project

FIXTURE = HERE / 'fixtures/feishu_std_cube.3mf'


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives evidence only.
    return model


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    with stage(analysis, 'open_unsliced_plate'):
        before = save_snapshot(session, work, 'before')
        _plates, instances = read_project(before)
        analysis['presets'] = project_presets(before)
        analysis['before_is_sliced'] = project_has_gcode(before)
        analysis['plate_objects'] = sorted(instance.name for instance in instances)
        if not instances or analysis['before_is_sliced']:
            raise ValueError(f'the plate must hold a model and no slice result: {analysis["plate_objects"]!r}, '
                             f'sliced={analysis["before_is_sliced"]}')
    with stage(analysis, 'observe_before_slice'):
        analysis['menu_before_slice'] = export_menu_reading(session, work, 'menu-before.png')
    with stage(analysis, 'slice'):
        slice_until_exportable(session, work, analysis, 'Export G-code')
        capture(session, work / 'sliced.png')
    with stage(analysis, 'observe_after_slice'):
        analysis['menu_after_slice'] = export_menu_reading(session, work, 'menu-after.png')
    gaps = analysis['expectation_gaps'] = export_rows_expectation_gaps(
        analysis['menu_before_slice']['export'], analysis['menu_after_slice']['export'])
    for clause, failed in gaps.items():
        analysis['results'][clause] = 'PASS' if not failed else f'FAIL ({"; ".join(failed)[:400]})'
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    analysis['editor_after_case'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    print(f'[m7x238] gaps {gaps!r}', flush=True)
    if not session.alive() or leftover:
        raise ValueError(f'editor left in an unexpected state: {analysis["editor_after_case"]!r}')


if __name__ == '__main__':
    raise SystemExit(case_main(238, FIXTURE, prepare_fixture, steps))
