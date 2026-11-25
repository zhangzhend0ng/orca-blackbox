#!/usr/bin/env python3
# feishu: baseline#231
# m7x_231_import_zip.py — Feishu #231: import a ZIP holding three STLs and check that all three models load.
"""Import models.zip through File > Import > Import Zip Archive, tick everything in the Archive
preview, and check that the three cubes reach the plate and the object list under their file names."""
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

import m7_common as m7
from harness import winutil
from m7x_244_add_model import prepare_plate
from m7x_249_add_part import capture, stage
from m8_common import wait_arrival
from plate_reserve_case import case_main
from zip_import_cases import (build_archive, choose_zip, describe, list_words, press_named, sidebar_words,
                              shoot, wait_closed, wait_preview)
from zip_import_oracle import (EXPECTED, MEMBERS, digest, remove_stale, temp_collisions, verify_member_digests,
                               verify_object_list, verify_zip_import)

STEMS = tuple(name.rsplit('.', 1)[0] for name, _size in MEMBERS)


def prepare_fixture(template, _work):
    return template


def preview_rows(preview, path, analysis, key):
    """Screenshot the Archive preview and read its list. Observation only:
    the rows are drawn, not windowed, so a failed reading must not hide the import."""
    frame = shoot(preview, path)
    try:
        analysis['preview'][key] = [word[0] for word in list_words(preview, frame, 'wxDataView')]
    except Exception as exc:  # noqa: BLE001 - diagnostic reading, never a verdict
        analysis['preview'][key] = f'unreadable ({type(exc).__name__}: {exc})'


def steps(session, work, analysis, _args):
    analysis.setdefault('timings', {})
    archive = work / 'inputs' / 'models.zip'
    with stage(analysis, 'prepare_empty_plate'):
        center = m7.find_centroid(session)
        if not center:
            raise ValueError('initial printer fixture did not open')
        analysis['bed_point'] = list(center)
        prepare_plate(session, work, analysis)
        capture(session, work / 'prepare-before.png')
    with stage(analysis, 'build_archive'):
        sources = build_archive(archive, work)
        analysis['archive'] = {'file': 'inputs/models.zip', 'not_harvested': ['models.zip', 'readme.txt'],
                               **digest(archive), 'members': {name: digest(path) for name, path in sources.items()}}
        temp = tempfile.gettempdir()
        analysis['temp_dir'] = str(temp)
        analysis['temp_collisions'] = temp_collisions(temp, sources)
        analysis['temp_leftovers_removed'] = remove_stale(temp, sources)
    with stage(analysis, 'import_zip_chooser'):
        chooser = choose_zip(session, archive, work, analysis)
    with stage(analysis, 'archive_preview'):
        preview = wait_preview(session)
        analysis['preview'] = {'controls': describe(preview)}
        preview_rows(preview, work / 'archive-preview.png', analysis, 'rows_initial')
        # Every row starts unchecked unless the archive holds exactly one model
        # (FileArchiveDialog.cpp, sm-v2.4.0), so Open alone would import nothing.
        analysis['preview']['all_click'] = press_named(preview, 'All')
        time.sleep(0.8)
        preview_rows(preview, work / 'archive-preview-all.png', analysis, 'rows_after_all')
    with stage(analysis, 'open_archive'):
        analysis['preview']['open_click'] = press_named(preview, 'Open')
        if not wait_closed(preview) or winutil.user32.IsWindowVisible(chooser):
            raise ValueError('Archive preview or chooser did not close after Open')
    with stage(analysis, 'observe_import'):
        arrived, fraction = wait_arrival(session, timeout_s=30, min_frac=0.001)
        analysis['import_fraction'] = fraction
        if not arrived:
            raise ValueError('no model appeared after opening the archive')
        # Three files load one after another: the object list naming all of
        # them is the arrival signal, not the coloured area of the first cube.
        deadline = time.monotonic() + 25
        while True:
            try:
                analysis['object_list'] = verify_object_list(sidebar_words(session), STEMS)
                unreadable = None
                break
            except ValueError as exc:
                unreadable = exc
                analysis['object_list'] = {'error': str(exc)}
                if time.monotonic() > deadline:
                    break
                time.sleep(1.0)
        capture(session, work / 'imported.png')
    with stage(analysis, 'save_and_verify'):
        project = work / 'imported.3mf'
        if not m7.save_project_as(session, project, timeout_s=40):
            raise ValueError('failed to save the imported project')
        # The retained cubes must be the zip contents before they stand in for it.
        analysis['archive']['members_in_zip'] = verify_member_digests(archive, sources)
        analysis['saved'] = verify_zip_import(project, sources)
        print('[m7x231] saved', analysis['saved'], flush=True)
        if unreadable is not None:
            raise unreadable
        analysis['results'][EXPECTED] = 'PASS'


def main():
    return case_main(231, HERE / 'fixtures/agent_layer_cube.3mf', prepare_fixture, steps)


if __name__ == '__main__':
    raise SystemExit(main())
