#!/usr/bin/env python3
# m7t89.py — Feishu #89 主流程-模板: 模型创建旋转涂色切片
#   O-01 open -> M-20 model create (Add Primitive > Cube) -> M-11 rotate
#   Z 45 -> M-17 color painting (dab) -> M-02 slice -> O-02 close
# The color-paint dab is m4e's paint primitive against the MmSegmentation
# gizmo ('Color painting [N]').

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import winutil  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t89]"


def steps(session, results):
    results["empty bed at boot"] = (
        "PASS" if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR
        else "FAIL")
    added = m7.op_add_primitive(session, "cube")
    results["model created (M-20)"] = "PASS" if added else "FAIL"
    if not added:
        return
    ok, text = m7.op_gizmo_field(session, lambda t: "rotate" in t,
                                 "rotation", 2, "45")
    results["rotate Z commits 45"] = (
        "PASS" if ok else f"FAIL (now {text!r})")

    # M-17: color painting dab (the paint toolbar sits at the PAINT band)
    if not m7.select_model(session):
        results["model selected"] = "FAIL"
        return
    results["model selected"] = "PASS"
    px, ptip = m7.find_slot(session, lambda t: "color painting" in t)
    if px:
        m7.click_slot(session, px)
        time.sleep(2.5)
        pos = m7.find_centroid(session)
        if pos:
            sx, sy = m7.client(session, *pos)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.5)
    results["color painting activates"] = (
        f"PASS ({ptip!r})" if px else "FAIL")
    m7.op_slice(session, results)


if __name__ == "__main__":
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=None)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        steps(session, results)
        raise SystemExit(m7.m7_verdict(results))
    finally:
        session.close()
        print("[m7] app closed")
