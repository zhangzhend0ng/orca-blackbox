#!/usr/bin/env python3
# m7t77.py — Feishu #77 主流程-模板: 基础模型分割验证
#   M-01 import -> M-14 cut -> M-09 move -> M-03 arrange -> M-02 slice
#   -> O-02 close
# The Cut gizmo (GLGizmoCut3D, tooltip 'Cut [C]') opens an ImGui window
# with a 'Perform cut' button; the default plane at half height splits the
# object in two — observable as two blobs on the plate. The M-09 move is
# driven through the Move gizmo's Position X field (m6a pattern).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import winutil  # noqa: E402
from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t77]"


def perform_cut(session):
    """Activate the Cut gizmo and click its 'Perform cut' ImGui button."""
    if not m7.select_model(session):
        return False
    x, tip = m7.find_slot(session, lambda t: "cut" in t)
    if x is None:
        print(f"{LOG} cut slot not found")
        return False
    m7.click_slot(session, x)
    time.sleep(2.0)
    words = m7.words(session)
    hit = next((w for w in words if w[0].lower().startswith("perform")), None)
    if not hit:
        print(f"{LOG} no 'Perform' button in the cut window "
              f"({[w[0] for w in words][:12]})")
        return False
    sx, sy = m7.client(session, hit[1] + 20, hit[2] + 5)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    winutil.real_click_screen(sx, sy)
    time.sleep(3.0)
    return True


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    results["cut performs"] = (
        "PASS" if perform_cut(session) else "FAIL")
    time.sleep(2.0)
    results["two parts after cut"] = (
        "PASS" if m7.blob_count(session) >= 2 else "FAIL")
    ok, text = m7.op_gizmo_field(session, lambda t: "move" in t,
                                 "position", 0, "30")
    results["move X commits 30"] = (
        "PASS" if ok else f"FAIL (now {text!r})")
    arr_x, _tip = m7.find_slot(session, lambda t: "arrange" in t)
    if arr_x:
        m7.click_slot(session, arr_x)
        time.sleep(5.0)
    results["arrange runs"] = "PASS" if arr_x else "FAIL"
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
