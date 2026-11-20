"""Exercise credential binding without a VM, network, GUI or real credentials."""
import os
from pathlib import Path
import runpy
import subprocess

import pytest


@pytest.mark.skipif(os.name != "nt", reason="PowerShell credential constructor is Windows-only")
def test_verification_command_binds_credential_without_prompting(monkeypatch):
    monkeypatch.setenv("ORCA_BB_GUEST_USER", "unit-only")
    monkeypatch.setenv("ORCA_BB_GUEST_PASS", "dummy-not-a-real-password")
    source = Path(__file__).resolve().parents[1] / "runner" / "push_verify.py"
    module = runpy.run_path(str(source), run_name="unit_only")
    # Isolate the unrelated Security module autoloader: this regression concerns
    # binding the credential variable, not encrypting a password or authenticating.
    stub = ("function ConvertTo-SecureString { param($String, [switch]$AsPlainText, "
            "[switch]$Force); [System.Security.SecureString]::new() }; ")
    script = stub + module["CRED"] + "; if ($null -eq $cred) { exit 3 }; 'credential-bound'"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "credential-bound"
