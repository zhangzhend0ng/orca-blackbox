#!/usr/bin/env python3
# m7x_233_export_merged_stl.py — Feishu #233: export every plate object as one STL through File > Export and open it in F3D
# feishu: baseline#233
"""Feishu #233【合并导出】多对象导出为单个 STL，文件可被第三方打开 (P1).

Precondition (Feishu): 盘上有 2 个模型（立方体 + 球体）.
Steps (Feishu): 1. 点击「文件→导出→导出所有对象为单个 STL…」; 2. 选择导出路径保存，记录文件名与扩展名;
3. 用第三方查看器打开.
Expected (Feishu): 生成 .stl 文件，包含两个模型的合并几何；文件非 0 字节，可正常打开.

The standard cube is loaded and a sphere is added from the blank plate menu
(Add Primitive > Sphere). The application drops a new primitive on the grid
cell nearest the plate centre that no object covers, so its centre lands just
outside the cube while the sphere itself overlaps it; when the saved plate
shows an overlap, Arrange separates the two. `before` is saved once the plate
holds a cube and a sphere apart from each other and on the bed. File > Export >
Export all objects as one STL then saves under the bare name `all-objects`
into the run directory: the application decides the extension. The STL is read
offline against `before`, and F3D opens the same bytes and a malformed control.
"""
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from export_io_oracle import merged_stl_expectation_gaps, plate_object_layout, verify_merged_stl, viewer_gaps  # noqa: E402
from file_export_cases import export_via_file_menu  # noqa: E402
from harness import topbar_util  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from m7x_250_negative_part import highlight_menu_item, open_part_submenu, send_menu_key  # noqa: E402
from m7x_252_export_stl_viewer import open_in_viewer  # noqa: E402
from plate_layout_case import activate_on_blank_plate  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402

FIXTURE = HERE / 'fixtures/feishu_std_cube.3mf'
LOG = '[m7x233]'
# The same plate offsets plate_layout_case uses to hit plate without a model.
BLANK_OFFSETS = ((.09, 0), (-.09, 0), (0, .065), (0, -.065), (.11, .045), (-.11, .045))
SEPARATED = ('two_objects', 'cube_and_sphere', 'disjoint', 'inside_bed')


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives evidence only.
    return model


def blank_plate_candidates(session):
    """Plate points away from the rendered models, anchored on the largest model."""
    width = m7.capture_bgr(session).shape[1]
    center = m7.find_centroid(session)
    if not center:
        raise ValueError('no rendered model to anchor blank plate points on')
    x, y = center
    return [(x + round(width * dx), y + round(width * dy)) for dx, dy in BLANK_OFFSETS]


def add_sphere(session, analysis):
    entry = analysis['add_sphere'] = {'candidates': blank_plate_candidates(session)}
    submenu = open_part_submenu(session, menu_label='Add Primitive', child_label='Sphere',
                                candidates=entry['candidates'], log=LOG)
    if not submenu:
        raise ValueError('the blank plate menu did not expose Add Primitive > Sphere')
    _child, handle, index = submenu
    entry['primitive_rows'] = [{'index': i, 'label': text, 'enabled': not flags & 3}
                               for i, text, flags in topbar_util.menu_items(handle)]
    if not highlight_menu_item(session, handle, index, log=LOG) or not send_menu_key(session, 0x0D, log=LOG):
        raise ValueError('could not activate the Sphere row')
    time.sleep(2)


def separated(session, work, analysis, attempts=3):
    """Save `before` once the plate holds a cube and a sphere apart on the bed; Arrange when they overlap."""
    readings = analysis['layouts'] = []
    arranged = False
    for _attempt in range(attempts):
        stale = work / 'before.3mf'
        if stale.exists():
            stale.unlink()  # save_snapshot waits for the file: a stale one would pass for the new save.
        before = save_snapshot(session, work, 'before')
        layout = plate_object_layout(before)
        readings.append(layout['checks'])
        if all(layout['checks'][name] for name in SEPARATED):
            analysis['plate'] = layout
            analysis['arranged'] = arranged
            return before
        if not layout['checks']['two_objects'] or not layout['checks']['cube_and_sphere']:
            raise ValueError(f'the plate does not hold a cube and a sphere: {layout["objects"]!r}')
        if not arranged:
            with stage(analysis, 'arrange'):
                activate_on_blank_plate(session, 'Arrange', LOG)
            arranged = True
        time.sleep(4)
    raise ValueError(f'the cube and the sphere are still not apart on the bed: {readings!r}')


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    analysis['fixture'] = {'name': args.model.name, 'bytes': args.model.stat().st_size,
                           'sha256': sha256(args.model.read_bytes()).hexdigest()}
    with stage(analysis, 'add_sphere'):
        add_sphere(session, analysis)
    with stage(analysis, 'separate_objects'):
        before = separated(session, work, analysis)
    with stage(analysis, 'export_merged_stl'):
        receipt = export_via_file_menu(session, 'Export all objects as one STL', work, 'all-objects', work, analysis,
                                       title_substr='Export STL file', kind='stl')
    exported = work / receipt['saved_name']
    with stage(analysis, 'read_merged_stl'):
        gaps = analysis['expectation_gaps'] = merged_stl_expectation_gaps(before, exported, receipt['saved_extension'])
        if not gaps['包含两个模型的合并几何']:
            analysis['merged_geometry'] = verify_merged_stl(before, exported)
    analysis['viewer'] = {}
    with stage(analysis, 'open_in_viewer'):
        try:
            open_in_viewer(args, exported, work, analysis)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            analysis['viewer_error'] = f'{type(exc).__name__}: {exc}'
        gaps['可正常打开'] = viewer_gaps(analysis['viewer'])
        analysis['viewer']['same_bytes_as_export'] = (
            analysis['viewer'].get('source_sha256') == receipt['file_sha256'])
        if not analysis['viewer']['same_bytes_as_export']:
            gaps['可正常打开'].append('viewer did not read the exported bytes')
    for clause, failed in gaps.items():
        analysis['results'][clause] = 'PASS' if not failed else f'FAIL ({"; ".join(failed)[:400]})'
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    analysis['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    print(f'[m7x233] {receipt["saved_name"]}: gaps {gaps!r}', flush=True)
    if not session.alive() or leftover:
        raise ValueError(f'editor left in an unexpected state after the export: {analysis["editor_after_export"]!r}')


if __name__ == '__main__':
    raise SystemExit(case_main(233, FIXTURE, prepare_fixture, steps,
                               lambda parser: parser.add_argument('--viewer', type=Path)))
