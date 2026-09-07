#!/usr/bin/env python3
# m7t73.py — Feishu #73 主流程-模板: 新建项目测试
#   O-01 open -> O-05 new project -> M-20 model create -> M-19 delete
#   -> O-02 close
# Asserts: new project leaves the empty plate; the primitive (M-20) lands;
# Delete All empties again.

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402


def steps(session, results):
    results["empty bed at boot"] = (
        "PASS" if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR
        else "FAIL")
    ok, _dlg = m7.file_menu_dispatch(session, "New Project")
    results["new project dispatches"] = "PASS" if ok else "FAIL"
    time.sleep(2.0)
    if not ok:
        return
    results["plate still empty"] = (
        "PASS" if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR
        else "FAIL")
    added = m7.op_add_primitive(session, "cube")
    results["model created (M-20)"] = "PASS" if added else "FAIL"
    m7.step_delete_all(session, results)


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
