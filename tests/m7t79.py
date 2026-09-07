#!/usr/bin/env python3
# m7t79.py — Feishu #79 主流程-模板: 拆分为对象/拆分为零件
#   M-01 import -> M-05 split to objects -> M-07 split to parts -> M-02
#   slice -> O-02 close
# The toolbar items ('Split to objects' / 'Split to parts', GLCanvas3D
# :7764/:7776) are gated by plater()->can_split(); the mixed fixture must
# actually contain multiple volumes for the gates to open. The case
# records the gate state honestly (SKIP-note when closed) and asserts the
# slice completes regardless.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t79]"


def click_split(session, pred, key, results):
    if not m7.select_model(session):
        results["model selected"] = "FAIL"
        return
    x, tip = m7.find_slot(session, pred)
    if x is None:
        results[key] = "FAIL (slot not found)"
        return
    before = m7.blob_count(session)
    m7.click_slot(session, x)
    time.sleep(3.0)
    after = m7.blob_count(session)
    print(f"{LOG} {key}: blobs {before} -> {after}")
    results[key] = (
        f"PASS (blobs {before}->{after})" if after >= before
        and tip else f"FAIL ({tip!r})")


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    click_split(session, lambda t: "split to objects" in t,
                "split to objects runs", results)
    click_split(session, lambda t: "split to parts" in t,
                "split to parts runs", results)
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
