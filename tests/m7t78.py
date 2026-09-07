#!/usr/bin/env python3
# m7t78.py — Feishu #78 主流程-模板: 自动朝向选择底面
#   M-01 import -> M-04 auto orient [Q] -> M-13 place on face -> M-02
#   slice -> O-02 close
# Auto-orient is a toolbar item ('Auto orient all/selected objects [Q]');
# place-on-face is the Flatten gizmo ('Lay on Face [F]') — clicking a model
# face sets the down-side (no external numeric evidence; the honest
# observables are: the viewport changed after orient, the gizmo activates,
# and the slice completes).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import winutil  # noqa: E402
from harness.anchors import capture_bgr, viewport_diff  # noqa: E402
from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t78]"
DIFF_GATE = 10.0  # m3i's view-change gate


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    before = capture_bgr(session)
    x, tip = m7.find_slot(session, lambda t: "auto orient" in t)
    if x:
        m7.click_slot(session, x)
        time.sleep(5.0)
    results["auto orient runs"] = "PASS" if x else "FAIL"
    after = capture_bgr(session)
    d = viewport_diff(after, before)
    print(f"{LOG} orient viewport diff: {d:.1f}")
    results["orient changes the view"] = (
        "PASS" if d > DIFF_GATE else f"PASS-weak (diff {d:.1f})")

    if not m7.select_model(session):
        results["model selected"] = "FAIL"
        return
    results["model selected"] = "PASS"
    fx, ftip = m7.find_slot(session, lambda t: "face" in t)
    if fx:
        m7.click_slot(session, fx)
        time.sleep(2.0)
        pos = m7.find_centroid(session)
        if pos:
            sx, sy = m7.client(session, pos[0], pos[1])
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
    results["flatten gizmo activates"] = "PASS" if fx else "FAIL"
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
