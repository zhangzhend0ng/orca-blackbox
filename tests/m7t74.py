#!/usr/bin/env python3
# m7t74.py — Feishu #74 主流程-模板: 单模型切片调整测试
#   M-01 import -> M-09 move -> M-11 rotate Z 45 -> M-12 scale 120
#   -> M-02 slice -> O-02 close
# Asserts: each gizmo field commits its value (OCR), the model stays on
# the plate, and the slice completes (m2 done rendering).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF  # noqa: E402

LOG = "[m7t74]"
import m7_common as m7  # noqa: E402


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    ok, text = m7.op_gizmo_field(session, lambda t: "move" in t,
                                 "position", 0, "60")
    results["move X commits 60"] = (
        "PASS" if ok else f"FAIL (now {text!r})")
    ok, text = m7.op_gizmo_field(session, lambda t: "rotate" in t,
                                 "rotate", -1, "45")
    if not ok:
        print(f"{LOG} rotate words: {[w[0] for w in m7.words(session)][:26]}")
    results["rotate Z commits 45"] = (
        "PASS" if ok else f"FAIL (now {text!r})")
    ok, text = m7.op_gizmo_field(session, lambda t: "scale" in t,
                                 "scale", 0, "120")
    if not ok:
        print(f"{LOG} scale words: {[w[0] for w in m7.words(session)][:26]}")
    results["scale commits 120"] = (
        "PASS" if ok else f"FAIL (now {text!r})")
    results["model still on plate"] = (
        "PASS" if m7.model_present(session) else "FAIL")
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
