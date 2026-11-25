"""tests/gui/m7x_254_gcode_tmp_probe.py with the app replaced by fakes: its stop rules, timeline and file reading.

Nothing here starts the application. The watch loop runs on a fake clock over scripted plate files,
warning dialog and export row; only the file and memory readings touch the real machine.
"""
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("m7x_254_gcode_tmp_probe",
                                              ROOT / "tests" / "gui" / "m7x_254_gcode_tmp_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

PLATE = ROOT / "docs/runs/evidence/win11-254-2026-11-25/1d2de6b4-run1-baseline.gcode"
ENABLED = "File > Export > Export G-code is enabled"


def _watch(monkeypatch, tmp_path, files, dialog=None, row=None, *, hold=False, answer=True):
    """One run of the watch loop on a fake clock. `files`, `dialog` and `row` map the seconds since
    the click to the plate files, a warning hwnd and the export row state."""
    clock, notes = [100.0], []
    fake = SimpleNamespace(monotonic=lambda: clock[0],
                           sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    now = lambda: round(clock[0] - 100, 2)  # noqa: E731

    def handle(session, hwnd, work, warnings, sample, started, hold_flag):
        notes.append(("answer", now()))
        clicked = "not clicked: --hold-warning" if hold_flag else {"center": [0, 0]} if answer else "not clicked"
        warnings.append({"title": probe.WARNING, "seen_at_s": sample["t_s"], "settled_at_s": now(), "clicked": clicked})
        if answer and not hold_flag:
            warnings[-1]["closed"] = True
        return answer and not hold_flag

    def export_row(session):
        state = row(now()) if row else False
        notes.append(("row", now(), state))
        return {"menu_opened": True, "row_enabled": state, "menus_left_open": 0}

    monkeypatch.setattr(probe, "time", fake)
    monkeypatch.setattr(probe, "plate_files", lambda folder, pid: files(now()))
    monkeypatch.setattr(probe, "toolbar", lambda session: {"main window": True, "Slice plate": False, "Print": False})
    monkeypatch.setattr(probe, "dialog_titles", lambda pid: [])
    monkeypatch.setattr(probe, "memory", lambda: {"total_mb": 4000, "avail_phys_mb": 300.0, "commit_avail_mb": 900.0})
    monkeypatch.setattr(probe.m7, "wait_dialog",
                        lambda pid, timeout_s, title_substr: dialog and dialog(now()) or None)
    monkeypatch.setattr(probe, "export_row", export_row)
    monkeypatch.setattr(probe, "handle_warning", handle)
    session = SimpleNamespace(pid=4242, hwnd=1, alive=lambda: True)
    args = SimpleNamespace(hold_warning=hold, menu_s=5, limit_s=60, quiet_s=15)
    analysis = {}
    reason = probe.watch(session, tmp_path, tmp_path, analysis, 100.0, args)
    return reason, analysis, notes


def _growing(rename_at=None, cap=None, rate=1000):
    def files(t):
        if t < 2:
            return []
        size = min(cap, rate * int(t)) if cap else rate * int(t)
        return [[".4242.0.gcode", size, 0]] if rename_at is not None and t >= rename_at else [
            [".4242.0.gcode.tmp", size, 0]]
    return files


def _warning(first, last=None):
    """What m7.wait_dialog returns (class, title, rect, hwnd) while the warning is up."""
    return lambda t: (None, probe.WARNING, None, 77) if t >= first and (last is None or t <= last) else None


def test_stops_on_the_enabled_export_row_after_the_rename(tmp_path, monkeypatch):
    reason, analysis, notes = _watch(monkeypatch, tmp_path, _growing(rename_at=8), row=lambda t: t >= 9)
    assert reason == ENABLED and analysis["stop"]["at_s"] == 10.0
    timeline = analysis["timeline"]
    assert [timeline[key] for key in ("first_plate_file_at_s", "renamed_to_gcode_at_s", "export_row_enabled_at_s")] == [
        2.0, 8.0, 10.0]
    assert timeline["slice_button_disabled_at_s"] == 0.0      # greyed from the first second on
    assert timeline["warning_open_at_s"] is None and "export_row_at_stop" not in analysis
    assert [note[1] for note in notes if note[0] == "row"] == [0.0, 5.0, 10.0]
    assert (tmp_path / "probe.log").read_text(encoding="utf-8").splitlines()[2].startswith(
        "t=   2.00s files=[.4242.0.gcode.tmp:2000]")


def test_stalled_partial_file_ends_the_watch(tmp_path, monkeypatch):
    reason, analysis, notes = _watch(monkeypatch, tmp_path, _growing(cap=28672, rate=4000))
    assert reason == "plate file unchanged for 15 s" and analysis["stop"]["at_s"] == 23.0
    timeline = analysis["timeline"]
    assert [timeline["first_plate_file_at_s"], timeline["last_growth_at_s"], timeline["renamed_to_gcode_at_s"]] == [
        2.0, 8.0, None]
    assert not timeline["complete_plate_file_at_stop"]
    assert analysis["export_row_at_stop"]["row_enabled"] is False     # one reading at the stop
    assert analysis["samples"][-1]["files"] == [[".4242.0.gcode.tmp", 28672, 0]]


def test_warning_is_answered_and_the_file_grows_on_to_the_end(tmp_path, monkeypatch):
    def files(t):
        if t < 2:
            return []
        return [[".4242.0.gcode" if t >= 8 else ".4242.0.gcode.tmp", 5000 if t == 6 else min(8000, 1000 * int(t)), 0]]
    reason, analysis, notes = _watch(monkeypatch, tmp_path, files, dialog=_warning(6, 6), row=lambda t: t >= 9)
    assert reason == ENABLED and ("answer", 6.0) in notes
    timeline = analysis["timeline"]
    assert [timeline[key] for key in ("warning_open_at_s", "warning_answered_at_s", "growth_resumed_at_s")] == [
        6.0, 6.0, 7.0]
    assert timeline["sizes_while_warning_open"] == [5000] and timeline["complete_plate_file_at_stop"]
    assert analysis["stop"]["failed_attempts"] == 0 and len(analysis["warnings"]) == 1


def test_two_unanswered_attempts_end_the_watch_as_a_failure(tmp_path, monkeypatch):
    reason, analysis, notes = _watch(monkeypatch, tmp_path, _growing(), dialog=_warning(6), answer=False)
    assert reason == probe.UNANSWERED and analysis["stop"]["at_s"] == 7.0
    assert analysis["stop"]["failed_attempts"] == 2 and [note for note in notes if note[0] == "answer"] == [
        ("answer", 6.0), ("answer", 7.0)]
    assert analysis["timeline"]["warning_answered_at_s"] is None
    assert "export_row_at_stop" in analysis and analysis["export_row_at_stop"]["row_enabled"] is False


def test_held_warning_is_recorded_once_and_the_frozen_file_ends_the_watch(tmp_path, monkeypatch):
    def files(t):
        if t < 2:
            return []
        return [[".4242.0.gcode.tmp", 6000 if t >= 6 else 1000 * int(t), 0]]
    reason, analysis, notes = _watch(monkeypatch, tmp_path, files, dialog=_warning(6), hold=True)
    assert reason == "plate file unchanged for 15 s" and analysis["stop"]["at_s"] == 21.0
    assert analysis["stop"]["failed_attempts"] == 0 and [note for note in notes if note[0] == "answer"] == [
        ("answer", 6.0)]
    timeline = analysis["timeline"]
    assert timeline["warning_open_samples"] == 16 and timeline["sizes_while_warning_open"] == [6000]
    assert timeline["last_growth_at_s"] == 6.0 and not timeline["complete_plate_file_at_stop"]
    assert analysis["export_row_at_stop"]["row_enabled"] is False


def test_no_plate_file_runs_into_the_time_limit(tmp_path, monkeypatch):
    reason, analysis, notes = _watch(monkeypatch, tmp_path, lambda t: [])
    assert reason == "time limit" and analysis["stop"]["at_s"] == 60.0
    assert analysis["timeline"]["first_plate_file_at_s"] is None


def test_renamed_file_with_a_disabled_row_ends_after_the_grace(tmp_path, monkeypatch):
    reason, analysis, notes = _watch(monkeypatch, tmp_path, _growing(rename_at=4))
    assert reason == "plate file renamed but the export row stayed disabled"
    assert analysis["stop"]["at_s"] == 34.0 and analysis["timeline"]["renamed_to_gcode_at_s"] == 4.0


def test_plate_facts_tell_a_complete_plate_from_its_stalled_parts():
    raw = PLATE.read_bytes()
    complete = probe.plate_facts(raw)
    assert complete["executable_block_closed"] and complete["config_block_complete"]
    assert complete["declared_layers"] == complete["layer_change_markers"] == 100
    assert complete["last_commands"][-3:] == ["M106 S0", "M106 P2 S0", "M73 P100 R0"]
    # the two sizes #254 was left with: before the first layer, and inside layer six
    early, later = probe.plate_facts(raw[:28672]), probe.plate_facts(raw[:69632])
    for part in (early, later):
        assert not part["executable_block_closed"] and not part["config_block_complete"]
        assert part["declared_layers"] == 100 and part["layer_change_markers"] < 100
    assert (early["layer_change_markers"], later["layer_change_markers"]) == (0, 6)
    numbered = b"; total layer number: 3\n;LAYER:0\n;LAYER:1\n;LAYER:3\n; EXECUTABLE_BLOCK_END\n; CONFIG_BLOCK_START\n; CONFIG_BLOCK_END\n"
    assert probe.plate_facts(numbered)["numbered_layers_consecutive_from_zero"] is False
    assert probe.plate_facts(numbered.replace(b";LAYER:3", b";LAYER:2"))["numbered_layers_consecutive_from_zero"] is True


def test_memory_reading_has_both_inputs_of_the_guard():
    readings = probe.memory()
    assert readings["total_mb"] > 0 and readings["avail_phys_mb"] > 0 and readings["commit_avail_mb"] > 0


def test_vendored_sphere_is_the_fixture_the_probe_expects():
    digest = hashlib.sha256((ROOT / "fixtures" / "feishu_std_sphere.3mf").read_bytes()).hexdigest()
    assert digest == probe.MODEL_FIXTURES["_sphere"][1]
