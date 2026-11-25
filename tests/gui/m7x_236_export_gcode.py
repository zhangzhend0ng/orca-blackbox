#!/usr/bin/env python3
# m7x_236_export_gcode.py — Feishu #236: export the sliced plate as a plain .gcode file through File > Export
# feishu: baseline#236
"""Feishu #236【纯 G-code】切片后导出纯 .gcode 文件，可打印 (P0).

Steps (Feishu): 1. 点击「文件→导出→导出 G-code…」; 2. 导出并检查扩展名、文件头/尾内容.
Expected (Feishu): 生成 .gcode 文件，含起始/结束 G-code，无空文件，层命令连续.

The standard cube (U1 0.4 mm, PLA, 0.20 mm Standard) is sliced, the File >
Export > Export G-code row is waited for as the completion signal (answering
the runtime memory guard when the guest is low on memory), and the save dialog
is navigated to the run directory and given the bare name `plate`: the
application decides the extension. The file that lands is read offline by
tests/export_io_oracle.py; each clause of the expectation reports its own gaps.
Its extruding moves are also measured against the cube as it stood in the
saved `before` project (gcode_footprint): model material may leave an object's
box by at most 1.0 mm, so a file shifted off the plate fails the first clause.
"""
from hashlib import sha256
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from export_io_oracle import gcode_expectation_gaps, gcode_export_facts, gcode_footprint, project_presets  # noqa: E402
from file_export_cases import export_via_file_menu, read_export_menu, slice_until_exportable  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402

FIXTURE = HERE / 'fixtures/feishu_std_cube.3mf'


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives evidence only.
    return model


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    with stage(analysis, 'open_plate'):
        before = save_snapshot(session, work, 'before')
        analysis['initial_printer'] = project_presets(before)
        analysis['export_menu_before_slice'] = read_export_menu(session)['export']
    with stage(analysis, 'slice'):
        slice_until_exportable(session, work, analysis, 'Export G-code')
        capture(session, work / 'sliced.png')
    with stage(analysis, 'export_gcode'):
        receipt = export_via_file_menu(session, 'Export G-code', work, 'plate', work, analysis,
                                       title_substr='Save G-code file as', kind='gcode')
    with stage(analysis, 'read_gcode'):
        target = work / receipt['saved_name']
        facts = gcode_export_facts(target)
        analysis['gcode'] = facts
        # The material must lie where the plate's objects were: a file that prints somewhere
        # else is not this plate's G-code, whatever else it contains.
        try:
            footprint = gcode_footprint(target, before)
        except ValueError as exc:
            footprint = {'error': str(exc), 'checks': {'footprint_unreadable': False}}
        analysis['footprint'] = footprint
        gaps = analysis['expectation_gaps'] = gcode_expectation_gaps(facts, receipt['saved_extension'], footprint)
    for clause, failed in gaps.items():
        analysis['results'][clause] = 'PASS' if not failed else f'FAIL ({", ".join(failed)})'
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    analysis['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    print(f'[m7x236] {receipt["saved_name"]}: {facts["layer_count"]} layers, gaps {gaps!r}', flush=True)
    if not session.alive() or leftover:
        raise ValueError(f'editor left in an unexpected state after the export: {analysis["editor_after_export"]!r}')


if __name__ == '__main__':
    raise SystemExit(case_main(236, FIXTURE, prepare_fixture, steps))
