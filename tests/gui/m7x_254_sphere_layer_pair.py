#!/usr/bin/env python3
# m7x_254_sphere_layer_pair.py — Edit both sphere layer heights and verify an independent GUI reslice.
# feishu: baseline#254

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

import cv2

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
import m7_common as m7
from harness import anchors, process_panel as panel, winutil
from harness.agent_protocol import MODEL_FIXTURES
from harness.pilot_param_layer_pair import verify_business
from m3_common import add_common_args
from m7x_250_negative_part import load_fixture, slice_and_export
from harness.model_move_pilot import geometry_unchanged

FIXTURE = HERE / "fixtures" / "feishu_std_sphere.3mf"
TARGET = ("0.20", "0.25")


def require(check, message):
    if not check:
        raise ValueError(message)


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
        after = panel.real_edit_set(session, rect, hwnd, value)
        require(after is not None and Decimal(after) == Decimal(value), f"Edit {index} read {after}")
        panel.neutralize_focus(session)
        time.sleep(6)  # The process pane rebuilds after committing a height.
        expected[index] = value
        row = {"field": ["layer_height", "initial_layer_print_height"][index],
               "before": before, "submitted": value, "pair": [e[2] for e in fields(session, expected)]}
        edits_log.append(row)
        print(f"[m7x254] {row}", flush=True)


def slice_project(args, work, project, stage, results, analysis):
    session, arrived = load_fixture(args, work, stage + "-profile", project)
    try:
        require(arrived, f"{stage} sphere did not appear")
        quality(session)
        require(slice_and_export(session, results, stage + " slice", work / (stage + ".gcode")),
                f"{stage} G-code export failed")
        score, *_ = anchors.wait_for(session, "tab_preview_active", timeout_s=2)
        if score < anchors.MATCH_THRESHOLD:
            ok, score = anchors.click_and_verify(session, "tab_preview_inactive", "tab_preview_active")
            require(ok, f"{stage} Preview did not open")
        image = anchors.capture_bgr(session)
        require(cv2.imwrite(str(work / (stage + "-preview.png")), image), "Preview capture failed")
        analysis[stage + "_preview"] = {"score": score, "colored_fraction": anchors.has_colored_content(image)}
        require(analysis[stage + "_preview"]["colored_fraction"] > 0, "Empty viewport")
    finally:
        session.close()


def run(args, work, results, analysis):
    original = args.model.read_bytes()
    require(hashlib.sha256(original).hexdigest() == MODEL_FIXTURES["_sphere"][1], "Wrong sphere fixture")
    baseline = work / "default.3mf"
    baseline.write_bytes(original)
    slice_project(args, work, baseline, "baseline", results, analysis)
    source = work / "edit-source.3mf"
    source.write_bytes(original)
    saved = work / "sphere-edited.3mf"
    session, arrived = load_fixture(args, work, "editor-profile", source)
    try:
        require(arrived, "Edit source missing")
        quality(session)
        other = ("0.24", "0.30")
        set_pair(session, TARGET, other, analysis["edits"])
        set_pair(session, other, TARGET, analysis["edits"])
        require(m7.save_project_as(session, saved, timeout_s=45), "Edited project save failed")
    finally:
        session.close()
    edited = saved.read_bytes()
    require(geometry_unchanged(edited, original), "Sphere mesh or placement changed")
    slice_project(args, work, saved, "target", results, analysis)
    require(saved.read_bytes() == edited, "Reopen modified the edited project")
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
    analysis = {"edits": []}
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
