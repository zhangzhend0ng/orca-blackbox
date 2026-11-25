"""Wiring of the File > Export GUI helpers against fake windows (no application, no guest).

The helpers drive real Win32 objects on the guest; here every window call is
replaced by a recording fake so that the order of the actions, the refusal
paths and the receipt are pinned without a GUI."""
import ctypes
from itertools import count
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

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
        self.images = []
        monkeypatch.setattr(cases, 'capture_window', lambda hwnd, path: self.images.append(Path(path).name)
                            or {'width_px': 800, 'height_px': 600})
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


def test_a_case_that_exports_twice_keeps_each_dialog_image_and_receipt_apart(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, title='Save Sliced file as:')
    analysis = {}
    first = cases.export_via_file_menu(rig.session, 'Export plate sliced file', tmp_path, 'plate', tmp_path, analysis,
                                       'Save Sliced file as', 'gcode')
    rig.visible, rig.text = True, rig.default
    second = cases.export_via_file_menu(rig.session, 'Export plate sliced file', tmp_path, 'sphere', tmp_path, analysis,
                                        'Save Sliced file as', 'gcode',
                                        image='sphere-export-dialog.png', key='complex_export')
    assert analysis['export'] is first and analysis['complex_export'] is second and 'export' in analysis
    assert rig.images == ['export-dialog.png', 'sphere-export-dialog.png']
    assert first['typed_name'] == 'plate' and second['typed_name'] == 'sphere'
    assert sorted(path.name for path in tmp_path.iterdir()) == ['plate.gcode', 'sphere.gcode']


def test_each_slice_gets_its_own_reading_while_the_guard_records_stay_together(monkeypatch, tmp_path):
    rig = Guard(monkeypatch, tmp_path)
    monkeypatch.setattr(m7, 'file_menu_dispatch', lambda *a, **k: (True, None))
    monkeypatch.setattr(cases, 'read_export_menu', lambda session: {'file': [], 'export': ROWS})
    monkeypatch.setattr(cases, 'topbar_labels', lambda session: ['panel', '', 'Slice plate', '', 'Print'])
    monkeypatch.setattr(cases, 'click_slice_start', lambda session: True)
    analysis = {}
    for key in ('simple_slice', 'complex_slice'):
        cases.slice_until_exportable(rig.session, tmp_path, analysis, 'Export plate sliced file', key=key)
        rig.up = True
    assert 'slice' not in analysis and set(analysis) == {'simple_slice', 'complex_slice', 'memory_guard_dialogs',
                                                         'guard_failures'}
    assert [record['screenshot'] for record in analysis['memory_guard_dialogs']] == [
        'memory-guard-0.png', 'memory-guard-1.png']
    assert analysis['guard_failures'] == 0 and analysis['simple_slice']['polls'] == 1
    assert analysis['complex_slice']['export_menu_after'] == ROWS


def test_plate_slice_case_runs_two_sessions_and_judges_the_three_clauses(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / 'tests' / 'gui'))
    import m7x_234_export_plate_slice as case
    from PIL import Image
    sessions = []

    def boot(args, model=None):
        sessions.append(model.name)
        return SimpleNamespace(pid=SESSION_PID, alive=lambda: True, close=lambda: sessions.append('closed'))

    models = iter((case.CUBE, case.SPHERE))

    def snapshot(session, work, phase):
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / f'{phase}.png')
        target = work / f'{phase}.3mf'
        target.write_bytes(next(models).read_bytes())
        return target

    def sliced(session, work, analysis, item, timeout_s=150, key='slice'):
        analysis[key] = {'item': item, 'polls': 1}

    def export(session, item, directory, name, work, analysis, title, kind, image, key):
        assert item == 'Export plate sliced file' and title == 'Save Sliced file as' and kind == 'archive'
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / image)
        text = (gcode.gcode_text(5, box=gcode.CUBE_BOX) if name == 'plate'
                else gcode.gcode_text(60, box=gcode.SPHERE_BOX, name='球体'))
        path = gcode.write_sliced(Path(directory) / f'{name}.gcode.3mf', gcode=text.encode('utf-8'))
        analysis[key] = {'item': item, 'saved_name': path.name, 'saved_extension': '.gcode.3mf'}
        return analysis[key]

    monkeypatch.setattr(case, 'boot_session', boot)
    monkeypatch.setattr(case.m7, 'ensure_maximized', lambda session: True)
    monkeypatch.setattr(case, 'wait_arrival', lambda session, timeout_s, min_frac: (True, 0.01))
    monkeypatch.setattr(case, 'save_snapshot', snapshot)
    monkeypatch.setattr(case, 'slice_until_exportable', sliced)
    monkeypatch.setattr(case, 'capture', lambda session, path: Image.new('RGB', (4, 4), (9, 9, 9)).save(path))
    monkeypatch.setattr(case, 'export_via_file_menu', export)
    monkeypatch.setattr(case.m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    analysis = {'results': {}, 'timings': {}}
    args = SimpleNamespace(exe=None, model=case.CUBE)
    case.run(args, tmp_path, analysis)
    assert sessions == ['feishu_std_cube.3mf', 'closed', 'feishu_std_sphere.3mf', 'closed']
    assert analysis['results'] == dict.fromkeys(gcode.CLAUSES, 'PASS')
    assert analysis['size_comparison']['checks'] == {'complex_file_larger': True, 'complex_gcode_larger': True}
    assert analysis['simple']['presets'] == analysis['complex']['presets']  # the same printer and process preset
    assert [o['shape'] for o in analysis['simple']['plate_objects']] == ['cube']
    assert [o['shape'] for o in analysis['complex']['plate_objects']] == ['sphere']
    assert analysis['sliced_files']['simple']['gcode']['layer_count'] == 5
    assert analysis['sliced_files']['complex']['gcode']['layer_count'] == 60
    # Each archive's material is located on the plate it was sliced from.
    assert [analysis['sliced_files'][label]['footprint']['names_in_gcode'] for label in ('simple', 'complex')] == [
        ['立方体'], ['球体']]
    assert all(analysis['sliced_files'][label]['footprint']['checks'].values() for label in ('simple', 'complex'))
    assert analysis['sliced_files']['complex']['footprint']['moves']['brim'] == 0
    assert set(analysis['harvested_references']) == {label for label, _path, _kind in case.REFERENCES}
    assert set(analysis['timings']) == {'simple_open', 'simple_slice', 'simple_export', 'complex_open',
                                        'complex_slice', 'complex_export'}
    assert sorted(path.name for path in tmp_path.iterdir() if path.suffix in ('.png', '.3mf')) == [
        'before.3mf', 'before.png', 'export-dialog.png', 'plate.gcode.3mf', 'sliced.png', 'sphere-before.3mf',
        'sphere-before.png', 'sphere-export-dialog.png', 'sphere-sliced.png', 'sphere.gcode.3mf']


def test_plate_slice_case_still_judges_the_cube_when_the_sphere_session_fails(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / 'tests' / 'gui'))
    import m7x_234_export_plate_slice as case
    from PIL import Image
    closed = []

    def boot(args, model=None):
        return SimpleNamespace(pid=SESSION_PID, alive=lambda: True, close=lambda: closed.append(model.name))

    models = iter((case.CUBE, case.SPHERE))

    def snapshot(session, work, phase):
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / f'{phase}.png')
        target = work / f'{phase}.3mf'
        target.write_bytes(next(models).read_bytes())
        return target

    def sliced(session, work, analysis, item, timeout_s=150, key='slice'):
        analysis[key] = {'item': item}
        if key == 'complex_slice':
            raise ValueError('the Sphere click did not take')

    def export(session, item, directory, name, work, analysis, title, kind, image, key):
        path = gcode.write_sliced(Path(directory) / f'{name}.gcode.3mf',
                                  gcode=gcode.gcode_text(box=gcode.CUBE_BOX).encode('utf-8'))
        analysis[key] = {'saved_name': path.name, 'saved_extension': '.gcode.3mf'}
        return analysis[key]

    monkeypatch.setattr(case, 'boot_session', boot)
    monkeypatch.setattr(case.m7, 'ensure_maximized', lambda session: True)
    monkeypatch.setattr(case, 'wait_arrival', lambda session, timeout_s, min_frac: (True, 0.01))
    monkeypatch.setattr(case, 'save_snapshot', snapshot)
    monkeypatch.setattr(case, 'slice_until_exportable', sliced)
    monkeypatch.setattr(case, 'capture', lambda session, path: None)
    monkeypatch.setattr(case, 'export_via_file_menu', export)
    monkeypatch.setattr(case.m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    monkeypatch.setattr(case, 'harvested_readings', lambda entries: {})
    analysis = {'results': {}, 'timings': {}}
    case.run(SimpleNamespace(exe=None, model=case.CUBE), tmp_path, analysis)
    assert closed == ['feishu_std_cube.3mf', 'feishu_std_sphere.3mf']
    assert analysis['results']['生成 .gcode.3mf 文件'] == 'PASS'
    assert analysis['results']['内含 G-code 与预览信息'] == 'PASS'
    assert analysis['results']['文件大小随切片复杂度合理增大'].startswith(
        "FAIL (no readable plate G-code for ['complex']: the two files cannot be compared; "
        'complex plate: ValueError: the Sphere click did not take')
    assert analysis['complex']['error'] == 'ValueError: the Sphere click did not take'
    assert m7.m7_verdict(analysis['results']) == 1


def rig_case(monkeypatch, tmp_path, export):
    """The #234 case with every window call faked; `export` writes what the application would have saved."""
    sys.path.insert(0, str(ROOT / 'tests' / 'gui'))
    import m7x_234_export_plate_slice as case
    from PIL import Image
    models = iter((case.CUBE, case.SPHERE))

    def boot(args, model=None):
        return SimpleNamespace(pid=SESSION_PID, alive=lambda: True, close=lambda: None)

    def snapshot(session, work, phase):
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / f'{phase}.png')
        target = work / f'{phase}.3mf'
        target.write_bytes(next(models).read_bytes())
        return target

    monkeypatch.setattr(case, 'boot_session', boot)
    monkeypatch.setattr(case.m7, 'ensure_maximized', lambda session: True)
    monkeypatch.setattr(case, 'wait_arrival', lambda session, timeout_s, min_frac: (True, 0.01))
    monkeypatch.setattr(case, 'save_snapshot', snapshot)
    monkeypatch.setattr(case, 'slice_until_exportable', lambda session, work, analysis, item, timeout_s=150, key='slice':
                        analysis.__setitem__(key, {'item': item, 'polls': 1}))
    monkeypatch.setattr(case, 'capture', lambda session, path: None)
    monkeypatch.setattr(case, 'export_via_file_menu', export)
    monkeypatch.setattr(case.m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    monkeypatch.setattr(case, 'harvested_readings', lambda entries: {})
    analysis = {'results': {}, 'timings': {}}
    case.run(SimpleNamespace(exe=None, model=case.CUBE), tmp_path, analysis)
    return analysis


def test_plate_slice_case_fails_the_gcode_clause_when_the_sphere_gcode_misses_the_sphere(monkeypatch, tmp_path):
    def export(session, item, directory, name, work, analysis, title, kind, image, key):
        text = gcode.gcode_text(5, box=gcode.CUBE_BOX) if name == 'plate' else gcode.shifted(
            gcode.gcode_text(60, box=gcode.SPHERE_BOX, name='球体'), 3, 3)
        path = gcode.write_sliced(Path(directory) / f'{name}.gcode.3mf', gcode=text.encode('utf-8'))
        analysis[key] = {'saved_name': path.name, 'saved_extension': '.gcode.3mf'}
        return analysis[key]

    analysis = rig_case(monkeypatch, tmp_path, export)
    assert analysis['results'] == {
        '生成 .gcode.3mf 文件': 'PASS', '内含 G-code 与预览信息': "FAIL (complex: extrusion_on_objects ['model_on_objects'])",
        '文件大小随切片复杂度合理增大': 'PASS'}
    assert analysis['sliced_files']['complex']['footprint']['max_excursion_mm']['model'] == pytest.approx(2.79)
    assert m7.m7_verdict(analysis['results']) == 1


def gcode_case(monkeypatch, tmp_path, text):
    """The #236 case's steps with every window call faked; the export lands as `text`."""
    sys.path.insert(0, str(ROOT / 'tests' / 'gui'))
    import m7x_236_export_gcode as case
    from PIL import Image

    def snapshot(session, work, phase):
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / f'{phase}.png')
        target = work / f'{phase}.3mf'
        target.write_bytes(case.FIXTURE.read_bytes())
        return target

    def export(session, item, directory, name, work, analysis, title_substr, kind):
        assert (item, title_substr, kind) == ('Export G-code', 'Save G-code file as', 'gcode')
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / 'export-dialog.png')
        path = gcode.write_gcode(Path(directory) / 'plate.gcode', text)
        analysis['export'] = {'saved_name': path.name, 'saved_extension': '.gcode'}
        return analysis['export']

    monkeypatch.setattr(case, 'save_snapshot', snapshot)
    monkeypatch.setattr(case, 'read_export_menu', lambda session: {'file': [], 'export': gcode.EXPORT_ROWS})
    monkeypatch.setattr(case, 'slice_until_exportable', lambda session, work, analysis, item: {'item': item})
    monkeypatch.setattr(case, 'capture', lambda session, path: Image.new('RGB', (4, 4), (9, 9, 9)).save(path))
    monkeypatch.setattr(case, 'export_via_file_menu', export)
    monkeypatch.setattr(case.m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    analysis = {'results': {}, 'timings': {}}
    case.steps(SimpleNamespace(pid=SESSION_PID, alive=lambda: True), tmp_path, analysis,
               SimpleNamespace(model=case.FIXTURE))
    return analysis


def test_gcode_case_fails_the_first_clause_when_the_export_misses_the_cube(monkeypatch, tmp_path):
    (tmp_path / 'as-exported').mkdir()
    good = gcode_case(monkeypatch, tmp_path / 'as-exported', gcode.gcode_text(box=gcode.CUBE_BOX))
    assert good['results'] == dict.fromkeys(
        ('生成 .gcode 文件', '含起始/结束 G-code', '无空文件', '层命令连续'), 'PASS')
    assert all(good['footprint']['checks'].values()) and good['footprint']['names_in_gcode'] == ['立方体']
    (tmp_path / 'shifted').mkdir()
    moved = gcode_case(monkeypatch, tmp_path / 'shifted', gcode.shifted(gcode.gcode_text(box=gcode.CUBE_BOX), 3, 0))
    assert moved['results'] == {'生成 .gcode 文件': 'FAIL (extrusion_on_objects)', '含起始/结束 G-code': 'PASS',
                                '无空文件': 'PASS', '层命令连续': 'PASS'}
    assert moved['footprint']['max_excursion_mm']['model'] == pytest.approx(2.79)
    assert m7.m7_verdict(moved['results']) == 1


def all_plates_case(monkeypatch, tmp_path, landed):
    """The #235 case's steps with every window call faked; `landed(work, name)` writes what the
    application saved and returns the name of one landed file."""
    sys.path.insert(0, str(ROOT / 'tests' / 'gui'))
    import m7x_235_export_all_plates as case
    from PIL import Image
    started = []

    def snapshot(session, work, phase):
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / f'{phase}.png')
        return gcode.two_plate_project(work)

    def export(session, item, directory, name, work, analysis, title_substr, kind):
        assert (item, title_substr, kind) == ('Export all plate sliced file', 'Save Sliced file as', 'archive')
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / 'export-dialog.png')
        saved = landed(Path(directory), name)
        analysis['export'] = {'typed_name': name, 'saved_name': saved, 'saved_extension': '.gcode.3mf'}
        return analysis['export']

    def slice_all(session, work, analysis, item, timeout_s=150, key='slice', click=None):
        started.append((item, click))
        analysis['slice'] = {'item': item, 'polls': 3}
        return analysis['slice']

    monkeypatch.setattr(case, 'save_snapshot', snapshot)
    monkeypatch.setattr(case, 'read_export_menu', lambda session: {'file': [], 'export': gcode.EXPORT_ROWS})
    monkeypatch.setattr(case, 'slice_until_exportable', slice_all)
    monkeypatch.setattr(case, 'capture', lambda session, path: Image.new('RGB', (4, 4), (9, 9, 9)).save(path))
    monkeypatch.setattr(case, 'topbar_labels', lambda session: ['panel', '', 'Slice all', '', 'Print'])
    monkeypatch.setattr(case, 'export_via_file_menu', export)
    monkeypatch.setattr(case.m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    analysis = {'results': {}, 'timings': {}}
    case.steps(SimpleNamespace(pid=SESSION_PID, alive=lambda: True), tmp_path, analysis,
               SimpleNamespace(model=gcode.FIXTURES / 'feishu_std_cubesfar.3mf'))
    # Both plates are sliced in one go by the Slice all click, and the wait is for the row of every plate.
    assert [item for item, _click in started] == ['Export all plate sliced file']
    assert analysis['slice_all_clicks'] == []
    assert analysis['topbar_before_slice'][-1] == 'Print' and analysis['topbar_after_slice'][2] == 'Slice all'
    assert analysis['plates'] == {'names': ['Keep', 'Remove'], 'objects': {'Keep': ['Alpha'], 'Remove': ['Bravo']}}
    assert set(analysis['timings']) == {'open_plates', 'slice_all', 'export_all_plates', 'read_products'}
    # Only what the export left counts as a product, not the project files this case made itself.
    assert [product['name'] for product in analysis['products']] == sorted(
        path.name for path in tmp_path.iterdir() if path.name.endswith('.gcode.3mf'))
    return analysis


def plate_texts(second=None):
    return (gcode.gcode_text(box=gcode.ALPHA_BOX, name='Alpha'),
            second if second is not None else gcode.gcode_text(box=gcode.BRAVO_BOX, name='Bravo'))


def test_all_plates_case_reports_one_archive_for_two_plates_as_it_is(monkeypatch, tmp_path):
    alpha, bravo = plate_texts()

    def one_archive(work, name):
        return gcode.write_plates(work / f'{name}.gcode.3mf', {1: alpha, 2: bravo}).name

    analysis = all_plates_case(monkeypatch, tmp_path, one_archive)
    assert analysis['results'] == {
        '每个盘各生成对应切片文件': 'PASS',
        '共 2 个': 'FAIL (1 sliced file(s) landed for 2 plates (plates.gcode.3mf); they hold the G-code of 2 plate(s))',
        '均含有效 G-code': 'PASS'}
    assert m7.m7_verdict(analysis['results']) == 1
    assert [row['member'] for row in analysis['all_plates']['plates']] == [
        'Metadata/plate_1.gcode', 'Metadata/plate_2.gcode']


def test_all_plates_case_passes_when_each_plate_has_its_own_file(monkeypatch, tmp_path):
    alpha, bravo = plate_texts()

    def separate(work, name):
        gcode.write_plates(work / f'{name}-remove.gcode.3mf', {2: bravo})
        return gcode.write_plates(work / f'{name}-keep.gcode.3mf', {1: alpha}).name

    analysis = all_plates_case(monkeypatch, tmp_path, separate)
    assert analysis['results'] == dict.fromkeys(gcode.PLATE_CLAUSES, 'PASS')
    assert m7.m7_verdict(analysis['results']) == 0
    assert [row['file'] for row in analysis['all_plates']['plates']] == ['plates-keep.gcode.3mf', 'plates-remove.gcode.3mf']


def test_all_plates_case_fails_the_plate_whose_gcode_misses_its_object(monkeypatch, tmp_path):
    alpha, bravo = plate_texts(gcode.shifted(gcode.gcode_text(box=gcode.BRAVO_BOX, name='Bravo'), 3, 3))

    def one_archive(work, name):
        return gcode.write_plates(work / f'{name}.gcode.3mf', {1: alpha, 2: bravo}).name

    analysis = all_plates_case(monkeypatch, tmp_path, one_archive)
    assert analysis['results'] == {
        '每个盘各生成对应切片文件': "FAIL (plate 2 (Remove): its G-code does not land on this plate ['model_on_objects'])",
        '共 2 个': 'FAIL (1 sliced file(s) landed for 2 plates (plates.gcode.3mf); they hold the G-code of 2 plate(s))',
        '均含有效 G-code': 'PASS'}
    assert analysis['all_plates']['plates'][1]['footprint']['max_excursion_mm']['model'] == pytest.approx(2.79)


def slice_popup_rig(monkeypatch, *, rooted_takes=True, unrooted_takes=False, popup_survives=True,
                    row='Slice all', opens=True, enabled=True, label='Slice plate'):
    """A slice button whose dropdown opens a popup at (1660, 60)-(1769, 130) with two rows.

    A click on a row takes only as the flags say; a swallowed click leaves the popup open or
    closes it. What each click did is recorded in `state['clicks']`."""
    state = {'label': label, 'popup': None, 'clicks': [], 'enabled': enabled}
    popup_rows = [(row, (1660, 67, 1769, 95), 11), ('Slice plate', (1660, 95, 1769, 123), 12)]

    def find_slice_buttons(hwnd):
        return ('', (1600, 40, 1650, 60), 5), (state['label'], (1660, 40, 1800, 90), 6)

    def click(x, y, root_hwnd=None):
        state['clicks'].append((x, y, root_hwnd))
        if root_hwnd == 4242 and (1600, 40, 1650, 60)[0] <= x <= 1650:
            state['popup'] = 505 if opens else None
            return 505 if opens else None
        if root_hwnd == 4242 and (1660, 40, 1800, 90)[0] <= x <= 1800:
            return 6  # the slice button itself
        if root_hwnd == 505:
            takes = rooted_takes
        elif root_hwnd is None:
            takes = unrooted_takes
        else:
            return None
        if takes:
            state['label'] = 'Slice all'
            state['popup'] = None
            return 11
        if not popup_survives:
            state['popup'] = None
        return None if root_hwnd is None else 505

    ticking(monkeypatch)
    monkeypatch.setattr(cases.export_util, 'find_slice_buttons', find_slice_buttons)
    monkeypatch.setattr(cases.export_util, 'wait_popup',
                        lambda pid, timeout_s=5.0: ('wxWindowNR', 'panel', (1660, 60, 1769, 130), state['popup'])
                        if state['popup'] else None)
    monkeypatch.setattr(cases.export_util, '_children_texts', lambda hwnd: list(popup_rows))
    monkeypatch.setattr(cases.winutil, 'msg_click_screen', click)
    monkeypatch.setattr(cases.winutil.user32, 'IsWindow', lambda hwnd: hwnd == state['popup'])
    monkeypatch.setattr(cases.winutil.user32, 'IsWindowEnabled', lambda hwnd: state['enabled'])
    monkeypatch.setattr(cases.winutil, 'close_window', lambda hwnd: state.__setitem__('popup', None))
    return state


def test_slice_all_row_is_clicked_inside_the_popup_and_confirmed_by_the_buttons_label(monkeypatch):
    import m7x_235_export_all_plates as case
    state = slice_popup_rig(monkeypatch)
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is True
    row = (1660 + 1769) // 2, (67 + 95) // 2
    # Dropdown, the row with the popup as the root of the hit test, then the button once it reads Slice all.
    assert state['clicks'] == [(1625, 50, 4242), (*row, 505), (1730, 65, 4242)]
    assert record == [{'attempt': 0, 'click': 'inside the popup', 'row': [1660, 67, 1769, 95], 'hit': '0xb',
                       'label': 'Slice all'},
                      {'button': [1660, 40, 1800, 90], 'label': 'Slice all', 'hit': '0x6'}]
    assert callable(case.click_slice_all)


def test_slice_all_row_falls_back_to_the_un_rooted_click_and_to_a_reopened_dropdown(monkeypatch):
    import m7x_235_export_all_plates as case
    row = (1660 + 1769) // 2, (67 + 95) // 2
    # The click inside the popup is swallowed and the popup stays: the un-rooted click is tried next.
    state = slice_popup_rig(monkeypatch, rooted_takes=False, unrooted_takes=True)
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is True
    assert state['clicks'] == [(1625, 50, 4242), (*row, 505), (*row, None), (1730, 65, 4242)]
    assert [(entry.get('attempt'), entry.get('click'), entry.get('label')) for entry in record] == [
        (0, 'inside the popup', 'Slice plate'), (0, 'un-rooted', 'Slice all'),
        (None, None, 'Slice all')]
    # A swallowed click that also closes the popup: the dropdown is opened again, not clicked where it was.
    state = slice_popup_rig(monkeypatch, rooted_takes=False, unrooted_takes=False, popup_survives=False)
    state['label'] = 'Slice plate'
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is False
    assert state['clicks'] == [(1625, 50, 4242), (*row, 505)] * 2
    assert [entry.get('error', entry.get('click')) for entry in record] == ['inside the popup'] * 2
    assert all('Slice plate' == entry['label'] for entry in record)


def test_slice_all_is_refused_when_the_row_or_an_enabled_button_is_missing(monkeypatch):
    import m7x_235_export_all_plates as case
    state = slice_popup_rig(monkeypatch, row='Slice everything')
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is False
    assert state['popup'] is None and len(state['clicks']) == 2  # opened twice, no row pressed
    assert all(entry['error'] == 'the dropdown shows Slice all 0 times' for entry in record)
    state = slice_popup_rig(monkeypatch, opens=False)
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is False
    assert all(entry['error'] == 'the slice dropdown did not open' for entry in record)
    state = slice_popup_rig(monkeypatch, enabled=False)
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is False
    assert record[-1] == {'error': 'the slice button is not an enabled Slice all button', 'label': 'Slice all'}
    assert not any(root == 4242 and x == 1730 for x, y, root in state['clicks'])
    # Already in the Slice all mode: the button is pressed at once.
    state = slice_popup_rig(monkeypatch, label='Slice all')
    record = []
    assert case.click_slice_all(SimpleNamespace(pid=SESSION_PID, hwnd=4242), record) is True
    assert state['clicks'] == [(1730, 65, 4242)] and record[-1]['label'] == 'Slice all'


def test_slice_wait_can_be_started_by_another_click_and_keeps_its_default(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path)
    monkeypatch.setattr(m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    monkeypatch.setattr(m7, 'file_menu_dispatch', lambda *a, **k: (True, None))
    monkeypatch.setattr(cases, 'read_export_menu', lambda session: {'file': [], 'export': ROWS})
    monkeypatch.setattr(cases, 'topbar_labels', lambda session: [])
    pressed = []
    reading = cases.slice_until_exportable(
        rig.session, tmp_path, {}, 'Export all plate sliced file', click=lambda session: pressed.append('all') or True)
    assert reading['polls'] == 1 and pressed == ['all']
    monkeypatch.setattr(cases, 'click_slice_start', lambda session: pressed.append('plate') or True)
    cases.slice_until_exportable(rig.session, tmp_path, {}, 'Export G-code')
    assert pressed == ['all', 'plate']
    monkeypatch.setattr(cases, 'click_slice_start', lambda session: False)
    with pytest.raises(ValueError, match='the Slice click did not take'):
        cases.slice_until_exportable(rig.session, tmp_path, {}, 'Export G-code')




def ticking(monkeypatch):
    """A clock that advances half a second on every reading: waiting loops end at once."""
    clock = iter(count * 0.5 for count in range(4000))
    monkeypatch.setattr(cases.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(cases.time, 'sleep', lambda seconds: None)


def test_open_menus_are_closed_with_real_escape_only_while_orca_is_the_foreground(monkeypatch):
    menus, keys, foreground = [['menu'], ['menu', 'submenu']], [], {'pid': SESSION_PID}

    def escape(pressed):
        keys.append(pressed)
        if len(menus) > 1:
            menus.pop()  # the first Escape closes the submenu, the second the File menu
        else:
            menus.clear()

    monkeypatch.setattr(cases.topbar_util, '_enum_menu_windows', lambda pid: list(menus))
    monkeypatch.setattr(cases.topbar_util, 'close_menu_windows', lambda pid: None)
    monkeypatch.setattr(cases.winutil.user32, 'GetForegroundWindow', lambda: 11)
    monkeypatch.setattr(cases.winutil, '_window_pid', lambda hwnd: foreground['pid'])
    monkeypatch.setattr(cases.m7.mdu, '_send_keys', escape)
    ticking(monkeypatch)
    session = SimpleNamespace(pid=SESSION_PID, hwnd=4242)
    assert cases.dismiss_menus(session) is True and keys == [[(0x1B, False), (0x1B, True)]] * 2
    keys.clear()
    assert cases.dismiss_menus(session) is True and keys == []  # nothing was open
    menus.extend(['menu', 'submenu'])
    foreground['pid'] = SESSION_PID + 1  # another window has the keyboard: no key is sent
    assert cases.dismiss_menus(session) is False and keys == []


def menus_rig(monkeypatch, tmp_path, *, hover_opens=True, key_opens=True, wrong_submenu=False,
              row_rect_known=True, closes=True, foreground=True, screen_fails=False):
    """A File menu at (100, 100)-(300, 300) with two rows of even height; its Export row is the
    lower one, (100, 200)-(300, 298), and leads to HMENU 9002. When the submenu shows it is the
    window at (300, 180)-(560, 400). What opens it, and whether it is the right one, is set by
    the flags; every move of the cursor and every key is recorded in `calls`."""
    import m8x_48_modal_color_header as header
    calls, state = [], {'menus': [], 'closes': closes, 'foreground': foreground}
    menus = {9001: [(0, 'New Project\tCtrl+N', 0), (1, 'Export', 16)],
             9002: [(index, text, 3 if index in (3, 4, 5) else 0) for index, text in enumerate(ROWS)],
             9009: [(0, 'Import 3MF/STL/STEP/SVG/OBJ/AMF...\tCtrl+I', 0)]}  # the Import submenu
    windows = {501: (100, 100, 300, 300), 502: (300, 180, 560, 400), 509: (300, 120, 560, 160)}

    def show(which=502):
        if 502 not in state['menus'] and 509 not in state['menus']:
            state['menus'].append(which)

    def open_file(session):
        calls.append(('open',))
        state['menus'].append(501)
        return windows[501], 501, 9001

    def item_info(hmenu, index):
        return 4242, 9002

    def menu_hmenu(hwnd):
        return {501: 9001, 502: 9002, 509: 9009}.get(hwnd, 0)

    def row_rect(menu_hwnd, hmenu, index, rect):
        box = ctypes.cast(rect, ctypes.POINTER(cases.wintypes.RECT)).contents
        if menu_hwnd == 501 and index == 1 and row_rect_known:
            box.left, box.top, box.right, box.bottom = 100, 200, 300, 298
        elif menu_hwnd == 502:
            box.left, box.top, box.right, box.bottom = 300, 180 + 20 * index, 560, 200 + 20 * index
        else:
            return 0
        return 1

    def set_cursor(x, y):
        calls.append(('cursor', x, y))
        if hover_opens and foreground and state['menus'] == [501] and 200 <= y <= 298:
            show(509 if wrong_submenu else 502)

    def key(pressed):
        calls.append(('key', pressed[0][0]))
        if pressed[0][0] == 0x1B:  # Escape closes the submenu first, then the File menu
            if state['closes']:
                if len(state['menus']) > 1:
                    state['menus'].pop()
                else:
                    state['menus'].clear()
        elif key_opens and foreground and state['menus'] == [501]:
            show(509 if wrong_submenu else 502)

    def grab():
        if screen_fails:
            raise cases.winutil.CaptureError('BitBlt failed')
        return 640, 480, frame.tobytes()

    def cursor_pos(point):
        last = [call for call in calls if call[0] == 'cursor'][-1]
        contents = ctypes.cast(point, ctypes.POINTER(cases.wintypes.POINT)).contents
        contents.x, contents.y = last[1], last[2]
        return 1

    frame = np.zeros((480, 640, 4), np.uint8)
    frame[180:400, 300:560, :3] = (40, 40, 40)  # the dark submenu
    for index in range(7):  # one line of text per row: dim where the row is disabled
        frame[188 + 20 * index:196 + 20 * index, 316:470, :3] = (110, 110, 110) if index in (3, 4, 5) else (230, 230, 230)
    monkeypatch.setattr(header, 'bring_main_to_mouse', lambda hwnd: state['foreground'])
    monkeypatch.setattr(cases.topbar_util, 'open_file_menu', open_file)
    monkeypatch.setattr(cases.topbar_util, 'find_item', lambda hmenu, text: 1)
    monkeypatch.setattr(cases.topbar_util, 'item_info', item_info)
    monkeypatch.setattr(cases.topbar_util, 'menu_hmenu', menu_hmenu)
    monkeypatch.setattr(cases.topbar_util, 'menu_items', lambda hmenu: list(menus[hmenu]))
    monkeypatch.setattr(cases.topbar_util, '_enum_menu_windows',
                        lambda pid: [(*windows[handle], handle) for handle in state['menus']])
    monkeypatch.setattr(cases.topbar_util, 'close_menu_windows', lambda pid: None)
    monkeypatch.setattr(cases.winutil.user32, 'GetForegroundWindow', lambda: 11)
    monkeypatch.setattr(cases.winutil.user32, 'GetMenuItemRect', row_rect)
    monkeypatch.setattr(cases.winutil.user32, 'SetCursorPos', set_cursor)
    monkeypatch.setattr(cases.winutil.user32, 'GetCursorPos', cursor_pos)
    monkeypatch.setattr(cases.winutil, '_window_pid', lambda hwnd: SESSION_PID)
    monkeypatch.setattr(cases.m7.mdu, '_send_keys', key)
    monkeypatch.setattr(cases.winutil, 'screen_grab', grab)
    ticking(monkeypatch)
    return calls, state


def read_menu(monkeypatch, tmp_path, **flags):
    calls, state = menus_rig(monkeypatch, tmp_path, **flags)
    reading = cases.export_menu_reading(SimpleNamespace(pid=SESSION_PID, hwnd=4242), tmp_path, 'menu.png')
    return reading, calls, state


def test_export_rows_are_read_from_the_menus_whether_or_not_the_submenu_shows_on_screen(monkeypatch, tmp_path):
    reading, calls, state = read_menu(monkeypatch, tmp_path, hover_opens=False, key_opens=False)
    assert [row['label'] for row in reading['file']] == ['New Project\tCtrl+N', 'Export']
    assert [row['label'] for row in reading['export']] == ROWS
    assert [row['enabled'] for row in reading['export']] == [True, True, True, False, False, False, True]
    picture = reading['menu_picture']
    # No picture: the reason is written out with where the cursor went and which menus were open.
    assert picture['image'] is None and picture['unavailable'] == 'the Export submenu did not open on screen'
    assert picture['file_menu_px'] == [100, 100, 300, 300] and picture['foreground'] is True
    assert picture['tried'][0] == {'how': 'row rectangle', 'point': [200, 249]}
    assert picture['tried'][-1] == {'how': 'Right arrow key'}  # the key was sent and did not open it either
    assert len(picture['tried']) == 8  # the row's rectangle, six places around it, then the key
    assert picture['pointer'] == {'cursor': [200, 231], 'foreground_is_orca': True}  # the cursor stayed where it last went
    assert picture['menu_windows'] == [[100, 100, 300, 300]]
    assert not (tmp_path / 'menu.png').exists() and state['menus'] == []
    assert ('key', 0x27) in calls and ('key', 0x1B) in calls
    # Without the foreground nothing is sent: the rows are still read, and no picture is tried.
    reading, calls, state = read_menu(monkeypatch, tmp_path, foreground=False)
    assert [row['enabled'] for row in reading['export']] == [True, True, True, False, False, False, True]
    assert reading['menu_picture'] == {'image': None, 'file_menu_px': [100, 100, 300, 300], 'foreground': False,
                                      'unavailable': 'Orca could not come to the foreground; the submenu was not opened for a picture'}
    assert calls == [('open',), ('key', 0x1B)] and state['menus'] == []  # only the menu was closed
    # Another submenu (Import's) is never taken for Export, even when the key opens it.
    reading, calls, state = read_menu(monkeypatch, tmp_path, wrong_submenu=True)
    assert reading['menu_picture']['image'] is None and reading['menu_picture']['unavailable'] == (
        'the Export submenu did not open on screen')
    assert all('opened' not in entry for entry in reading['menu_picture']['tried'])


def test_export_menu_picture_is_kept_when_the_submenu_shows(monkeypatch, tmp_path):
    import cv2
    reading, calls, state = read_menu(monkeypatch, tmp_path)
    picture = reading['menu_picture']
    assert picture['image'] == 'menu.png' and picture['screen_px'] == [640, 480]
    assert picture['menus_px'] == {'file': [100, 100, 300, 300], 'export': [300, 180, 560, 400]}
    assert picture['opened_by'] == [{'how': 'row rectangle', 'point': [200, 249], 'opened': True}]
    assert ('cursor', 200, 245) in calls and calls[-2:] == [('key', 0x1B), ('key', 0x1B)]
    assert state['menus'] == []
    # The picture is the desktop around both menus with a margin: 88..572 across, 88..412 down.
    kept = cv2.imread(str(tmp_path / 'menu.png'))
    assert kept.shape[:2] == (324, 484)
    assert kept[100:108, 228:382].min() == 230  # text of the first row
    assert kept[160:168, 228:382].max() == 110  # dim text of the first disabled row
    # What the picture shows agrees with what the menu reports.
    assert [row['enabled'] for row in reading['export']] == [True, True, True, False, False, False, True]
    assert [row['text_luminance'] for row in reading['export']] == [230, 230, 230, 110, 110, 110, 230]
    # Without the row's rectangle the cursor is parked where an even row pitch puts the row.
    reading, calls, state = read_menu(monkeypatch, tmp_path, row_rect_known=False)
    assert reading['menu_picture']['opened_by'] == [{'how': 'even pitch', 'point': [200, 249], 'opened': True}]
    # Only the key opens it: the pointer is tried first, each time on the row.
    reading, calls, state = read_menu(monkeypatch, tmp_path, hover_opens=False, key_opens=True)
    assert [entry['how'] for entry in reading['menu_picture']['opened_by']][0] == 'row rectangle'
    assert reading['menu_picture']['opened_by'][-1] == {'how': 'Right arrow key', 'opened': True}
    assert ('key', 0x27) in calls and reading['menu_picture']['image'] == 'menu.png'
    # A desktop picture that cannot be taken is reported with the rows intact.
    reading, calls, state = read_menu(monkeypatch, tmp_path, screen_fails=True)
    assert reading['menu_picture']['image'] is None
    assert reading['menu_picture']['unavailable'] == 'the desktop picture failed (BitBlt failed)'
    assert [row['enabled'] for row in reading['export']] == [True, True, True, False, False, False, True]


def test_only_a_menu_that_refuses_to_close_fails_the_reading(monkeypatch, tmp_path):
    calls, state = menus_rig(monkeypatch, tmp_path, closes=False)
    with pytest.raises(ValueError, match=r'the File menu stayed open: \[\[100, 100, 300, 300\], \[300, 180, 560, 400\]\]'):
        cases.export_menu_reading(SimpleNamespace(pid=SESSION_PID, hwnd=4242), tmp_path, 'menu.png')
    assert calls.count(('key', 0x1B)) == 3


def export_rows(disabled):
    return [{'index': index, 'label': text,
             'enabled': gcode.EXPORT_ROWS[index].partition('\t')[0].rstrip('. ') not in disabled}
            for index, text in enumerate(gcode.EXPORT_ROWS)]


def disabled_case(monkeypatch, tmp_path, before, after):
    """The #238 case's steps with every window call faked; the menu reads `before`, then `after`."""
    sys.path.insert(0, str(ROOT / 'tests' / 'gui'))
    import m7x_238_export_disabled as case
    from PIL import Image
    shown = []

    def snapshot(session, work, phase):
        Image.new('RGB', (4, 4), (9, 9, 9)).save(work / f'{phase}.png')
        target = work / f'{phase}.3mf'
        target.write_bytes(case.FIXTURE.read_bytes())
        return target

    def read(session, work, image):
        shown.append(image)
        # The rows are read; the picture is the one thing that did not work on the guest.
        return {'export': before if len(shown) == 1 else after, 'file': [],
                'menu_picture': {'image': None, 'unavailable': 'the Export submenu did not open on screen'}}

    monkeypatch.setattr(case, 'save_snapshot', snapshot)
    monkeypatch.setattr(case, 'export_menu_reading', read)
    monkeypatch.setattr(case, 'slice_until_exportable',
                        lambda session, work, analysis, item: analysis.__setitem__('slice', {'item': item}))
    monkeypatch.setattr(case, 'capture', lambda session, path: Image.new('RGB', (4, 4), (9, 9, 9)).save(path))
    monkeypatch.setattr(case.m7, 'wait_dialog', lambda pid, timeout_s=15.0, title_substr='': None)
    analysis = {'results': {}, 'timings': {}}
    case.steps(SimpleNamespace(pid=SESSION_PID, alive=lambda: True), tmp_path, analysis,
               SimpleNamespace(model=case.FIXTURE))
    assert shown == ['menu-before.png', 'menu-after.png']
    assert analysis['before_is_sliced'] is False and analysis['plate_objects'] == ['立方体']
    assert analysis['slice']['item'] == 'Export G-code'
    assert set(analysis['timings']) == {'open_unsliced_plate', 'observe_before_slice', 'slice', 'observe_after_slice'}
    # The verdict came from the rows; with no picture on disk there is nothing else to show.
    assert sorted(path.name for path in tmp_path.iterdir()) == ['before.3mf', 'before.png', 'sliced.png']
    return analysis


SLICE_ROWS = ('Export plate sliced file', 'Export all plate sliced file', 'Export G-code')


def test_disabled_rows_case_passes_when_the_slice_rows_wake_up_after_slicing(monkeypatch, tmp_path):
    analysis = disabled_case(monkeypatch, tmp_path, export_rows(SLICE_ROWS), export_rows(()))
    assert analysis['results'] == dict.fromkeys(gcode.ROW_CLAUSES, 'PASS')
    assert m7.m7_verdict(analysis['results']) == 0


def test_disabled_rows_case_fails_the_clause_that_does_not_hold(monkeypatch, tmp_path):
    analysis = disabled_case(monkeypatch, tmp_path, export_rows(SLICE_ROWS[:2]), export_rows(('Export G-code',)))
    assert analysis['results'] == {
        '切片导出类条目置灰': "FAIL (before slicing: 'Export G-code' is enabled)",
        '切片完成后恢复可用': "FAIL (after slicing: 'Export G-code' is disabled)"}
    assert m7.m7_verdict(analysis['results']) == 1
