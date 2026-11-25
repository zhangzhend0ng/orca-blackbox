#!/usr/bin/env python3
# m7x_201_save_project_reopen.py — Feishu #201: save a named project and reopen the same file.
# feishu: baseline#201

import argparse
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7
from harness import topbar_util, winutil
from harness.project_3mf import _archive, _geometry
from m3_common import add_common_args, boot_session
from m8_common import wait_arrival
from project_file_cases import digest_file, dispatch_file_command, project_title, wait_project_write

FIXTURE = HERE / "fixtures" / "agent_layer_cube.3mf"


def project_geometry(path):
    faces, _, matrix = _geometry(_archive(path.read_bytes(), lambda: False))
    return faces, matrix


def translated_geometry(faces, x_delta):
    return tuple(tuple((x + x_delta, y, z) for x, y, z in face) for face in faces)


def dispatch_edit_command(session, label):
    menu = topbar_util.open_dropdown_menu(session)
    if not menu:
        print("[m7x201] Edit dropdown did not open")
        return False
    _, _, root = menu
    try:
        edit_index = topbar_util.find_item(root, "Edit")
        if edit_index is None:
            print(f"[m7x201] Edit missing in {topbar_util.menu_items(root)!r}")
            return False
        _, edit = topbar_util.item_info(root, edit_index)
        rows = topbar_util.menu_items(edit)
        for index, text, flags in rows:
            if text.partition("\t")[0].replace("&", "").strip().casefold() == label and not flags & 3:
                print(f"[m7x201] Edit > {text!r}")
                return topbar_util.activate_menu_item(session, edit, index)
        print(f"[m7x201] {label!r} not enabled in {rows!r}")
        return False
    finally:
        topbar_util.close_menu_windows(session.pid)


def move_existing_object(session, origin):
    # The archive precondition proves that Select All selects exactly this cube.
    canvas = winutil.deepest_child_at(session.hwnd, *m7.client(session, *origin))
    if (winutil.window_class(canvas) != "wxGLCanvas" or not winutil.user32.IsWindowEnabled(canvas)
            or winutil._window_pid(canvas) != session.pid):
        print(f"[m7x201] unexpected canvas: {canvas:#x}, {winutil.window_class(canvas)!r}")
        return None
    if not dispatch_edit_command(session, "select all"):
        return None
    time.sleep(0.6)
    # Orca moves a selected instance 10 mm along world X for unmodified Right.
    winutil.msg_key(canvas, 0x27)  # VK_RIGHT.
    time.sleep(1.2)
    winutil.msg_key(canvas, 0x1B)  # Escape clears selection for comparable rendering.
    time.sleep(0.8)
    return m7.find_centroid(session)


def run_case(args, project, work):
    results = {}
    initial_faces, initial_matrix = project_geometry(project)
    initial_x = initial_matrix[9]
    delta = 10
    expected_x = initial_x + delta

    editor_args = SimpleNamespace(exe=args.exe, datadir=work / "edit-profile")
    editor = boot_session(editor_args, model=project)
    try:
        loaded, fraction = wait_arrival(editor, timeout_s=30)
        m7.ensure_maximized(editor)
        original_title = project_title(editor)
        origin = m7.find_centroid(editor)
        print(f"[m7x201] original pid={editor.pid}, title={original_title!r}, "
              f"project={project}, modeled={fraction:.3%}, X={initial_x}, optical centroid={origin}")
        if not (loaded and original_title == project.stem and origin is not None):
            return {"#201 named project opened": "FAIL"}
        results["#201 named project opened"] = "PASS"

        edited = move_existing_object(editor, origin)
        changed = edited is not None and math.dist(origin, edited) >= 4
        results["#201 existing object's X changed"] = (
            f"{'PASS' if changed else 'FAIL'} (viewport centroid {origin} -> {edited}; "
            f"initial X={initial_x}, target X={expected_x})")
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
            f"{'PASS' if matches else 'FAIL'} (translation={matrix[9:]}, intended X={expected_x})")
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
        m7.ensure_maximized(reader)
        current_title = project_title(reader)
        independent = loaded and reader.pid != editor.pid and current_title == project.stem
        observed = m7.find_centroid(reader) if independent else None
        retained = (observed is not None and math.dist(observed, edited) <= 4
                    and math.dist(observed, origin) >= 4)
        results["#201 independently reopening the saved project"] = (
            f"{'PASS' if retained else 'FAIL'} (path={project}, editor_pid={editor.pid}, "
            f"reopen_pid={reader.pid}, title={current_title!r}, modeled={fraction:.3%}, "
            f"initial centroid={origin}, edited={edited}, reopened={observed})")
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
