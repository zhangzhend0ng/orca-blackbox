#!/usr/bin/env python3
# m7x_234_export_plate_slice.py — Feishu #234: export the sliced plate as a .gcode.3mf file through File > Export
# feishu: baseline#234
"""Feishu #234【切片导出】当前盘已切片时导出切片文件，扩展名为 .gcode.3mf (P0).

Precondition (Feishu): 当前盘已完成切片（有 G-code 预览）.
Steps (Feishu): 1. 点击「文件→导出→导出当前盘切片文件…」（或 Ctrl+G）; 2. 选择路径保存;
3. 检查扩展名与文件内容.
Expected (Feishu): 生成 .gcode.3mf 文件，内含 G-code 与预览信息，文件大小随切片复杂度合理增大.

The last clause needs two plates of different complexity, so the case runs
two sessions with the same printer and process preset (U1 0.4 mm, PLA,
0.20 mm Standard): the standard cube (12 triangles) and the standard sphere
(3,968 triangles). Each is sliced, waited for by the enabled state of the
File > Export > Export plate sliced file row, and exported under a bare name
into the run directory, so that the application decides the extension. The
cube's file is `plate.gcode.3mf`, the sphere's `sphere.gcode.3mf`. The
archive sizes and the G-code inside them are compared; readings of exports
collected earlier are listed next to them when those files are on the machine.
The G-code inside each archive must also deposit its material on the objects
of the plate it was sliced from (gcode_footprint, against the saved `before`).
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from export_io_oracle import harvested_readings, plate_object_layout, project_presets, sliced_expectation_gaps  # noqa: E402
from file_export_cases import export_via_file_menu, slice_until_exportable  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from m8_common import wait_arrival  # noqa: E402
from plate_reserve_case import save_snapshot  # noqa: E402

LOG = '[m7x234]'
ITEM = 'Export plate sliced file'
TITLE = 'Save Sliced file as'
CUBE = HERE / 'fixtures/feishu_std_cube.3mf'
SPHERE = HERE / 'fixtures/feishu_std_sphere.3mf'
# label, bare name typed into the save dialog, prefix of the retained evidence
SAMPLES = (('simple', 'plate', ''), ('complex', 'sphere', 'sphere-'))
# Exports collected before this case, read again here when they are on this machine.
REFERENCES = (
    ('standard cube, sliced file (guest probe b958af2, run 1)',
     HERE / 'docs/runs/evidence/elevenhour-filemenu-2026-11-25/b958af2-probe1-plate-sliced.gcode.3mf', 'sliced'),
    ('standard cube, plain G-code (guest probe b958af2, run 1)',
     HERE / 'docs/runs/evidence/elevenhour-filemenu-2026-11-25/b958af2-probe1-plate-gcode.gcode', 'gcode'),
    ('standard cube, plain G-code (harvest e9aa6f88eca940b385bfe531703f644e, uia_param_std_save_only)',
     HERE / 'artifacts/windows_mcp_harvest/e9aa6f88eca940b385bfe531703f644e/exports/0001.gcode', 'gcode'),
    ('standard sphere, plain G-code (harvest a673f4e21e424361bd8e83f6273aff7d, uia_param_sphere_save_only)',
     HERE / 'artifacts/windows_mcp_harvest/a673f4e21e424361bd8e83f6273aff7d/exports/0001.gcode', 'gcode'),
)


def run_sample(args, work, analysis, label, model, name, prefix):
    """One session: open `model`, slice it, export its sliced file; returns the receipt and the saved plate."""
    reading = analysis[label] = {'fixture': {'name': model.name, 'bytes': model.stat().st_size,
                                              'sha256': sha256(model.read_bytes()).hexdigest()}}
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / f'{label}-profile'), model=model)
    try:
        m7.ensure_maximized(session)
        if not wait_arrival(session, timeout_s=30, min_frac=0.001)[0]:
            raise ValueError(f'{model.name} did not render')
        with stage(analysis, f'{label}_open'):
            before = save_snapshot(session, work, prefix + 'before')
            reading['presets'] = project_presets(before)
            reading['plate_objects'] = plate_object_layout(before)['objects']
        with stage(analysis, f'{label}_slice'):
            slice_until_exportable(session, work, analysis, ITEM, key=f'{label}_slice')
            reading['slice'] = analysis.pop(f'{label}_slice')
            capture(session, work / (prefix + 'sliced.png'))
        with stage(analysis, f'{label}_export'):
            receipt = export_via_file_menu(session, ITEM, work, name, work, analysis, TITLE, 'archive',
                                           image=prefix + 'export-dialog.png', key=f'{label}_export')
            reading['export'] = analysis.pop(f'{label}_export')
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        reading['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
        if not session.alive() or leftover:
            raise ValueError(f'editor left in an unexpected state after the export: {reading["editor_after_export"]!r}')
        return receipt, before
    finally:
        session.close()


def run(args, work, analysis):
    samples, projects = {}, {}
    for label, name, prefix in SAMPLES:
        model = args.model if label == 'simple' else SPHERE
        try:
            receipt, before = run_sample(args, work, analysis, label, model, name, prefix)
        except Exception as exc:  # noqa: BLE001 - recorded; the verdict below turns red on it
            # The cube alone decides the first two clauses; without the sphere there is no size comparison.
            if label == 'simple':
                raise
            analysis[label]['error'] = f'{type(exc).__name__}: {exc}'
            traceback.print_exc()
            break
        samples[label] = (work / receipt['saved_name'], receipt['saved_extension'])
        projects[label] = before
    # Each archive's G-code must deposit its material on the objects of the plate it was sliced from.
    gaps, readings, comparison = sliced_expectation_gaps(samples, projects)
    if analysis.get('complex', {}).get('error'):
        gaps['文件大小随切片复杂度合理增大'].append(f'complex plate: {analysis["complex"]["error"]}')
    analysis['sliced_files'] = readings
    analysis['size_comparison'] = comparison
    analysis['harvested_references'] = harvested_readings(REFERENCES)
    analysis['expectation_gaps'] = gaps
    for clause, failed in gaps.items():
        analysis['results'][clause] = 'PASS' if not failed else f'FAIL ({"; ".join(failed)[:400]})'
    if comparison:
        print(f'{LOG} file bytes {comparison["simple"]["file_bytes"]} -> {comparison["complex"]["file_bytes"]}, '
              f'G-code bytes {comparison["simple"]["gcode_bytes"]} -> {comparison["complex"]["gcode_bytes"]}',
              flush=True)


def main():
    parser = add_common_args(argparse.ArgumentParser(), default_model=CUBE)
    args = parser.parse_args()
    root = args.datadir.resolve().parent / 'feishu-object-cases' / '234'
    root.mkdir(exist_ok=True, parents=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    print(f'{LOG} retained work directory: {work}', flush=True)
    analysis = {'case': 234, 'results': {}, 'timings': {}}
    started = time.monotonic()
    try:
        run(args, work, analysis)
    except Exception as exc:
        analysis['results']['unfinished checks'] = f'FAIL ({type(exc).__name__}: {exc})'
        traceback.print_exc()
    finally:
        analysis['wall_seconds'] = round(time.monotonic() - started, 3)
        (work / 'analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    return m7.m7_verdict(analysis['results'])


if __name__ == '__main__':
    raise SystemExit(main())
