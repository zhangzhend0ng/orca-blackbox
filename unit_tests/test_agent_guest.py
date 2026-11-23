"""Worker lifecycle using fake UI/processes only; never starts a GUI or Job."""
import json
from types import SimpleNamespace

import pytest

from harness import agent_guest as worker, agent_project_ui
from harness.agent_protocol import PROJECT_CASE, read_json, write_json_once
from harness.run_contract import validate_contract
from harness.run_verdict import contract_digest


def message(seq, tool):
    return {"schema_version":1,"run_id":"run1","seq":seq,"method":tool,
        "arguments":{"x":100,"y":50,"text":"0.24"} if tool == "edit" else {},
        "observation_id":None if seq == 1 else f"run1_{seq-1:04d}"}


@pytest.mark.parametrize("flow", ["complete", "extra-observe", "duplicate-save", "deadline-reopen"])
def test_project_worker_preserves_ready_and_switches_receipt_frames_report_at_reopen(tmp_path, monkeypatch, flow):
    contract = validate_contract({"schema_version":1,"case_id":PROJECT_CASE,"contract_version":"ai-project-1",
        "executor":"agent_mcp","required_checks":["path","business"],
        "steps":[{"id":"persist","goal":"Save reopen and slice the GUI project"}],
        "limits":{"timeout_s":900,"max_actions":12,"max_retries":0,"max_cost_usd":0}})
    (tmp_path / "contract.json").write_text(json.dumps(contract.to_dict()),encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    now = [0.]
    ns = lambda:10**18+int(now[0]*10**9)
    monkeypatch.setattr(worker,"time",SimpleNamespace(monotonic=lambda:now[0],time_ns=ns,
        sleep=lambda seconds:now.__setitem__(0,now[0]+seconds)))
    monkeypatch.setattr(worker.host_guard,"in_guest",lambda:True)
    instances = []
    class UI:
        def __init__(self, path, guard):
            self.app = SimpleNamespace(pid=10,hwnd=11)
            self.guard,self.performed,self.closed = guard,[],False
            self.boot_details={"fixture_path":"input/fixture.3mf","fixture_sha256":"a"*64,
                               "datadir":"profile","driver_pid":worker.os.getpid()}
            instances.append(self)
        def identity(self):
            return {"pid":self.app.pid,"hwnd":self.app.hwnd,"width":313,"height":68,"dpi":96}, (
                313,68,bytes([self.app.pid,0,0,255])*(313*68))
        def perform(self, tool, arguments):
            self.performed.append(tool)
            if tool == "edit":
                return {"target_hwnd":12,"control_class":"Edit","before_text":"0.4","after_text":"0.24"}
            if tool == "save_project":
                return {"dialog_hwnd":13,"edit_hwnd":14,"path":"projects/0001.3mf","sha256":"b"*64,"size_bytes":123}
            if tool == "reopen_project":
                closed_ns = ns()
                now[0] += 901 if flow == "deadline-reopen" else 1
                self.app=SimpleNamespace(pid=30,hwnd=31)
                return {"path":"projects/0001.3mf","sha256":"b"*64,"size_bytes":123,"datadir":"profile_reopen",
                    "old_pid":10,"old_hwnd":11,"old_exit_code":0,"old_closed_at_ns":closed_ns,"new_pid":30,
                    "new_hwnd":31,"new_started_at_ns":ns(),"driver_pid":worker.os.getpid()}
            if tool == "slice":
                return {"button_hwnd":32,"done_observed":True}
            return {"dialog_hwnd":33,"edit_hwnd":34,"path":"exports/0001.gcode","sha256":"c"*64,"size_bytes":456}
        def close(self):
            self.closed=True
    monkeypatch.setattr(agent_project_ui,"ProjectUI",UI)
    sequence=["observe","edit","save_project","reopen_project","slice","export_gcode","finish"]
    if flow == "extra-observe":
        sequence.insert(3,"observe")
    if flow == "duplicate-save":
        sequence.insert(3,"save_project")
    original=worker.write_json_once
    def write(path,value):
        original(path,value)
        if path.name == "ready.json":
            for seq, tool in enumerate(sequence,1):
                original(artifacts / "mailbox" / f"request_{seq:04d}.json",message(seq,tool))
    monkeypatch.setattr(worker,"write_json_once",write)
    succeeded=flow in {"complete","extra-observe"}
    assert worker.run_guest(artifacts,"run1",contract_digest(contract)) == (0 if succeeded else 1)
    ready, report=read_json(artifacts/"ready.json"),read_json(artifacts/"agent_report.json")
    rows=[json.loads(line) for line in (artifacts/"trace.ndjson").read_text().splitlines()]
    receipts=[json.loads(line) for line in (artifacts/"operation_receipts.ndjson").read_text().splitlines()]
    assert (ready["app_pid"],ready["hwnd"]) == (10,11)
    assert instances[0].closed and report["status"] == ("completed" if succeeded else "failed")
    if succeeded:
        reopen_seq=sequence.index("reopen_project")+1
        assert (report["app_pid"],report["hwnd"]) == (30,31)
        for row in rows:
            expected=(10,11) if row["request"]["seq"] < reopen_seq else (30,31)
            window=row["response"]["observation"]["window"]
            assert (window["pid"],window["hwnd"]) == expected
            frames=row["response"]["observation"]["frames"]
            assert frames[1]["captured_at_ns"]-frames[0]["captured_at_ns"] >= 10**9
        changed=next(row for row in receipts if row["method"]=="reopen_project")
        assert changed["seq"]==reopen_seq and changed["window"]=={"pid":30,"hwnd":31}
        assert changed["details"]["old_pid"]==ready["app_pid"] and changed["details"]["new_pid"]==report["app_pid"]
    elif flow == "duplicate-save":
        assert rows[-1]["response"]["error_code"]=="operation_budget"
        assert instances[0].performed==["edit","save_project"]
        assert sum(row["method"]=="save_project" for row in receipts)==1
    else:
        assert rows[-1]["response"]["error_code"]=="worker_deadline"
        assert (report["app_pid"],report["hwnd"])==(30,31)
        assert not any(row["method"]=="reopen_project" for row in receipts)
        assert "slice" not in instances[0].performed


def test_reopen_profile_is_seeded_once_with_fresh_false_and_fixed_saved_input(tmp_path, monkeypatch):
    import harness
    seeded, launched = [],[]
    def seed(path, fresh, conf_extra=None):
        # the reopen session is seeded under the edit session's conf
        # (dd3d40d: #296's rows exist only in develop mode)
        seeded.append((path,fresh,conf_extra))
        path.mkdir()
    app=object()
    monkeypatch.setattr(harness,"profile",SimpleNamespace(seed_profile=seed),raising=False)
    monkeypatch.setattr(harness,"launcher",SimpleNamespace(launch=lambda **kwargs:launched.append(kwargs) or app),raising=False)
    monkeypatch.setattr(harness,"winutil",SimpleNamespace(),raising=False)
    saved=tmp_path/"projects/0001.3mf"
    result=worker._WindowsUI(tmp_path,model=saved,profile_name="profile_reopen")
    assert seeded==[(tmp_path/"profile_reopen",False,None)]
    assert launched==[{"datadir":tmp_path/"profile_reopen","model":saved,"dismiss_wizard":True}]
    assert result.app is app and result.shape is None
    with pytest.raises(FileExistsError):
        worker._WindowsUI(tmp_path,model=saved,profile_name="profile_reopen")
    assert len(launched)==1


def test_reopen_profile_gets_the_edit_sessions_conf(tmp_path, monkeypatch):
    import harness
    seeded = []
    def seed(path, fresh, conf_extra=None):
        seeded.append(conf_extra)
        path.mkdir()
    monkeypatch.setattr(harness,"profile",SimpleNamespace(seed_profile=seed),raising=False)
    monkeypatch.setattr(harness,"launcher",SimpleNamespace(launch=lambda **kwargs:object()),raising=False)
    monkeypatch.setattr(harness,"winutil",SimpleNamespace(),raising=False)
    develop={"app":{"user_mode":"develop"}}
    worker._WindowsUI(tmp_path,model=tmp_path/"projects/0001.3mf",profile_name="profile_reopen",conf_extra=develop)
    assert seeded==[develop]
