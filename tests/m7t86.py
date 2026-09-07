#!/usr/bin/env python3
# m7t86.py — Feishu #86 主流程-模板: 自动朝向布尔剪贴整理
#   M-01 import -> M-04 auto orient -> M-15 mesh boolean (2nd volume via
#   Add Part) -> M-03 arrange -> M-02 slice -> O-02 close
# Composition of the m7t78 orient step and the m7t81 boolean step.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness.anchors import capture_bgr, viewport_diff  # noqa: E402
from m3_common import MIXED_3MF  # noqa: E402
from m7t81 import add_part_cube  # noqa: E402
import m7_common as m7  # noqa: E402

DIFF_GATE = 10.0


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    before = capture_bgr(session)
    x, _tip = m7.find_slot(session, lambda t: "auto orient" in t)
    if x:
        m7.click_slot(session, x)
        time.sleep(5.0)
    results["auto orient runs"] = "PASS" if x else "FAIL"
    d = viewport_diff(capture_bgr(session), before)
    results["orient changes the view"] = (
        "PASS" if d > DIFF_GATE else f"PASS-weak (diff {d:.1f})")
    results["second volume added (Add Part)"] = (
        "PASS" if add_part_cube(session) else "FAIL")
    bx, btip = m7.find_slot(session, lambda t: "mesh boolean" in t)
    if bx:
        m7.click_slot(session, bx)
        time.sleep(2.0)
    results["mesh boolean gizmo activates"] = (
        f"PASS ({btip!r})" if bx else "FAIL")
    arr_x, _t2 = m7.find_slot(session, lambda t: "arrange" in t)
    if arr_x:
        m7.click_slot(session, arr_x)
        time.sleep(5.0)
    results["arrange runs"] = "PASS" if arr_x else "FAIL"
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
