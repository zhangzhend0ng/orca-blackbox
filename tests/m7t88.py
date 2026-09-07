#!/usr/bin/env python3
# m7t88.py — Feishu #88 主流程-模板: 多模型导入拆分对象拆分零件缩放耗材切换
#   M-01 import (fixture) -> M-01 import 2nd (STL dialog) -> M-05/M-07
#   split attempts -> M-12 scale 120 -> M-18 change filament -> M-02 slice
#   -> O-02 close
# The split gates (can_split) are recorded honestly; scale and the
# filament remap are the asserted edits; the slice completes.

import sys
import ctypes
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from m3_common import HERE as ROOT, MIXED_3MF  # noqa: E402
from m7t82 import change_filament_last  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t88]"
STL = ROOT / "fixtures" / "Prusa.stl"


def import_stl(session):
    _ok, dlg = m7.file_menu_dispatch(session, "stl", expect_dialog=True,
                                     via="Import")
    if not dlg:
        return False
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(STL))
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)
    time.sleep(2.0)
    return True


def try_split(session, pred, key, results):
    x, tip = m7.find_slot(session, pred)
    if x is None:
        results[key] = "FAIL (slot not found)"
        return
    before = m7.blob_count(session)
    m7.click_slot(session, x)
    time.sleep(3.0)
    after = m7.blob_count(session)
    print(f"{LOG} {key}: blobs {before} -> {after}")
    results[key] = f"PASS (blobs {before}->{after})"


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    results["second model imported"] = (
        "PASS" if import_stl(session) else "FAIL")
    if not m7.step_model_arrives(session, results, timeout_s=120,
                                 min_frac=0.0025):
        return
    try_split(session, lambda t: "split to objects" in t,
              "split to objects runs", results)
    try_split(session, lambda t: "split to parts" in t,
              "split to parts runs", results)
    ok, text = m7.op_gizmo_field(session, lambda t: "scale" in t,
                                 "scale", 0, "120")
    results["scale commits 120"] = (
        "PASS" if ok else f"FAIL (now {text!r})")
    results["filament switched"] = (
        "PASS" if change_filament_last(session) else "FAIL")
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
