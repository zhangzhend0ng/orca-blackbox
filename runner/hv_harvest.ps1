# hv_harvest.ps1 — pull the last guest batch's failed-case list into
# artifacts\failed_cases.txt, closing the only-failed loop:
#   batch -> hv_harvest.ps1 -> hv_go.ps1 -OnlyFailed
#
# Needs PS Direct (elevated) — run via the relay or an admin window:
#   & runner\hv_harvest.ps1
# Relay-safe by construction: no exit/return statements (the daemon runs
# command strings via Invoke-Expression in its own runspace).
#
# Source of truth is the guest's C:\coil\regress_summary.txt:
#   "FAILED: <name> <name> ..."  -> names written one per line
#   "SUMMARY: PASS=n FAIL=0"     -> host list cleared (no stale reruns)
#   no summary file              -> host list untouched (unknown state)
param([switch]$V3, [string]$WindowsMcpRunId = '', [switch]$NativeSave)
. (Join-Path $PSScriptRoot '_common.ps1')
if($NativeSave -and -not $WindowsMcpRunId){throw '-NativeSave requires -WindowsMcpRunId'}

$repo = Split-Path $PSScriptRoot -Parent
$artifacts = Join-Path $repo 'artifacts'
New-Item -ItemType Directory -Force $artifacts | Out-Null
$ff = Join-Path $artifacts 'failed_cases.txt'

if ($WindowsMcpRunId) {
  if ($V3 -or $WindowsMcpRunId -cnotmatch '^[0-9a-f]{32}$') { throw 'Invalid probe harvest selection' }
  $target = Join-Path $artifacts ('windows_mcp_harvest\' + $WindowsMcpRunId)
  New-Item -ItemType Directory -Force $target | Out-Null
  $remote = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb,$id,$nativeSave)
    $root=if($nativeSave){Join-Path $sb ('artifacts\v3\'+$id+'\artifacts')}else{Join-Path $sb ('artifacts\windows_mcp_runs\'+$id)}
    if($nativeSave -and !(Test-Path -LiteralPath $root)){
      $runner='C:\coil\run_suite.ps1'
      $log=Join-Path $sb 'artifacts\windows_mcp_probe.log'
      if((Test-Path -LiteralPath $runner) -and [IO.File]::ReadAllText($runner).Contains("--run-id '$id'") -and
          (Test-Path -LiteralPath $log)){
        $file=Get-Item -LiteralPath $log
        if($file.Length -le 65536 -and -not ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)){
          @{name='runner_startup_failure.log';data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($log))}
        }
      }
      return
    }
    # Never harvest the run's authentication token or config/profile files.
    $names=@('process.json','worker.json','worker.log','server.log','ready.json')
    if($nativeSave){$names=@('canvas_diagnostic.json','setup.json','control_cancel.json','process.json','proof.json','native_worker.json','native_worker.log','native_trace.ndjson','host_done.json','scope.json','server.log','ready.json','initial.png','agent_final.png','proof_final.png','projects/0001.3mf','proof/0001.3mf','exports/0001.gcode')}
    if($nativeSave){
      $names+=@('canvas_setup.json','authority_abort.json','authority_probe.json','desktop_video.json','desktop.mp4','mix_controls.ndjson',
                'fixture_suite.json','fixture_case.json','input/fixture.3mf','initial_state.3mf','resolved_plan.json',
                'initial_state/projects/0001.3mf','close_windows.json')
      $names+=@(Get-ChildItem -LiteralPath $root -Filter 'mix_controls_*.png' | Where-Object {$_.Name -cmatch '^mix_controls_(ratio|gradient)_(dialog|choices|compatible)\.png$'} | ForEach-Object Name)
      $names+=@(Get-ChildItem -LiteralPath $root -Filter 'canvas_input_*.json' | Where-Object {$_.Name -cmatch '^canvas_input_([1-9]|[1-3][0-9]|40)\.json$'} | ForEach-Object Name)
      $names+=@(Get-ChildItem -LiteralPath $root -Filter 'native_observation_*.png' | Where-Object {$_.Name -cmatch '^native_observation_([1-9]|[1-3][0-9]|40)\.png$'} | ForEach-Object Name)
      $names+=@(Get-ChildItem -LiteralPath $root -Filter 'process_readback_*.png' | Where-Object {$_.Name -cmatch '^process_readback_[0-9a-f]{64}\.png$'} | ForEach-Object Name)
    }
    $names+=@(Get-ChildItem -LiteralPath $root -Filter 'state_*.png' | Where-Object {$_.Name -cmatch '^state_[0-9]{2}_(prepare|preview)\.png$'} | ForEach-Object Name)
    foreach($name in $names) {
      $p=Join-Path $root $name
      if(Test-Path -LiteralPath $p) {
        $file=Get-Item -LiteralPath $p
        $limit=if($nativeSave){67108864}else{2000000}
        if($file.Length -gt $limit -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'probe_artifact_rejected'}
        @{name=$name;data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($p))}
      }
    }
    if($nativeSave){
      $parent=Split-Path $root -Parent
      $resultPath=Join-Path $parent 'result.json'
      $processPath=Join-Path $root 'process.json'
      if((Test-Path -LiteralPath $resultPath) -and (Test-Path -LiteralPath $processPath)){
        $r=[IO.File]::ReadAllText($resultPath)|ConvertFrom-Json
        $p=[IO.File]::ReadAllText($processPath)|ConvertFrom-Json
        if($p.run_id -ne $id -or $p.active_processes -ne 0 -or $r.cleanup_confirmed -ne $true){throw 'native_cleanup_unconfirmed'}
        $token=Join-Path $root 'token'
        if(Test-Path -LiteralPath $token){
          $item=Get-Item -LiteralPath $token -Force
          if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'token_link_rejected'}
          Remove-Item -LiteralPath $token -Force
        }
        $receipt=@{run_id=$id;active_processes=$p.active_processes;token_exists=(Test-Path -LiteralPath $token);cleanup_confirmed=$r.cleanup_confirmed}
        @{name='teardown.json';data=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($receipt|ConvertTo-Json -Compress)))}
      }
      foreach($name in @('result.json','manifest.json','contract.json')){
        $p=Join-Path (Split-Path $root -Parent) $name
        if(Test-Path -LiteralPath $p){@{name=$name;data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($p))}}
      }
    }
  } -ArgumentList $guestSandbox,$WindowsMcpRunId,([bool]$NativeSave)
  foreach($file in $remote){
    $destination=Join-Path $target $file.name
    New-Item -ItemType Directory -Force (Split-Path $destination -Parent)|Out-Null
    [IO.File]::WriteAllBytes($destination,[Convert]::FromBase64String($file.data))
  }
  "Windows-MCP probe diagnostics harvested -> $target (no GREEN/baseline update)"
}
elseif ($V3) {
  $payload = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb)
    $file = Join-Path $sb 'artifacts\v3_suite.json'
    if (Test-Path $file) { Get-Content $file -Raw -Encoding UTF8 }
  } -ArgumentList $guestSandbox
  if (-not $payload) { throw 'V3 suite result missing; no legacy result substituted' }
  $data = $payload | ConvertFrom-Json
  if ($data.schema_version -ne 1 -or $data.mode -notin @('script_shadow', 'agent_shadow') -or $data.release_eligible -ne $false) {
    throw 'Unexpected V3 suite result schema'
  }
  $payload | Set-Content (Join-Path $artifacts 'v3_suite.json') -Encoding UTF8
  'V3 SHADOW suite report harvested; legacy JUnit and failed list unchanged'
}
else {
$remote = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($sb)
  $s = if (Test-Path C:\coil\regress_summary.txt) { Get-Content C:\coil\regress_summary.txt -Raw } else { '' }
  $j = if (Test-Path (Join-Path $sb 'artifacts\junit.xml')) { Get-Content (Join-Path $sb 'artifacts\junit.xml') -Raw -Encoding UTF8 } else { '' }
  [pscustomobject]@{ summary = $s; junit = $j }
} -ArgumentList $guestSandbox
$summary = $remote.summary

$failedLine = @($summary -split "`n" | Where-Object { $_ -match '^FAILED:' })[0]
if ($failedLine) {
  $names = @(($failedLine -replace '^FAILED:\s*', '') -split '\s+' | Where-Object { $_ })
  $names | Set-Content $ff
  "harvested $($names.Count) failed case(s) -> $ff"
  $names | ForEach-Object { "  $_" }
}
elseif ($summary -match 'SUMMARY: PASS=(\d+) FAIL=0') {
  Remove-Item $ff -ErrorAction SilentlyContinue
  "no failures (PASS=$($Matches[1])) — cleared $ff"
}
else {
  "no summary on guest (mid-run or never started) — $ff left untouched"
}

if ($remote.junit) {
  $remote.junit | Set-Content (Join-Path $artifacts 'junit.xml') -Encoding UTF8
  "junit.xml pulled -> $(Join-Path $artifacts 'junit.xml')"
}
}
