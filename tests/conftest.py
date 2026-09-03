# conftest.py — session-level RIG GATES (STRUCTURING_PLAN 第二期 #2).
#
# The vision cases are calibrated for ONE rig: 1920x1080, 100% DPI, the
# physical console, and no remote-control layer suppressing SendInput
# (real-click cases m4g/m5/m3i depend on it). Anything else fails the whole
# session BEFORE any case boots the app — a wrong rig must be loud and
# instant, not 40 confusing reds.
#
# Measured 09-03 on the win11-test guest: no remote-control layer, console
# session, 1920x1080 @ 96 DPI.

import ctypes
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_W, EXPECTED_H = 1920, 1080
EXPECTED_DPI = 96


def _rig_problems() -> list[str]:
    problems: list[str] = []
    user32 = ctypes.WinDLL("user32")
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    if (w, h) != (EXPECTED_W, EXPECTED_H):
        problems.append(
            f"resolution {w}x{h} != {EXPECTED_W}x{EXPECTED_H} — cases are "
            f"calibrated for this rig (host-side: tools/setres_1080.py)")
    dpi = EXPECTED_DPI
    try:
        dpi = int(user32.GetDpiForSystem())
    except Exception:
        pass  # pre-1607 Windows: treat as 100%
    if dpi != EXPECTED_DPI:
        problems.append(
            f"system DPI {dpi} != {EXPECTED_DPI} — template matching is "
            f"scale-sensitive; pin the display to 100%")
    try:
        from harness.env_check import detect_remote_control
        finding = detect_remote_control()
        if finding:
            problems.append(f"remote-control layer active: {finding}")
    except Exception as exc:  # noqa: BLE001 — a broken detector is a gate failure
        problems.append(f"remote-control detection failed: {exc}")
    return problems


@pytest.fixture(scope="session", autouse=True)
def rig_gates():
    problems = _rig_problems()
    if problems:
        pytest.exit("RIG GATES FAILED (before any case boots the app): "
                    + " | ".join(problems), returncode=2)
    yield
