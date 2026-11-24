"""The process-panel flows of #276 and #264: their per-stage times, the registry
behind those, and the readiness wait that replaces the fixed wait after Enter
(the #276 trials, the two #264 scenarios).

Fake Win32 boundaries only: nothing here launches an application."""
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

import pytest

from harness import agent_business_ui as module
from harness import mixing_util
from harness import native_matrix as nm
from harness import native_preset_script as nps
from harness.native_preset_script import (TIMED_FLOWS, WAITS_264, ensure_process_advanced, flow_step_measure,
                                          timed_flow_step, waits_flow_commit)
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
    # a failing edit_param_cases screenshots the sidebar for real: never from a test
    monkeypatch.setattr(nsb, "_save_failure_shot", lambda *args: None)
    return SimpleNamespace(calls=calls, ui=ui, page=page, knobs=knobs)


def recording_measure(calls):
    """A `measure` that marks where each timed span opens, then runs the step."""
    def measure(name, action, *args, **kwargs):
        calls.append(("measure", name))
        return action(*args, **kwargs)
    return measure


def parse_stages(text):
    """(name, ok) of every stage line in `text`, in print order: a span is
    written when it closes, so children come before their parent."""
    return [line.groups()[:2] for line in filter(None, map(STAGE_LINE.fullmatch, text.splitlines()))]


def stage_lines(capsys):
    return parse_stages(capsys.readouterr().out)


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


# fa706g3 run 19d61032: the third box is wheeled into view and its row located
# again; the four boxes share one label.
STAGES_264 = [
    "tab.Quality", "checkbox.Detect overhang", "tab.Speed", "checkbox.Slow down",
    "locate.Overhang speed[0]", "edit_readback.Overhang speed[0]", "field.Overhang speed[0]",
    "locate.Overhang speed[1]", "edit_readback.Overhang speed[1]", "field.Overhang speed[1]",
    "locate.Overhang speed[2]", "locate.Overhang speed[2]",
    "edit_readback.Overhang speed[2]", "field.Overhang speed[2]",
    "locate.Overhang speed[3]", "edit_readback.Overhang speed[3]", "field.Overhang speed[3]"]
# The names of the #276 baseline (guest run ec032d7c), unchanged.
STAGES_276 = [
    "tab.Quality", "locate.Layer height", "edit_readback.Layer height", "field.Layer height",
    "locate.Outer wall line width", "edit_readback.Outer wall line width", "field.Outer wall line width",
    "tab.Speed", "locate.Outer wall speed", "edit_readback.Outer wall speed", "field.Outer wall speed"]


@pytest.mark.parametrize("scenario,stages", [
    ("uia_param_overhang_speeds", STAGES_264),
    ("compare_276_quality", STAGES_276),
], ids=["264", "276"])
def test_stage_names_separate_parents_children_and_same_labelled_fields(world, scenario, stages, capsys):
    pcl.run_ops(world.ui, nsb.scenario_ops(scenario), measure=timed_flow_step)
    assert stage_lines(capsys) == [(name, "1") for name in stages]


# Feishu #264 names the FDM test model (欧特克FDM测试): the `_fdmt` twin is the
# row as written, the cube's run its comparison.
@pytest.mark.parametrize("scenario", ["uia_param_overhang_speeds", "uia_param_overhang_speeds_fdmt"], ids=["cube", "fdmt"])
def test_the_264_scenarios_log_the_same_stages_under_the_one_tag_from_edit_param_cases(business, scenario, capsys):
    nsb.edit_param_cases(business.ui, scenario)
    lines = [line for line in capsys.readouterr().out.splitlines() if STAGE_LINE.fullmatch(line)]
    assert all(line.startswith("[flow264] ") for line in lines)
    assert parse_stages("\n".join(lines)) == [(name, "1") for name in STAGES_264]


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
    ("uia_param_overhang_speeds_fdmt", "[flow264]"),
    ("compare_265_quality", None),
    ("uia_param_speed_limits", None),
    ("uia_param_speed_limits_std02", None),
    ("uia_param_overhang_speeds_std02", None),
    ("uia_param_overhang_speeds_shapes", None),
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
    # a timed name is a registered scenario, or the twin of one on another fixture
    assert set(TIMED_FLOWS) <= set(nm.SCENARIOS) | set(nm.std_twins(nm.SCENARIOS))
    assert all((flow_step_measure(name) is not None) == name.startswith("compare_276_") for name in MAINTENANCE_TRIALS)
    # a #264 scenario that waits is timed: its stage lines are what the wait's cost is read from
    assert WAITS_264 <= set(TIMED_FLOWS)


@pytest.mark.parametrize("scenario,prepared,prefix,waits", [
    ("uia_param_overhang_speeds", False, "[flow264]", True),
    ("uia_param_overhang_speeds_fdmt", False, "[flow264]", True),
    ("uia_param_overhang_speeds_std02", False, None, False),
    ("uia_param_accelerations", False, None, False),
    ("compare_276_quality", True, "[flow276]", True),
    ("compare_276_strength", True, "[flow276]", True),
    ("compare_265_quality", True, None, False),
])
def test_edit_param_cases_passes_the_registered_timer_to_run_ops(monkeypatch, scenario, prepared, prefix, waits,
                                                                 capsys):
    seen = []
    ops = [{"op": "float", "label": "Layer height", "value": "0.2"}]
    monkeypatch.setattr(nsb, "scenario_ops", lambda scenario: ops)
    monkeypatch.setattr(pcl, "run_ops", lambda ui, got, **options: seen.append((ui, got, options)))
    nsb.edit_param_cases(object(), scenario)
    [(ui, got, options)] = seen
    assert got is ops
    assert options.keys() == (({"prepare_advanced"} if prepared else set()) | ({"measure"} if prefix else set())
                              | ({"ready_commit"} if waits else set()))
    if waits:
        assert options["ready_commit"] is True
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


# ---- the readiness wait that replaces edit's fixed 6 s: the #276 fields, the #264 boxes ----

CAP, POLL = module.FLOW_COMMIT_CAP_S, module.FLOW_COMMIT_POLL_S
NOT_STABLE = "[param-uia] flow_commit_not_stable ok=0 value={!r}"
LAYER, OVERHANG = "Layer height", "Overhang speed"
BOTH_264 = ["uia_param_overhang_speeds", "uia_param_overhang_speeds_fdmt"]
BOXES_264 = ["40", "30", "20", "10"]


class FakeApp:
    """What the application does after Enter, on the fake clock: the windows
    it keeps, the control tree it shows (it grows with `version`), and the
    changes a test schedules with at(when, action). Fidelity gap: nothing
    happens by itself - no rebuild, no repaint - only what a test schedules;
    `churning` rebuilds the tree on every tick."""

    def __init__(self, page):
        self.page, self.events, self.version, self.churning = page, [], 0, False
        self.alive, self.disabled = {11, *page.edits}, set()

    @property
    def tree(self):
        return [("row %d" % index, "Edit", (250, 900 + 30 * index, 330, 920 + 30 * index), 500 + index)
                for index in range(self.version + 1)]

    def at(self, when, action):
        self.events.append([when, action])

    def tick(self, now):
        for event in self.events:
            if event[0] is not None and event[0] <= now:
                event[0] = None
                event[1]()
        if self.churning:
            self.version += 1


@pytest.fixture
def business(world, monkeypatch):
    """A real BusinessUI on the fake page: edit(), pause(), owned() and the
    readiness wait are the driver's own. Its clock is a counter that sleeps
    advance, so no test waits for real: `now` is that counter, `asked` every
    pause the ui requested, `app.at(when, action)` what the application does."""
    ui = module.BusinessUI.__new__(module.BusinessUI)
    page, now, asked = world.page, [0.0], []
    app = FakeApp(page)
    ui.app = world.ui.app
    ui.guard = lambda: None
    ui.identity = lambda: ({"width": 1920, "height": 1200}, None)     # the #264 stack reaches y 1166

    def edit_at(_root, x, y):
        return next(h for h, (rect, _text) in page.edits.items() if h in app.alive
                    and rect[0] <= x < rect[2] and rect[1] <= y < rect[3])

    def type_text(hwnd, text):       # as an Edit takes WM_SETTEXT; Enter is the application's to answer
        if text != "\r":
            page.edits[hwnd][1] = text

    def advance(seconds):
        now[0] += seconds
        app.tick(now[0])

    def pause(seconds):
        asked.append(seconds)
        module.BusinessUI.pause(ui, seconds)

    ui.wu = SimpleNamespace(
        client_to_screen=lambda hwnd, x, y: (x, y), deepest_child_at=edit_at,
        window_class=lambda hwnd: "Edit" if hwnd in page.edits else "wxGLCanvas",
        window_rect=lambda hwnd: tuple(page.edits[hwnd][0]) if hwnd in page.edits else (CANVAS_LEFT, 0, 1900, 1031),
        _window_pid=lambda hwnd: ui.app.pid,
        user32=SimpleNamespace(IsWindow=lambda h: h in app.alive, IsWindowVisible=lambda h: True,
                               IsChild=lambda root, h: True,
                               IsWindowEnabled=lambda h: h in app.alive and h not in app.disabled),
        edit_text=lambda h: page.edits[h][1], msg_click_screen=lambda *args: None,
        _send_msg=lambda *args: None, msg_text=type_text)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=advance))
    monkeypatch.setattr(mixing_util, "children", lambda hwnd: app.tree)
    ui.pause = pause
    return SimpleNamespace(ui=ui, app=app, page=page, now=now, asked=asked)


def settle_edit(business, text="0.42"):
    return business.ui.edit(EDIT_X, ROW_Y, text, wait_commit=business.ui.wait_flow_commit)


def texts(business):
    return [business.page.edits[h][1] for h in business.page.row_edits[LAYER]]


def box_texts(business):
    return [business.page.edits[h][1] for h in business.page.row_edits[OVERHANG]]


def never_wait(self, target, wanted):
    pytest.fail("the readiness wait was used outside the #276 trials and the two #264 scenarios")


def test_a_field_that_holds_its_value_on_a_still_page_ends_the_wait_after_three_polls(business):
    assert settle_edit(business)["after_text"] == "0.42"
    assert business.now[0] == pytest.approx(2 * POLL)
    assert business.asked == [0.5, 0.5]              # the fixed pause(6) is never asked for


def test_a_value_showing_while_the_page_is_still_rebuilding_is_not_taken_as_done(business):
    app = business.app
    app.at(0.3, lambda: setattr(app, "version", 1))       # the rebuild moves controls ...
    app.at(1.1, lambda: setattr(app, "version", 2))       # ... twice; the field shows its value throughout
    settle_edit(business)
    assert business.now[0] == pytest.approx(2.5)          # three still polls after the last move, not after Enter


def test_a_page_that_never_settles_waits_exactly_what_the_fixed_wait_took_and_does_not_raise(business, capsys):
    business.app.churning = True
    assert settle_edit(business)["after_text"] == "0.42"
    capped, asked = business.now[0], list(business.asked)
    assert capped == pytest.approx(CAP) and max(asked) == POLL
    assert capsys.readouterr().out.splitlines() == [NOT_STABLE.format("0.42")]     # said once, not raised
    business.now[0], business.asked[:] = 0.0, []
    business.ui.edit(EDIT_X, ROW_Y, "0.42")                # what it replaces, on the same clock
    assert business.asked == [6] and business.now[0] == pytest.approx(capped)
    assert capsys.readouterr().out == ""


def test_a_field_that_shows_its_value_while_greyed_out_is_not_taken_as_ready(business, capsys):
    layer = business.page.row_edits[LAYER][0]
    business.app.at(0.3, lambda: business.app.disabled.add(layer))
    pcl.uia_set_float(business.ui, LAYER, "0.42", ready_commit=True)       # the value is right: the readback passes
    assert texts(business) == ["0.42"]
    assert business.now[0] == pytest.approx(CAP)
    assert capsys.readouterr().out.splitlines() == [NOT_STABLE.format("0.42")]


def test_a_target_replaced_mid_wait_is_still_reported_as_edit_target_disappeared(business, capsys):
    page, app, old = business.page, business.app, business.page.row_edits[LAYER][0]

    def replace():                       # the rebuilt page gets a new Edit where the old one was
        app.alive.remove(old)
        page.edits[900] = [list(page.edits[old][0]), "0.42"]
        app.alive.add(900)

    app.at(0.6, replace)
    with pytest.raises(ProtocolError, match="^edit_target_disappeared$"):
        pcl.uia_set_float(business.ui, LAYER, "0.42", ready_commit=True)
    assert business.now[0] == pytest.approx(CAP)           # after the wait, as the fixed wait did
    assert capsys.readouterr().out == ""                   # and with no new signature


def test_a_field_that_ends_on_another_value_is_rejected_by_the_readback(business, capsys):
    app, layer = business.app, business.page.row_edits[LAYER][0]

    def clamp():                         # the application takes 0.42 down to its own maximum while rebuilding
        app.version = 1
        business.page.edits[layer][1] = "0.5"

    app.at(0.3, clamp)
    with pytest.raises(ProtocolError, match=r"param_uia_readback:Layer height:'0\.5'$"):
        pcl.uia_set_float(business.ui, LAYER, "0.42", ready_commit=True)
    assert business.now[0] == pytest.approx(CAP)
    assert capsys.readouterr().out.splitlines() == [NOT_STABLE.format("0.42")]


def test_the_276_field_passes_as_soon_as_the_page_stops_without_the_fixed_wait(business, capsys):
    business.app.at(0.3, lambda: setattr(business.app, "version", 1))       # one rebuild pass
    pcl.uia_set_float(business.ui, LAYER, "0.42", ready_commit=True)
    assert texts(business) == ["0.42"]
    assert business.now[0] == pytest.approx(1.5) and business.asked == [0.5, 0.5, 0.5]
    assert capsys.readouterr().out == ""


def test_a_box_wheeled_into_view_still_waits_for_its_committed_value(business):
    boxes = business.page.row_edits[OVERHANG]
    pcl.uia_set_float(business.ui, OVERHANG, "10", "Overhang", field_index=2, ready_commit=True)
    assert business.page.edits[boxes[2]][1] == "10"
    assert business.asked == [1.0, 0.5, 0.5]              # the page settles after its wheel, never 6 s


@pytest.mark.parametrize("scenario,waits", [
    ("compare_276_quality", True), ("compare_276_strength", True),
    ("uia_param_overhang_speeds", True), ("uia_param_overhang_speeds_fdmt", True),
    ("compare_265_quality", False), ("compare_265_strength", False),
    ("uia_param_speed_limits", False), ("uia_param_speed_limits_std02", False),
    # other twins of the row do not wait with it
    ("uia_param_overhang_speeds_std02", False), ("uia_param_overhang_speeds_shapes", False),
    ("uia_param_accelerations", False), ("uia_param_accelerations_fdmt", False),
])
def test_only_the_276_trials_and_the_two_264_names_wait_for_the_committed_value(scenario, waits):
    assert waits_flow_commit(scenario) is waits


def test_edit_without_a_hook_keeps_the_fixed_six_second_wait(business, monkeypatch):
    monkeypatch.setattr(module.BusinessUI, "wait_flow_commit", never_wait)
    assert business.ui.edit(EDIT_X, ROW_Y, "0.42")["after_text"] == "0.42"
    assert business.asked == [6] and business.now[0] == pytest.approx(6)


def test_edit_hands_the_hook_the_target_and_the_text(business):
    seen = []
    receipt = business.ui.edit(EDIT_X, ROW_Y, "0.42", wait_commit=lambda target, text: seen.append((target, text)))
    assert seen == [(business.page.row_edits[LAYER][0], "0.42")]
    assert business.asked == [] and receipt["committed"] is True


def test_without_the_flag_nothing_passes_the_hook_down(world, monkeypatch):
    real_float, real_edit, floats, edits = pcl.uia_set_float, world.ui.edit, [], []
    monkeypatch.setattr(pcl, "uia_set_float",
                        lambda *args, **options: (floats.append(options), real_float(*args, **options))[1])
    world.ui.edit = lambda x, y, text, **options: (edits.append(options), real_edit(x, y, text))[1]
    pcl.run_ops(world.ui, nsb.scenario_ops("uia_param_overhang_speeds"))
    # four ops from run_ops, none flagged (the parked box re-enters with the
    # flag at its default), and edit() is never offered the hook
    top = [options for options in floats if "_parked" not in options]
    assert len(top) == 4 and all("ready_commit" not in options for options in top)
    assert not any(options.get("ready_commit") for options in floats) and edits == [{}] * 4


def test_with_the_flag_every_float_op_gets_the_ui_own_wait(world):
    spy = world.ui.wait_flow_commit = lambda target, wanted: None
    real_edit, edits = world.ui.edit, []
    world.ui.edit = lambda x, y, text, **options: (edits.append(options), real_edit(x, y, text))[1]
    ops = nsb.scenario_ops("uia_param_overhang_speeds")
    pcl.run_ops(world.ui, ops, measure=recording_measure(world.calls), ready_commit=True)
    assert edits == [{"wait_commit": spy}] * 4


def edit_param_cases_stops_at_run_ops(monkeypatch):
    """edit_param_cases for real, run_ops a recorder of the options it was
    given. A failing edit_param_cases screenshots the sidebar: never from here."""
    monkeypatch.setattr(nsb, "_save_failure_shot", lambda *args: None)
    seen = []
    monkeypatch.setattr(pcl, "run_ops", lambda ui, ops, **options: seen.append(options))
    return seen


@pytest.mark.parametrize("scenario", BOTH_264, ids=["cube", "fdmt"])
def test_both_264_names_get_the_flag_from_edit_param_cases(monkeypatch, scenario):
    seen = edit_param_cases_stops_at_run_ops(monkeypatch)
    nsb.edit_param_cases(object(), scenario)
    assert [set(options) for options in seen] == [{"measure", "ready_commit"}]
    assert seen[0]["ready_commit"] is True


def test_edit_param_cases_passes_the_flag_exactly_where_waits_flow_commit_says(monkeypatch):
    """Every name a command line may take, with its own ops from the real table:
    the flag reaches run_ops for the #276 trials and the two #264 names, and
    reaches nothing else that has ops."""
    seen = edit_param_cases_stops_at_run_ops(monkeypatch)
    flagged = set()
    for scenario in dict.fromkeys((*nm.scenario_names(), *MAINTENANCE_TRIALS)):
        if nsb.scenario_ops(scenario) is None:
            continue
        seen.clear()
        nsb.edit_param_cases(object(), scenario)
        assert len(seen) == 1, scenario
        # the flag, and nothing else, is what the two #264 names gained
        assert ("ready_commit" in seen[0]) is waits_flow_commit(scenario), scenario
        assert set(seen[0]) - {"ready_commit"} == (
            ({"prepare_advanced"} if scenario in MAINTENANCE_TRIALS else set())
            | ({"measure"} if flow_step_measure(scenario) else set())), scenario
        if "ready_commit" in seen[0]:
            assert seen[0]["ready_commit"] is True
            flagged.add(scenario)
    assert flagged == {name for name in MAINTENANCE_TRIALS if name.startswith("compare_276_")} | set(BOTH_264)


# Before the first box is driven, run_ops has paused four times for 1 s: the
# two tab switches and the two checkbox ops (a page pause each).
FIRST_BOX = 4 * 1.0


@pytest.mark.parametrize("scenario", BOTH_264, ids=["cube", "fdmt"])
def test_both_264_flows_wait_for_the_committed_value_of_each_box_and_never_for_the_fixed_six_seconds(business, scenario,
                                                                                                    capsys):
    real, waits = business.ui.wait_flow_commit, []
    business.ui.wait_flow_commit = lambda target, wanted: (waits.append((target, wanted)), real(target, wanted))[1]
    nsb.edit_param_cases(business.ui, scenario)
    assert box_texts(business) == BOXES_264
    assert waits == list(zip(business.page.row_edits[OVERHANG], BOXES_264))     # once per box, its handle and its value
    # the pauses asked for, in order: 1 s per tab switch and after every op,
    # two 0.5 s polls per box on a still page, the wheeled third box its 1 s
    # first, and run_ops's final 6 s
    assert business.asked == [1.0, 1.0, 1.0, 1.0, 0.5, 0.5, 1.0, 0.5, 0.5, 1.0,
                              1.0, 0.5, 0.5, 1.0, 0.5, 0.5, 1.0, 6]
    # 4 s of page pauses + four boxes x 2 s + the wheel's 1 s + the final 6 s; with
    # the fixed wait the same run took 39 s (four boxes x 7 s)
    assert business.now[0] == pytest.approx(19)
    assert "flow_commit" not in capsys.readouterr().out


@pytest.mark.parametrize("scenario", BOTH_264, ids=["cube", "fdmt"])
def test_a_264_run_on_pages_that_never_settle_costs_what_the_fixed_wait_cost_and_still_passes(business, scenario, capsys):
    pcl.run_ops(business.ui, nsb.scenario_ops(scenario))             # as before the flag: the fixed 6 s per box
    fixed = sum(business.asked)
    business.page.reset()
    business.now[0], business.asked[:] = 0.0, []
    business.app.churning = True
    nsb.edit_param_cases(business.ui, scenario)
    assert box_texts(business) == BOXES_264
    assert sum(business.asked) == pytest.approx(fixed) and business.asked[-2:] == [1.0, 6]
    out = capsys.readouterr().out
    # said once per box, with the value that was wanted; nothing raised
    assert [line for line in out.splitlines() if "flow_commit" in line] == [NOT_STABLE.format(value) for value in BOXES_264]
    assert parse_stages(out) == [(name, "1") for name in STAGES_264]


@pytest.mark.parametrize("scenario", [
    "uia_param_accelerations", "uia_param_jerk", "uia_param_speed_limits", "uia_param_first_speeds_fdmt",
], ids=["accelerations", "jerk", "speed_limits", "first_speeds_fdmt"])
def test_other_param_scenarios_keep_the_fixed_wait_through_their_own_ops(business, monkeypatch, scenario, capsys):
    monkeypatch.setattr(module.BusinessUI, "wait_flow_commit", never_wait)
    # the scenario's own ops on the fake page: every label sits on its single-Edit row
    monkeypatch.setattr(pcl, "_find_phrase_row_any", lambda app, phrase, group_substr=None: (
        business.page.row_y(LAYER), phrase if isinstance(phrase, str) else phrase[0]))
    ops = nsb.scenario_ops(scenario)
    assert all(op["op"] == "float" for op in ops)                 # floats only: nothing here needs another fake
    nsb.edit_param_cases(business.ui, scenario)
    # every edit's wait is the fixed 6 s, then run_ops's 1 s after the op (and
    # its 1 s after a tab switch first); its final 6 s
    expected = []
    for op in ops:
        expected += [1.0] * ("tab" in op) + [6, 1.0]
    assert business.asked == expected + [6]
    assert texts(business) == [ops[-1]["value"]] and "flow_commit" not in capsys.readouterr().out


@pytest.mark.parametrize("damage", ["ends-on-another-value", "click-lands-on-the-next-box"])
def test_under_the_readiness_wait_the_264_readback_stays_the_gate(business, capsys, damage):
    page, boxes = business.page, business.page.row_edits[OVERHANG]
    if damage == "ends-on-another-value":
        def clamp():                      # the application takes the second band to its own maximum while rebuilding
            business.app.version = 1
            page.edits[boxes[1]][1] = "35"

        second = FIRST_BOX + 2 * POLL + 1.0           # the first box's 1 s wait, then the 1 s after its op
        business.app.at(second + 0.6, clamp)          # inside the second box's wait
        refused, now, said = "param_uia_readback:Overhang speed:'35'$", second + CAP, [NOT_STABLE.format("30")]
        left = ["40", "35", "", ""]                   # the wait ran to its cap for the wanted 30, and was not the gate
    else:
        real = business.ui.wu.deepest_child_at
        below = dict(zip(boxes, boxes[1:]))
        business.ui.wu.deepest_child_at = lambda root, x, y: below.get(real(root, x, y), real(root, x, y))
        refused, now, said = "param_uia_readback:Overhang speed:'40'$", FIRST_BOX + 2 * POLL, []
        left = ["", "40", "", ""]                     # typed into the box below the one the row lookup named
    with pytest.raises(ProtocolError, match=refused):
        nsb.edit_param_cases(business.ui, "uia_param_overhang_speeds")
    assert box_texts(business) == left and business.now[0] == pytest.approx(now)
    assert [line for line in capsys.readouterr().out.splitlines() if "flow_commit" in line] == said


@pytest.mark.parametrize("scenario,asked,timed", [
    # the edit's wait(es), run_ops's pause after the op, run_ops's final settle
    ("compare_265_quality", [6, 1.0, 6], False),
    ("compare_276_quality", [0.5, 0.5, 1.0, 6], True),
], ids=["265", "276"])
def test_in_the_matched_trials_only_276_gives_up_the_fixed_wait(business, monkeypatch, scenario, asked, timed,
                                                                capsys):
    monkeypatch.setattr(nsb, "scenario_ops", lambda scenario: [{"op": "float", "label": LAYER, "value": "0.2"}])
    monkeypatch.setattr(nps, "ensure_process_advanced", lambda ui: None)
    nsb.edit_param_cases(business.ui, scenario)
    assert business.asked == asked and texts(business) == ["0.2"]
    assert ("edit_readback.Layer height" in capsys.readouterr().out) is timed


def test_a_276_run_whose_pages_settle_spends_a_second_per_field_instead_of_six(business, monkeypatch, capsys):
    monkeypatch.setattr(nps, "ensure_process_advanced", lambda ui: None)
    nsb.edit_param_cases(business.ui, "compare_276_quality")
    page = business.page
    assert [page.edits[page.row_edits[label][0]][1]
            for label in (LAYER, "Outer wall line width", "Outer wall speed")] == ["0.2", "0.42", "700"]
    assert business.asked[:-2].count(0.5) == 6 and 6 not in business.asked[:-2]   # a second per field
    out = capsys.readouterr().out
    assert parse_stages(out) == [(name, "1") for name in STAGES_276] and "flow_commit" not in out


def test_a_276_run_on_pages_that_never_settle_still_passes_and_says_so_per_field(business, monkeypatch, capsys):
    business.app.churning = True
    monkeypatch.setattr(nps, "ensure_process_advanced", lambda ui: None)
    nsb.edit_param_cases(business.ui, "compare_276_quality")
    page = business.page
    assert [page.edits[page.row_edits[label][0]][1]
            for label in (LAYER, "Outer wall line width", "Outer wall speed")] == ["0.2", "0.42", "700"]
    # three capped waits, five 1 s pauses, run_ops's final 6 s
    assert sum(business.asked) == pytest.approx(3 * CAP + 5 + 6)
    out = capsys.readouterr().out
    assert [line for line in out.splitlines() if "flow_commit" in line] == [NOT_STABLE.format(value)
                                                                            for value in ("0.2", "0.42", "700")]
    assert parse_stages(out) == [(name, "1") for name in STAGES_276]


# ---- scroll_group_into_view: one wheel call sized from the title's own rect ----

# Census c101c0f4 (2.4.0, page at top, 1032-tall work area): the options
# viewport, and the top of 'Overhangs', the last group of the Quality page.
BAND = (718, 1031)
TITLE_H = 18
OVERHANGS = 2560
EDGE = BAND[1] - 24                    # a title's bottom has to reach [BAND[0] + 2, EDGE]
STEP = pp.WHEEL_STEP_PX
GROUP = "Overhangs"


def refuse(*args, **kwargs):
    pytest.fail("a test reached the desktop: real wheel input or a real focus reset")


class ScrollPage:
    """The options page as scroll_group_into_view reads it: the title's rect
    follows the page offset, a notch moves the page STEP px, and the page
    stops at its top and at `end`. `jumpy` is how many notches the FIRST wheel
    moves beyond what it was asked; a `dead` page moves for no wheel until
    its focus reset."""

    def __init__(self, title_top, end=None, jumpy=0, dead=False):
        self.title_top, self.end, self.jumpy, self.dead = title_top, end, jumpy, dead
        self.offset, self.calls, self.resets = 0, [], []

    def title(self, session, substr):
        top = self.title_top - self.offset
        return (13, top, 406, top + TITLE_H), 4321

    def wheel(self, session, viewport, notches, delta=-120):
        self.calls.append((notches, delta))
        if self.dead:
            return
        step = STEP * (notches + self.jumpy) * (-1 if delta > 0 else 1)
        self.jumpy = 0
        self.offset = max(0, self.offset + step)
        if self.end is not None:
            self.offset = min(self.end, self.offset)

    def reset(self, session, why=""):
        self.resets.append(why)
        self.dead = False
        return True


@pytest.fixture
def make_page(monkeypatch):
    """A maker of fake pages for scroll_group_into_view, which then runs for
    real on them. A page cannot be made without every collaborator the
    function has being faked with it, and the real wheel input and the real
    focus resets - which would act on whatever window sits on this desktop -
    are refused."""
    def make(title_top, band=BAND, **options):
        page = ScrollPage(title_top, **options)
        page.band = band
        monkeypatch.setattr(pp, "options_viewport", lambda session: ((1, band[0], 421, band[1]), 4321))
        monkeypatch.setattr(pp, "view_band", lambda session: band)
        monkeypatch.setattr(pp, "client_origin", lambda session: (0, 0))
        monkeypatch.setattr(pp, "time", SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None))
        monkeypatch.setattr(pp, "real_wheel", refuse)
        monkeypatch.setattr(pp, "neutralize_focus", refuse)
        monkeypatch.setattr(pp, "group_title", page.title)
        monkeypatch.setattr(pp, "wheel_viewport", page.wheel)
        monkeypatch.setattr(pp, "focus_off_edit", page.reset)
        return page
    return make


def scroll_group(page):
    """Run the real function on `page` (the title 'Overhangs'); what it returned."""
    return pp.scroll_group_into_view(None, GROUP, timeout_s=5.0)


def title_at(page):
    """The title as the page shows it now."""
    return page.title(None, GROUP)


def in_band(page):
    """True when the title's bottom is where the function wants it: inside its band."""
    return page.band[0] + 2 <= title_at(page)[0][3] <= page.band[1] - 24


def test_a_title_already_in_the_band_is_returned_without_a_wheel(make_page):
    page = make_page(OVERHANGS)
    page.offset = 1600
    assert scroll_group(page) == title_at(page) and in_band(page)
    assert page.calls == [] and page.resets == []


@pytest.mark.parametrize("title_top,start,wheel,landing", [
    (EDGE + 40 - TITLE_H, 0, (1, -120), STEP),                      # 40px under the band edge
    (EDGE + STEP - TITLE_H, 0, (1, -120), STEP),                    # a notch under it: the landing is the edge itself
    (BAND[0] + 2 - 40 + 300 - TITLE_H, 300, (1, 120), 240),         # 40px over the band top, the page 300px down
], ids=["40px-under", "a-notch-under", "40px-over"])
def test_a_title_at_most_a_notch_outside_the_band_still_takes_one_notch(make_page, title_top, start, wheel, landing):
    page = make_page(title_top)
    page.offset = start
    assert scroll_group(page) == title_at(page) and in_band(page)
    assert page.calls == [wheel] and page.offset == landing and page.resets == []


def notches_to_reach(page, down):
    """What the 1-notch loop sent: whole notches until the title's bottom passed the band edge it had to cross."""
    bottom = page.title_top + TITLE_H - page.offset
    left = bottom - (page.band[1] - 24) if down else (page.band[0] + 2) - bottom
    return -(-left // STEP)


@pytest.mark.parametrize("title_top,start,wheels", [
    (OVERHANGS, 0, [(27, -120)]),                 # census c101c0f4: its bottom 1571px under the band edge
    (1720, 1500, [(9, 120)]),                     # 482px over the band top, the page 1500px down
    (EDGE + 55 * STEP - TITLE_H, 0, [(40, -120), (15, -120)]),       # more notches than one call may carry
], ids=["overhangs-27-notches", "over-the-band", "beyond-one-call"])
def test_a_title_further_out_gets_its_notches_in_one_call_and_lands_where_the_one_notch_loop_landed(make_page, title_top,
                                                                                                  start, wheels):
    page = make_page(title_top)
    page.offset = start
    notches = notches_to_reach(page, wheels[0][1] < 0)      # read before the page moves
    assert scroll_group(page) == title_at(page) and in_band(page)
    # as many notches as the 1-notch loop sent, in as few calls as the largest allows
    assert sum(count for count, _delta in wheels) == notches
    assert max(count for count, _delta in wheels) <= pp.RESET_WHEEL_NOTCHES
    assert page.calls == wheels and page.resets == []
    assert page.offset == start + notches * STEP * (1 if wheels[0][1] < 0 else -1)     # wheeling down moves the page up


@pytest.mark.parametrize("end,after_the_burst", [
    (1540, [(1, -120)] * 7),                            # 31px short of the band: single notches from then on
    (1500, [(2, -120), (2, -120)] + [(1, -120)] * 5),   # 71px short: the still page is only counted one wheel later
], ids=["31px-short", "71px-short"])
def test_a_page_that_stops_short_takes_its_burst_then_the_stall_tail_in_single_notches(make_page, end, after_the_burst):
    page = make_page(OVERHANGS, end=end)
    assert scroll_group(page) == title_at(page)          # accepted where the page stopped, as before
    assert page.calls == [(27, -120)] + after_the_burst and page.offset == end
    # the tail the loop always had, in both cases: the third still page it measures resets the focus, the sixth accepts
    assert len(after_the_burst) == 7 and page.resets == ["scroll_group(%r)" % GROUP]


def test_a_wheel_dead_until_its_focus_reset_meets_the_same_stall_logic_then_one_burst_for_the_rest(make_page):
    page = make_page(OVERHANGS, dead=True)
    assert scroll_group(page) == title_at(page) and page.offset == 27 * STEP      # the landing of 27 single notches
    # the still page is counted from the second wheel; the third single is the
    # reset and the fourth the first live notch (still counted against the old
    # measurement); then one burst covers the 25 notches left
    assert page.calls == [(27, -120), (27, -120)] + [(1, -120)] * 4 + [(25, -120)]
    assert page.resets == ["scroll_group(%r)" % GROUP]


def test_a_burst_that_overshoots_the_band_is_corrected_by_one_notch_onto_the_one_notch_landing(make_page):
    # a short band, 702..776, and a title 100px under its edge: 2 notches
    page = make_page(776 + 100 - TITLE_H, band=(700, 800), jumpy=1)
    assert scroll_group(page) == title_at(page) and in_band(page)
    # the burst moved 3 notches (696: over the band top); one notch back, onto the landing of 2 single notches
    assert page.calls == [(2, -120), (1, 120)] and page.offset == 2 * STEP and page.resets == []
