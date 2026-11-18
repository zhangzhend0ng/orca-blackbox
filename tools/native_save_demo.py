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
    "tools/native_save_run.py", "tools/native_save_guest.py", "tools/native_save_server.py", "harness/native_authority.py",
    "harness/native_desktop_video.py",
    "harness/native_script_baseline.py", "harness/process_panel.py", "harness/agent_project_ui.py", "harness/agent_business_ui.py",
    "harness/native_uia_replay.py", "contracts/replays/uia_layer.json", "contracts/replays/uia_save.json",
    "contracts/replays/uia_canvas.json", "contracts/replays/uia_process.json",
    "tests/engine/m6a_transform_verify.py", "tests/mixing/m4e_mixing_paint.py",
    "harness/native_recovery.py", "harness/native_diagnostic_recovery.py", "harness/canvas_approval.py",
    "harness/native_authority_probe.py", "harness/native_canvas_verify.py", "harness/runtime_ports.py",
    "contracts/evidence/canvas-diagnostic-bb64.json",
    "harness/pilot_top_layers.py", "harness/pilot_scale_x.py", "harness/pilot_infill_material.py",
    "harness/pilot_process_combo.py", "harness/pilot_mix_recipes.py", "fixtures/mixed_filament_test.3mf",
    "tools/native_mix_census.py", "tests/mixing/m4i_mixing_slice.py", "tests/mixing/m3u_mixing_ratio_flow.py",
    "harness/native_uia.py", "harness/native_uia_hybrid.py", "harness/pilot_uia_goals.py",
    "harness/native_mix_uia.py", "harness/native_mix_badges.py", "tools/native_mix_accessibility.ps1",
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


def wait_script(run_id):
    from runner.windows_mcp_bridge import GuestHTTP

    deadline = time.monotonic() + 940
    control = GuestHTTP(r"C:\coil\orca-blackbox-v3-r1", run_id, deadline=deadline, channel="control", goal_save=True)
    while time.monotonic() < deadline:
        result = control.remote({"op": "result"})
        if result.get("pending") is not True:
            return 0 if result.get("verified_pass") is True else 1
        time.sleep(2)
    raise TimeoutError("native_script_result_timeout")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=None)
    p.add_argument("--record-desktop", action="store_true", help="Record the dedicated win11-test desktop.")
    p.add_argument("--goal-only", action="store_true", help="Omit the guided UI route for ZCode.")
    p.add_argument("--inspect-mix-controls", action="store_true", help="Capture Add Mix controls during the scripted probe.")
    p.add_argument("--actor", choices=("codex", "zcode", "script"), default="codex")
    from harness.native_matrix import REPLAY_SOURCES, SCENARIOS, UIA_HYBRID_SCENARIOS, UIA_LAYER_SCENARIO, UIA_MIX_RECIPES
    p.add_argument("--scenario", choices=tuple(s for s in SCENARIOS if s not in {"canvas_probe", "authority_probe"}))
    args = p.parse_args()
    if args.scenario is None:
        args.scenario = "base" if args.actor == "codex" else UIA_LAYER_SCENARIO
    if args.goal_only and (args.actor != "zcode" or args.scenario not in UIA_HYBRID_SCENARIOS):
        p.error("--goal-only requires --actor zcode and a UIA hybrid scenario")
    if args.inspect_mix_controls and (args.actor != "script" or args.scenario != UIA_MIX_RECIPES):
        p.error("--inspect-mix-controls requires the mixing baseline script")
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
    sources = HOST_SOURCES
    if args.scenario in REPLAY_SOURCES:
        from harness.native_uia_replay import recipe_path
        recording = recipe_path(args.scenario).relative_to(REPO).as_posix()
        if recording not in sources:
            sources += (recording,)
    for source in sources:
        subprocess.check_output(["git", "ls-files", "--error-unmatch", source], cwd=REPO, stderr=subprocess.DEVNULL)
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *sources], cwd=REPO).returncode:
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
    capture_request = ""
    for enabled, folder in ((args.record_desktop, "native_video_requests"),
                            (args.inspect_mix_controls, "native_mix_census_requests")):
        if not enabled:
            continue
        capture_request += ("Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$id) "
            "$dir=Join-Path $sb 'artifacts/" + folder + "'; $null=[IO.Directory]::CreateDirectory($dir); "
            "$file=[IO.File]::Open((Join-Path $dir $id),[IO.FileMode]::CreateNew); $file.Dispose()} "
            "-ArgumentList $guestSandbox,"+quoted(run_id)+"\n")
    script.write_text("$ErrorActionPreference='Stop'\ntry {\n"
        "$env:ORCA_BB_GUEST_SANDBOX="+quoted(r"C:\coil\orca-blackbox-v3-r1")+"\n. "+quoted(REPO / "runner/_common.ps1")+"\n"
        "$state=Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$git) "
        "@{head=(& $git -C $sb rev-parse HEAD);dirty=@(& $git -C $sb status --porcelain);"
        r"runtime=(Test-Path 'C:\coil\tools\windows-mcp-0.8.9\python.exe')} } -ArgumentList $guestSandbox,$guestGit"+"\n"
        "if($state.head.Trim() -ne "+quoted(head)+" -or $state.dirty.Count"
        + (" -or -not $state.runtime" if args.actor != "script" or args.scenario in REPLAY_SOURCES or args.inspect_mix_controls
           else "") + "){throw 'demo_guest_sync_or_runtime_required'}\n"
        +capture_request+
        "& "+quoted(REPO / "runner/hv_go.ps1")+" -NoSync -WindowsMcpProbe -NativeSave -ProbeRunId "+quoted(run_id)
        +" -NativeActor "+args.actor+" -NativeScenario "+args.scenario+" *> "+quoted(root / "launch.log")+"\n"
        "$r=@{ok=$true;head="+quoted(head)+"}\n"
        "}catch{$r=@{ok=$false;error_type=$_.Exception.GetType().Name;message=$_.Exception.Message}}\n"
        "$r|ConvertTo-Json|Set-Content "+quoted(launch_done)+" -Encoding UTF8\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "source_sha": head, "phase": "launching"}), flush=True)
    detached(script, launch_done, 180)
    error, code = None, 1
    try:
        if args.actor == "script":
            code = wait_script(run_id)
        elif args.actor == "zcode":
            from tools.windows_mcp_zcode_probe import main as run_actor
            command = ["--run-id", run_id, "--scenario", args.scenario]
            if args.goal_only:
                command.append("--goal-only")
            code = run_actor(command)
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
    if args.goal_only:
        summary["prompt_mode"] = "goal_only"
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if code == 0 and result.get("verified_pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
