#!/usr/bin/env python3
# m7x_251_reload_from_disk.py — Feishu #251: reload a modified STL and observe missing-source handling.
# feishu: baseline#251

import argparse
import re
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7
import m8_common as m8
from harness import export_util, topbar_util, winutil
from m3_common import add_common_args, boot_session
from m7x_199_new_project_title import save_prompt_words
from m7x_202_save_as_project import save_as
from model_context_cases import open_model_menu
from project_file_cases import digest_file, wait_project_write

LOG = "[m7x251]"
MENU = "Reload from disk"


def write_cube(path, size):
    """Write a 12-triangle binary STL with dimensions in millimeters."""
    points = ((0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0),
              (0, 0, size), (size, 0, size), (size, size, size), (0, size, size))
    faces = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
    triangle = struct.Struct("<12fH")
    with path.open("wb") as output:
        output.write(struct.pack("<80sI", b"Orca black-box #251 cube", len(faces)))
        for face in faces:
            vertices = tuple(axis for index in face for axis in points[index])
            output.write(triangle.pack(0, 0, 0, *vertices, 0))


def read_mesh(project):
    """Read the single exported model and original source association."""
    with ZipFile(project) as archive:
        models = [ET.fromstring(archive.read(name)) for name in archive.namelist()
                  if name.startswith("3D/") and name.endswith(".model")]
        settings = ET.fromstring(archive.read("Metadata/model_settings.config"))
    meshes = [mesh for model in models for mesh in model.findall("./{*}resources/{*}object/{*}mesh")]
    instances = sum(len(model.findall("./{*}build/{*}item")) for model in models)
    if len(meshes) != 1 or instances != 1:
        raise ValueError(f"expected 1 mesh and 1 instance, got {len(meshes)} and {instances}")
    vertices = meshes[0].findall("./{*}vertices/{*}vertex")
    spans = []
    for axis in "xyz":
        coordinates = [float(vertex.attrib[axis]) for vertex in vertices]
        spans.append(max(coordinates) - min(coordinates))
    source = settings.find("./object/part/metadata[@key='source_file']")
    return tuple(spans), source.get("value", "") if source is not None else ""


def observe_mesh(session, project, source):
    if not save_as(session, project) or not wait_project_write(session, project, None, timeout_s=30):
        print(f"{LOG} could not save geometry snapshot {project}")
        return None
    dimensions, reported_source = read_mesh(project)
    source_matches = reported_source and Path(reported_source) == source
    print(f"{LOG} {project.name}: XYZ mm={dimensions}, source_file={reported_source!r}, "
          f"same source={bool(source_matches)}")
    return dimensions if source_matches else None


def reload_selected(session):
    opened = open_model_menu(session, MENU)
    if opened is None:
        return False
    _, hmenu, index = opened
    try:
        return topbar_util.activate_menu_item(session, hmenu, index)
    finally:
        topbar_util.close_menu_windows(session.pid)


def observe_missing_dialog(session, source, screenshot):
    dialog = export_util.wait_toplevel(session.pid, lambda cls, _t, _r: cls == "#32770", timeout_s=10)
    if not dialog:
        print(f"{LOG} missing source: no Orca dialog")
        return False, True
    _, title, _, hwnd = dialog
    try:
        width, height, raw = winutil.capture_window(hwnd)
        image = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
        saved = cv2.imwrite(str(screenshot), cv2.cvtColor(image, cv2.COLOR_BGRA2BGR))
        print(f"{LOG} missing-source dialog screenshot saved={saved}: {screenshot}")
    except (winutil.CaptureError, cv2.error) as exc:
        print(f"{LOG} missing-source dialog screenshot unavailable: {exc}")
    edit = export_util.find_edit(hwnd)
    selected = winutil.edit_text(edit, size=260) if edit else ""
    if edit and "select a file" in title.casefold():
        body = ""
        behavior = "replacement file chooser"
    else:
        body = " ".join(word[0] for word in save_prompt_words(hwnd))
        behavior = "message dialog"
    message = f"{title} {body}".casefold()
    explicit_error = (behavior == "message dialog" and bool(re.search(
        r"\b(?:file|source)\b.*\b(?:not found|does not exist|missing|cannot be found)\b", message)))
    print(f"{LOG} missing {source}: {behavior}, title={title!r}, filename={selected!r}, "
          f"body={body!r}, explicit missing error={explicit_error}")
    if edit:
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)  # IDCANCEL
    else:
        m7.click_dialog_button(hwnd, "OK", fallback_first=False)
    deadline = time.monotonic() + 8
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.25)
    closed = not winutil.user32.IsWindowVisible(hwnd)
    print(f"{LOG} missing-source dialog closed={closed}")
    return explicit_error, closed


def main():
    args = add_common_args(argparse.ArgumentParser()).parse_args()
    root = args.datadir.resolve().parent / "feishu-object-cases" / "251"
    root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    source = workspace / "reload_cube.stl"
    original = workspace / "source-20mm.stl"
    modified = workspace / "source-30mm.stl"
    project_before = workspace / "before-reload.3mf"
    project_after = workspace / "after-reload.3mf"
    project_missing = workspace / "after-missing.3mf"
    write_cube(original, 20)
    write_cube(modified, 30)
    shutil.copyfile(original, source)
    print(f"{LOG} work directory={workspace}, isolated source={source}, "
          f"20 mm STL SHA-256={digest_file(source)}")
    args.datadir = workspace / "profile"
    session = boot_session(args, model=source)
    try:
        arrived, fraction = m8.wait_arrival(session, timeout_s=45)
        if not arrived:
            return m7.m7_verdict({"#251 external STL imported": f"FAIL (colored fraction={fraction:.3%})"})
        m7.ensure_maximized(session)
        first = observe_mesh(session, project_before, source)
        results = {"#251 imported external STL has 20 mm XYZ": "PASS" if first == (20, 20, 20) else "FAIL"}
        if first != (20, 20, 20):
            return m7.m7_verdict(results)

        shutil.copyfile(modified, source)
        print(f"{LOG} updated exact source path={source}, 30 mm STL SHA-256={digest_file(source)}")
        invoked = reload_selected(session)
        second = observe_mesh(session, project_after, source) if invoked else None
        updated = second == (30, 30, 30)
        results["#251 context reload reads 30 mm XYZ from disk"] = "PASS" if updated else "FAIL"
        if not updated:
            return m7.m7_verdict(results)

        source.unlink()
        print(f"{LOG} deleted isolated source={source}, source still exists={source.exists()}")
        missing_invoked = reload_selected(session)
        explicit, closed = (
            observe_missing_dialog(session, source, workspace / "missing-dialog.png")
            if missing_invoked else (False, False)
        )
        results["#251 context reload displays explicit missing-source error"] = "PASS" if explicit else "FAIL"
        final = observe_mesh(session, project_missing, source) if closed else None
        results["#251 missing source leaves previous 30 mm model"] = (
            "PASS" if final == second else "FAIL")
        return m7.m7_verdict(results)
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
