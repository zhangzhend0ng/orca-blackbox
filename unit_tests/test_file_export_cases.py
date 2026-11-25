"""Wiring of the File > Export GUI helpers against fake windows (no application, no guest).

The helpers drive real Win32 objects on the guest; here every window call is
replaced by a recording fake so that the order of the actions, the refusal
paths and the receipt are pinned without a GUI."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'unit_tests'))

import file_export_cases as cases  # noqa: E402
import m7_common as m7  # noqa: E402
import test_export_io_oracle as gcode  # noqa: E402

ROWS = [{'index': index, 'label': text, 'enabled': True, 'submenu': False}
        for index, text in enumerate(gcode.EXPORT_ROWS)]
DIALOG, EDIT, SESSION_PID = 4242, 9, 4321


class Rig:
    """One native save dialog, its file name box and a record of every message."""

    def __init__(self, monkeypatch, tmp_path, title='Save G-code file as:', closes_on='name'):
        self.tmp_path, self.title, self.closes_on = tmp_path, title, closes_on
        self.visible, self.default, self.calls, self.typed = True, '立方体_PLA_21m22s', [], []
        self.text = self.default
        monkeypatch.setattr(cases, 'read_export_menu', lambda session: {'file': [], 'export': ROWS})
        monkeypatch.setattr(m7, 'file_menu_dispatch', self.dispatch)
        monkeypatch.setattr(cases, 'descendants', lambda hwnd: [('ComboBox', '', 7), ('Edit', '', EDIT)])
        monkeypatch.setattr(cases, 'combobox_items', lambda box: {'selected': 0, 'items': ['G-code files (*.gcode)']})
        monkeypatch.setattr(cases.export_util, 'find_edit', lambda hwnd: EDIT)
        monkeypatch.setattr(cases.winutil, '_window_pid', lambda hwnd: SESSION_PID)
        monkeypatch.setattr(cases.winutil, 'select_all', self.select_all)
        monkeypatch.setattr(cases.winutil, 'msg_text', self.type)
        monkeypatch.setattr(cases.winutil, 'edit_text', lambda hwnd, size=64: self.text)
        monkeypatch.setattr(cases.winutil, '_send_msg', self.send)
        monkeypatch.setattr(cases.winutil.user32, 'IsWindowVisible', lambda hwnd: self.visible)
        monkeypatch.setattr(cases, 'capture_window', lambda hwnd, path: {'width_px': 800, 'height_px': 600})
        monkeypatch.setattr(cases.time, 'sleep', lambda seconds: None)
        self.session = SimpleNamespace(pid=SESSION_PID, alive=lambda: True)

    def dispatch(self, session, item, expect_dialog=False, via=None, timeout_s=12.0, *, inspect_enabled=False):
        self.calls.append(('dispatch', item, via, expect_dialog))
        return True, ('#32770', self.title, (0, 0, 1, 1), DIALOG)

    def select_all(self, hwnd):
        self.calls.append(('select_all',))

    def type(self, hwnd, text):
        self.calls.append(('type', text))
        self.text = text

    def send(self, hwnd, msg, wparam, lparam):
        self.calls.append(('send', msg, wparam))
        if msg != 0x0111 or wparam != 1:
            return
        target = Path(self.text)
        if target.is_dir():
            return  # the dialog navigates and stays open
        self.typed.append(self.text)
        gcode.write_gcode(self.tmp_path / f'{self.text}.gcode', gcode.gcode_text())
        if self.closes_on == 'name':
            self.visible = False


def test_export_navigates_first_and_lets_the_application_name_the_file(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path)
    analysis = {}
    receipt = cases.export_via_file_menu(rig.session, 'Export G-code', tmp_path, 'plate', tmp_path, analysis,
                                         'Save G-code file as', 'gcode')
    assert receipt['saved_name'] == 'plate.gcode' and receipt['saved_extension'] == '.gcode'
    assert receipt['typed_name'] == 'plate' and receipt['filename_before_save'] == 'plate'
    assert receipt['default_name'] == '立方体_PLA_21m22s' and receipt['title'] == 'Save G-code file as:'
    assert receipt['types'] == [{'selected': 0, 'items': ['G-code files (*.gcode)']}]
    assert receipt['dialog_closed'] and receipt['app_alive'] and receipt['file_bytes'] > 0
    assert analysis['export'] is receipt
    # Directory first (the dialog stays open), then the bare name; never a path with an extension.
    assert rig.calls[:7] == [('dispatch', 'Export G-code', 'Export', True), ('select_all',),
                             ('type', str(tmp_path)), ('send', 0x0111, 1), ('select_all',),
                             ('type', 'plate'), ('send', 0x0111, 1)]
    assert (tmp_path / 'export-dialog.png').exists() is False  # the image call is faked; nothing else is written
    assert sorted(p.name for p in tmp_path.iterdir()) == ['plate.gcode']


def test_export_refuses_a_disabled_or_missing_row_before_touching_any_dialog(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path)
    monkeypatch.setattr(cases, 'read_export_menu', lambda session: {
        'file': [], 'export': [dict(row, enabled=row['index'] != 5) for row in ROWS]})
    with pytest.raises(ValueError, match='File > Export > Export G-code is disabled'):
        cases.export_via_file_menu(rig.session, 'Export G-code', tmp_path, 'plate', tmp_path, {}, 'x', 'gcode')
    monkeypatch.setattr(cases, 'read_export_menu', lambda session: {'file': [], 'export': ROWS[:5]})
    with pytest.raises(ValueError, match="has no row 'Export G-code'"):
        cases.export_via_file_menu(rig.session, 'Export G-code', tmp_path, 'plate', tmp_path, {}, 'x', 'gcode')
    assert rig.calls == []


def test_export_never_cancels_a_dialog_with_another_title(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, title='Memory Usage Warning')
    with pytest.raises(ValueError, match="opened 'Memory Usage Warning', expected a dialog titled 'Save G-code file as'"):
        cases.export_via_file_menu(rig.session, 'Export G-code', tmp_path, 'plate', tmp_path, {}, 'Save G-code file as',
                                   'gcode')
    # Cancelling that dialog would answer "No, Stop": nothing may be sent to it.
    assert rig.calls == [('dispatch', 'Export G-code', 'Export', True)]


def test_export_refuses_to_overwrite_and_reports_a_dialog_that_stays_open(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path)
    (tmp_path / 'plate.gcode').write_text('stale', encoding='utf-8')
    with pytest.raises(ValueError, match="'plate' already exists"):
        cases.export_via_file_menu(rig.session, 'Export G-code', tmp_path, 'plate', tmp_path, {}, 's', 'gcode')
    assert rig.calls == []
    (tmp_path / 'plate.gcode').unlink()
    stuck = Rig(monkeypatch, tmp_path, closes_on='never')
    monkeypatch.setattr(cases, '_wait_closed', lambda hwnd, timeout_s: False)
    with pytest.raises(ValueError, match="stayed open after the save"):
        cases.export_via_file_menu(stuck.session, 'Export G-code', tmp_path, 'plate', tmp_path, {}, 's', 'gcode')


class Guard(Rig):
    """The memory guard: its Yes button closes only on a click resolved inside the dialog."""

    def __init__(self, monkeypatch, tmp_path, closes=True):
        super().__init__(monkeypatch, tmp_path)
        self.closes, self.up = closes, True
        monkeypatch.setattr(cases.winutil.user32, 'IsWindowVisible', lambda hwnd: self.up)
        monkeypatch.setattr(m7, 'wait_dialog', self.wait_dialog)
        monkeypatch.setattr(cases, 'descendants', lambda hwnd: [
            ('wxWindowNR', 'Available system memory is critically low during slicing.', 20),
            ('wxWindowNR', 'Yes, Continue', 11), ('wxWindowNR', 'No, Stop', 12)])
        monkeypatch.setattr(cases.export_util, '_children_texts', lambda hwnd: [
            ('', (0, 0, 10, 10), 10), ('Yes, Continue', (100, 200, 300, 240), 11), ('No, Stop', (320, 200, 440, 240), 12),
            ('', (500, 500, 510, 510), 13)])
        monkeypatch.setattr(cases.winutil, 'msg_click_screen', self.click)
        monkeypatch.setattr(cases.winutil, 'window_from_screen_point', lambda x, y: 11)
        monkeypatch.setattr(cases.winutil, 'real_click_screen', lambda x, y: self.calls.append(('real click', x, y)) or 2)
        monkeypatch.setattr(cases.winutil.user32, 'SetCursorPos', lambda x, y: self.calls.append(('park', x, y)))

    def wait_dialog(self, pid, timeout_s=15.0, title_substr=''):
        return ('#32770', 'Memory Usage Warning', (0, 0, 1, 1), DIALOG) if self.up else None

    def click(self, x, y, root_hwnd=None):
        self.calls.append(('click', x, y, root_hwnd))
        if self.closes and root_hwnd == DIALOG:
            self.up = False


def test_memory_guard_is_answered_by_its_yes_button_only(monkeypatch, tmp_path):
    guard = Guard(monkeypatch, tmp_path)
    analysis = {}
    assert cases.answer_memory_guard(guard.session, tmp_path, analysis) is True
    record = analysis['memory_guard_dialogs'][0]
    assert record['texts'] == ['Available system memory is critically low during slicing.', 'Yes, Continue', 'No, Stop']
    assert record['button'] == [100, 200, 300, 240] and record['closed'] and record['screenshot'] == 'memory-guard-0.png'
    # The button centre and nothing else: no Enter, no default-button command, no real click.
    assert guard.calls == [('click', 200, 220, None), ('click', 200, 220, DIALOG)]
    assert analysis.get('guard_failures', 0) == 0
    assert cases.answer_memory_guard(guard.session, tmp_path, analysis) is False  # already gone


def test_memory_guard_stops_after_two_unanswered_dialogs(monkeypatch, tmp_path):
    guard = Guard(monkeypatch, tmp_path, closes=False)
    analysis = {}
    cases.answer_memory_guard(guard.session, tmp_path, analysis)
    assert analysis['guard_failures'] == 1 and 'error' not in analysis
    with pytest.raises(ValueError, match='could not be answered with "Yes, Continue"'):
        cases.answer_memory_guard(guard.session, tmp_path, analysis)
    assert len(analysis['memory_guard_dialogs']) == 2
    # All three tiers were tried on each dialog; the real one only after parking the cursor on the button.
    assert [tier['how'] for tier in analysis['memory_guard_dialogs'][0]['tiers']] == list(cases.GUARD_CLICK_TIERS)
    assert ('park', 200, 220) in guard.calls and ('real click', 200, 220) in guard.calls


def test_memory_guard_without_exactly_one_yes_button_is_not_clicked(monkeypatch, tmp_path):
    guard = Guard(monkeypatch, tmp_path)
    monkeypatch.setattr(cases.export_util, '_children_texts', lambda hwnd: [('', (0, 0, 1, 1), 10)])
    with pytest.raises(ValueError, match='expected one "Yes, Continue" button, found 0'):
        cases.answer_memory_guard(guard.session, tmp_path, {})
    assert guard.calls == []


def test_slice_wait_takes_the_enabled_export_row_as_the_completion_signal(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path)
    monkeypatch.setattr(m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    states = iter([(False, None), (False, None), (False, None), (True, None)])
    polls = []

    def inspect(session, item, expect_dialog=False, via=None, timeout_s=12.0, *, inspect_enabled=False):
        polls.append((item, via, inspect_enabled))
        return next(states)

    monkeypatch.setattr(m7, 'file_menu_dispatch', inspect)
    monkeypatch.setattr(cases, 'read_export_menu', lambda session: {'file': [], 'export': ROWS})
    monkeypatch.setattr(cases, 'topbar_labels', lambda session: ['panel', '', 'Slice plate', '', 'Print'])
    monkeypatch.setattr(cases, 'click_slice_start', lambda session: True)
    analysis = {}
    reading = cases.slice_until_exportable(rig.session, tmp_path, analysis, 'Export G-code', timeout_s=5)
    assert len(polls) == 4 and polls[0] == ('Export G-code', 'Export', True)
    assert reading['polls'] == 4 and reading['export_enabled_after_seconds'] >= 0
    assert reading['topbar_before'] == reading['topbar_after'] == ['panel', '', 'Slice plate', '', 'Print']
    assert 'clicked_at' not in analysis['slice']
    assert analysis['memory_guard_dialogs'] == []


def test_slice_wait_reports_the_menu_when_the_row_never_enables(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path)
    monkeypatch.setattr(m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    monkeypatch.setattr(m7, 'file_menu_dispatch', lambda *a, **k: (False, None))
    monkeypatch.setattr(cases, 'read_export_menu', lambda session: {'file': [], 'export': ROWS})
    monkeypatch.setattr(cases, 'topbar_labels', lambda session: [])
    monkeypatch.setattr(cases, 'click_slice_start', lambda session: True)
    analysis = {}
    monkeypatch.setattr(cases, 'topbar_labels', lambda session: [])
    monkeypatch.setattr(cases, 'click_slice_start', lambda session: True)
    ticks = iter(step * 0.5 for step in range(40))
    monkeypatch.setattr(cases.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(ValueError, match="stayed disabled"):
        cases.slice_until_exportable(rig.session, tmp_path, analysis, 'Export G-code', timeout_s=1)
    assert analysis['slice']['export_enabled_after_seconds'] is None
    assert analysis['slice']['export_menu_at_timeout'] == ROWS and 'clicked_at' not in analysis['slice']
    assert analysis['memory_guard_dialogs'] == [] and analysis['guard_failures'] == 0
