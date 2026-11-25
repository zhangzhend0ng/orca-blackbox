#!/usr/bin/env python3
# m7x_254_sphere_layer_pair.py — Edit both sphere layer heights and verify an independent GUI reslice.
# feishu: baseline#254

import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
import m7_common as m7
from harness import anchors, process_panel as panel, winutil
from harness.agent_protocol import MODEL_FIXTURES
from harness.pilot_param_layer_pair import verify_business
from m3_common import add_common_args, boot_session
from m7x_249_add_part import stage as measure_stage
from m8_common import wait_arrival
from harness.model_move_pilot import geometry_unchanged

FIXTURE = HERE / "fixtures" / "feishu_std_sphere.3mf"
TARGET = ("0.20", "0.25")


def require(check, message):
    if not check:
        raise ValueError(message)


def load_sphere(args, work, profile, project):
    session = boot_session(SimpleNamespace(exe=args.exe, datadir=work / profile), model=project)
    try:
        m7.ensure_maximized(session)
        # A 20 mm sphere occupies 0.216% of the guest viewport. The positive
        # object extrusion and mesh checks below independently identify it.
        arrived, fraction = wait_arrival(session, timeout_s=30, min_frac=0.001)
        require(arrived, f"Sphere did not appear in {profile} ({fraction:.3%})")
        return session
    except BaseException:
        session.close()
        raise


def fields(session, expected):
    edits = panel.float_edits_in_view(session)[:2]
    values = [value for _, _, value in edits]
    require(len(edits) == 2 and edits[0][0][1] < edits[1][0][1]
            and all(winutil._window_pid(h) == session.pid for _, h, _ in edits)
            and list(map(Decimal, values)) == list(map(Decimal, expected)),
            f"Quality height fields read {values}, expected {expected}")
    return edits


def quality(session):
    require(panel.click_tab(session, "Quality", "height"), "Quality page did not open")
    require(panel.wait_float_edit(session, timeout_s=20), "Quality fields did not appear")
    fields(session, TARGET)


def set_pair(session, current, wanted, edits_log):
    expected = list(current)
    for index, value in enumerate(wanted):
        rect, hwnd, before = fields(session, expected)[index]
        x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        require(winutil.deepest_child_at(session.hwnd, x, y) == hwnd
                and winutil.window_class(hwnd) == "Edit" and winutil.user32.IsWindowEnabled(hwnd),
                f"Invalid Quality edit {index}")
        # Use the same owned native Edit input sequence as BusinessUI.edit.
        winutil.msg_click_screen(x, y, session.hwnd)
        winutil._send_msg(hwnd, 0x00B1, 0, -1)  # EM_SETSEL
        winutil.msg_text(hwnd, value)
        require(Decimal(winutil.edit_text(hwnd)) == Decimal(value), f"Edit {index} rejected {value}")
        winutil.msg_text(hwnd, "\r")
        winutil._send_msg(hwnd, 0x0008, 0, 0)  # WM_KILLFOCUS commits the wx field.
        time.sleep(6)  # The process pane rebuilds after committing a height.
        expected[index] = value
        row = {"field": ["layer_height", "initial_layer_print_height"][index],
               "before": before, "submitted": value, "pair": [e[2] for e in fields(session, expected)]}
        edits_log.append(row)
        print(f"[m7x254] {row}", flush=True)


def retain_plate(session, private_temp, project, output, started_ns):
    # PartPlate uses a process-specific model directory and a per-plate PID filename.
    # Read the slicer's own output while its process still owns the active Preview.
    pattern = f"snapmaker_orca_model/*/*#{session.pid}#*/Metadata/.{session.pid}.*.gcode"
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline and session.alive():
        matches = list(private_temp.glob(pattern))
        require(len(matches) <= 1, "Ambiguous GUI plate in the fresh session")
        if matches:
            path = matches[0]
            info = path.stat()
            if info.st_mtime_ns >= started_ns and 0 < info.st_size <= 10_000_000:
                raw = path.read_bytes()
                if (len(raw) == info.st_size and path.stat().st_mtime_ns == info.st_mtime_ns
                        and b"; CONFIG_BLOCK_END" in raw and b"; EXECUTABLE_BLOCK_END" in raw):
                    with output.open("xb") as stream:
                        stream.write(raw)
                    return {"pid": session.pid, "plate": str(path.relative_to(private_temp)),
                            "slice_started_ns": started_ns, "modified_ns": info.st_mtime_ns,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "project_sha256": hashlib.sha256(project.read_bytes()).hexdigest()}
        time.sleep(0.4)
    raise ValueError(f"No newly generated complete GUI plate for PID {session.pid} in {private_temp}")


def slice_project(args, work, project, stage, results, analysis):
    private_temp = work / (stage + "-temp")
    private_temp.mkdir()
    with patch.dict(os.environ, {"TMP": str(private_temp), "TEMP": str(private_temp)}):
        session = load_sphere(args, work, stage + "-profile", project)
    try:
        quality(session)
        started_ns = time.time_ns()
        require(m7.op_slice(session, results, key=stage + " slice", timeout_s=120), f"{stage} slice failed")
        score, *_ = anchors.wait_for(session, "tab_preview_active", timeout_s=2)
        if score < anchors.MATCH_THRESHOLD:
            ok, score = anchors.click_and_verify(session, "tab_preview_inactive", "tab_preview_active")
            require(ok, f"{stage} Preview did not open")
        image = anchors.capture_bgr(session)
        require(cv2.imwrite(str(work / (stage + "-preview.png")), image), "Preview capture failed")
        analysis[stage + "_preview"] = {"score": score, "colored_fraction": anchors.has_colored_content(image)}
        require(analysis[stage + "_preview"]["colored_fraction"] > 0, "Empty viewport")
        analysis[stage + "_plate"] = retain_plate(session, private_temp, project, work / (stage + ".gcode"), started_ns)
    finally:
        session.close()


def run(args, work, results, analysis):
    original = args.model.read_bytes()
    require(hashlib.sha256(original).hexdigest() == MODEL_FIXTURES["_sphere"][1], "Wrong sphere fixture")
    # Orca appends the opened filename to its embedded preset IDs. Use the
    # canonical filename that the preserved-settings verifier recognizes.
    source = work / "fixture.3mf"
    source.write_bytes(original)
    with measure_stage(analysis, "baseline_reopen_slice_export"):
        slice_project(args, work, source, "baseline", results, analysis)
    require(source.read_bytes() == original, "Baseline changed the source project")
    saved = work / "sphere-edited.3mf"
    session = load_sphere(args, work, "editor-profile", source)
    try:
        quality(session)
        other = ("0.24", "0.30")
        set_pair(session, TARGET, other, analysis["edits"])
        control = work / "off-target.3mf"
        require(m7.save_project_as(session, control, timeout_s=45), "Off-target save failed")
        with ZipFile(control) as archive:
            config = json.loads(archive.read("Metadata/project_settings.config"))
        pair = [config[k] for k in ("layer_height", "initial_layer_print_height")]
        require(list(map(Decimal, pair)) == list(map(Decimal, other)), f"Off-target save contains {pair}")
        analysis["off_target_saved"] = pair
        set_pair(session, other, TARGET, analysis["edits"])
        require(m7.save_project_as(session, saved, timeout_s=45), "Edited project save failed")
    finally:
        session.close()
    edited = saved.read_bytes()
    require(geometry_unchanged(edited, original), "Sphere mesh or placement changed")
    with measure_stage(analysis, "target_reopen_slice_export"):
        slice_project(args, work, saved, "target", results, analysis)
    require(saved.read_bytes() == edited, "Reopen modified the edited project")
    masks = []
    for name in ("baseline", "target"):
        frame = cv2.imread(str(work / (name + "-preview.png")))
        masks.append(np.ptp(anchors.viewport_crop(frame), axis=2) > anchors.SPREAD_COLORED)
    common, either = np.logical_and(*masks).sum(), np.logical_or(*masks).sum()
    overlap = float(common / either) if either else 0
    analysis["colored_preview_overlap"] = overlap
    require(overlap >= 0.9, f"Colored Preview paths no longer agree ({overlap:.1%})")
    for stage, model in (("baseline", original), ("target", edited)):
        analysis[stage] = verify_business(model, original, (work / (stage + ".gcode")).read_bytes())
    keys = ("layer_count", "first_z", "last_z", "layer_height", "initial_layer_print_height")
    require(all(analysis["baseline"][k] == analysis["target"][k] for k in keys), "Different layer schedules")
    results["GUI edit, reopened sphere and both extrusion schedules"] = "PASS"


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=FIXTURE).parse_args()
    root = args.datadir.resolve().parent / "feishu-object-cases" / "254"
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    print(f"[m7x254] retained work directory: {work}", flush=True)
    results = {}
    analysis = {"edits": [], "timings": {}}
    try:
        run(args, work, results, analysis)
    except Exception as error:
        analysis["failure"] = f"{type(error).__name__}: {error}"
        results["Feishu #254"] = "FAIL (" + analysis["failure"] + ")"
    finally:
        (work / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
