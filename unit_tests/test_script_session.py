"""Composition checks do not start processes or GUI."""
from unittest.mock import Mock

import pytest

from harness import script_session


def test_script_contract_is_a_fixed_registry_capability():
    assert script_session.registered_script_cases() == ("m0_boot_check",)
    contract = script_session.script_contract("m0_boot_check")
    assert contract.executor == "script"
    assert contract.required_checks == ("path", "business")
    assert [step.id for step in contract.steps] == ["boot", "capture", "close"]
    with pytest.raises(ValueError):
        script_session.script_contract("../../arbitrary.py")
    with pytest.raises(ValueError):
        script_session.script_contract("m5a_preset_cycle")


def test_host_override_does_not_enable_real_script(monkeypatch, tmp_path):
    monkeypatch.setattr(script_session.host_guard, "in_guest", lambda: False)
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    runtime = Mock()
    monkeypatch.setattr(script_session, "run_once", runtime)
    with pytest.raises(ValueError, match="guest execution required"):
        script_session.run_script("m0_boot_check", tmp_path / "new")
    runtime.assert_not_called()
    assert not (tmp_path / "new").exists()


def test_real_script_cannot_split_desktop_lock_with_another_root(monkeypatch, tmp_path):
    monkeypatch.setattr(script_session.host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(script_session, "SCRIPT_ROOT", tmp_path / "canonical")
    with pytest.raises(ValueError, match="canonical"):
        script_session.run_script("m0_boot_check", tmp_path / "other")
    assert not (tmp_path / "other").exists()
