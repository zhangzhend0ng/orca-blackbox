#!/usr/bin/env python3
# m7t83.py — Feishu #83 主流程-模板: 新建项目导入模型
#   O-01 open -> O-05 new project -> M-01 import STL -> M-02 slice
#   -> O-02 close
# The import reuses m7c's proven path (File menu dispatch -> native open
# dialog -> filename -> IDOK); the observable chain: plate empty after New
# Project, Prusa.stl arrives, slice completes.

import sys
import ctypes
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from m3_common import HERE as ROOT  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t83]"
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
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
    time.sleep(2.0)
    return True


def steps(session, results):
    results["empty bed at boot"] = (
        "PASS" if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR
        else "FAIL")
    ok, _dlg = m7.file_menu_dispatch(session, "New Project")
    results["new project dispatches"] = "PASS" if ok else "FAIL"
    time.sleep(2.0)
    results["import dispatches"] = (
        "PASS" if import_stl(session) else "FAIL")
    if not m7.step_model_arrives(session, results, timeout_s=120,
                                 min_frac=0.0025):
        return
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
