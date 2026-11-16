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
    ("Snapmaker Orca 2.3.6", "Do you want to save changes to fixture?", "&No", True),
    ("Snapmaker Orca - Delete all", "Do you want to save changes?", "No", False),
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


@pytest.mark.parametrize("caption,close_requested,extra,omit,accepted", [
    ("Snapmaker Orca - Save", True, "Remember my choice.", None, True),
    ("Snapmaker Orca - Save", True, "", None, True),
    ("Snapmaker Orca - Save", False, "", None, False),
    ("Snapmaker Orca - Delete all", True, "", None, False),
    ("Snapmaker Orca - Save", True, "Delete all printers?", None, False),
    ("Snapmaker Orca - Save", True, "", "htmlWindow", False),
    ("Snapmaker Orca - Save", True, "", "Cancel", False),
    ("Snapmaker Orca - Save", True, "No", None, False),
])
def test_html_save_matches_observed_close_dialog_only(caption, close_requested, extra, omit, accepted):
    labels = ["", "Yes", "No", "Cancel", "htmlWindow", "", extra]
    children = [(label, (0,0,1,1), 100+i) for i, label in enumerate(labels) if label != omit]
    selected = module._discard_choice(caption, children, close_requested=close_requested)
    assert (selected is not None and selected[0] == "No") is accepted


@pytest.mark.parametrize("owner,caption,message,accepted", [
    (11, "Snapmaker Orca 2.3.6", "Do you want to save changes?", True),
    (99, "Snapmaker Orca 2.3.6", "Do you want to save changes?", False),
    (11, "Snapmaker Orca 2.3.6", "Delete all printers?", False),
    (11, "Snapmaker Orca - Save", "htmlWindow", True),
    (99, "Snapmaker Orca - Save", "htmlWindow", False),
])
def test_close_checks_dialog_owner_and_retains_first_bounded_diagnostic(tmp_path, monkeypatch, owner, caption, message, accepted):
    import json
    ui, alive, clicks, now = ui_shell(), [True], [], [0]
    ui.artifacts, ui.base = tmp_path, object()
    ui.app.alive = lambda: alive[0]
    ui.owned = lambda hwnd: hwnd in {11, 20, 21}
    def click(*args):
        clicks.append(args)
        alive[0] = False
    commands = []
    def get_window(hwnd, command):
        commands.append(command)
        if command == 2:
            return 11  # Z-order trap: the next window may coincidentally be MainFrame.
        assert command == 4
        return owner if hwnd == 20 else 0
    ui.wu = SimpleNamespace(_window_pid=lambda hwnd: 12 if hwnd in {11,20,21} else 88,
        close_window=lambda hwnd: None, enum_windows=lambda: [(20, 12), (30, 88)],
        window_title=lambda hwnd: caption, window_class=lambda hwnd: "#32770",
        msg_click_screen=click, user32=SimpleNamespace(GetWindow=get_window,
        GetParent=lambda hwnd: owner if hwnd == 20 else 0, GetAncestor=lambda hwnd,flag: 11,
        IsChild=lambda root,child: False, IsWindowVisible=lambda hwnd: True, IsWindowEnabled=lambda hwnd: True))
    children = ([("", (0,0,1,1), 22), ("Yes", (0,0,1,1), 23), ("No", (2,2,4,4), 21),
        ("Cancel", (0,0,1,1), 24), ("htmlWindow", (0,0,1,1), 25),
        ("", (0,0,1,1), 26), ("Remember my choice.", (0,0,1,1), 27)] if message == "htmlWindow" else [
        (message, (0,0,1,1), 22), ("No", (2,2,4,4), 21)] + [("X" * 1000, (0,0,1,1), 23)] * 40)
    ui.eu = SimpleNamespace(_children_texts=lambda hwnd: children)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0],
        time_ns=lambda: 10**18 + int(now[0] * 10**9), sleep=lambda seconds: now.__setitem__(0, now[0]+seconds)))
    if accepted:
        ui.close()
        assert clicks == [(3, 3, 20)] and not alive[0]
        assert not (tmp_path / "close_windows.json").exists()
        assert commands and set(commands) == {4}
        return
    with pytest.raises(ProtocolError, match="graceful_close_unconfirmed"):
        ui.close()
    assert not clicks
    path = tmp_path / "close_windows.json"
    first = path.read_bytes()
    diagnostic = json.loads(first)
    assert diagnostic["diagnostic_only"] is True and diagnostic["oracle_evidence"] is False
    assert len(diagnostic["windows"]) == 1 and diagnostic["windows"][0]["owner_hwnd"] == owner
    assert len(diagnostic["windows"][0]["children"]) == min(32, len(children))
    assert max(len(row["text"]) for row in diagnostic["windows"][0]["children"]) <= 160
    with pytest.raises(ProtocolError, match="graceful_close_unconfirmed"):
        ui.close()
    assert path.read_bytes() == first
    assert commands and set(commands) == {4}


@pytest.mark.parametrize("owner_pid,is_descendant,owner_parent,accepted", [
    (12, True, 0, True),  # Plater child owns its close confirmation.
    (12, False, 0, False),  # Same PID and shared hidden root-owner are insufficient.
    (88, True, 0, False),  # A foreign-PID edge is never traversed.
    (12, False, 11, True),  # Existing GW_OWNER chain to MainFrame remains accepted.
    (12, False, 30, False),  # Cyclic owner links fail closed.
])
def test_close_owner_accepts_main_descendant_but_rejects_unrelated_or_foreign_windows(owner_pid, is_descendant, owner_parent, accepted):
    ui = ui_shell()
    ui.owned = lambda hwnd: hwnd == 20
    commands = []
    def get_window(hwnd, command):
        commands.append(command)
        if command == 2:
            return 31  # Same-PID unrelated next window: never a valid owner edge.
        assert command == 4
        return 30 if hwnd == 20 else owner_parent
    ui.wu = SimpleNamespace(window_class=lambda hwnd: "#32770",
        _window_pid=lambda hwnd: owner_pid,
        user32=SimpleNamespace(GetWindow=get_window,
                              IsChild=lambda root,hwnd: root == 11 and hwnd == 30 and is_descendant))
    assert ui.owned_dialog(20) is accepted
    assert module.GW_OWNER == 4 and commands and set(commands) == {4}
