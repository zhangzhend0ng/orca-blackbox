#!/usr/bin/env python3
# m7x_235_export_all_plates.py — Feishu #235: slice both plates of a two-plate project and export every plate through File > Export
# feishu: baseline#235
"""Feishu #235【多盘导出】多盘均已切片时，一次性导出所有盘切片文件 (P1).

Precondition (Feishu): 工程含 2 个盘且均已切片.
Steps (Feishu): 1. 点击「文件→导出→导出所有盘切片文件…」; 2. 导出并核对产物数量.
Expected (Feishu): 每个盘各生成对应切片文件（共 2 个），均含有效 G-code.

The two-plate project of #242 (a cube on plate Keep, a box on plate Remove,
built from the standard cubes-far fixture) is loaded and saved as `before`.
Slice all is chosen in the slice dropdown and pressed once; the application
slices the plates one after another, and the enabled state of File > Export >
Export all plate sliced file (gated on every plate having a result) is the
completion signal, with the runtime memory guard answered on the way. The
save dialog is then navigated to the run directory and given the bare name
`plates`. Whatever lands besides this case's own evidence counts as a
product: the files are listed, and for each plate the landed file that holds
its G-code is read offline. "共 2 个" is judged as written, one sliced file
per plate, so an archive that carries both plates in one file fails that
clause with its contents written out.
"""
from hashlib import sha256
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from export_io_oracle import all_plates_expectation_gaps, project_presets  # noqa: E402
from file_export_cases import click_slice_all, export_via_file_menu, read_export_menu, slice_until_exportable, topbar_labels  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402
from plate_reserve_oracle import create_delete_plate_fixture, read_project

ITEM = 'Export all plate sliced file'
TITLE = 'Save Sliced file as'
NAME = 'plates'


def prepare_fixture(model, work):
    # Plate Keep holds the left cube (Alpha), plate Remove the scaled right one (Bravo).
    fixture = work / 'two-plates.3mf'
    create_delete_plate_fixture(model, fixture)
    return fixture


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    with stage(analysis, 'open_plates'):
        before = save_snapshot(session, work, 'before')
        plates, instances = read_project(before)
        analysis['plates'] = {'names': list(plates),
                              'objects': {plate: sorted(i.name for i in instances if i.plate == plate)
                                          for plate in plates}}
        analysis['presets'] = project_presets(before)
        analysis['export_menu_before_slice'] = read_export_menu(session)['export']
        analysis['topbar_before_slice'] = topbar_labels(session)
    with stage(analysis, 'slice_all'):
        slice_until_exportable(session, work, analysis, ITEM, click=click_slice_all)
        analysis['topbar_after_slice'] = topbar_labels(session)
        capture(session, work / 'sliced.png')
    present = {path.name for path in work.iterdir()}
    with stage(analysis, 'export_all_plates'):
        export_via_file_menu(session, ITEM, work, NAME, work, analysis, TITLE, 'archive')
    products = sorted(path for path in work.iterdir()
                      if path.is_file() and path.name not in present and path.name != 'export-dialog.png'
                      and not path.name.startswith('memory-guard-'))
    analysis['products'] = [{'name': path.name, 'bytes': path.stat().st_size,
                             'sha256': sha256(path.read_bytes()).hexdigest()} for path in products]
    with stage(analysis, 'read_products'):
        gaps, readings = all_plates_expectation_gaps(before, products)
    analysis['all_plates'] = readings
    analysis['expectation_gaps'] = gaps
    for clause, failed in gaps.items():
        analysis['results'][clause] = 'PASS' if not failed else f'FAIL ({"; ".join(failed)[:400]})'
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    analysis['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    print(f'[m7x235] products {[path.name for path in products]}, gaps {gaps!r}', flush=True)
    if not session.alive() or leftover:
        raise ValueError(f'editor left in an unexpected state after the export: {analysis["editor_after_export"]!r}')


if __name__ == '__main__':
    raise SystemExit(case_main(235, HERE / 'fixtures/feishu_std_cubesfar.3mf', prepare_fixture, steps))
