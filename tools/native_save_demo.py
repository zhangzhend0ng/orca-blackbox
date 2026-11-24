"""Host one-shot coordinator. GUI launch remains exclusively in hv_go.

Requires an already synchronized clean guest checkout. Authentication is the
existing actor configuration selected for this run; credentials are never copied.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
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
    "harness/native_script_baseline.py", "harness/native_pairwise.py", "harness/process_panel.py", "harness/agent_project_ui.py", "harness/agent_business_ui.py",
    "harness/native_uia_replay.py", "contracts/replays/uia_layer.json", "contracts/replays/uia_save.json",
    "contracts/replays/uia_canvas.json", "contracts/replays/uia_process.json",
    "tests/engine/m6a_transform_verify.py", "tests/mixing/m4e_mixing_paint.py",
    "harness/native_recovery.py", "harness/native_diagnostic_recovery.py", "harness/canvas_approval.py",
    "harness/native_authority_probe.py", "harness/native_canvas_verify.py", "harness/runtime_ports.py",
    "contracts/evidence/canvas-diagnostic-bb64.json",
    "harness/pilot_top_layers.py", "harness/pilot_scale_x.py", "harness/pilot_infill_material.py",
    "harness/pilot_process_combo.py", "harness/pilot_mix_recipes.py", "fixtures/mixed_filament_test.3mf",
    "tools/native_mix_census.py", "tests/mixing/m4i_mixing_slice.py", "tests/mixing/m3u_mixing_ratio_flow.py",
    "harness/native_uia.py", "harness/native_uia_hybrid.py", "harness/native_process_viewport.py", "harness/pilot_uia_goals.py", "harness/agent_guest.py",
    "harness/native_mix_uia.py", "harness/native_mix_badges.py", "tools/native_mix_accessibility.ps1",
    "harness/native_save_session.py", "harness/project_3mf.py", "harness/runtime.py", "harness/native_matrix.py", "harness/native_pilots.py", "harness/pilot_common.py", "harness/pilot_infill.py", "harness/pilot_material3.py", "harness/canvas_input.py", "harness/pilot_strength.py", "harness/pilot_transform.py", "harness/pilot_material.py", "harness/guard_fault.py", "tools/zcode_matrix.py", "tools/windows_mcp_zcode_probe.py", "tools/zcode_session_driver.mjs", "harness/ip_guard.py",
    "harness/zcode_gateway.py")


def quoted(value):
    return "'"+str(value).replace("'", "''")+"'"


def stage_model(root, run_id, model_path, head):
    from harness.agent_protocol import LAYER_FIXTURE
    from harness.model_move_pilot import CATALOG, LIMIT, TEMPLATE, canonical, digest, prepare_mesh, validate_plan

    with model_path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    model_format = model_path.suffix.lower().lstrip(".")
    project = prepare_mesh(raw, model_format, (REPO / LAYER_FIXTURE).read_bytes())
    plan = validate_plan({"run_id": run_id, "template": TEMPLATE, "source_sha256": head,
        "model": {"name": model_path.name, "format": model_format, "size": len(raw), "sha256": digest(raw)},
        "environment": CATALOG["sut"], "prepared_sha256": digest(project),
        "import_policy": "geometry_in_fixed_process"}, run_id)
    model = root / "prepared.3mf"
    manifest = root / "resolved_plan.json"
    model.write_bytes(project)
    manifest.write_bytes(canonical(plan))
    # Preserve exact source bytes locally. The guest receives the normalized
    # project and its plan through the existing Hyper-V management channel.
    (root / ("source." + model_format)).write_bytes(raw)
    script = (
        "$modelSession=New-PSSession -VMName $vm -Credential $cred -ErrorAction Stop\n"
        "try {\n"
        "$target=Join-Path $guestSandbox ('artifacts/native_model_requests/'+" + quoted(run_id) + ")\n"
        "Invoke-Command -Session $modelSession {param($d) "
        "if(Test-Path -LiteralPath $d){throw 'model_request_exists'}; "
        "$null=[IO.Directory]::CreateDirectory($d)} -ArgumentList $target\n"
        "function Send-ModelFile($localPath,$name,$sha) {\n"
        "  $stream=[IO.File]::OpenRead($localPath)\n"
        "  try {\n"
        "    $buffer=New-Object byte[] 196608\n"
        "    while(($n=$stream.Read($buffer,0,$buffer.Length)) -gt 0) {\n"
        "      $chunk=[Convert]::ToBase64String($buffer,0,$n)\n"
        "      Invoke-Command -Session $modelSession {param($path,$data) "
        "$s=[IO.File]::Open($path,[IO.FileMode]::Append); try {"
        "$b=[Convert]::FromBase64String($data);$s.Write($b,0,$b.Length)} finally {$s.Dispose()}} "
        "-ArgumentList (Join-Path $target $name),$chunk\n"
        "    }\n"
        "  } finally {$stream.Dispose()}\n"
        "  $actual=Invoke-Command -Session $modelSession {param($path) "
        "(Get-FileHash -LiteralPath $path).Hash } -ArgumentList (Join-Path $target $name)\n"
        "  if($actual -ne $sha){throw 'model_transfer_digest'}\n"
        "}\n"
        "Send-ModelFile " + quoted(model) + " 'prepared.3mf' " + quoted(digest(project)) + "\n"
        "Send-ModelFile " + quoted(manifest) + " 'resolved_plan.json' " + quoted(digest(canonical(plan))) + "\n"
        "} finally {Remove-PSSession $modelSession}\n"
    )
    return plan, script


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


def wait_script(run_id, *, require_suite_result=False, scenario="base"):
    from runner.windows_mcp_bridge import GuestHTTP

    deadline = time.monotonic() + 940
    control = GuestHTTP(r"C:\coil\orca-blackbox-v3-r1", run_id, deadline=deadline, channel="control",
                        goal_save=True, scenario=scenario)
    while time.monotonic() < deadline:
        result = control.remote({"op": "result", "require_suite_result": require_suite_result})
        if result.get("pending") is not True:
            if result.get("suite_exited_without_result"):
                raise RuntimeError("demo_suite_exited_without_result")
            return 0 if result.get("verified_pass") is True else 1
        time.sleep(2)
    raise TimeoutError("native_script_result_timeout")


def main():
    started = time.monotonic()
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=None)
    p.add_argument("--model", type=Path, help="STL or 3MF geometry for the bound-model translation trial.")
    p.add_argument("--record-desktop", action="store_true", help="Record the dedicated win11-test desktop.")
    p.add_argument("--goal-only", action="store_true", help="Omit the guided UI route for ZCode.")
    p.add_argument("--inspect-mix-controls", action="store_true", help="Capture Add Mix controls during the scripted probe.")
    p.add_argument("--probe-mix-waits", action="store_true", help="Measure the mixing replay with readiness checks replacing fixed sleeps.")
    p.add_argument("--probe-mix-boot", action="store_true", help="Include readiness-based startup dialog scanning in the mixing waits probe.")
    p.add_argument("--actor", choices=("codex", "zcode", "script"), default="codex")
    from harness.native_matrix import BOUND_MODEL_MOVE, FIXTURE_SCENARIOS, RECORDED_SCENARIOS, REPLAY_SOURCES, UIA_HYBRID_SCENARIOS, UIA_LAYER_SCENARIO, UIA_MIX_RECIPES, UIA_REPLAY_MIX, scenario_names
    from harness.native_pairwise import CONFIG_CASES, OPERATIONS, PAIR_CASES
    # scenario_names: the registered scenarios and their `_std02` twins.
    p.add_argument("--scenario", choices=tuple(s for s in scenario_names() if s not in {"canvas_probe", "authority_probe"}))
    args = p.parse_args()
    args.probe_mix_waits |= args.probe_mix_boot
    if args.scenario is None:
        args.scenario = BOUND_MODEL_MOVE if args.model is not None else "base" if args.actor == "codex" else UIA_LAYER_SCENARIO
    if (args.scenario == BOUND_MODEL_MOVE) != (args.model is not None) or (args.model is not None and args.actor != "script"):
        p.error("--model requires --actor script and the bound_model_move scenario")
    from harness.agent_protocol import MAINTENANCE_TRIALS
    if args.goal_only and (args.actor != "zcode" or args.scenario not in UIA_HYBRID_SCENARIOS | MAINTENANCE_TRIALS.keys()):
        p.error("--goal-only requires --actor zcode and a UIA hybrid scenario")
    if args.inspect_mix_controls and (args.actor != "script" or args.scenario != UIA_MIX_RECIPES):
        p.error("--inspect-mix-controls requires the mixing baseline script")
    if args.probe_mix_waits and (args.actor != "script" or args.scenario != UIA_REPLAY_MIX):
        p.error("--probe-mix-waits requires the recorded mixing replay")
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
    fixture_cases = ()
    if args.scenario in FIXTURE_SCENARIOS:
        from harness.native_fixture_suite import FIXTURE_CASES
        fixture_cases = FIXTURE_CASES
        sources += ("harness/native_fixture_suite.py",)
    recording_scenarios = fixture_cases or (args.scenario,)
    if args.scenario in PAIR_CASES:
        recording_scenarios = tuple(OPERATIONS[name].recording for name in PAIR_CASES[args.scenario]) + ("uia_replay_move_layer",)
    if args.scenario in CONFIG_CASES or args.scenario == BOUND_MODEL_MOVE:
        sources += ("contracts/config_dependencies.json", "harness/native_config_cases.py",
                    "harness/agent_layer_verify.py", "tools/scan_config_dependencies.py")
    if args.scenario in CONFIG_CASES:
        recording_scenarios += ("uia_replay_layer", "uia_replay_enums")
    if args.model is not None:
        sources += ("harness/model_move_pilot.py", "fixtures/agent_layer_cube.3mf")
    from harness.agent_protocol import suffixed_fixture
    if args.scenario in MAINTENANCE_TRIALS:
        sources += ("harness/agent_protocol.py", "harness/native_preset_script.py",
                    "harness/param_case_lib.py", "harness/param_comparison.py", "harness/pilot_param_265_overhang_curl.py",
                    "harness/pilot_param_276_speed_limits.py")
    other_fixture = suffixed_fixture(args.scenario)
    if args.scenario in MAINTENANCE_TRIALS and other_fixture is None:
        raise ValueError("comparison_fixture_not_registered")
    if other_fixture:
        # The run opens another fixture than the cube's: its bytes belong to the
        # sources like the cube's do (tracked and unmodified against HEAD, checked below).
        sources += (other_fixture[0],)
    for scenario in recording_scenarios:
        if scenario not in REPLAY_SOURCES:
            continue
        from harness.native_uia_replay import recipe_path
        recording = recipe_path(scenario).relative_to(REPO).as_posix()
        if recording not in sources:
            sources += (recording,)
    for source in sources:
        subprocess.check_output(["git", "ls-files", "--error-unmatch", source], cwd=REPO, stderr=subprocess.DEVNULL)
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *sources], cwd=REPO).returncode:
        raise ValueError("demo_executed_host_source_not_committed")
    if args.actor == "zcode":
        from tools.windows_mcp_zcode_probe import provider_metadata
        from harness.native_matrix import GUARD_DISCONNECT_SCENARIO
        from harness.zcode_gateway import check_gateway
        provider_metadata(Path.home()/".zcode/v2/provider_config.json")
        if args.scenario == GUARD_DISCONNECT_SCENARIO:
            from harness.ip_guard import IPGuard
            IPGuard().check()
        else:
            check_gateway()
    root = REPO / "artifacts/native_save_demo" / run_id
    root.mkdir(parents=True, exist_ok=False)
    launch_done = root / "launch.json"
    script = root / "launch.ps1"
    capture_request = ""
    plan = None
    if args.model is not None:
        plan, capture_request = stage_model(root, run_id, args.model, head)
    for enabled, folder in ((args.record_desktop, "native_video_requests"),
                            (args.inspect_mix_controls, "native_mix_census_requests"),
                            (args.probe_mix_waits, "native_mix_wait_requests"),
                            (args.probe_mix_boot, "native_mix_boot_requests")):
        if not enabled:
            continue
        capture_request += ("Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$id) "
            "$dir=Join-Path $sb 'artifacts/" + folder + "'; $null=[IO.Directory]::CreateDirectory($dir); "
            "$file=[IO.File]::Open((Join-Path $dir $id),[IO.FileMode]::CreateNew); $file.Dispose()} "
            "-ArgumentList $guestSandbox,"+quoted(run_id)+"\n")
    sut_check = ""
    if args.scenario in CONFIG_CASES or args.scenario == BOUND_MODEL_MOVE:
        from harness.native_config_cases import CATALOG
        sut = CATALOG["sut"]
        profile_command = ("import json; from harness.profile import default_presets_dir; "
                           "from tools.scan_config_dependencies import installed_vendor; "
                           "root=default_presets_dir(); "
                           "print(json.dumps({v: installed_vendor(root,v)[1] for v in ('Snapmaker','BBL')}))")
        sut_check = (
            "$sut=Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$git,$python) "
            "Push-Location $sb; try {$exe=& $python -B -c "
            "'from harness.launcher import default_exe; print(default_exe())'; "
            "if($LASTEXITCODE -ne 0){throw 'config_guest_exe_lookup'}; "
            "$profiles=& $python -B -c " + quoted(profile_command) + "; "
            "if($LASTEXITCODE -ne 0){throw 'config_guest_preset_lookup'}; "
            "@{hash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash;"
            "dll=(Get-FileHash -LiteralPath (Join-Path (Split-Path $exe) 'Snapmaker_Orca.dll')).Hash;"
            "vendors=($profiles|ConvertFrom-Json);"
            "presets=(& $git -C $sb rev-parse 'HEAD:resources')} } finally {Pop-Location} "
            "} -ArgumentList $guestSandbox,$guestGit,$guestPython\n"
            "if($sut.hash -ne " + quoted(sut["exe_sha256"]) + " -or $sut.presets -ne "
            + quoted(sut["preset_tree"]) + " -or $sut.dll -ne " + quoted(sut["dll_sha256"])
            + "".join(f" -or $sut.vendors.{vendor}.json_tree_sha256 -ne " + quoted(info["json_tree_sha256"])
                      for vendor, info in sut["installed_vendors"].items())
            + "){throw 'config_guest_build_or_preset_digest_changed'}\n"
        )
    script.write_text("$ErrorActionPreference='Stop'\n"
        # 2026-11-23 wedge instrument: stage markers tell exactly where the
        # elevated child dies when launch_done never appears (wedge: hv_go
        # output complete, no receipt, no guest run dir).
        "function Mark([string]$s){[IO.File]::AppendAllText('"+str(root / "launch.stages").replace(chr(92),chr(92)*2)+"', $s+' '+([DateTime]::Now.ToString('HH:mm:ss.fff'))+[Environment]::NewLine)}\n"
        "Mark 'start'\ntry {\n"
        "$env:ORCA_BB_GUEST_SANDBOX="+quoted(r"C:\coil\orca-blackbox-v3-r1")+"\n. "+quoted(REPO / "runner/_common.ps1")+"\n"
        "Mark 'pre-state-check'\n"
        "$state=Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {param($sb,$git) "
        "@{head=(& $git -C $sb rev-parse HEAD);dirty=@(& $git -C $sb status --porcelain);"
        r"runtime=(Test-Path 'C:\coil\tools\windows-mcp-0.8.9\python.exe')} } -ArgumentList $guestSandbox,$guestGit"+"\n"
        "if($state.head.Trim() -ne "+quoted(head)+" -or $state.dirty.Count"
        + (" -or -not $state.runtime" if args.actor != "script" or args.scenario in RECORDED_SCENARIOS or fixture_cases or args.inspect_mix_controls
           else "") + "){throw 'demo_guest_sync_or_runtime_required'}\n"
        +sut_check+capture_request+
        "Mark 'pre-hvgo'\n"
        "& "+quoted(REPO / "runner/hv_go.ps1")+" -NoSync -WindowsMcpProbe -NativeSave -ProbeRunId "+quoted(run_id)
        +" -NativeActor "+args.actor+" -NativeScenario "+args.scenario
        +(" -ProbeMixWaits" if args.probe_mix_waits else "")+" *> "+quoted(root / "launch.log")+"\n"
        "Mark 'post-hvgo'\n"
        "$r=@{ok=$true;head="+quoted(head)+(";sut=$sut" if sut_check else "")+"}\n"
        "}catch{Mark 'catch'\n$r=@{ok=$false;error_type=$_.Exception.GetType().Name;message=$_.Exception.Message}}\n"
        "Mark 'pre-receipt'\n"
        "$r|ConvertTo-Json -Depth 6|Set-Content "+quoted(launch_done)+" -Encoding UTF8\n"
        "Mark 'done'\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "source_sha": head, "phase": "launching"}), flush=True)
    detached(script, launch_done, 180)
    error, code = None, 1
    try:
        if args.actor == "script":
            code = wait_script(run_id, require_suite_result=plan is not None, scenario=args.scenario)
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
    child_harvest = ""
    if fixture_cases:
        child_ids = [uuid.uuid5(uuid.UUID(run_id), scenario).hex for scenario in fixture_cases]
        suite_path = REPO / "artifacts/windows_mcp_harvest" / run_id / "fixture_suite.json"
        harvest_command = quoted(REPO / "runner/hv_harvest.ps1") + " -NativeSave -WindowsMcpRunId "
        child_harvest = (
            "if (Test-Path -LiteralPath " + quoted(suite_path) + "){\n"
            "$children=@((Get-Content -Raw -LiteralPath " + quoted(suite_path) + " | ConvertFrom-Json).cases)\n"
            "foreach($child in $children){\n"
            "if ($child.run_id -cnotin @(" + ",".join(map(quoted, child_ids)) + ")){throw 'fixture_child_identity'}\n"
            "& " + harvest_command + "$child.run_id *>> " + quoted(root / "harvest.log") + "\n}\n}\n"
        )
    harvest.write_text("$ErrorActionPreference='Stop'\ntry {\n"
        "$env:ORCA_BB_GUEST_SANDBOX="+quoted(r"C:\coil\orca-blackbox-v3-r1")+"\n"+cancel+"& "
        +quoted(REPO / "runner/hv_harvest.ps1")+" -NativeSave -WindowsMcpRunId "+quoted(run_id)
        +" *> "+quoted(root / "harvest.log")+"\n"+child_harvest+"$r=@{ok=$true}\n"
        "}catch{$r=@{ok=$false;error_type=$_.Exception.GetType().Name}}\n"
        "$r|ConvertTo-Json|Set-Content "+quoted(harvest_done)+" -Encoding UTF8\n", encoding="utf-8")
    harvest_started = time.monotonic()
    detached(harvest, harvest_done, 120)
    harvest_seconds = time.monotonic() - harvest_started
    result_path = REPO / "artifacts/windows_mcp_harvest" / run_id / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {"verified_pass": False}
    plan_matches = None
    if plan is not None:
        path = result_path.with_name("resolved_plan.json")
        plan_matches = path.exists() and json.loads(path.read_bytes()) == plan
    summary = {"run_id": run_id, "source_sha": head, "actor": args.actor, "scenario": args.scenario, "actor_exit": code,
               "actor_error": error, "result": result, "release_eligible": False,
               "host_wall_seconds": time.monotonic() - started, "harvest_seconds": harvest_seconds}
    business_pass = True
    if args.scenario in MAINTENANCE_TRIALS:
        from harness.param_comparison import comparison_business_status
        business_pass = False
        summary["comparison"] = {"status": "no_verified_gui_result", **comparison_business_status({})}
        if result.get("verified_pass") is True and code == 0:
            from harness.native_pilots import comparison_baseline, native_fixture, verify_business
            try:
                harvest = result_path.parent
                proof = json.loads((harvest / "proof.json").read_bytes())
                fixture = (harvest / "input/fixture.3mf").read_bytes()
                project = (harvest / "proof/0001.3mf").read_bytes()
                export = (harvest / "exports/0001.gcode").read_bytes()
                if (hashlib.sha256(fixture).hexdigest() != native_fixture(args.scenario)[1]
                        or hashlib.sha256(project).hexdigest() != proof["project_sha256"]
                        or hashlib.sha256(export).hexdigest() != proof["gcode_sha256"]
                        or proof["run_id"] != run_id):
                    raise ValueError("comparison_artifact_identity")
                baseline_root = Path(os.environ.get("ORCA_BB_HARVEST", result_path.parent.parent))
                baseline = comparison_baseline(args.scenario, baseline_root)
                detail = verify_business(args.scenario, project, fixture, export, baseline_gcode=baseline)
                verdict = comparison_business_status(detail)
                business_pass = verdict["business_status"] == "PASS"
                summary["comparison"] = {
                    "status": "paired" if verdict["comparison_checked"] else "unverified",
                    **verdict, "detail": detail,
                }
            except (OSError, ValueError, KeyError) as exc:
                summary["comparison"] = {
                    "status": "unverified", **comparison_business_status({}), "reason": str(exc)[:250],
                }
    if args.goal_only:
        summary["prompt_mode"] = "goal_only"
    if args.probe_mix_waits:
        summary["mix_wait_probe"] = True
    if plan is not None:
        summary.update(model=plan["model"], plan_matches=plan_matches)
    if args.probe_mix_boot:
        summary["mix_boot_probe"] = True
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if code == 0 and result.get("verified_pass") is True and plan_matches is not False and business_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
