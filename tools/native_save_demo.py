"""Host one-shot coordinator. GUI launch remains exclusively in hv_go.

Requires an already synchronized clean guest checkout. Authentication is the
existing actor configuration selected for this run; credentials are never copied.
"""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from runner.relay_run import relay_transact

HOST_SOURCES = ("tools/native_save_demo.py", "tools/windows_mcp_codex_probe.py",
    "runner/windows_mcp_bridge.py", "runner/agent_bridge.py", "runner/relay_run.py",
    "harness/agent_model.py", "harness/win32_job.py", "harness/native_save_policy.py",
    "runner/hv_go.ps1", "runner/hv_harvest.ps1", "runner/_common.ps1",
    "tools/native_save_guest.py", "tools/native_save_server.py", "harness/native_authority.py",
    "harness/native_recovery.py", "harness/native_diagnostic_recovery.py", "harness/canvas_approval.py",
    "harness/native_authority_probe.py", "harness/native_canvas_verify.py", "harness/runtime_ports.py",
    "contracts/evidence/canvas-diagnostic-bb64.json",
    "harness/pilot_top_layers.py", "harness/pilot_scale_x.py", "harness/pilot_infill_material.py",
    "harness/native_save_session.py", "harness/project_3mf.py", "harness/runtime.py", "harness/native_matrix.py", "harness/native_pilots.py", "harness/pilot_common.py", "harness/pilot_infill.py", "harness/pilot_material3.py", "harness/canvas_input.py", "harness/pilot_strength.py", "harness/pilot_transform.py", "harness/pilot_material.py", "harness/guard_fault.py", "tools/zcode_matrix.py", "tools/windows_mcp_zcode_probe.py", "tools/zcode_session_driver.mjs", "harness/ip_guard.py")


def quoted(value):
    return "'"+str(value).replace("'", "''")+"'"


def detached(script, completed, seconds):
    command = ("Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList "
               "@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',"+quoted(script)+") | Select-Object -ExpandProperty Id")
    pid = relay_transact(command, timeout_s=15)
    if not pid or not pid.strip().isdigit():
        raise RuntimeError("demo_relay_launch_unconfirmed")
    cutoff = time.monotonic()+seconds
    while time.monotonic() < cutoff:
        if completed.exists():
            try:
                receipt = json.loads(completed.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                time.sleep(.1)
                continue
            if receipt.get("ok") is not True:
                raise RuntimeError("demo_management_failed:"+str(receipt.get("error_type")))
            return receipt
        time.sleep(.2)
    raise TimeoutError("demo_management_timeout")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=None)
    p.add_argument("--actor", choices=("codex", "zcode"), default="codex")
    from harness.native_matrix import SCENARIOS
    p.add_argument("--scenario", choices=tuple(s for s in SCENARIOS if s not in {"canvas_probe", "authority_probe"}), default="base")
    args = p.parse_args()
    from harness.native_matrix import scenario_spec
    scenario_spec(args.actor, args.scenario)
    from harness.native_pilots import require_pilot_ready
    require_pilot_ready(args.scenario)
    run_id = args.run_id or uuid.uuid4().hex
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid_demo_run_id")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("invalid_demo_head")
    for source in HOST_SOURCES:
        subprocess.check_output(["git", "ls-files", "--error-unmatch", source], cwd=REPO, stderr=subprocess.DEVNULL)
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *HOST_SOURCES], cwd=REPO).returncode:
        raise ValueError("demo_executed_host_source_not_committed")
    if args.actor == "zcode":
        from tools.windows_mcp_zcode_probe import provider_metadata
        from harness.ip_guard import IPGuard
        provider_metadata(Path.home()/".zcode/v2/provider_config.json")
        IPGuard().check()
    root = REPO / "artifacts/native_save_demo" / run_id
    root.mkdir(parents=True, exist_ok=False)
    launch_done = root / "launch.json"
    script = root / "launch.ps1"
    script.write_text("$ErrorActionPreference='Stop'\ntry {\n"
        "$env:ORCA_BB_GUEST_SANDBOX="+quoted(r"C:\coil\orca-blackbox-v3-r1")+"\n. "+quoted(REPO / "runner/_common.ps1")+"\n"
        "$state=Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$git) "
        "@{head=(& $git -C $sb rev-parse HEAD);dirty=@(& $git -C $sb status --porcelain);"
        r"runtime=(Test-Path 'C:\coil\tools\windows-mcp-0.8.9\python.exe')} } -ArgumentList $guestSandbox,$guestGit"+"\n"
        "if($state.head.Trim() -ne "+quoted(head)+" -or $state.dirty.Count -or -not $state.runtime){throw 'demo_guest_sync_or_runtime_required'}\n"
        "& "+quoted(REPO / "runner/hv_go.ps1")+" -NoSync -WindowsMcpProbe -NativeSave -ProbeRunId "+quoted(run_id)
        +" -NativeActor "+args.actor+" -NativeScenario "+args.scenario+" *> "+quoted(root / "launch.log")+"\n"
        "$r=@{ok=$true;head="+quoted(head)+"}\n"
        "}catch{$r=@{ok=$false;error_type=$_.Exception.GetType().Name;message=$_.Exception.Message}}\n"
        "$r|ConvertTo-Json|Set-Content "+quoted(launch_done)+" -Encoding UTF8\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "source_sha": head, "phase": "launching"}), flush=True)
    detached(script, launch_done, 180)
    error, code = None, 1
    try:
        if args.actor == "zcode":
            from tools.windows_mcp_zcode_probe import main as run_actor
            code = run_actor(["--run-id", run_id, "--scenario", args.scenario])
        else:
            from tools.windows_mcp_codex_probe import main as run_actor
            code = run_actor(["--run-id", run_id, "--goal-save"])
    except BaseException as exc:
        error = type(exc).__name__
    harvest_done = root / "harvest.json"
    harvest = root / "harvest.ps1"
    cancel = ""
    if code != 0:
        cancel = (". "+quoted(REPO / "runner/_common.ps1")+"\n"
            "Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$id) "
            "$r=Join-Path $sb ('artifacts\\v3\\'+$id);$a=Join-Path $r 'artifacts';"
            "if(!(Test-Path (Join-Path $r 'result.json')) -and (Test-Path $a)){"
            "[IO.File]::WriteAllText((Join-Path $a 'control_cancel.json'),'{\"reason\":\"host_error\"}');"
            "for($i=0;$i-lt 100;$i++){if(Test-Path (Join-Path $a 'process.json')){break};Start-Sleep -Milliseconds 300}}"
            "} -ArgumentList $guestSandbox,"+quoted(run_id)+"\n")
    harvest.write_text("$ErrorActionPreference='Stop'\ntry {\n"
        "$env:ORCA_BB_GUEST_SANDBOX="+quoted(r"C:\coil\orca-blackbox-v3-r1")+"\n"+cancel+"& "
        +quoted(REPO / "runner/hv_harvest.ps1")+" -NativeSave -WindowsMcpRunId "+quoted(run_id)
        +" *> "+quoted(root / "harvest.log")+"\n$r=@{ok=$true}\n"
        "}catch{$r=@{ok=$false;error_type=$_.Exception.GetType().Name}}\n"
        "$r|ConvertTo-Json|Set-Content "+quoted(harvest_done)+" -Encoding UTF8\n", encoding="utf-8")
    detached(harvest, harvest_done, 120)
    result_path = REPO / "artifacts/windows_mcp_harvest" / run_id / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {"verified_pass": False}
    summary = {"run_id": run_id, "source_sha": head, "actor": args.actor, "scenario": args.scenario, "actor_exit": code,
               "actor_error": error, "result": result, "release_eligible": False}
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if code == 0 and result.get("verified_pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
