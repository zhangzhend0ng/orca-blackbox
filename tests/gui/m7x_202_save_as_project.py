#!/usr/bin/env python3
# m7x_202_save_as_project.py — Feishu #202: Save As leaves the source intact and redirects Save.
# feishu: baseline#202

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7
from harness import export_util, winutil
from m2_slice_chain import wait_model_loaded
from m3_common import MIXED_3MF, add_common_args, boot_session
from m7x_199_new_project_title import import_unsaved_model
from project_file_cases import digest_file, dispatch_file_command, project_title, wait_project_write

LOG = "[m7x202]"
SOURCE_NAME = "test_project.3mf"
TARGET_NAME = "test_project_v2.3mf"


def project_contents(path):
    """Read printer preset, object names and plate instances from an actual 3MF."""
    with ZipFile(path) as project:
        model = ET.fromstring(project.read("3D/3dmodel.model"))
        object_info = ET.fromstring(project.read("Metadata/model_settings.config"))
        settings = json.loads(project.read("Metadata/project_settings.config"))
    names = tuple(sorted(element.attrib["value"] for element in object_info.findall("./object/metadata")
                         if element.attrib.get("key") == "name"))
    instances = len(model.findall("./{*}build/{*}item"))
    printer_id = settings["printer_settings_id"]
    print(f"{LOG} {path.name} raw printer_settings_id={printer_id!r}")
    # Orca adds the project supplying this cached preset as a display suffix.
    printer_id = printer_id.removesuffix(f"({TARGET_NAME})").removesuffix(f"({SOURCE_NAME})")
    printer_signature = (printer_id, settings["printer_model"], settings["printer_variant"],
                         tuple(settings["nozzle_diameter"]))
    return printer_signature, names, instances


def title_matches(session, expected, timeout_s=12.0):
    deadline = time.monotonic() + timeout_s
    while session.alive() and time.monotonic() < deadline:
        if project_title(session) == expected:
            print(f"{LOG} active project title={expected!r}")
            return True
        time.sleep(0.3)
    print(f"{LOG} active project title={project_title(session)!r}, expected {expected!r}")
    return False


def save_as(session, destination):
    if not dispatch_file_command(session, "Save Project as"):
        return False
    dialog = export_util.wait_save_dialog(session.pid, timeout_s=12.0)
    if not dialog:
        print(f"{LOG} Save Project as did not open a native chooser")
        return False
    hwnd = dialog[3]
    edit = export_util.find_edit(hwnd)
    if not edit:
        print(f"{LOG} no filename Edit in {dialog[1]!r}")
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(destination))
    typed = winutil.edit_text(edit, size=260)
    print(f"{LOG} chooser={dialog[1]!r}, actual selected filename={typed!r}")
    if typed != str(destination):
        return False
    winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 1, 0)  # IDOK
    deadline = time.monotonic() + 8.0
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.25)
    closed = not winutil.user32.IsWindowVisible(hwnd)
    print(f"{LOG} Save As chooser closed={closed}")
    return closed


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF).parse_args()
    artifacts = args.datadir.resolve().parent / "feishu-project-cases" / "202"
    artifacts.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(dir=artifacts))
    old_path = workspace / "source" / SOURCE_NAME
    new_path = workspace / "target" / TARGET_NAME
    old_path.parent.mkdir()
    new_path.parent.mkdir()
    shutil.copyfile(args.model, old_path)
    args.datadir = workspace / "profile"
    seed_digest = digest_file(old_path)
    print(f"{LOG} isolated source={old_path}, target={new_path}, fixture copy SHA-256={seed_digest}")

    session = boot_session(args, model=old_path)
    try:
        arrived, model_fraction = wait_model_loaded(session, timeout_s=65)
        if not arrived or not title_matches(session, old_path.stem):
            return m7.m7_verdict({"#202 source project is open": f"FAIL (model={model_fraction:.3%})"})
        m7.ensure_maximized(session)
        source_before = digest_file(old_path)
        scene_before = project_contents(old_path)
        print(f"{LOG} source before Save As SHA-256={source_before}, scene={scene_before!a}")
        if not source_before or not scene_before[1] or scene_before[2] == 0 or new_path.exists():
            return m7.m7_verdict({"#202 isolated source/target precondition": "FAIL"})

        selected = save_as(session, new_path)
        first_digest = wait_project_write(session, new_path, None, timeout_s=30) if selected else None
        if not first_digest:
            return m7.m7_verdict({"#202 Save As generates new project": "FAIL"})
        shutil.copyfile(new_path, workspace / "after-save-as.3mf")
        source_after_as = digest_file(old_path)
        scene_as = project_contents(new_path)
        title_as = title_matches(session, new_path.stem)
        print(f"{LOG} after Save As source SHA-256={source_after_as}, target SHA-256={first_digest}, "
              f"target scene={scene_as!a}")
        results = {
            "#202 Save As generates new project": "PASS" if scene_as == scene_before else "FAIL",
            "#202 source bytes unchanged after Save As": "PASS" if source_after_as == source_before else "FAIL",
            "#202 current title points to new name": "PASS" if title_as else "FAIL",
        }
        if not all(value == "PASS" for value in results.values()):
            return m7.m7_verdict(results)

        edited = import_unsaved_model(session)
        unsaved_digest = digest_file(new_path)
        print(f"{LOG} after STL import before ordinary Save: changed on screen={edited}, "
              f"target SHA-256={unsaved_digest}")
        if not edited or unsaved_digest != first_digest:
            results["#202 later edit remains unsaved before ordinary Save"] = "FAIL"
            return m7.m7_verdict(results)

        saved = dispatch_file_command(session, "Save Project")
        final_digest = wait_project_write(session, new_path, first_digest, timeout_s=30) if saved else None
        old_final = digest_file(old_path)
        final_scene = project_contents(new_path) if final_digest else None
        print(f"{LOG} after ordinary Save source SHA-256={old_final}, target SHA-256={final_digest}, "
              f"target scene={final_scene!a}")
        old_names = Counter(name.casefold() for name in scene_as[1])
        new_names = Counter(name.casefold() for name in final_scene[1]) if final_scene else Counter()
        added_names = tuple((new_names - old_names).elements())
        edit_persisted = (final_scene is not None and final_scene[0] == scene_as[0]
                          and not (old_names - new_names) and added_names in (("prusa",), ("prusa.stl",))
                          and final_scene[2] == scene_as[2] + 1)
        results["#202 ordinary Save persists edit to new path"] = (
            "PASS" if edit_persisted and title_matches(session, new_path.stem) else "FAIL")
        results["#202 source bytes unchanged after ordinary Save"] = (
            "PASS" if old_final == source_before else "FAIL")
        return m7.m7_verdict(results)
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
