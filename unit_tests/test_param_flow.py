"""Per-stage times of run_ops, and the one registry that decides which scenarios get them.

Fake Win32 boundaries only: nothing here launches an application."""
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

from harness import native_matrix as nm
from harness.native_preset_script import (TIMED_FLOWS, ensure_process_advanced, flow_step_measure,
                                          timed_flow_step)
from harness import native_script_baseline as nsb
from harness import param_case_lib as pcl
from harness import process_panel as pp
from harness.agent_protocol import MAINTENANCE_TRIALS, ProtocolError

CANVAS_LEFT = 426              # client x where the 3D view starts; the Edits sit left of it
ROW_Y = 965                    # client y of every row before the page is wheeled
EDIT_X = 290                   # client x of the centre of every Edit
RECT = (100, 800, 118, 818)    # the checkbox the fakes report
# The reader of the #276 stage lines (artifacts/rotate276-1125/flow_read.py),
# anchored: the whole line has to be a stage line.
STAGE_LINE = re.compile(r"\[flow\d+\] (.+?) ok=([01]) seconds=([0-9.]+)")


class Page:
    """The app's control tree as the driver's Win32 calls see it: labelled rows
    30px apart, a row with several Edits a stack centred on its label line at
    a 27px pitch. A wheel moves every Edit up by whole notches. Fidelity gap:
    nothing is ever rebuilt, hidden or disabled, and typed text stays."""

    ROWS = {"Layer height": 1, "Outer wall line width": 1, "Outer wall speed": 1, "Overhang speed": 4}

    def __init__(self):
        self.edits, self.homes, self.top, self.row_edits, hwnd = {}, {}, {}, {}, 100
        for label, count in self.ROWS.items():
            self.top[label] = top = ROW_Y + 30 * len(self.top) + 60 * (count > 1)
            self.row_edits[label] = []
            for field in range(count):
                cy = top + 27 * field - 40 * (count > 1)
                self.edits[hwnd] = [[250, cy - 10, 330, cy + 10], ""]
                self.homes[hwnd] = list(self.edits[hwnd][0])
                self.row_edits[label].append(hwnd)
                hwnd += 1
        self.reset()

    def reset(self):
        for hwnd, home in self.homes.items():
            self.edits[hwnd][0] = list(home)
        self.shift = 0

    def row_y(self, label):
        return self.top[label] - self.shift

    def wheel(self, notches):
        for rect, _text in self.edits.values():
            rect[1] -= pp.WHEEL_STEP_PX * notches
            rect[3] -= pp.WHEEL_STEP_PX * notches
        self.shift += pp.WHEEL_STEP_PX * notches


class FakeWin32gui:
    def __init__(self, page):
        self.page = page

    def EnumChildWindows(self, parent, visit, lparam):
        for hwnd in list(self.page.edits):
            visit(hwnd, lparam)

    @staticmethod
    def IsWindowVisible(hwnd):
        return True

    @staticmethod
    def IsWindowEnabled(hwnd):
        return True


class FakeUI:
    """The driver's ui. Every call run_ops makes is recorded; edit() types into
    the Edit at (x, y) and answers the readback receipt."""

    def __init__(self, page, calls):
        self.page, self.calls = page, calls
        self.app = SimpleNamespace(hwnd=11, pid=12)
        self.wu = SimpleNamespace(
            window_class=lambda hwnd: "Edit" if hwnd in page.edits else "wxGLCanvas",
            _window_pid=lambda hwnd: self.app.pid,
            window_rect=lambda hwnd: tuple(page.edits[hwnd][0]) if hwnd in page.edits else (CANVAS_LEFT, 0, 1900, 1031),
            client_to_screen=lambda hwnd, x, y: (x, y))

    def main_input(self):
        self.calls.append(("main_input",))

    def pause(self, seconds):
        self.calls.append(("pause", seconds))

    def edit(self, x, y, text):
        self.calls.append(("edit", x, y, text))
        handle = next(h for h, (rect, _text) in self.page.edits.items()
                      if rect[0] <= x < rect[2] and rect[1] <= y < rect[3])
        self.page.edits[handle][1] = text
        return {"target_hwnd": handle, "control_class": "Edit", "after_text": text, "committed": True}


@pytest.fixture
def world(monkeypatch):
    """run_ops and uia_set_float for real against the fake page (the #264 row
    and the #276 rows); every other collaborator a recording stub whose
    answers sit on `world.knobs`. The work area ends 5px under the third
    overhang box, as on fa706g3 (run 19d61032), so that one is wheeled into
    view and its row located again."""
    calls = []
    page = Page()
    ui = FakeUI(page, calls)
    knobs = SimpleNamespace(click_tab=True, checkbox=(True, RECT), dialog=(None, ""), found=[(RECT, 5)], paint=0.9,
                            found_row=True)

    def find_row(app, phrase, group_substr=None):
        calls.append(("find_row", phrase, group_substr))
        matched = phrase if isinstance(phrase, str) else phrase[0]
        return (page.row_y(matched) if knobs.found_row else None), matched

    # the work area is window geometry: it stays put while the page is wheeled
    work_bottom = page.edits[page.row_edits["Overhang speed"][2]][0][3] + 5
    monkeypatch.setitem(sys.modules, "win32gui", FakeWin32gui(page))
    monkeypatch.setattr(pcl, "_canvas_hwnd", lambda ui: 777)
    monkeypatch.setattr(pcl, "_find_phrase_row_any", find_row)
    monkeypatch.setattr(pcl, "settle_dialog", lambda ui, known, answer=None, expect=None: (
        calls.append(("settle_dialog", known, answer, expect)) or knobs.dialog))
    monkeypatch.setattr(pp, "work_area", lambda: (0, 0, CANVAS_LEFT, work_bottom))
    monkeypatch.setattr(pp, "options_viewport", lambda app: (0, 700, CANVAS_LEFT, 1000))
    monkeypatch.setattr(pp, "wheel_viewport", lambda app, viewport, notches, delta: calls.append(("wheel", notches, delta)) or page.wheel(notches))
    monkeypatch.setattr(pp, "ensure_advanced", lambda app, want=True: calls.append(("ensure_advanced", app, want)) or True)
    monkeypatch.setattr(pp, "click_tab", lambda app, tab, hint="": calls.append(("click_tab", app, tab, hint)) or knobs.click_tab)
    monkeypatch.setattr(pp, "neutralize_focus", lambda app: calls.append(("neutralize_focus", app)) or True)
    monkeypatch.setattr(pp, "top_dialog_set", lambda app: calls.append(("top_dialog_set", app)) or set())
    monkeypatch.setattr(pp, "set_option_checkbox", lambda app, label, want, group_substr=None: (
        calls.append(("set_option_checkbox", app, label, want, group_substr)) or knobs.checkbox))
    monkeypatch.setattr(pp, "find_option_checkbox", lambda app, label, group=None: (
        calls.append(("find_option_checkbox", app, label, group)) or knobs.found))
    monkeypatch.setattr(pp, "checked_state", lambda app, rect: calls.append(("checked_state", app, rect)) or knobs.paint)
    return SimpleNamespace(calls=calls, ui=ui, page=page, knobs=knobs)


def recording_measure(calls):
    """A `measure` that marks where each timed span opens, then runs the step."""
    def measure(name, action, *args, **kwargs):
        calls.append(("measure", name))
        return action(*args, **kwargs)
    return measure


def stage_lines(capsys):
    """(name, ok) of every stage line in the captured output, in print order:
    a span is written when it closes, so children come before their parent."""
    return [line.groups()[:2] for line in filter(None, map(STAGE_LINE.fullmatch,
                                                           capsys.readouterr().out.splitlines()))]


def two_runs(world, ops, error=None):
    """(plain, timed) call logs of the same ops from the same page. Both runs
    must end the same way."""
    logs = []
    for measure in (None, recording_measure(world.calls)):
        world.page.reset()
        world.calls.clear()
        try:
            pcl.run_ops(world.ui, ops, measure=measure)
            outcome = ("ok", None)
        except ProtocolError as exc:
            outcome = ("error", str(exc))
        logs.append((outcome, list(world.calls)))
    assert [log[0] for log in logs] == [("error", error) if error else ("ok", None)] * 2
    return [log[1] for log in logs]


@pytest.mark.parametrize("scenario,edits,pauses,wheels", [
    ("uia_param_overhang_speeds", 4, 9, 1),     # 6 ops + 2 tab switches + the wheel of the parked box
    ("compare_276_quality", 3, 5, 0),           # 3 ops + 2 tab switches
], ids=["264", "276"])
def test_timing_changes_no_call_or_pause_of_run_ops(world, scenario, edits, pauses, wheels):
    plain, timed = two_runs(world, nsb.scenario_ops(scenario))
    # the plain run is a real one: every edit, every fixed pause, the wheel
    assert (sum(call[0] == "edit" for call in plain), plain.count(("pause", 1.0)),
            plain.count(("wheel", 1, -120)), ("pause", 6) in plain) == (edits, pauses, wheels, True)
    assert [call for call in timed if call[0] != "measure"] == plain


@pytest.mark.parametrize("scenario,stages", [
    # fa706g3 run 19d61032: the third box is wheeled into view and its row
    # located again; the four boxes share one label.
    ("uia_param_overhang_speeds", [
        "tab.Quality", "checkbox.Detect overhang", "tab.Speed", "checkbox.Slow down",
        "locate.Overhang speed[0]", "edit_readback.Overhang speed[0]", "field.Overhang speed[0]",
        "locate.Overhang speed[1]", "edit_readback.Overhang speed[1]", "field.Overhang speed[1]",
        "locate.Overhang speed[2]", "locate.Overhang speed[2]",
        "edit_readback.Overhang speed[2]", "field.Overhang speed[2]",
        "locate.Overhang speed[3]", "edit_readback.Overhang speed[3]", "field.Overhang speed[3]"]),
    # The names of the #276 baseline (guest run ec032d7c), unchanged.
    ("compare_276_quality", [
        "tab.Quality", "locate.Layer height", "edit_readback.Layer height", "field.Layer height",
        "locate.Outer wall line width", "edit_readback.Outer wall line width", "field.Outer wall line width",
        "tab.Speed", "locate.Outer wall speed", "edit_readback.Outer wall speed", "field.Outer wall speed"]),
], ids=["264", "276"])
def test_stage_names_separate_parents_children_and_same_labelled_fields(world, scenario, stages, capsys):
    pcl.run_ops(world.ui, nsb.scenario_ops(scenario), measure=timed_flow_step)
    assert stage_lines(capsys) == [(name, "1") for name in stages]


def test_checkbox_stage_times_the_locate_and_click_call_only(world):
    world.knobs.dialog = (99, "Spiral mode ...")
    ops = [{"op": "checkbox", "label": "Spiral", "value": True, "group": "Special mode", "answer": "Yes"}]
    _plain, timed = two_runs(world, ops)
    app = world.ui.app
    assert timed == [("main_input",), ("ensure_advanced", app, True), ("main_input",), ("top_dialog_set", app),
                     ("measure", "checkbox.Spiral"),
                     ("set_option_checkbox", app, "Spiral", True, "Special mode"),
                     ("settle_dialog", set(), "Yes", None),
                     ("main_input",), ("find_option_checkbox", app, "Spiral", "Special mode"),
                     ("checked_state", app, RECT), ("pause", 1.0), ("pause", 6), ("main_input",)]


@pytest.mark.parametrize("answers,error", [
    ({"paint": 0.0}, "param_checkbox:Spiral:reverted"),
    ({"checkbox": (None, None)}, "param_checkbox:Spiral"),
    ({"click_tab": False}, "param_tab:Quality"),
], ids=["box-put-back-after-its-dialog", "box-never-ticked", "tab-not-clicked"])
def test_a_failing_op_raises_the_same_error_with_and_without_timing(world, answers, error):
    for name, value in answers.items():
        setattr(world.knobs, name, value)
    world.knobs.dialog = (99, "Spiral mode ...")
    ops = [{"tab": "Quality", "op": "checkbox", "label": "Spiral", "value": True, "answer": "Yes"}]
    plain, timed = two_runs(world, ops, error)
    assert plain and [call for call in timed if call[0] != "measure"] == plain


def test_an_op_that_raises_is_logged_ok0_on_its_own_stage_and_still_raises(world, capsys):
    world.knobs.found_row = False      # the row lookup answers "not on the page"
    with pytest.raises(ProtocolError, match="param_row:Layer height"):
        pcl.run_ops(world.ui, [{"op": "float", "label": "Layer height", "value": "0.2"}], measure=timed_flow_step)
    # the lookup itself returned (ok=1); the op raised outside that span
    assert stage_lines(capsys) == [("locate.Layer height", "1"), ("field.Layer height", "0")]


def test_a_stage_line_reports_the_step_outcome_and_returns_the_result(capsys):
    def refuse():
        raise ProtocolError("param_tab:Speed")

    assert timed_flow_step("tab.Quality", lambda: "clicked") == "clicked"
    with pytest.raises(ProtocolError, match="param_tab:Speed"):
        timed_flow_step("tab.Speed", refuse)
    assert stage_lines(capsys) == [("tab.Quality", "1"), ("tab.Speed", "0")]


@pytest.mark.parametrize("scenario,prefix", [
    ("compare_276_quality", "[flow276]"),
    ("compare_276_strength", "[flow276]"),
    ("uia_param_overhang_speeds", "[flow264]"),
    ("compare_265_quality", None),
    ("uia_param_speed_limits", None),
    ("uia_param_speed_limits_std02", None),
    ("uia_param_overhang_speeds_std02", None),
    ("uia_param_accelerations", None),
    ("uia_param_save_only", None),
])
def test_only_the_registered_scenarios_get_a_stage_timer(scenario, prefix, capsys):
    timer = flow_step_measure(scenario)
    if prefix is None:
        assert timer is None
        return
    assert timer("probe", lambda: "done") == "done"
    assert capsys.readouterr().out.startswith(prefix + " probe ok=1 seconds=")


def test_the_registry_names_registered_scenarios_and_times_every_276_trial():
    assert set(TIMED_FLOWS) <= set(nm.SCENARIOS)
    assert all((flow_step_measure(name) is not None) == name.startswith("compare_276_") for name in MAINTENANCE_TRIALS)


@pytest.mark.parametrize("scenario,prepared,prefix", [
    ("uia_param_overhang_speeds", False, "[flow264]"),
    ("uia_param_accelerations", False, None),
    ("compare_276_quality", True, "[flow276]"),
    ("compare_265_quality", True, None),
])
def test_edit_param_cases_passes_the_registered_timer_to_run_ops(monkeypatch, scenario, prepared, prefix, capsys):
    seen = []
    ops = [{"op": "float", "label": "Layer height", "value": "0.2"}]
    monkeypatch.setattr(nsb, "scenario_ops", lambda scenario: ops)
    monkeypatch.setattr(pcl, "run_ops", lambda ui, got, **options: seen.append((ui, got, options)))
    nsb.edit_param_cases(object(), scenario)
    [(ui, got, options)] = seen
    assert got is ops
    assert options.keys() == ({"prepare_advanced"} if prepared else set()) | ({"measure"} if prefix else set())
    if prefix:
        assert options["measure"]("probe", lambda: None) is None
        assert capsys.readouterr().out.startswith(prefix + " probe ok=1 seconds=")
    if prepared:
        assert options["prepare_advanced"] is ensure_process_advanced


def test_worker_times_the_save_stage_through_the_same_registry():
    source = (Path(__file__).resolve().parents[1] / "tools" / "native_save_guest.py").read_text(encoding="utf-8")
    assert re.search(r'timer = flow_step_measure\(scenario\)\s+'
                     r'if timer:\s+timer\("save", ui\.save_project, prepared_dialog=setup\.get\("dialog_hwnd"\)\)\s+'
                     r'else:\s+ui\.save_project\(prepared_dialog=setup\.get\("dialog_hwnd"\)\)', source)
    assert 'startswith("compare_276_")' not in source      # the one copy of that rule is flow_step_measure
