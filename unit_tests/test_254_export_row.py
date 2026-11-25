"""tests/gui/m7x_254_sphere_layer_pair.py with the application replaced by fakes: its slice wait ends
on the enabled Export G-code row, answers the memory guard on the way, and leaves a failure in the
results when the click is rejected or the row stays disabled.

Nothing here starts the application. op_slice, the export menu and the guard are scripted; only the
clock is replaced, by one that advances with every sleep.
"""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
for place in ("tests", "tests/engine", "tests/gui"):
    sys.path.insert(0, str(ROOT / place))      # the script's own imports need these beside the harness
SPEC = importlib.util.spec_from_file_location("m7x_254_sphere_layer_pair",
                                              ROOT / "tests" / "gui" / "m7x_254_sphere_layer_pair.py")
case = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(case)

ROW = "Export G-code"


def fake_app(monkeypatch, row, *, button="FAIL", guard=None):
    """The application replaced by fakes. `row` maps the poll number to the export row's state;
    `button` is what op_slice leaves in the results for the stage; `guard` is what answering the
    memory guard does. Returns what the fakes were asked."""
    notes, polls, clock = [], [0], [1000.0]
    monkeypatch.setattr(case, "time", SimpleNamespace(
        monotonic=lambda: clock[0], time_ns=lambda: 1,
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)))

    def op_slice(session, results, key="slice completes", export_to=None, timeout_s=600):
        notes.append(("op_slice", key, timeout_s))
        results[key] = button
        return button == "PASS"

    def answer_memory_guard(session, work, analysis):
        notes.append(("guard",))
        return guard(analysis) if guard else False

    def dispatch(session, item, expect_dialog=False, timeout_s=12.0, via=None, *, inspect_enabled=False):
        polls[0] += 1
        state = row(polls[0])
        notes.append(("row", item, via, inspect_enabled, state))
        return state, None

    monkeypatch.setattr(case.m7, "op_slice", op_slice)
    monkeypatch.setattr(case, "answer_memory_guard", answer_memory_guard)
    monkeypatch.setattr(case.m7, "file_menu_dispatch", dispatch)
    return SimpleNamespace(notes=notes, polls=polls, clock=clock)


def test_the_wait_ends_when_the_export_row_is_enabled(tmp_path, monkeypatch):
    # op_slice saw no "done" rendering within its glance; the row says when slicing is done
    app = fake_app(monkeypatch, lambda poll: poll >= 3)
    results, analysis = {}, {}
    reading = case.slice_until_exportable(object(), tmp_path, "baseline", results, analysis)
    assert reading == {"export_enabled_after_seconds": 3.0, "polls": 3}      # two sleeps of 1.5 s
    assert results == {"baseline slice": "PASS"}
    assert ("op_slice", "baseline slice", case.BUTTON_GLANCE_S) in app.notes
    assert [note for note in app.notes if note[0] == "guard"] == [("guard",)] * 3
    assert [note[1:] for note in app.notes if note[0] == "row"] == [(ROW, "Export", True, False)] * 2 + [
        (ROW, "Export", True, True)]
    # the guard is looked for before the row, every time
    assert [note[0] for note in app.notes] == ["op_slice", "guard", "row", "guard", "row", "guard", "row"]


def test_a_done_looking_button_does_not_end_the_wait(tmp_path, monkeypatch):
    # the button already looked done to op_slice, as it did on the guest while a warning had the export paused
    app = fake_app(monkeypatch, lambda poll: poll >= 5, button="PASS")
    results = {}
    reading = case.slice_until_exportable(object(), tmp_path, "target", results, {})
    assert reading["polls"] == 5 and results == {"target slice": "PASS"}
    # and it does not rescue a row that never turns enabled
    app = fake_app(monkeypatch, lambda poll: False, button="PASS")
    results = {}
    with pytest.raises(ValueError, match="stayed disabled"):
        case.slice_until_exportable(object(), tmp_path, "target", results, {}, timeout_s=0)
    assert results == {"target slice": f"FAIL ({ROW!r} stayed disabled 0s after the Slice click)"}
    assert app.polls[0] == 1 and ("guard",) in app.notes


def test_a_rejected_click_stops_before_the_wait(tmp_path, monkeypatch):
    app = fake_app(monkeypatch, lambda poll: True, button="FAIL (slice click rejected)")
    results = {}
    with pytest.raises(ValueError, match="slice click rejected"):
        case.slice_until_exportable(object(), tmp_path, "baseline", results, {})
    assert results == {"baseline slice": "FAIL (slice click rejected)"}
    assert not [note for note in app.notes if note[0] in ("row", "guard")]


def test_a_guard_that_will_not_close_stops_the_run(tmp_path, monkeypatch):
    def stubborn(analysis):
        analysis["guard_failures"] = analysis.get("guard_failures", 0) + 1
        if analysis["guard_failures"] >= 2:
            raise ValueError('"Memory Usage Warning" could not be answered with "Yes, Continue"')
        return True

    # while the dialog is up the export stays paused, so the row stays disabled
    app = fake_app(monkeypatch, lambda poll: False, guard=stubborn)
    results, analysis = {}, {}
    with pytest.raises(ValueError, match="could not be answered"):
        case.slice_until_exportable(object(), tmp_path, "baseline", results, analysis, timeout_s=1000)
    # the row is asked about only after a guard was answered without raising: once, before the second one
    assert analysis["guard_failures"] == 2 and results == {"baseline slice": "FAIL"}
    assert [note[0] for note in app.notes] == ["op_slice", "guard", "row", "guard"]


def test_the_stage_reads_the_plate_only_after_the_row_is_enabled(tmp_path, monkeypatch):
    order = []
    session = SimpleNamespace(pid=4242, alive=lambda: True, close=lambda: order.append("close"))
    app = fake_app(monkeypatch, lambda poll: poll >= 2)
    real_dispatch = case.m7.file_menu_dispatch

    def dispatch(*args, **kwargs):
        enabled, dialog = real_dispatch(*args, **kwargs)
        order.append(("row", enabled))
        return enabled, dialog

    monkeypatch.setattr(case.m7, "file_menu_dispatch", dispatch)
    monkeypatch.setattr(case, "load_sphere", lambda args, work, profile, project: session)
    monkeypatch.setattr(case, "quality", lambda session: None)
    monkeypatch.setattr(case, "retain_plate", lambda *args: order.append("retain_plate") or {"kept": True})
    monkeypatch.setattr(case.anchors, "wait_for", lambda session, name, timeout_s=0: (1.0, 0, 0, 0, 0))
    monkeypatch.setattr(case.anchors, "capture_bgr", lambda session: np.zeros((4, 4, 3), np.uint8))
    monkeypatch.setattr(case.anchors, "has_colored_content", lambda image: 0.5)
    results, analysis = {}, {"edits": []}
    case.slice_project(SimpleNamespace(exe=None), tmp_path, tmp_path / "sphere.3mf", "baseline", results, analysis)
    assert order == [("row", False), ("row", True), "retain_plate", "close"]
    assert results == {"baseline slice": "PASS"}
    assert analysis["baseline_slice"]["polls"] == 2 and analysis["baseline_plate"] == {"kept": True}
    assert analysis["baseline_preview"] == {"score": 1.0, "colored_fraction": 0.5}
    assert (tmp_path / "baseline-preview.png").is_file() and (tmp_path / "baseline-temp").is_dir()


def test_the_old_completion_signal_is_no_longer_used():
    source = (ROOT / "tests" / "gui" / "m7x_254_sphere_layer_pair.py").read_text("utf-8")
    assert "wait_slicing_done" not in source and "timeout_s=120" not in source
    assert source.count("op_slice(") == 1 and "timeout_s=BUTTON_GLANCE_S" in source
    assert "inspect_enabled=True" in source and "answer_memory_guard" in source
