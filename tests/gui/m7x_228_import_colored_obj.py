#!/usr/bin/env python3
# m7x_228_import_colored_obj.py — Feishu #228: import an OBJ with two materials through File > Import, then slice and export
# feishu: baseline#228
"""Feishu #228【带颜色】导入带 .mtl 材质的 OBJ，颜色正确保留 (P1).

Precondition (Feishu): 准备 model.obj + model.mtl + 贴图，面片含红、蓝两种材质分区.
Steps (Feishu): 1. 通过文件对话框选中 model.obj（mtl/贴图位于同目录）; 2. 导入后观察模型配色;
3. 切片查看颜色分区分料.
Path (Feishu): 文件 → 导入 → 导入 3MF/STL/STEP/SVG/OBJ/AMF…
Expected (Feishu): 模型导入成功，两种颜色按面片正确显示；切片后按颜色生成对应耗材/换料.

The fixture is written by the case: a 20 mm cube whose left half is the
material ``red`` and whose right half is ``blue``, ``model.mtl`` with ``red``
(``Kd 1 0 0``, ``map_Kd texture.png``) and ``blue`` (``Kd 0 0 1``), a red
16 x 16 ``texture.png``, the faces carrying UVs. With ``--geometry two-boxes``
(the default, 24 faces) the cube is two closed 10 x 20 x 20 boxes whose shared
wall at x = 0 is two coincident faces; with ``--geometry split-cube`` (20
faces) it is one closed cube cut at x = 0, every edge in two faces. The plate
starts empty with the standard cube's printer (U1 0.4 mm), the OBJ is handed
to File > Import's one model row, and whatever dialog the application shows
for the materials is surveyed and accepted (tests/colored_obj_cases.py). The
project is saved as ``imported.3mf``, sliced until File > Export's ``Export
G-code`` row is enabled, and exported as ``plate.gcode``.
tests/colored_obj_oracle.py reads both files: the first clause from the paint
on the saved faces, the second from the tools that extrude in the G-code.

What the application does with such an OBJ on the guest build (ref
``sync/softfever-20261010``, 813784a9d0): ``load_obj`` keeps one object with
one mesh (Format/OBJ.cpp:243-260), the textured mesh goes to the ``Import
Model`` dialog (Model.cpp:356-365, GUI/Plater.cpp:24060), and its result is
applied to the faces of the first part, the extruders being set to the
smallest filament used (GUI/Plater.cpp:24255-24272). So one object with one
part is expected, painted face by face; the attribute and the filaments are
read as saved, not assumed.

After everything judged, and never judged itself, the same geometry with
``Kd`` colours only (``model_kd.obj``, no texture, no UVs; the face colours
become ``precomputed_face_colors``, Model.cpp:398-415) is imported into the
same session and saved as ``control.3mf``: a reading for comparison, under
``control`` in the analysis. ``--no-control`` leaves it out.
"""
from hashlib import sha256
from pathlib import Path
import sys
import traceback

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from colored_obj_cases import hand_file_to_import, wait_import, write_fixture  # noqa: E402
from colored_obj_oracle import (  # noqa: E402
    CLAUSE_COLORS, CLAUSE_FILAMENTS, GEOMETRIES, filament_readings, material_triangles, painted_readings)
from file_export_cases import export_via_file_menu, slice_until_exportable  # noqa: E402
from m7x_227_import_stl import import_stl  # noqa: E402
from m7x_244_add_model import prepare_plate  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402

FIXTURE = HERE / 'fixtures' / 'feishu_std_cube.3mf'
LOG = '[m7x228]'


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives the OBJ and evidence only.
    return model


def extra_args(parser):
    parser.add_argument('--geometry', choices=sorted(GEOMETRIES), default='two-boxes',
                        help='shape of the OBJ fixture (two-boxes: 24 faces; split-cube: 20 faces)')
    parser.add_argument('--no-control', action='store_true',
                        help='leave out the control import of model_kd.obj after the judged run')


def verdict(readings):
    """'PASS', or 'FAIL (...)' naming what could not be read or the checks that failed."""
    checks = readings.get('checks') or {}
    if not checks:
        return f'FAIL (not read: {readings.get("error", "no readings")})'
    failed = [name for name, passed in checks.items() if not passed]
    return 'PASS' if not failed else f'FAIL ({", ".join(failed)})'


def control_import(session, work, analysis, geometry):
    """The same geometry with Kd colours only, imported after the judged run and saved: a
    reading to compare with, whatever happens to it."""
    control = analysis['control'] = {'fixture': write_fixture(work, 'model_kd', texture=False, uv=False, geometry=geometry)}
    try:
        with stage(analysis, 'control_import'):
            control['chooser'] = hand_file_to_import(session, work / 'model_kd.obj', work, control,
                                                     'chooser', 'control-chooser.png')
            arrived, fraction = wait_import(session, work, control, stem='control-dialog')
            control['arrived'], control['import_fraction'] = arrived, fraction
            control['saved'] = painted_readings(save_snapshot(session, work, 'control'), 'model_kd.obj',
                                                material_triangles(geometry))
            print(f'{LOG} control saved: {control["saved"].get("filaments")} {control["saved"].get("paint_states")!r}',
                  flush=True)
    except Exception as exc:  # noqa: BLE001 - a control is recorded, never judged
        control['error'] = f'{type(exc).__name__}: {exc}'
        traceback.print_exc()
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    control['editor_after'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    analysis['fixture'] = {**write_fixture(work, geometry=args.geometry),
                           'template': {'name': args.model.name, 'bytes': args.model.stat().st_size,
                                        'sha256': sha256(args.model.read_bytes()).hexdigest()}}
    expected = material_triangles(args.geometry)
    source = work / 'model.obj'
    with stage(analysis, 'empty_plate'):
        center = m7.find_centroid(session)
        if center is None:
            raise ValueError('the U1 template did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
    with stage(analysis, 'import_chooser'):
        import_stl(session, source, work, analysis)
    with stage(analysis, 'observe_import'):
        arrived, fraction = wait_import(session, work, analysis)
        analysis['import_fraction'] = fraction
        if not arrived:
            raise ValueError('model.obj did not appear on the plate')
    with stage(analysis, 'save_imported'):
        imported = save_snapshot(session, work, 'imported')
        analysis['imported'] = painted_readings(imported, 'model.obj', expected)
        print(f'{LOG} imported: {analysis["imported"].get("filaments")} {analysis["imported"].get("paint_states")!r}',
              flush=True)
    with stage(analysis, 'slice'):
        slice_until_exportable(session, work, analysis, 'Export G-code')
        capture(session, work / 'sliced.png')
    with stage(analysis, 'export_gcode'):
        receipt = export_via_file_menu(session, 'Export G-code', work, 'plate', work, analysis,
                                       title_substr='Save G-code file as', kind='gcode')
    with stage(analysis, 'read_gcode'):
        analysis['gcode'] = filament_readings(work / receipt['saved_name'], analysis['imported'])
        print(f'{LOG} {receipt["saved_name"]}: tools extruding {analysis["gcode"].get("tools_extruding")}, '
              f'changes {analysis["gcode"].get("change_count")}', flush=True)
    analysis['results'][CLAUSE_COLORS] = verdict(analysis['imported'])
    analysis['results'][CLAUSE_FILAMENTS] = verdict(analysis['gcode'])
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    analysis['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    if not session.alive() or leftover:
        raise ValueError(f'editor left in an unexpected state after the export: {analysis["editor_after_export"]!r}')
    if not args.no_control:
        control_import(session, work, analysis, args.geometry)


if __name__ == '__main__':
    raise SystemExit(case_main(228, FIXTURE, prepare_fixture, steps, extra_args))
