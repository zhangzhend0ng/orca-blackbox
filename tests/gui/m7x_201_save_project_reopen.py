#!/usr/bin/env python3
# m7x_201_save_project_reopen.py — Feishu #201: save a named project and reopen the same file.
# feishu: baseline#201

import argparse
from decimal import Decimal, InvalidOperation
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7
from harness import winutil
from harness.project_3mf import _archive, _geometry
from m3_common import add_common_args, boot_session
from m6a_transform_verify import position_row_wait
from m8_common import wait_arrival
from project_file_cases import digest_file, dispatch_file_command, project_title, wait_project_write

FIXTURE = HERE / "fixtures" / "agent_layer_cube.3mf"


def project_geometry(path):
    faces, _, matrix = _geometry(_archive(path.read_bytes(), lambda: False))
    return faces, matrix


def translated_geometry(faces, x_delta):
    return tuple(tuple((x + x_delta, y, z) for x, y, z in face) for face in faces)


def position_value(text):
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def foreground(session):
    m7.ensure_maximized(session)
    winutil.force_set_foreground(session.hwnd)
    return winutil.user32.GetForegroundWindow() == session.hwnd


def read_reopened_position(session):
    if not foreground(session) or not m7.select_model(session):
        return ""
    slot, _ = m7.find_slot(session, lambda text: "move" in text)
    if slot is None:
        return ""
    m7.click_slot(session, slot)
    _box, text = position_row_wait(session)
    return text


def run_case(args, project, work):
    results = {}
    initial_faces, initial_matrix = project_geometry(project)
    initial_x = initial_matrix[9]
    target = str(int(initial_x) + 10)
    expected_x = Decimal(target)
    delta = expected_x - initial_x

    editor_args = SimpleNamespace(exe=args.exe, datadir=work / "edit-profile")
    editor = boot_session(editor_args, model=project)
    try:
        loaded, fraction = wait_arrival(editor, timeout_s=30)
        original_title = project_title(editor)
        print(f"[m7x201] original pid={editor.pid}, title={original_title!r}, "
              f"project={project}, modeled={fraction:.3%}, X={initial_x}")
        if not (loaded and original_title == project.stem and foreground(editor)):
            return {"#201 named project opened": "FAIL"}
        results["#201 named project opened"] = "PASS"

        edited, text = m7.op_gizmo_field(editor, lambda tip: "move" in tip, "position", 0, target)
        changed = edited and position_value(text) == expected_x
        results["#201 existing object's X changed"] = (
            f"{'PASS' if changed else 'FAIL'} (initial={initial_x}, target={target}, UI={text!r})")
        if not changed:
            return results

        # Capture the loaded, isolated file just before save to distinguish a
        # normal save from any identity update Orca may do while opening it.
        before_save = digest_file(project)
        shutil.copyfile(project, work / "before-save.3mf")
        if project_geometry(project) != (initial_faces, initial_matrix):
            results["#201 File > Save Project rewrites the named file"] = "FAIL (file changed before Save)"
            return results
        sent = dispatch_file_command(editor, "Save Project")
        saved_digest = wait_project_write(editor, project, before_save) if sent else None
        saved = saved_digest is not None and project_title(editor) == project.stem and editor.alive()
        results["#201 File > Save Project rewrites the named file"] = (
            f"{'PASS' if saved else 'FAIL'} (command={sent}, path={project}, sha256={saved_digest})")
        if not saved:
            return results
        faces, matrix = project_geometry(project)
        matches = (matrix[:9] == initial_matrix[:9] and matrix[9] == expected_x
                   and matrix[10:] == initial_matrix[10:]
                   and faces == translated_geometry(initial_faces, delta))
        results["#201 saved geometry contains the edit"] = (
            f"{'PASS' if matches else 'FAIL'} (translation={matrix[9:]}, intended X={target})")
        if not matches:
            return results
    finally:
        editor.close()

    if editor.alive() or digest_file(project) != saved_digest:
        results["#201 independently reopening the saved project"] = "FAIL (editor still alive or save changed after close)"
        return results
    shutil.copyfile(project, work / "after-save.3mf")
    reader_args = SimpleNamespace(exe=args.exe, datadir=work / "reopen-profile")
    reader = boot_session(reader_args, model=project)
    try:
        loaded, fraction = wait_arrival(reader, timeout_s=30)
        current_title = project_title(reader)
        independent = loaded and reader.pid != editor.pid and current_title == project.stem
        text = read_reopened_position(reader) if independent else ""
        retained = independent and position_value(text) == expected_x
        results["#201 independently reopening the saved project"] = (
            f"{'PASS' if retained else 'FAIL'} (path={project}, editor_pid={editor.pid}, "
            f"reopen_pid={reader.pid}, title={current_title!r}, modeled={fraction:.3%}, X={text!r})")
        return results
    finally:
        reader.close()


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=FIXTURE).parse_args()
    runs = args.datadir.parent / "feishu-project-cases" / "201"
    runs.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=runs))
    print(f"[m7x201] retained work directory: {work}")
    project = work / "test_project.3mf"
    shutil.copyfile(args.model, project)
    return m7.m7_verdict(run_case(args, project, work))


if __name__ == "__main__":
    raise SystemExit(main())
