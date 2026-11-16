"""Fake Win32 boundaries only: these tests never launch an application."""
from types import SimpleNamespace

import pytest

from harness import agent_business_ui as module
from harness.agent_protocol import ProtocolError


def ui_shell():
    ui = module.BusinessUI.__new__(module.BusinessUI)
    ui.guard = lambda: None
    ui.app = SimpleNamespace(hwnd=11, pid=12)
    ui.identity = lambda: ({"width": 1920, "height": 1032}, None)
    return ui


def test_pause_handles_guard_advancing_clock_past_end(monkeypatch):
    ui = ui_shell()
    now, sleeps = [0], []
    def guard():
        now[0] += 2
    ui.guard = guard
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleeps.append))
    ui.pause(1)
    assert sleeps == [0]


@pytest.mark.parametrize("owned,kind,child,enabled", [
    (False, "Edit", True, True), (True, "ComboBox", True, True),
    (True, "Edit", False, True), (True, "Edit", True, False),
])
def test_edit_rejects_foreign_nonedit_unrelated_and_disabled_controls(owned, kind, child, enabled):
    ui, actions = ui_shell(), []
    ui.owned = lambda hwnd: owned
    ui.wu = SimpleNamespace(client_to_screen=lambda *args: (400, 700), deepest_child_at=lambda *args: 20,
        window_class=lambda hwnd: kind, user32=SimpleNamespace(IsChild=lambda *args: child,
        IsWindowEnabled=lambda hwnd: True if hwnd == 11 else enabled), msg_text=lambda *args: actions.append(args))
    with pytest.raises(ProtocolError, match="edit_target_not_owned_edit"):
        ui.edit(100, 200, "0.24")
    assert not actions


def test_edit_uses_model_client_coordinate_native_selection_and_own_value():
    ui, actions = ui_shell(), []
    ui.pause = lambda seconds: None
    ui.owned = lambda hwnd: hwnd == 20
    value = ["0.4"]
    def type_text(hwnd, text):
        actions.append(("text", hwnd, text))
        if text != "\r":
            value[0] = text
    ui.wu = SimpleNamespace(client_to_screen=lambda hwnd,x,y: (1000+x, 2000+y),
        deepest_child_at=lambda *args: 20, window_class=lambda hwnd: "Edit",
        user32=SimpleNamespace(IsChild=lambda *args: True, IsWindowEnabled=lambda hwnd: True),
        edit_text=lambda hwnd: value[0], msg_click_screen=lambda *args: actions.append(("click", *args)),
        _send_msg=lambda *args: actions.append(("message", *args)), msg_text=type_text)
    result = ui.edit(100, 200, "0.40")
    assert actions[0] == ("click", 1100, 2200, 11)
    assert ("message", 20, 0x00B1, 0, -1) in actions
    assert result == {"target_hwnd": 20, "control_class": "Edit", "before_text": "0.4", "after_text": "0.40"}


def test_cancel_before_edit_prevents_any_input():
    ui = ui_shell()
    ui.guard = lambda: (_ for _ in ()).throw(ProtocolError("host_cancelled"))
    with pytest.raises(ProtocolError, match="host_cancelled"):
        ui.perform("edit", {"x": 100, "y": 200, "text": "0.24"})


def test_modal_blocked_main_window_cannot_receive_hidden_edit_input():
    ui = ui_shell()
    ui.wu = SimpleNamespace(user32=SimpleNamespace(IsWindowEnabled=lambda hwnd: False))
    with pytest.raises(ProtocolError, match="main_window_modal_blocked"):
        ui.edit(100, 200, "0.24")


def test_slice_clicks_once_then_times_out_without_blind_replay():
    ui, clicks = ui_shell(), []
    ui.export_mode = lambda: None
    ui.owned = lambda hwnd: True
    ui.wu = SimpleNamespace(user32=SimpleNamespace(IsWindowEnabled=lambda hwnd: True))
    ui.eu = SimpleNamespace(find_slice_buttons=lambda hwnd: (None, ("Slice", (1,2,3,4), 30)))
    ui.click_rect = clicks.append
    ui.pause = lambda seconds: None
    def timeout(predicate, seconds):
        assert seconds == 180
        raise ProtocolError("gui_wait_timeout")
    ui.wait = timeout
    with pytest.raises(ProtocolError, match="gui_wait_timeout"):
        ui.slice()
    assert clicks == [(1,2,3,4)]


def test_existing_export_is_never_deleted_or_clicked(tmp_path):
    ui, clicks = ui_shell(), []
    ui.artifacts, ui.exports = tmp_path, 0
    output = tmp_path / "exports/0001.gcode"
    output.parent.mkdir()
    output.write_bytes(b"keep")
    ui.export_mode = lambda: ("Export G-code file", (1,2,3,4), 30)
    ui.owned = lambda hwnd: True
    ui.wu = SimpleNamespace(user32=SimpleNamespace(IsWindowEnabled=lambda hwnd: True))
    ui.click_rect = clicks.append
    with pytest.raises(ProtocolError, match="export_exists"):
        ui.export_gcode()
    assert output.read_bytes() == b"keep" and not clicks


def test_export_passes_screen_rectangle_once_and_writes_fixed_filename(tmp_path, monkeypatch):
    ui, clicks, typed, now = ui_shell(), [], [], [0]
    ui.artifacts, ui.exports = tmp_path, 0
    ui.export_mode = lambda: ("Export G-code file", (1001,2002,1101,2042), 30)
    ui.owned = lambda hwnd: True
    ui.click_rect = clicks.append
    ui.eu = SimpleNamespace(wait_save_dialog=lambda *args, **kwargs: ("#32770", "Save G-code file as:", (0,0,1,1), 40),
                            find_edit=lambda hwnd: 41)
    def message(hwnd, msg, wp, lp):
        if msg == 0x0111:
            (tmp_path / "exports/0001.gcode").write_bytes(b"; actual export\n")
    ui.wu = SimpleNamespace(user32=SimpleNamespace(IsWindowEnabled=lambda hwnd: True, IsChild=lambda *args: True),
        _send_msg=message, msg_text=lambda hwnd,text: typed.append((hwnd,text)))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + max(seconds, .001))))
    result = ui.export_gcode()
    assert clicks == [(1001,2002,1101,2042)]
    assert typed == [(41, str(tmp_path / "exports/0001.gcode"))]
    assert result["path"] == "exports/0001.gcode" and result["size_bytes"] == 16
    assert ui.exports == 1


@pytest.mark.parametrize("caption,message,button,accepted", [
    ("Snapmaker Orca", "Do you want to save changes to fixture?", "&No", True),
    ("Snapmaker Orca", "Delete printer?", "&No", False),
    ("Unexpected", "Do you want to save changes?", "No", False),
    ("Snapmaker Orca", "Do you want to save changes?", "Cancel", False),
    ("Unsaved Changes", "Modified settings", "Don't save", True),
    ("Unsaved Changes", "Modified settings", "Discard", True),
])
def test_close_no_is_limited_to_the_owned_app_save_question(caption, message, button, accepted):
    candidate = (button, (0, 0, 10, 10), 40)
    children = [(message, (0, 0, 10, 10), 39), candidate]
    assert (module._discard_choice(caption, children) == candidate) is accepted
