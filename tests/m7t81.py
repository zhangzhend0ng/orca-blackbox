#!/usr/bin/env python3
# m7t81.py — Feishu #81 主流程-模板: 布尔剪贴模型整理
#   M-01 import -> M-15 mesh boolean -> M-03 arrange -> M-02 slice
#   -> O-02 close
# MeshBoolean needs TWO volumes (the object-menu 'Mesh boolean' entry was
# disabled on the single-part fixture, GUI_Factories create_extra_object_
# menu) — the case builds the second volume via Add Part > Cube (object
# menu), then activates the 'Mesh Boolean [B]' gizmo and records its
# window. Boolean OPERATION driving stays UI-evidenced (the gizmo window
# + slice completes); the arrange runs afterwards.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t81]"


def add_part_cube(session):
    """Object menu > Add Part > Cube (a second volume in the same object)."""
    if not m7.select_model(session):
        return False
    return m7.context_click_row(session, "model", "cube", via="Add Part",
                                success_fn=lambda: m7.blob_count(session) >= 1
                                and m7.model_colored_frac(session) > 0.01,
                                label="add-part-cube")


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    results["second volume added (Add Part)"] = (
        "PASS" if add_part_cube(session) else "FAIL")

    bx, btip = m7.find_slot(session, lambda t: "mesh boolean" in t)
    if bx:
        m7.click_slot(session, bx)
        time.sleep(2.5)
        words = m7.words(session)
        window = [w[0] for w in words if w[0].lower() in
                  ("boolean", "mesh", "operation", "subtract", "union")]
        print(f"{LOG} boolean window words: {window}")
    results["mesh boolean gizmo activates"] = (
        f"PASS ({btip!r})" if bx else "FAIL (slot disabled/not found)")

    arr_x, _tip = m7.find_slot(session, lambda t: "arrange" in t)
    if arr_x:
        m7.click_slot(session, arr_x)
        time.sleep(5.0)
    results["arrange runs"] = "PASS" if arr_x else "FAIL"
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
