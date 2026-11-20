"""Prepare/run five fixed project-persistence trials, sequentially on one guest."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid
import zipfile

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
CASE = "m3g_export_3mf"
GUEST = r"C:\coil\orca-blackbox-v3-r1"
SUT = r"C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe"
SUT_SHA = "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf"
FAULTS = (None, "save_before_edit", "missing_reopen", "missing_slice", None)
LEGACY_DIRTY = {"harness/launcher.py", "harness/profile.py"}
SEQ = r"(?:000[1-9]|001[0-2])"
ALLOWED = re.compile(r"(?:contract\.json|manifest\.json|events\.ndjson|result\.json|artifacts/(?:"
    r"agent\.log|ready\.json|agent_report\.json|process\.json|operation_receipts\.ndjson|trace\.ndjson|control_cancel\.json|close_windows\.json|project_save_dialog\.json|"
    r"input/fixture\.3mf|projects/0001\.3mf|exports/0001\.gcode|mailbox/(?:request|response)_" + SEQ +
    r"\.json|frames/" + SEQ + r"(?:_[ab]\.bmp|\.png)))")
MAX_TOTAL, MAX_FILE, MAX_PROJECT = 300*1024**2, 64*1024**2, 16*1024**2


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def once(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read_json(path):
    from runner.agent_bridge import decode_json
    with Path(path).open("rb") as stream:
        raw = stream.read(1024*1024+1)
    if len(raw)>1024*1024:
        raise ValueError("batch_json_size")
    return decode_json(raw)


def batch_root(batch_id):
    if type(batch_id) is not str or not re.fullmatch(r"[a-z0-9_]{1,48}", batch_id):
        raise ValueError("invalid_batch_id")
    root = REPO / "artifacts/v3_batches" / batch_id
    if root.resolve() != root:
        raise ValueError("batch_link")
    return root


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True,
                          text=True, timeout=60).stdout.rstrip("\r\n")


def require_clean_source():
    # These pre-existing user edits are not executed by this host controller,
    # and are never included in the HEAD-only guest bundle.
    dirty=git("status","--porcelain","--untracked-files=no")
    for line in dirty.splitlines():
        if len(line)<4 or line[3:].replace("\\","/") not in LEGACY_DIRTY or line[:2]!=" M":
            raise ValueError("commit_other_tracked_changes_before_prepare_or_run")


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def prepare(batch_id, guest_base_ref):
    if type(guest_base_ref) is not str or not re.fullmatch(r"[0-9a-f]{40}", guest_base_ref):
        raise ValueError("invalid_guest_base_ref")
    require_clean_source()
    head = git("rev-parse", "HEAD")
    git("merge-base", "--is-ancestor", guest_base_ref, head)
    from harness.agent_model import default_codex_executable
    from harness.agent_protocol import LAYER_FIXTURE_SHA256
    from harness.agent_session import agent_contract
    from harness.run_verdict import contract_digest
    cli = default_codex_executable()
    root = batch_root(batch_id)
    root.mkdir(parents=True, exist_ok=False)
    bundle = root / "update.bundle"
    git("bundle", "create", str(bundle), guest_base_ref+"..HEAD")
    if bundle.stat().st_size > MAX_TOTAL:
        raise ValueError("bundle_size")
    plan = {"schema_version":1,"batch_id":batch_id,"case_id":CASE,"head":head,
        "guest_base_ref":guest_base_ref,"guest_root":GUEST,"sut_path":SUT,"sut_sha256":SUT_SHA,
        "cli_path":str(cli),"cli_sha256":sha(cli),"fixture_sha256":LAYER_FIXTURE_SHA256,
        "contract_sha256":contract_digest(agent_contract(CASE)),"bundle_sha256":sha(bundle),
        "phase_sha256":sha(REPO/"runner/v3_project_batch_phase.ps1"),
        "slots":[{"index":i,"run_id":uuid.uuid4().hex,"fault":fault,
                  "source":"codex_cli" if fault is None else "fault_probe_project_"+fault}
                 for i,fault in enumerate(FAULTS,1)]}
    once(root/"plan.json",plan)
    plan_sha = sha(root/"plan.json")
    for slot in plan["slots"]:
        for phase in ("setup","cancel","harvest"):
            code = ("& "+ps_quote(REPO/"runner/v3_project_batch_phase.ps1")+
                " -BatchId "+ps_quote(batch_id)+" -Slot "+str(slot["index"])+
                " -Phase "+ps_quote(phase)+" -PlanSha256 "+ps_quote(plan_sha)+"\n")
            with (root/f"{slot['index']}_{phase}.ps1").open("x",encoding="utf-8",newline="\n") as stream:
                stream.write(code)
    print(json.dumps({"phase":"prepared","batch_id":batch_id,"head":head,"slots":5}),flush=True)
    return plan


def validate_plan(plan, batch_id):
    fields={"schema_version","batch_id","case_id","head","guest_base_ref","guest_root","sut_path","sut_sha256",
            "cli_path","cli_sha256","fixture_sha256","contract_sha256","bundle_sha256","phase_sha256","slots"}
    if type(plan) is not dict or set(plan)!=fields or type(plan["schema_version"]) is not int or plan["schema_version"]!=1:
        raise ValueError("plan_schema")
    if (plan["batch_id"]!=batch_id or plan["case_id"]!=CASE or plan["guest_root"]!=GUEST
            or plan["sut_path"]!=SUT or plan["sut_sha256"]!=SUT_SHA):
        raise ValueError("plan_identity")
    for key in ("head","guest_base_ref","cli_sha256","fixture_sha256","contract_sha256","bundle_sha256","phase_sha256"):
        if type(plan[key]) is not str or not re.fullmatch(r"[0-9a-f]{40}" if key in {"head","guest_base_ref"} else r"[0-9a-f]{64}",plan[key]):
            raise ValueError("plan_hash")
    if type(plan["slots"]) is not list or len(plan["slots"])!=5:
        raise ValueError("plan_slots")
    ids=set()
    for i,(slot,fault) in enumerate(zip(plan["slots"],FAULTS),1):
        if (type(slot) is not dict or set(slot)!={"index","run_id","fault","source"}
                or type(slot["index"]) is not int or slot["index"]!=i or slot["fault"]!=fault
                or slot["source"]!=("codex_cli" if fault is None else "fault_probe_project_"+fault)
                or type(slot["run_id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}",slot["run_id"]) or slot["run_id"] in ids):
            raise ValueError("plan_slot_identity")
        ids.add(slot["run_id"])
    if type(plan["cli_path"]) is not str or not Path(plan["cli_path"]).is_absolute():
        raise ValueError("plan_cli_path")


def safe_extract(raw, destination):
    """Preflight the complete verified archive before writing a new directory."""
    if len(raw)>MAX_TOTAL:
        raise ValueError("zip_size")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        seen,total=set(),0
        for info in archive.infolist():
            name=info.filename
            mode=(info.external_attr>>16)&0o170000
            limit=MAX_PROJECT if name.endswith(".3mf") else MAX_FILE
            if (not ALLOWED.fullmatch(name) or name.casefold() in seen or info.is_dir()
                    or mode not in {0,stat.S_IFREG} or info.file_size>limit or info.flag_bits&1):
                raise ValueError("zip_entry_rejected")
            seen.add(name.casefold()); total+=info.file_size
            if total>MAX_TOTAL:
                raise ValueError("zip_total")
        destination=Path(destination)
        destination.mkdir(parents=True,exist_ok=False)
        for info in archive.infolist():
            target=destination/info.filename
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as stream:
                data=stream.read(info.file_size+1)
            if len(data)!=info.file_size:
                raise ValueError("zip_actual_size")
            with target.open("xb") as stream:
                stream.write(data)


def verified_extract(path, expected_sha, destination):
    """Hash and extract the same bounded immutable byte snapshot."""
    path=Path(path)
    if (path.is_symlink() or getattr(path.lstat(),"st_file_attributes",0)&stat.FILE_ATTRIBUTE_REPARSE_POINT
            or path.stat().st_size>MAX_TOTAL):
        raise ValueError("archive_file_rejected")
    with path.open("rb") as stream:
        raw=stream.read(MAX_TOTAL+1)
    if len(raw)>MAX_TOTAL or hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise ValueError("archive_hash_mismatch")
    safe_extract(raw,destination)


def phase(root, plan, slot, name):
    from runner.relay_run import RELAY_CMD, relay_transact
    if (root/f"{slot['index']}_{name}.json").exists():
        raise FileExistsError("phase_already_attempted")
    wrapper=root/f"{slot['index']}_{name}.ps1"
    expected=("& "+ps_quote(REPO/"runner/v3_project_batch_phase.ps1")+" -BatchId "+ps_quote(plan["batch_id"])+
        " -Slot "+str(slot["index"])+" -Phase "+ps_quote(name)+" -PlanSha256 "+ps_quote(sha(root/"plan.json"))+"\n")
    if wrapper.read_text(encoding="utf-8")!=expected:
        raise ValueError("phase_wrapper_changed")
    command="& "+ps_quote(wrapper)
    encoded=base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    child_args="-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand "+encoded
    idle_end=time.monotonic()+30
    while Path(RELAY_CMD).exists():
        if time.monotonic()>=idle_end:
            raise TimeoutError("relay_command_not_consumed")
        time.sleep(.1)
    result=relay_transact("Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList "+ps_quote(child_args),timeout_s=30)
    if result is None:
        raise TimeoutError("phase_launch_unconfirmed")
    receipt=root/f"{slot['index']}_{name}.json"
    end=time.monotonic()+(240 if name=="setup" else 1020 if name=="harvest" else 60)
    while not receipt.exists():
        if time.monotonic()>=end:
            raise TimeoutError("phase_receipt_deadline")
        time.sleep(.5)
    data=read_json(receipt)
    if data.get("ok") is not True or data.get("run_id")!=slot["run_id"] or data.get("phase")!=name:
        error=RuntimeError("phase_failed")
        error.phase_details={key:data[key] for key in ("phase","run_id","stage","error_type","error_code","error_id","category","line_numbers") if key in data}
        raise error
    if data.get("head")!=plan["head"] or data.get("sut_sha256")!=SUT_SHA:
        raise ValueError("phase_identity")
    return data


def controller(argv, log_path):
    """Only the owned controller/bridge/CLI subtree; never a process-name kill."""
    from harness.win32_job import OwnedJobProcess
    process=None; primary=None; quiet=False; code=None; expired=False
    try:
        process=OwnedJobProcess.start(argv,cwd=REPO,log_path=log_path,env=dict(os.environ))
        end=time.monotonic()+660
        while time.monotonic()<end:
            code,active=process.poll()
            if code is not None and active==0:
                quiet=True; break
            time.sleep(.2)
        expired=not quiet
    except BaseException as exc:
        primary=exc
    finally:
        if process is not None:
            try:
                if not quiet:
                    process.terminate(); end=time.monotonic()+30
                    while time.monotonic()<end:
                        code,active=process.poll()
                        if code is not None and active==0:
                            quiet=True; break
                        time.sleep(.2)
                if quiet: process.close()
            except BaseException as cleanup_error:
                if primary is None: primary=cleanup_error
        if not quiet and primary is None:
            primary=RuntimeError("host_cleanup_unconfirmed")
        if primary is not None:
            primary.host_tree_quiescent=quiet
            raise primary
    return code,expired


def bind_audit(audit,plan,slot):
    if (type(audit) is not dict or audit.get("audit_ok") is not True or audit.get("cleanup_confirmed") is not True
            or audit.get("run_id")!=slot["run_id"] or audit.get("contract_sha256")!=plan["contract_sha256"]):
        raise ValueError("audit_plan_identity")
    if slot["fault"] is None:
        if (audit.get("status")!="SHADOW" or audit.get("ai_trial") is not True or
                type(audit.get("model_lineage")) is not dict or
                audit["model_lineage"].get("cli_executable_sha256")!=plan["cli_sha256"]):
            raise ValueError("positive_audit_binding")
    elif (audit.get("status")!="EXPECTED_NON_GREEN" or audit.get("ai_trial") is not False
          or audit.get("fault_source")!=slot["source"]):
        raise ValueError("fault_audit_binding")
    return {**audit,"batch_binding_verified":True}


def run_batch(batch_id):
    root=batch_root(batch_id); plan=read_json(root/"plan.json"); validate_plan(plan,batch_id)
    require_clean_source()
    if git("rev-parse","HEAD")!=plan["head"]:
        raise ValueError("host_source_drift")
    if sha(root/"update.bundle")!=plan["bundle_sha256"] or sha(REPO/"runner/v3_project_batch_phase.ps1")!=plan["phase_sha256"]:
        raise ValueError("batch_asset_drift")
    once(root/"run_started.json",{"batch_id":batch_id,"started_at_ns":time.time_ns()})
    state=[{**slot,"state":"planned"} for slot in plan["slots"]]
    serial=0
    def progress(event):
        nonlocal serial
        once(root/f"state_{serial:04d}.json",{"event":event,"slots":state}); serial+=1
        print(json.dumps({"batch_id":batch_id,"phase":event,"slots":state}),flush=True)
    progress("planned")
    try:
        for slot in state:
            slot["state"]="started"; progress("setup")
            if slot["fault"] is None and sha(plan["cli_path"])!=plan["cli_sha256"]:
                raise ValueError("cli_drift")
            phase(root,plan,slot,"setup")
            progress("hostctl")
            program="v3_agent_host.py" if slot["fault"] is None else "v3_project_fault_probe.py"
            argv=[sys.executable,"-B",str(REPO/"tools"/program),"--run-id",slot["run_id"],"--guest-root",GUEST]
            argv+=(["--case",CASE,"--codex",plan["cli_path"]] if slot["fault"] is None else ["--fault",slot["fault"]])
            failure=None; expired=False
            try:
                code,expired=controller(argv,root/f"{slot['index']}_host.log")
                slot["host_exit_code"]=code
            except BaseException as exc:
                slot["host_error_type"]=type(exc).__name__
                slot["host_cleanup_unconfirmed"]=not getattr(exc,"host_tree_quiescent",False)
                if slot["host_cleanup_unconfirmed"]:
                    slot["guest_cleanup_confirmed"]=False
                    raise
                failure=exc
            if expired or failure is not None:
                slot["host_timeout"]=expired; progress("cancel")
                try:
                    phase(root,plan,slot,"cancel")
                except Exception as cancel_error:
                    slot["cancel_error_type"]=type(cancel_error).__name__
                    if failure is None: failure=cancel_error
            progress("harvest")
            evidence=phase(root,plan,slot,"harvest")
            archive=root/f"{slot['index']}_evidence.zip"
            destination=root/slot["run_id"]
            verified_extract(archive,evidence.get("zip_sha256"),destination)
            progress("audit")
            from tools.v3_project_audit import audit_project
            try:
                audit=audit_project(destination,REPO/"artifacts/v3_host"/slot["run_id"],expected_fault=slot["fault"])
                once(root/f"{slot['index']}_audit_raw.json",audit)
                slot["guest_cleanup_confirmed"]=audit.get("cleanup_confirmed") is True
            except Exception as audit_error:
                if failure is not None:
                    slot["audit_error_type"]=type(audit_error).__name__
                    raise failure
                raise
            if failure is not None:
                raise failure
            audit=bind_audit(audit,plan,slot)
            once(root/f"{slot['index']}_audit.json",audit)
            if (audit.get("audit_ok") is not True or audit.get("cleanup_confirmed") is not True
                    or expired or (slot["fault"] is None and slot.get("host_exit_code")!=0)):
                raise RuntimeError("slot_not_accepted")
            slot.update(state="completed",status=audit["status"]); progress("completed")
        once(root/"batch_result.json",{"completed":True,"slots":state,"release_eligible":False})
    except BaseException as exc:
        for slot in state:
            if slot["state"]=="planned": slot["state"]="not_executed"
            elif slot["state"]=="started": slot["state"]="stopped"
        progress("stopped")
        failure={"completed":False,"error_type":type(exc).__name__,"slots":state,"release_eligible":False}
        if hasattr(exc,"phase_details"): failure["phase_error"]=exc.phase_details
        once(root/"batch_result.json",failure)
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True)
    prepare_p=sub.add_parser("prepare"); prepare_p.add_argument("--batch-id",required=True)
    prepare_p.add_argument("--guest-base-ref",required=True)
    run_p=sub.add_parser("run"); run_p.add_argument("--batch-id",required=True)
    args=p.parse_args(argv)
    prepare(args.batch_id,args.guest_base_ref) if args.command=="prepare" else run_batch(args.batch_id)


if __name__=="__main__": main()
