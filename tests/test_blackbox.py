# tests/test_blackbox.py — the pytest SUBPROCESS SHELL
# (STRUCTURING_PLAN 第二期 #2).
#
# pytest 用例体 = subprocess.run(原脚本)：每个用例保持独立入口，挂起可被
# 外部超时单独处决且不连坐（2d 不变量——超时只杀驱动进程，app 由
# _sweep_app 收尾）；marks / --junitxml / --lf 由 pytest 白拿。Parametrize
# 从 cases.py 生成（单一事实源）；known_limitation 用例映射为
# xfail(strict=False)。
#
# Usage (guest rig, from the repo root):
#   python -m pytest tests/test_blackbox.py -k m0_anchor_health -v
#   python -m pytest tests/test_blackbox.py --junitxml=artifacts/pytest_junit.xml

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cases import CASES, enabled_cases  # noqa: E402

CASE_TIMEOUT_S = 25 * 60  # 单例最长超时（handoff 协议）


def _case_params():
    out = []
    for name in enabled_cases("smoke") + enabled_cases("regression"):
        meta = CASES[name]
        marks = [getattr(pytest.mark,
                         f"tier_{str(meta.get('tier', 'TBD')).lower()}")]
        if meta.get("known_limitation"):
            marks.append(pytest.mark.xfail(strict=False,
                                           reason="documented limitation"))
        out.append(pytest.param(name, id=name, marks=marks))
    return out


def _sweep_app():
    """The driver died under timeout: sweep the app or the NEXT case's
    seed_profile hits the datadir lock (PITFALLS #10). taskkill without /F
    posts WM_CLOSE (the graceful sweep), /F is the fallback."""
    subprocess.run(["taskkill", "/IM", "snapmaker-orca.exe"],
                   capture_output=True)
    subprocess.run(["taskkill", "/IM", "snapmaker-orca.exe", "/F"],
                   capture_output=True)


@pytest.mark.parametrize("case", _case_params())
def test_blackbox_case(case: str):
    script = HERE / f"{case}.py"
    log = ROOT / "artifacts" / f"pytest_{case}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("wb") as f:
            # bytes streams: the shell never re-decodes case output — the
            # log file is the single evidence artifact (same as run_regression)
            proc = subprocess.run([sys.executable, str(script)],
                                  stdout=f, stderr=subprocess.STDOUT,
                                  cwd=str(ROOT), timeout=CASE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _sweep_app()
        pytest.fail(f"{case} TIMEOUT after {CASE_TIMEOUT_S}s — driver killed, "
                    f"app swept; log: {log}", pytrace=False)
    assert proc.returncode == 0, f"{case} rc={proc.returncode} (log: {log})"
