"""Batch orchestration/extraction with fake phases and owned processes, no relay/VM."""
import io
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import zipfile

import pytest

from tools import v3_project_batch as batch


def archive(entries):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w") as stream:
        for name,data in entries: stream.writestr(name,data)
    return out.getvalue()


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    monkeypatch.setattr(batch,"REPO",tmp_path)
    root=tmp_path/"artifacts/v3_batches/test01";root.mkdir(parents=True)
    cli=tmp_path/"codex.exe";cli.write_bytes(b"fixed cli")
    phase=tmp_path/"runner/v3_project_batch_phase.ps1";phase.parent.mkdir();phase.write_bytes(b"fixed phase")
    (root/"update.bundle").write_bytes(b"bundle")
    plan={"schema_version":1,"batch_id":"test01","case_id":batch.CASE,"head":"a"*40,
        "guest_base_ref":"b"*40,"guest_root":batch.GUEST,"sut_path":batch.SUT,"sut_sha256":batch.SUT_SHA,
        "cli_path":str(cli),"cli_sha256":batch.sha(cli),"fixture_sha256":"c"*64,"contract_sha256":"d"*64,
        "bundle_sha256":batch.sha(root/"update.bundle"),"phase_sha256":batch.sha(phase),
        "slots":[{"index":i,"run_id":f"{i:032x}","fault":fault,
                  "source":"codex_cli" if fault is None else "fault_probe_project_"+fault}
                 for i,fault in enumerate(batch.FAULTS,1)]}
    batch.once(root/"plan.json",plan)
    monkeypatch.setattr(batch,"git",lambda *args:"a"*40 if args[0]=="rev-parse" else "")
    return root,plan


def accepted(plan,slot):
    return {"audit_ok":True,"cleanup_confirmed":True,"run_id":slot["run_id"],
        "contract_sha256":plan["contract_sha256"],"status":"SHADOW" if slot["fault"] is None else "EXPECTED_NON_GREEN",
        "ai_trial":slot["fault"] is None,"fault_source":None if slot["fault"] is None else slot["source"],
        "model_lineage":{"cli_executable_sha256":plan["cli_sha256"]}}


def wire_fakes(monkeypatch,root,plan,*,fail_slot=None,quiet=True,expired=False):
    from tools import v3_project_audit
    calls=[]
    def phase(_root,_plan,slot,name):
        calls.append((slot["index"],name))
        if name=="harvest":
            raw=archive([("manifest.json",b"{}"),("artifacts/process.json",b"{}")])
            target=root/f"{slot['index']}_evidence.zip";target.write_bytes(raw)
            return {"zip_sha256":batch.sha(target)}
        return {}
    monkeypatch.setattr(batch,"phase",phase)
    count=[0]
    def control(argv,log):
        count[0]+=1
        assert "--run-id" in argv and "--guest-root" in argv
        if count[0]==fail_slot:
            error=RuntimeError("controlled_failure");error.host_tree_quiescent=quiet;raise error
        return 0,expired
    monkeypatch.setattr(batch,"controller",control)
    monkeypatch.setattr(v3_project_audit,"audit_project",lambda run,host,expected_fault=None:
        accepted(plan,next(slot for slot in plan["slots"] if slot["run_id"]==run.name)))
    return calls


def test_all_five_slots_use_preregistered_ids_and_fixed_positive_fault_positive_order(prepared,monkeypatch):
    root,plan=prepared;calls=wire_fakes(monkeypatch,root,plan)
    batch.run_batch("test01")
    result=batch.read_json(root/"batch_result.json")
    assert result["completed"] and [row["run_id"] for row in result["slots"]]==[row["run_id"] for row in plan["slots"]]
    assert [row["state"] for row in result["slots"]]==["completed"]*5
    assert calls==[(i,name) for i in range(1,6) for name in ("setup","harvest")]
    assert all(batch.read_json(root/f"{i}_audit.json")["batch_binding_verified"] for i in range(1,6))
    with pytest.raises(FileExistsError): batch.run_batch("test01")


@pytest.mark.parametrize("quiet",[False,True])
def test_controller_failure_stops_later_ids_and_only_quiet_tree_can_cancel_and_harvest(prepared,monkeypatch,quiet):
    root,plan=prepared;calls=wire_fakes(monkeypatch,root,plan,fail_slot=2,quiet=quiet)
    with pytest.raises(RuntimeError,match="controlled_failure"): batch.run_batch("test01")
    result=batch.read_json(root/"batch_result.json")
    assert [row["state"] for row in result["slots"]]==["completed","stopped","not_executed","not_executed","not_executed"]
    assert [row["run_id"] for row in result["slots"]]==[row["run_id"] for row in plan["slots"]]
    assert ((2,"cancel") in calls) is quiet and ((2,"harvest") in calls) is quiet
    assert not any(index>2 for index,name in calls)
    assert result["slots"][1]["host_cleanup_unconfirmed"] is not quiet


def test_host_timeout_cancels_harvests_audits_then_stops_even_if_business_audit_passes(prepared,monkeypatch):
    root,plan=prepared;calls=wire_fakes(monkeypatch,root,plan,expired=True)
    with pytest.raises(RuntimeError,match="slot_not_accepted"): batch.run_batch("test01")
    assert calls==[(1,"setup"),(1,"cancel"),(1,"harvest")]
    assert batch.read_json(root/"batch_result.json")["slots"][0]["host_timeout"] is True


@pytest.mark.parametrize("change",[{"run_id":"f"*32},{"contract_sha256":"0"*64},
    {"model_lineage":{"cli_executable_sha256":"0"*64}},{"status":"GREEN"},{"ai_trial":1}])
def test_positive_audit_must_bind_run_contract_cli_status_and_trial(prepared,change):
    root,plan=prepared;slot=plan["slots"][0]
    with pytest.raises(ValueError): batch.bind_audit({**accepted(plan,slot),**change},plan,slot)


@pytest.mark.parametrize("change",[{"fault_source":"codex_cli"},{"status":"SHADOW"},{"ai_trial":True}])
def test_fault_audit_cannot_be_relabelled_or_counted_as_ai(prepared,change):
    root,plan=prepared;slot=plan["slots"][1]
    with pytest.raises(ValueError): batch.bind_audit({**accepted(plan,slot),**change},plan,slot)


@pytest.mark.parametrize("bad",["../outside","manifest.JSON","artifacts/profile/private.json","artifacts/mailbox/request_0013.json","C:/private"])
def test_zip_allowlist_rejects_paths_before_creating_destination(tmp_path,bad):
    destination=tmp_path/"new"
    with pytest.raises(ValueError,match="zip_entry_rejected"): batch.safe_extract(archive([(bad,b"x")]),destination)
    assert not destination.exists()


def test_zip_rejects_symlink_duplicate_and_caps_before_writing(tmp_path,monkeypatch):
    link=zipfile.ZipInfo("manifest.json");link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
    with pytest.raises(ValueError): batch.safe_extract(archive([(link,b"outside")]),tmp_path/"link")
    with pytest.warns(UserWarning): raw=archive([("manifest.json",b"one"),("manifest.json",b"two")])
    with pytest.raises(ValueError): batch.safe_extract(raw,tmp_path/"duplicate")
    monkeypatch.setattr(batch,"MAX_PROJECT",3)
    with pytest.raises(ValueError): batch.safe_extract(archive([("artifacts/projects/0001.3mf",b"four")]),tmp_path/"size")
    assert not list(tmp_path.iterdir())


def test_zip_preserves_files_and_refuses_existing_destination(tmp_path):
    raw=archive([("manifest.json",b"one"),("artifacts/projects/0001.3mf",b"PK data")])
    target=tmp_path/"run";batch.safe_extract(raw,target)
    assert (target/"manifest.json").read_bytes()==b"one"
    with pytest.raises(FileExistsError): batch.safe_extract(raw,target)


def test_archive_replacement_between_path_check_and_read_cannot_bypass_snapshot_hash(tmp_path,monkeypatch):
    original_raw=archive([("manifest.json",b"expected")])
    replaced_raw=archive([("manifest.json",b"replaced")])
    path=tmp_path/"archive.zip";path.write_bytes(original_raw)
    expected=batch.sha(path);original_open=Path.open
    def changed_open(self,*args,**kwargs):
        if self==path and args==("rb",): return io.BytesIO(replaced_raw)
        return original_open(self,*args,**kwargs)
    monkeypatch.setattr(Path,"open",changed_open)
    with pytest.raises(ValueError,match="archive_hash_mismatch"):
        batch.verified_extract(path,expected,tmp_path/"new")
    assert not (tmp_path/"new").exists()


@pytest.mark.parametrize("dirty,valid",[(" M harness/launcher.py\n M harness/profile.py",True),
    ("M  harness/launcher.py",False),(" R harness/launcher.py -> elsewhere.py",False),
    (" M harness/agent_guest.py",False)])
def test_only_known_worktree_user_edits_are_excluded_from_head_bundle(monkeypatch,dirty,valid):
    monkeypatch.setattr(batch,"git",lambda *args:dirty)
    if valid: batch.require_clean_source()
    else:
        with pytest.raises(ValueError): batch.require_clean_source()


def test_git_keeps_porcelain_first_line_leading_space(monkeypatch):
    monkeypatch.setattr(batch.subprocess,"run",lambda *a,**k:SimpleNamespace(stdout=" M harness/launcher.py\r\n"))
    assert batch.git("status","--porcelain")==" M harness/launcher.py"


def test_phase_error_keeps_safe_stage_and_code_instead_of_only_remoteexception(prepared,monkeypatch):
    from runner import relay_run
    root,plan=prepared;slot=plan["slots"][0]
    code=("& "+batch.ps_quote(batch.REPO/"runner/v3_project_batch_phase.ps1")+" -BatchId "+batch.ps_quote("test01")+
        " -Slot 1 -Phase 'harvest' -PlanSha256 "+batch.ps_quote(batch.sha(root/"plan.json"))+"\n")
    (root/"1_harvest.ps1").write_text(code,encoding="utf-8",newline="\n")
    monkeypatch.setattr(relay_run,"RELAY_CMD",str(root/"absent_relay_command"))
    def launch(*args,**kwargs):
        batch.once(root/"1_harvest.json",{"ok":False,"phase":"harvest","run_id":slot["run_id"],
            "stage":"harvest_zip","error_type":"RemoteException","error_code":"compression_type_unavailable",
            "error_id":"TypeNotFound","category":"InvalidOperation","line_numbers":[8],
            "raw_exception_message":"must not be forwarded"})
        return "spawned"
    monkeypatch.setattr(relay_run,"relay_transact",launch)
    with pytest.raises(RuntimeError) as raised:batch.phase(root,plan,slot,"harvest")
    assert raised.value.phase_details["stage"]=="harvest_zip"
    assert raised.value.phase_details["error_code"]=="compression_type_unavailable"
    assert "raw_exception_message" not in raised.value.phase_details


@pytest.mark.parametrize("kind",["success","timeout","poll_error","unconfirmed","interrupt"])
def test_owned_controller_tree_lifecycle_is_bounded_and_only_quiescent_can_close(tmp_path,monkeypatch,kind):
    from harness import win32_job
    now=[0.];calls=[];polls=[0]
    monkeypatch.setattr(batch,"time",SimpleNamespace(monotonic=lambda:now[0],sleep=lambda seconds:now.__setitem__(0,now[0]+seconds)))
    class Process:
        def poll(self):
            polls[0]+=1
            if kind=="poll_error" and polls[0]==1: raise OSError("poll")
            if kind=="interrupt" and polls[0]==1: raise KeyboardInterrupt()
            if kind=="success": return 0,0
            if "terminate" in calls and kind!="unconfirmed": return 1,0
            return None,2
        def terminate(self): calls.append("terminate")
        def close(self): calls.append("close")
    monkeypatch.setattr(win32_job.OwnedJobProcess,"start",lambda *a,**k:Process())
    if kind=="success": assert batch.controller(["fixed"],tmp_path/"log")== (0,False)
    elif kind=="timeout": assert batch.controller(["fixed"],tmp_path/"log")== (1,True)
    else:
        with pytest.raises(KeyboardInterrupt if kind=="interrupt" else OSError if kind=="poll_error" else RuntimeError) as raised:
            batch.controller(["fixed"],tmp_path/"log")
        assert raised.value.host_tree_quiescent is (kind!="unconfirmed")
    assert ("close" in calls) is (kind!="unconfirmed")
    assert now[0]<691
