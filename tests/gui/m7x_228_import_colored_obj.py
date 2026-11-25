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
material ``red`` and whose right half is ``blue``. The precondition names
three files and says that the faces hold two materials; it does not say that
the material references the texture. So the judged ``model.mtl`` gives each
material a ``Kd`` colour only (red ``1 0 0``, blue ``0 0 1``), the faces carry
no ``vt``, and ``texture.png`` (a red 16 x 16 picture) lies beside them in the
same directory. With ``--geometry two-boxes`` (the default, 24 faces) the cube
is two closed 10 x 20 x 20 boxes whose wall at x = 0 is two coincident faces;
with ``--geometry split-cube`` (20 faces) it is one closed cube cut at x = 0.

Why that form and not the textured one: on the guest (run dev228b-2c32e51c)
the application imported the textured form, ``map_Kd texture.png`` on the
material and ``vt`` on the faces, as plain geometry: no dialog, 24 faces
without paint, one tool in the G-code. For this form it showed ``Obj file
Import color``. The tag ``sm-v2.4.0`` (b1831e5d), which the guest behaved
like, says why: ``map_Kd`` sets ``has_uv_png`` (Format/OBJ.cpp:158-163), the
face-colour branch needs it false (Model.cpp:282) and the textured branch is
commented out (Model.cpp:290-296).

The plate starts empty with the U1 0.8 template whose first two filaments are
red and blue (fixtures/agent_layer_redblue.3mf; prepare_plate reads the U1 0.8
printer from the project it saves). The OBJ is handed to File > Import's one
model row, the application's own dialog is surveyed and its ``OK`` pressed
(tests/colored_obj_cases.py), the project is saved as ``imported.3mf``,
sliced until File > Export's ``Export G-code`` row is enabled, and exported as
``plate.gcode``. tests/colored_obj_oracle.py reads both files: the first
clause from the filament each face prints with, the second from the tools
that extrude in the G-code.

What that form leaves, by the same tag: ``obj_import_face_color_deal`` sets
the extruder of the object and of its one volume to the filament of the first
colour cluster and paints every face whose filament is above 1
(Model.cpp:3255-3280). The faces of filament 1 carry no paint and print with
that extruder. Whether both materials keep a filament of their own therefore
depends on which cluster the dialog lists first; that is read from the saved
project, never assumed.

After everything judged, and never judged itself, the textured form
(``model_tex.obj`` + ``model_tex.mtl``, ``map_Kd texture.png`` and ``vt``) is
imported into the same session: the dialogs it brings, the filament the faces
of the project it saves with (``control.3mf``) print with, and the tools it
prints with once the plate is sliced again (``control.gcode``, read inside
that object's blocks) go under ``control`` in the analysis.
``analysis['route']`` says for each form which way it went. ``--no-control``
leaves the control out.
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
    CLAUSE_COLORS, CLAUSE_FILAMENTS, GEOMETRIES, filament_readings, gcode_tools, material_triangles,
    painted_readings)
from file_export_cases import export_via_file_menu, slice_until_exportable  # noqa: E402
from m7x_227_import_stl import import_stl  # noqa: E402
from m7x_244_add_model import prepare_plate  # noqa: E402
from m7x_249_add_part import capture, stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402

# The U1 0.8 template with its first two filaments coloured red and blue
# (tools/make_agent_layer_redblue.py): the MTL carries a red and a blue material, and
# prepare_plate reads the U1 0.8 printer from the project it saves.
FIXTURE = HERE / 'fixtures' / 'agent_layer_redblue.3mf'
LOG = '[m7x228]'
CONTROL = 'model_tex'


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives the OBJ and evidence only.
    return model


def extra_args(parser):
    parser.add_argument('--geometry', choices=sorted(GEOMETRIES), default='two-boxes',
                        help='shape of the OBJ fixture (two-boxes: 24 faces; split-cube: 20 faces)')
    parser.add_argument('--no-control', action='store_true',
                        help='leave out the textured control import after the judged run')


def verdict(readings):
    """'PASS', or 'FAIL (...)' naming what could not be read or the checks that failed."""
    checks = readings.get('checks') or {}
    if not checks:
        return f'FAIL (not read: {readings.get("error", "no readings")})'
    failed = [name for name, passed in checks.items() if not passed]
    return 'PASS' if not failed else f'FAIL ({", ".join(failed)})'


def route(fixture, dialogs, saved):
    """One form's way in one place: its form, the dialogs that came and what was pressed in them,
    and the filament the faces of each material print with."""
    saved = saved or {}
    return {'form': fixture.get('form'), 'form_says': fixture.get('form_says'),
            'texture_referenced': fixture.get('texture_referenced'), 'obj_has_uv': fixture.get('obj_has_uv'),
            'dialogs': [{key: record.get(key) for key in ('title', 'class', 'pressed', 'closed', 'image', 'error')}
                        for record in dialogs],
            'filaments': saved.get('filaments'), 'faces_without_paint_print_with': saved.get('faces_without_paint_print_with'),
            'object_extruder': saved.get('object_extruder'), 'checks': saved.get('checks'), 'error': saved.get('error')}


def tools(gcode):
    gcode = gcode or {}
    picked = ('tools_extruding', 'change_count', 'object_tools_extruding', 'object_printed', 'filament_used', 'error')
    return {key: gcode[key] for key in picked if key in gcode}


def _faces_print_with(saved):
    return {name: row['faces'] for name, row in (saved.get('paint_states') or {}).items()}


def control_import(session, work, analysis, geometry):
    """After everything judged: the other form of the same geometry, the texture referenced and
    UVs on the faces, imported into the same session. Recorded, never judged: which dialog came
    (none did on the guest), the filament the faces of the project it saves with print with, and
    the tools it prints with once the plate is sliced again."""
    control = analysis['control'] = {'fixture': write_fixture(work, CONTROL, texture=True, uv=True, geometry=geometry)}
    try:
        with stage(analysis, 'control_import'):
            control['chooser'] = hand_file_to_import(session, work / f'{CONTROL}.obj', work, control,
                                                     'chooser', 'control-chooser.png')
            arrived, fraction = wait_import(session, work, control, stem='control-dialog')
            control['arrived'], control['import_fraction'] = arrived, fraction
            control['saved'] = painted_readings(save_snapshot(session, work, 'control'), f'{CONTROL}.obj',
                                                material_triangles(geometry))
            print(f'{LOG} control saved: {control["saved"].get("filaments")} {_faces_print_with(control["saved"])!r}',
                  flush=True)
    except Exception as exc:  # noqa: BLE001 - a control is recorded, never judged
        control['error'] = f'{type(exc).__name__}: {exc}'
        traceback.print_exc()
    try:
        # The plate holds the judged object too: the control's own tools are those of its blocks.
        with stage(analysis, 'control_gcode'):
            slice_until_exportable(session, work, control, 'Export G-code', timeout_s=60, key='slice')
            # A second name: the saved project already holds the name "control" in this directory.
            receipt = export_via_file_menu(session, 'Export G-code', work, 'control-gcode', work, control,
                                           title_substr='Save G-code file as', kind='gcode',
                                           image='control-export-dialog.png')
            control['gcode'] = gcode_tools(work / receipt['saved_name'], f'{CONTROL}.obj')
    except Exception as exc:  # noqa: BLE001
        control['gcode_error'] = f'{type(exc).__name__}: {exc}'
        traceback.print_exc()
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    control['editor_after'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    analysis['route']['control'] = {**route(control['fixture'], control.get('import_dialogs', []), control.get('saved')),
                                    'gcode': tools(control.get('gcode')), 'gcode_error': control.get('gcode_error'),
                                    'import_error': control.get('error')}


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
        print(f'{LOG} imported: {analysis["imported"].get("filaments")} '
              f'{_faces_print_with(analysis["imported"])!r}', flush=True)
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
    analysis['route'] = {'judged': {**route(analysis['fixture'], analysis.get('import_dialogs', []), analysis['imported']),
                                    'gcode': tools(analysis['gcode'])}}
    leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
    analysis['editor_after_export'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
    if not session.alive() or leftover:
        raise ValueError(f'editor left in an unexpected state after the export: {analysis["editor_after_export"]!r}')
    if not args.no_control:
        control_import(session, work, analysis, args.geometry)


if __name__ == '__main__':
    raise SystemExit(case_main(228, FIXTURE, prepare_fixture, steps, extra_args))
