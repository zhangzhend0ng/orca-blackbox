# host_guard.py — enforce "cases run on the guest VM" (README top discipline).
#
# The batch discipline (README "跑批纪律与收尾") says regression cases and
# probes run inside the Hyper-V guest (win11-test, via runner/hv_go.ps1);
# direct host execution is dev-only and must be explicitly allowed. This is
# the mechanical half of that rule: launcher.launch() refuses to start the
# app on a host unless ORCA_BB_ALLOW_HOST is set.
#
# Guest detection needs no hardcoded machine names. The Hyper-V KVP key
# depends on the VM's Data Exchange integration service. When it is absent,
# check the guest firmware's manufacturer and model. Historical violations
# this guard exists for (README
# discipline section, baseline): 09-02 / 09-08 / 09-16 / 09-17 — the agent
# kept running the suite on the host until told otherwise.
from __future__ import annotations

import os
import sys

try:
    import winreg
except ImportError:  # non-Windows: never a Hyper-V guest, treat as host
    winreg = None

_GUEST_KEY = r"SOFTWARE\Microsoft\Virtual Machine\Guest\Parameters"
_FIRMWARE_KEY = r"HARDWARE\DESCRIPTION\System\BIOS"


def in_guest() -> bool:
    """True inside the Hyper-V guest (win11-test); False on the host."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GUEST_KEY):
            return True
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _FIRMWARE_KEY) as key:
            manufacturer, _ = winreg.QueryValueEx(key, "SystemManufacturer")
            model, _ = winreg.QueryValueEx(key, "SystemProductName")
    except OSError:
        return False
    return manufacturer == "Microsoft Corporation" and model == "Virtual Machine"


def allow_host() -> bool:
    """Explicit dev-only opt-out: ORCA_BB_ALLOW_HOST=1/true/yes."""
    return os.environ.get("ORCA_BB_ALLOW_HOST", "").strip().lower() in {"1", "true", "yes"}


def assert_guest_or_allow() -> None:
    """Block a host-side app launch unless explicitly allowed; exit 2.

    Guest runs pass through silently. Host runs either carry the explicit
    dev-only flag (allowed, with a one-line warning that the results are not
    regression evidence) or are refused with the pointing message.
    """
    if in_guest():
        return
    if allow_host():
        print("[host_guard] host execution explicitly allowed (ORCA_BB_ALLOW_HOST) — "
              "dev-only: results from this run are NOT valid regression evidence.")
        return
    sys.stderr.write(
        "[host_guard] BLOCKED: cases/probes run inside the Hyper-V guest.\n"
        "  batch/regression: & runner\\hv_go.ps1\n"
        "  dev-only host run: set ORCA_BB_ALLOW_HOST=1 (then the run is dev evidence only)\n"
    )
    sys.exit(2)
