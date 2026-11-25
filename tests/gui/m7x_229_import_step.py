#!/usr/bin/env python3
# m7x_229_import_step.py — Feishu #229: import a STEP file of three coloured solids through File > Import
# feishu: baseline#229
"""Feishu #229: a STEP assembly of three coloured solids imported through File > Import (P1).

Precondition (Feishu): 准备含 3 个实体的装配体 assembly.step（各实体不同颜色）.
Steps (Feishu): 1. 通过「文件→导入」导入 assembly.step; 2. 观察对象列表与盘上零件数量/颜色.
Path (Feishu): 文件 → 导入 → 导入 3MF/STL/STEP/SVG/OBJ/AMF…
Expected (Feishu): 3 个实体均被导入，对象列表可见对应零件（或拆分为多对象），颜色保留，无缺件.

The STEP is fixtures/assembly.step (tools/make_assembly_step.py): three 10 mm
cubes 10 mm apart along x, red, green and blue. The plate starts empty with
the U1 0.8 template whose first filaments are red and blue
(fixtures/agent_layer_redblue.3mf; prepare_plate reads the U1 0.8 printer from
the project it saves). The file is handed to File > Import's one model row
(#227's import_stl), then the case waits for a model on the plate and for no
dialog. A dialog that comes is surveyed first (class, title, every child
window, a picture) and written to ``import_dialogs``; a loading box is waited
for, a dialog with an affirmative button has it pressed by text and is seen
to close, and an error dialog, or any other that stays 20 s, stops the case.
The project is saved as ``imported.3mf`` and the object list is read from the
sidebar. tests/step_import_oracle.py judges the four clauses from the saved
project and the list: an entity is a part of the saved project, so one object
with three parts and three objects read the same.

The application's command line refuses STEP files on this build
(``Unknown file format``, control of 2026-11-26), so nothing of this row is
known before the first guest run: whether the file loads as one object or
three, and what becomes of the colours.
"""
from hashlib import sha256
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests'), str(HERE / 'tests' / 'engine'), str(HERE / 'tests' / 'gui')]

import m7_common as m7  # noqa: E402
from colored_obj_cases import _accept, affirmative, app_dialogs, survey_dialog  # noqa: E402
from m7x_227_import_stl import import_stl, show_objects_tab, sidebar  # noqa: E402
from m7x_244_add_model import prepare_plate  # noqa: E402
from m7x_249_add_part import stage  # noqa: E402
from plate_reserve_case import case_main, save_snapshot  # noqa: E402
from step_import_oracle import recorded_results_match, step_import_readings, verdicts  # noqa: E402

# The U1 0.8 template with its first two filaments coloured red and blue
# (tools/make_agent_layer_redblue.py): prepare_plate reads the U1 0.8 printer from the project it saves.
FIXTURE = HERE / 'fixtures' / 'agent_layer_redblue.3mf'
STEP = HERE / 'fixtures' / 'assembly.step'
LOG = '[m7x229]'
STRANGER_WAIT_S = 20


def prepare_fixture(model, work):
    # The repository fixture is loaded as it is; the run directory receives the STEP and evidence only.
    return model


def _loading(title):
    return title.casefold().startswith('loading')


def wait_step_import(session, work, analysis, baseline=0, timeout_s=150):
    """After the chooser took the STEP: wait for a model on the plate and for no dialog.

    wait_arrival is no use on the empty U1 template (#251): its coloured
    fraction already clears the gate. Here a model is a candidate the plate
    shows (m7.model_candidates), and there must be more of them than the empty
    plate showed (`baseline`); the import has settled when that holds and no
    dialog is left, twice in a row."""
    deadline = time.monotonic() + timeout_s
    met = analysis.setdefault('import_dialogs', [])
    loading_seen, answered, strangers = set(), set(), {}
    quiet, state = 0, {}
    while time.monotonic() < deadline:
        dialogs = app_dialogs(session)
        for _cls, title, _rect, hwnd in dialogs:
            if _loading(title):
                loading_seen.add(title)
                continue
            if hwnd in answered:
                continue
            record = survey_dialog(work, hwnd, f'import-dialog-{len(met)}')
            met.append(record)
            print(f'[m7x229] dialog {title!r}: {[child["text"] for child in record["children"] if child["text"]][:24]!r}',
                  flush=True)
            if 'error' in title.casefold():
                raise ValueError(f'the application showed {title!r}: '
                                 f'{[child["text"] for child in record["children"] if child["text"]][:12]!r}')
            if affirmative(record['children']) is not None:
                _accept(session, work, hwnd, record)  # presses the button and sees the dialog close
                answered.add(hwnd)
        others = [(hwnd, title) for _cls, title, _rect, hwnd in dialogs if not _loading(title) and hwnd not in answered]
        now = time.monotonic()
        strangers = {hwnd: strangers.get(hwnd, now) for hwnd, _title in others}
        lingering = [title for hwnd, title in others if now - strangers[hwnd] > STRANGER_WAIT_S]
        if lingering:
            raise ValueError(f'a dialog without an affirmative button stayed open {STRANGER_WAIT_S}s: '
                             f'{lingering!r}; its survey is in import_dialogs')
        loading = [(hwnd, title) for _cls, title, _rect, hwnd in dialogs if _loading(title)]
        candidates = 0 if others or loading else len(m7.model_candidates(session, limit=10))
        state = {'candidates': candidates, 'baseline': baseline, 'dialogs': [title for _hwnd, title in others + loading]}
        quiet = quiet + 1 if candidates > baseline and not others and not loading else 0
        if quiet >= 2:
            break
        time.sleep(1.0)
    analysis['loading_dialogs'] = sorted(loading_seen)
    print(f'{LOG} import settled: {state}', flush=True)
    return state


def steps(session, work, analysis, args):
    analysis.setdefault('timings', {})
    source = work / 'assembly.step'
    with stage(analysis, 'copy_step'):
        shutil.copyfile(STEP, source)
        analysis['fixture'] = {'name': source.name, 'bytes': source.stat().st_size,
                               'sha256': sha256(source.read_bytes()).hexdigest(),
                               'template': {'name': args.model.name, 'bytes': args.model.stat().st_size,
                                            'sha256': sha256(args.model.read_bytes()).hexdigest()}}
    with stage(analysis, 'empty_plate'):
        center = m7.find_centroid(session)
        if center is None:
            raise ValueError('the U1 template did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
        analysis['empty_plate_candidates'] = len(m7.model_candidates(session, limit=10))
    with stage(analysis, 'import_chooser'):
        import_stl(session, source, work, analysis)
    with stage(analysis, 'observe_import'):
        settled = wait_step_import(session, work, analysis, baseline=analysis['empty_plate_candidates'])
        analysis['import_settled'] = settled
        if settled.get('candidates', 0) <= settled.get('baseline', 0):
            raise ValueError(f'the STEP did not settle on the plate: {settled!r}')
    with stage(analysis, 'save_imported'):
        imported = save_snapshot(session, work, 'imported')
        show_objects_tab(session)
        words = sidebar(session)
        analysis['object_list'] = {'words': [word[0] for word in words][:60]}
        analysis['imported'] = step_import_readings(imported, words)
        analysis['object_list'].update({key: (analysis['imported'].get('object_list') or {}).get(key)
                                        for key in ('names', 'found', 'listed')})
        print(f'{LOG} imported: {analysis["imported"].get("entity_count")} entities '
              f'{[entity["part"] for entity in analysis["imported"].get("entities", [])]!r}', flush=True)
    with stage(analysis, 'read_results'):
        analysis['results'].update(verdicts(analysis['imported']))
        # The record cannot outrun the files: the verdicts above are the ones recomputed from them.
        analysis['recorded_results_match'] = recorded_results_match(analysis, analysis['imported'])
        leftover = m7.wait_dialog(session.pid, timeout_s=0.5)
        analysis['editor_at_end'] = {'alive': session.alive(), 'dialog': leftover[1] if leftover else None}
        if not session.alive() or leftover:
            raise ValueError(f'editor left in an unexpected state: {analysis["editor_at_end"]!r}')


if __name__ == '__main__':
    raise SystemExit(case_main(229, FIXTURE, prepare_fixture, steps))
