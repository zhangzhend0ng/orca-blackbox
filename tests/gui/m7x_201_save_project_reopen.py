#!/usr/bin/env python3
# m7x_201_save_project_reopen.py — Feishu #201: save a named project and reopen the same file.
# feishu: baseline#201

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7
from harness import winutil
from harness.project_3mf import _archive, _geometry
from m3_common import add_common_args, boot_session
from m8_common import wait_arrival
from m8x_48_modal_color_header import bring_main_to_mouse, request_background_focus
from project_file_cases import digest_file, dispatch_file_command, project_title, wait_project_write

FIXTURE = HERE / "fixtures" / "agent_layer_cube.3mf"


def project_geometry(path):
    faces, _, matrix = _geometry(_archive(path.read_bytes(), lambda: False))
    return faces, matrix


def translated_geometry(faces, x_delta):
    return tuple(tuple((x + x_delta, y, z) for x, y, z in face) for face in faces)


def move_existing_object(session, origin):
    if not bring_main_to_mouse(session.hwnd):
        print("[m7x201] could not expose Orca on the guest desktop")
        return None
    x, y = origin
    point = m7.client(session, x, y)
    canvas = winutil.deepest_child_at(session.hwnd, *point)
    if (winutil.window_class(canvas) != "wxGLCanvas" or not winutil.user32.IsWindowEnabled(canvas)
            or winutil._window_pid(canvas) != session.pid):
        print(f"[m7x201] unexpected canvas: {canvas:#x}, {winutil.window_class(canvas)!r}")
        return None

    def cube_crop():
        radius = 25
        return m7.capture_bgr(session)[y - radius:y + radius, x - radius:x + radius].astype(int)

    def selection_delta(raw):
        return float(np.mean(np.max(np.abs(cube_crop() - raw), axis=2) >= 20))

    def focus_canvas():
        focus = request_background_focus(session.hwnd, canvas)
        return bool(focus and focus[1][1] == canvas
                    and winutil.user32.GetForegroundWindow() == session.hwnd)

    if not focus_canvas():
        print("[m7x201] guest input queue focus did not reach the Prepare canvas")
        return None
    raw = cube_crop()
    winutil.user32.SetCursorPos(*point)
    time.sleep(0.3)  # Let the canvas resolve the hovered model before clicking.
    winutil.msg_click_screen(*point, session.hwnd)
    time.sleep(0.8)
    selection = selection_delta(raw)
    if selection < 0.10:
        if not focus_canvas():
            return None
        # The archive precondition proves that Ctrl+A can select only this cube.
        # Real input preserves the modifier state the canvas's wxEVT_CHAR reads.
        m7.mdu._send_keys([(0x11, False), (ord("A"), False),
                           (ord("A"), True), (0x11, True)])
        time.sleep(0.8)
        selection = selection_delta(raw)
    print(f"[m7x201] selected cube pixel change={selection:.1%}, canvas={canvas:#x}")
    if not focus_canvas():
        return None

    # Orca moves a selected instance 10 mm along world X for unmodified Right.
    m7.mdu._send_keys([(0x27, False), (0x27, True)])
    time.sleep(1.2)
    m7.mdu._send_keys([(0x1B, False), (0x1B, True)])  # Comparable, unselected rendering.
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
        print(f"[m7x201] edit viewport centroid {origin} -> {edited}, moved={changed}; "
              f"initial X={initial_x}, target X={expected_x}")

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
        shutil.copyfile(project, work / "after-save.3mf")
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

    try:
        editor_exit = editor.popen.wait(timeout=8)
    except subprocess.TimeoutExpired:
        results["#201 independently reopening the saved project"] = "FAIL (editor still alive)"
        return results
    settled_digest = digest_file(project)
    settled_geometry = project_geometry(project)
    print(f"[m7x201] editor exited: pid={editor.pid}, exit_code={editor_exit}, "
          f"save SHA-256={saved_digest}, pre-reopen SHA-256={settled_digest}, "
          f"pre-reopen translation={settled_geometry[1][9:]}")
    if settled_geometry != (faces, matrix):
        results["#201 independently reopening the saved project"] = "FAIL (saved geometry changed after editor exit)"
        return results
    shutil.copyfile(project, work / "reopen-input.3mf")
    reader_args = SimpleNamespace(exe=args.exe, datadir=work / "reopen-profile")
    reader = boot_session(reader_args, model=project)
    try:
        loaded, fraction = wait_arrival(reader, timeout_s=30)
        m7.ensure_maximized(reader)
        current_title = project_title(reader)
        independent = loaded and reader.pid != editor.pid and current_title == project.stem
        observed = m7.find_centroid(reader) if independent else None
        retained = (observed is not None and edited is not None and math.dist(observed, edited) <= 4
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
