#!/usr/bin/env python3
# m7t75.py — Feishu #75 主流程-模板: 多模型布局切片测试
# feishu: baseline#153 baseline#158
#   M-01 import x2 (overlap) -> M-03 arrange -> M-19 delete one
#   -> M-02 slice (gcode exported as evidence) -> O-02 close
# Asserts: after arrange two separated blobs exist; after deleting one the
# plate keeps exactly one blob; the slice completes and exports gcode.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402
from m7_common import ART  # noqa: E402


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    added = m7.op_add_primitive(session, "cube")
    results["second model added (overlap)"] = "PASS" if added else "FAIL"

    arr_x, tip = m7.find_slot(session, lambda t: "arrange" in t)
    if arr_x:
        m7.click_slot(session, arr_x)
        time.sleep(6.0)
    results["arrange runs"] = "PASS" if arr_x else "FAIL"
    results["two models after arrange"] = (
        "PASS" if m7.model_blob_count(session) >= 2
        else f"FAIL ({m7.model_blob_count(session)} object-shaped blobs)")

    # M-19: right-click the model -> Delete (one object only). The check is
    # on OBJECT-shaped blobs: the plain blob count also sees the object name
    # label and the plate widgets, so "< 2" could never hold (09-23, g18).
    deleted = m7.context_click_row(session, "model", "delete",
                                   success_fn=lambda:
                                   m7.model_blob_count(session) < 2,
                                   label="delete-one")
    left = m7.model_blob_count(session)
    results["delete one leaves one"] = (
        "PASS" if deleted and left >= 1 else f"FAIL (left={left})")
    m7.op_slice(session, results,
                export_to=ART / "m7t75.gcode")


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
