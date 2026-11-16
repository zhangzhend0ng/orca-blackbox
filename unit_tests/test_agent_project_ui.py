"""Project lifecycle with fake windows/launches only; no GUI subprocesses."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import agent_guest, agent_project_ui as module
from harness.agent_protocol import ProtocolError


@pytest.fixture
def ui(tmp_path, monkeypatch):
    value = module.ProjectUI.__new__(module.ProjectUI)
    value.artifacts, value.saved, value.reopened, value.exports = tmp_path, None, False, 7
    value.guard = lambda: None
    value.main_input = lambda: None
    value.app = SimpleNamespace(pid=10, hwnd=11, popen=SimpleNamespace(poll=lambda: 0))
    value.base = SimpleNamespace(app=value.app)
    value.pause = lambda seconds: None
    value.named_child = lambda name: (name, (1,2,3,4), 99)
    value.click_rect = lambda rect: None
    value.close = lambda: None
    value.wu = SimpleNamespace(user32=SimpleNamespace(ShowWindow=lambda *args: None))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 100., time_ns=lambda: 10**18))
    return value


def project(ui):
    path = ui.artifacts / module.PROJECT_PATH
    path.parent.mkdir()
    path.write_bytes(b"PK\x03\x04saved-project")
    ui.saved = ui._snapshot()
    return path


def new_base(ui, monkeypatch, *, callback=None):
    calls = []
    def launch(artifacts, model, profile_name):
        assert profile_name == "profile_reopen" and not (artifacts / profile_name).exists()
        calls.append((artifacts, model, profile_name))
        if callback:
            callback()
        app = SimpleNamespace(pid=30, hwnd=31, popen=SimpleNamespace(poll=lambda: None))
        return SimpleNamespace(app=app, winutil=ui.wu,
            identity=lambda: ({"pid":30,"hwnd":31,"width":1920,"height":1032,"dpi":96}, None))
    monkeypatch.setattr(agent_guest, "_WindowsUI", launch)
    return calls


def test_reopen_reuses_worker_guard_and_counters_but_uses_fresh_profile_and_new_identity(ui, monkeypatch):
    path = project(ui)
    events = []
    ui.close = lambda: events.append("old_closed")
    ui.guard = lambda: events.append("guard")
    ui._close_requested = True
    calls = new_base(ui, monkeypatch, callback=lambda: events.append("new_launch"))
    result = ui.reopen_project()
    assert calls == [(ui.artifacts, path, "profile_reopen")]
    assert events.index("old_closed") < events.index("new_launch")
    assert result == {**ui.saved,"datadir":"profile_reopen","old_pid":10,"old_hwnd":11,
        "old_exit_code":0,"old_closed_at_ns":10**18,"new_pid":30,"new_hwnd":31,
        "new_started_at_ns":10**18,"driver_pid":module.os.getpid()}
    assert ui.app.pid == 30 and ui.base.app is ui.app and ui.reopened
    assert ui.exports == 7 and ui._close_requested is False


@pytest.mark.parametrize("exit_code", [None, 1, -9, False])
def test_reopen_requires_real_zero_exit_before_launch(ui, monkeypatch, exit_code):
    project(ui)
    ui.app.popen.poll = lambda: exit_code
    calls = new_base(ui, monkeypatch)
    with pytest.raises(ProtocolError, match="not_naturally_closed"):
        ui.reopen_project()
    assert not calls


def test_cancel_after_old_close_prevents_new_launch(ui, monkeypatch):
    project(ui)
    closed = []
    ui.close = lambda: closed.append(True)
    def guard():
        if closed:
            raise ProtocolError("host_cancelled")
    ui.guard = guard
    calls = new_base(ui, monkeypatch)
    with pytest.raises(ProtocolError, match="host_cancelled"):
        ui.reopen_project()
    assert closed and not calls


def test_preexisting_reopen_profile_is_never_reseeded_or_followed(ui, monkeypatch):
    project(ui)
    (ui.artifacts / "profile_reopen").mkdir()
    ui.close = lambda: pytest.fail("known invalid profile must fail before closing")
    calls = new_base(ui, monkeypatch)
    with pytest.raises(ProtocolError, match="profile_exists"):
        ui.reopen_project()
    assert not calls


@pytest.mark.parametrize("stage", ["before_close", "during_close"])
def test_saved_project_tampering_does_not_reopen_a_different_snapshot(ui, monkeypatch, stage):
    path = project(ui)
    if stage == "before_close":
        path.write_bytes(b"PK\x03\x04modified")
    else:
        ui.close = lambda: path.write_bytes(b"PK\x03\x04modified")
    calls = new_base(ui, monkeypatch)
    with pytest.raises(ProtocolError, match="saved_project_changed"):
        ui.reopen_project()
    assert not calls


def test_new_app_is_owned_by_cleanup_even_if_reopen_setup_fails(ui, monkeypatch):
    project(ui)
    new_base(ui, monkeypatch)
    ui.pause = lambda seconds: (_ for _ in ()).throw(ProtocolError("host_cancelled"))
    with pytest.raises(ProtocolError, match="host_cancelled"):
        ui.reopen_project()
    assert ui.app.pid == 30 and ui.base.app is ui.app


def test_save_never_overwrites_an_existing_project(ui):
    path = project(ui)
    original = path.read_bytes()
    ui.saved = None
    ui._save_command = lambda: pytest.fail("no save GUI input on collision")
    with pytest.raises(ProtocolError, match="project_exists"):
        ui.save_project()
    assert path.read_bytes() == original


@pytest.mark.parametrize("kind,error", [("oversize","project_file_size"),("nonzip","project_not_3mf")])
def test_project_snapshot_rejects_invalid_or_unverifiable_size(ui, kind, error):
    path = project(ui)
    if kind == "oversize":
        with path.open("r+b") as stream:
            stream.truncate(module.MAX_PROJECT_BYTES + 1)
    else:
        path.write_bytes(b"not a 3mf archive")
    with pytest.raises(ProtocolError, match=error):
        ui._snapshot()


def test_save_uses_owned_dialog_fixed_path_and_records_snapshot(ui, monkeypatch):
    clock, closed, writes = [0.], [False], []
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda:clock[0]))
    def wait(predicate, seconds):
        for _ in range(30):
            value = predicate()
            if value:
                return value
            clock[0] += .2
        raise ProtocolError("gui_wait_timeout")
    ui.wait = wait
    ui._save_command = lambda: writes.append("menu")
    ui.owned_dialog = lambda hwnd: hwnd == 20
    ui.owned = lambda hwnd: hwnd == 21
    ui.eu = SimpleNamespace(wait_save_dialog=lambda *args,**kwargs:("#32770","Save file as:",(0,0,1,1),20),
                            find_edit=lambda hwnd:21)
    def message(hwnd, msg, wp, lp):
        writes.append((hwnd,msg,wp,lp))
        if hwnd == 20 and msg == 0x0111:
            (ui.artifacts / module.PROJECT_PATH).write_bytes(b"PK\x03\x04saved-project")
            closed[0] = True
    ui.wu = SimpleNamespace(_send_msg=message, msg_text=lambda hwnd,text:writes.append(("text",hwnd,text)),
        window_class=lambda hwnd:"Edit", user32=SimpleNamespace(IsChild=lambda parent,child:parent==20 and child==21,
        IsWindow=lambda hwnd:not closed[0]))
    result = ui.save_project()
    assert ("text",21,str(ui.artifacts / module.PROJECT_PATH)) in writes
    assert result == {"dialog_hwnd":20,"edit_hwnd":21,**ui.saved}
    assert result["path"] == "projects/0001.3mf" and result["size_bytes"] == 17
    with pytest.raises(ProtocolError, match="already_saved"):
        ui.save_project()


@pytest.mark.parametrize("method", ["save_project", "reopen_project"])
def test_project_tools_do_not_accept_any_model_paths(ui, method):
    with pytest.raises(ProtocolError, match="no_arguments"):
        ui.perform(method, {"path":"../outside"})


def test_file_menu_is_clicked_once_and_menu_command_is_bounded(ui):
    clicks, messages = [], []
    ui.app = SimpleNamespace(hwnd=11,pid=10)
    ui.owned = lambda hwnd: hwnd in {50,60}
    ui.wait = lambda predicate, seconds: predicate()
    ui.tb = SimpleNamespace(_topbar=lambda hwnd:("",(100,200,1100,230),50),
        _enum_menu_windows=lambda pid:[(0,0,100,100,60)], menu_hmenu=lambda hwnd:70,
        menu_items=lambda handle:[(2,"Save Project as...\tCtrl+Shift+S",0)], item_info=lambda handle,index:(987,0))
    ui.wu = SimpleNamespace(user32=SimpleNamespace(SetCursorPos=lambda *args:None),
        msg_click_screen=lambda *args:clicks.append(args), _send_msg=lambda *args:messages.append(args))
    ui._save_command()
    assert clicks == [(120,215,11)]
    assert messages == [(11,0x0111,987,0),(60,0x001F,0,0)]


def test_rejected_dialog_records_first_sut_identity_without_relaxing_gate(ui):
    import json
    ui._save_command=lambda:None
    ui.wait=lambda predicate,seconds:predicate()
    ui.eu=SimpleNamespace(wait_save_dialog=lambda *a,**k:("#32770","Unexpected save title",(0,0,1,1),20))
    ui.owned_dialog=lambda hwnd:True
    def owner(hwnd,command):
        assert command==4
        return 11
    ui.wu=SimpleNamespace(_window_pid=lambda hwnd:10,window_title=lambda hwnd:"Current title",
        window_class=lambda hwnd:"#32770",user32=SimpleNamespace(GetWindow=owner,
        GetParent=lambda hwnd:11,GetAncestor=lambda hwnd,kind:11))
    with pytest.raises(ProtocolError,match="project_save_dialog_identity"):ui.save_project()
    path=ui.artifacts/"project_save_dialog.json";first=path.read_bytes();data=json.loads(first)
    assert data["owned_dialog"] is True and data["diagnostic_only"] is True and data["oracle_evidence"] is False
    assert data["candidate"]=={"hwnd":20,"pid":10,"caption":"Current title","wait_caption":"Unexpected save title",
                               "window_class":"#32770","owner_hwnd":11,"parent_hwnd":11,"root_owner_hwnd":11}
    ui.wu.window_title=lambda hwnd:"Later title"
    with pytest.raises(ProtocolError,match="project_save_dialog_identity"):ui.save_project()
    assert path.read_bytes()==first
