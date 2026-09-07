#!/usr/bin/env python3
# m7t72.py — Feishu #72 主流程-模板: 模型导入测试
#   O-01 open -> M-01 import -> M-19 delete -> O-02 close
# Ops: launcher model auto-load (the app's own post-init load_files path)
# is M-01; Edit > Delete All (MainFrame.cpp:2690) is M-19; WM_CLOSE is
# O-02. Asserts: model arrives, plate empties, app closes.

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    m7.step_delete_all(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
