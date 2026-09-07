#!/usr/bin/env python3
# m7t87.py — Feishu #87 主流程-模板: 选择底面可变层高绘制支撑
#   M-01 import -> M-13 place on face -> M-08 variable layer height
#   -> M-16 paint-on supports -> M-02 slice -> O-02 close
# Composition of m7t78's flatten step and m7t80's VLH + support-paint
# steps.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import winutil  # noqa: E402
from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    if not m7.select_model(session):
        results["model selected"] = "FAIL"
        return
    results["model selected"] = "PASS"

    fx, _tip = m7.find_slot(session, lambda t: "face" in t)
    if fx:
        m7.click_slot(session, fx)
        time.sleep(2.0)
        pos = m7.find_centroid(session)
        if pos:
            sx, sy = m7.client(session, *pos)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
    results["flatten gizmo activates"] = "PASS" if fx else "FAIL"

    vx, vtip = m7.find_slot(session, lambda t: "variable layer" in t)
    if vx:
        m7.click_slot(session, vx)
        time.sleep(2.0)
    results["variable layer height activates"] = (
        f"PASS ({vtip!r})" if vx else "FAIL")

    probe = winutil.client_to_screen(session.hwnd, 600, 400)
    hwnd = winutil.deepest_child_at(session.hwnd, *probe) or session.hwnd
    winutil._send_msg(hwnd, 0x0100, 0x1B, 0)  # WM_KEYDOWN ESC (close VLH)
    time.sleep(1.5)

    px, ptip = m7.find_slot(session, lambda t: "support painting" in t)
    if px:
        m7.click_slot(session, px)
        time.sleep(2.0)
        pos = m7.find_centroid(session)
        if pos:
            sx, sy = m7.client(session, *pos)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.5)
    results["support painting activates"] = (
        f"PASS ({ptip!r})" if px else "FAIL")
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
