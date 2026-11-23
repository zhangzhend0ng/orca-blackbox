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
param([switch]$V3, [string]$WindowsMcpRunId = '', [switch]$NativeSave, [switch]$CloudLoginProbe,
      [ValidatePattern('\A[0-9a-f]{32}\z')][string]$PerfBatchId)
. (Join-Path $PSScriptRoot '_common.ps1')
if($NativeSave -and -not $WindowsMcpRunId){throw '-NativeSave requires -WindowsMcpRunId'}
if($CloudLoginProbe -and (-not $WindowsMcpRunId -or $NativeSave)){throw 'Invalid cloud login harvest selection'}

$repo = Split-Path $PSScriptRoot -Parent
$artifacts = Join-Path $repo 'artifacts'
New-Item -ItemType Directory -Force $artifacts | Out-Null
$ff = Join-Path $artifacts 'failed_cases.txt'
$perfArtifact = '\A(?:[A-Za-z0-9_-]{1,60}__[0-9a-f]{32}\.(?:jsonl|frames\.csv|render\.bin)|showcase_[a-z_]+__[0-9a-f]{32}\.(?:mp4|video\.json))\z'

if ($PerfBatchId) {
  if ($V3 -or $WindowsMcpRunId) { throw 'Select only the perf batch for this harvest' }
  $target = Join-Path $artifacts "perf_harvest\$PerfBatchId"
  $guest = New-PSSession -VMName $vm -Credential $cred -ErrorAction Stop
  try {
    $inventory = @(Invoke-Command -Session $guest -ErrorAction Stop -ScriptBlock {
      param($sb, $id, $pattern)
      if ((Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue).State -eq 'Running') {
        throw 'Wait for the guest suite to stop before harvesting perf'
      }
      $base = Join-Path $sb 'artifacts\perf'
      $directory = Join-Path $base $id
      $manifestPath = Join-Path $directory 'batch.json'
      foreach ($path in @((Split-Path $base -Parent), $base, $directory, $manifestPath)) {
        $entry = Get-Item -LiteralPath $path -ErrorAction Stop
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Perf path is a link' }
      }
      if ($entry.PSIsContainer -or $entry.Length -gt 4096) { throw 'Invalid perf manifest' }
      $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($manifest.schema -ne 1 -or $manifest.batch_id -cne $id) { throw 'Perf batch identity mismatch' }
      Get-ChildItem -LiteralPath $directory -File |
        Where-Object { $_.Name -ceq 'batch.json' -or $_.Name -cmatch $pattern } |
        ForEach-Object {
          if ($_.Length -gt 64MB -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Unsupported perf artifact'
          }
          [pscustomobject]@{ name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
        }
    } -ArgumentList $guestSandbox, $PerfBatchId, $perfArtifact)
    if (-not ($inventory | Where-Object name -ceq 'batch.json')) { throw 'Perf batch manifest missing' }
    foreach ($directory in @($artifacts, (Split-Path $target -Parent), $target)) {
      $item = New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop
      if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Perf output is a link' }
    }
    foreach ($file in $inventory) {
      if ($file.name -cne 'batch.json' -and $file.name -cnotmatch $perfArtifact) {
        throw 'Unexpected perf artifact name'
      }
      $destination = Join-Path $target $file.name
      if (Test-Path -LiteralPath $destination) {
        $local = Get-Item -LiteralPath $destination -ErrorAction Stop
        if ($local.PSIsContainer -or ($local.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -cne $file.sha256) {
          throw "Existing perf artifact differs: $($file.name)"
        }
      } else {
        $tempFile = Join-Path $target ([guid]::NewGuid().ToString('N') + '.part')
        try {
          $stream = [IO.File]::Open($tempFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
          try {
            $offset = [long]0
            while ($offset -lt $file.bytes) {
              $length = [int][Math]::Min(192KB, $file.bytes - $offset)
              $chunk = Invoke-Command -Session $guest -ErrorAction Stop -ScriptBlock {
                param($sb, $id, $name, $offset, $length)
                $path = Join-Path $sb ("artifacts\perf\$id\" + $name)
                $entry = Get-Item -LiteralPath $path -ErrorAction Stop
                if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Perf input is a link' }
                $source = [IO.File]::OpenRead($path)
                try {
                  $source.Position = $offset
                  $buffer = New-Object byte[] $length
                  $read = $source.Read($buffer, 0, $length)
                  [Convert]::ToBase64String($buffer, 0, $read)
                } finally { $source.Dispose() }
              } -ArgumentList $guestSandbox, $PerfBatchId, $file.name, $offset, $length
              $bytes = [Convert]::FromBase64String([string]$chunk)
              if ($bytes.Length -ne $length) { throw "Incomplete perf artifact: $($file.name)" }
              $stream.Write($bytes, 0, $length)
              $offset += $length
            }
          } finally { $stream.Dispose() }
          if ((Get-FileHash -LiteralPath $tempFile -Algorithm SHA256).Hash -cne $file.sha256) {
            throw "Perf artifact hash mismatch: $($file.name)"
          }
          [IO.File]::Move($tempFile, $destination)
        } finally {
          if (Test-Path -LiteralPath $tempFile) { Remove-Item -LiteralPath $tempFile }
        }
      }
    }
    ('Perf batch {0}: {1} sample file(s) harvested -> {2}' -f $PerfBatchId, ($inventory.Count - 1), $target)
  } finally { Remove-PSSession $guest }
}
elseif ($WindowsMcpRunId) {
  if ($V3 -or $WindowsMcpRunId -cnotmatch '^[0-9a-f]{32}$') { throw 'Invalid probe harvest selection' }
  $target = Join-Path $artifacts ('windows_mcp_harvest\' + $WindowsMcpRunId)
  New-Item -ItemType Directory -Force $target | Out-Null
  $remote = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb,$id,$nativeSave,$cloudLogin)
    if ($cloudLogin) {
      $file = Join-Path $sb ('artifacts\cloud_login_runs\'+$id+'\result.json')
      if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Cloud login report missing' }
      $item = Get-Item -LiteralPath $file
      if ($item.Length -gt 65536 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Cloud login report rejected'
      }
      @{name='result.json';data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($file))}
      $report = [IO.File]::ReadAllText($file) | ConvertFrom-Json
      if ($report.mode -in @('upload_review','upload_live_video','print_live_video') -and $report.video) {
        $video = Join-Path (Split-Path $file -Parent) 'desktop.mp4'
        $item = Get-Item -LiteralPath $video -ErrorAction Stop
        if ($report.run_id -ne $id -or $item.Length -gt 20000000 -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (Get-FileHash -LiteralPath $video -Algorithm SHA256).Hash -ne $report.video.sha256) {
          throw 'Upload video rejected'
        }
        @{name='desktop.mp4';data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($video))}
      }
      if ($report.mode -in @('upload','upload_live_video','print_live_video') -and $report.gcode) {
        $name = 'orcabb' + $id.Substring(0,10) + '.gcode'
        if ($report.run_id -ne $id -or $report.gcode.name -ne $name) { throw 'Cloud G-code identity rejected' }
        $gcode = Join-Path (Split-Path $file -Parent) $name
        $item = Get-Item -LiteralPath $gcode -ErrorAction Stop
        if ($item.Length -gt 2000000 -or $item.Length -ne $report.gcode.bytes -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (Get-FileHash -LiteralPath $gcode -Algorithm SHA256).Hash -ne $report.gcode.sha256) {
          throw 'Cloud G-code content rejected'
        }
        @{name=$name;data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($gcode))}
        if ($report.send_only_page_verified -eq $true) {
          foreach ($diagnostic in @('upload-picker.png','upload-footer.png')) {
            $picker = Join-Path (Split-Path $file -Parent) $diagnostic
            if (Test-Path -LiteralPath $picker -PathType Leaf) {
              $item = Get-Item -LiteralPath $picker
              if ($item.Length -gt 1000000 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Upload diagnostic image rejected'
              }
              @{name=$diagnostic;data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($picker))}
            }
          }
        }
      }
      $image = Join-Path (Split-Path $file -Parent) 'signed_out.png'
      if (Test-Path -LiteralPath $image -PathType Leaf) {
        $item = Get-Item -LiteralPath $image
        if ($item.Length -gt 1800000 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
          throw 'Cloud login image rejected'
        }
        @{name='signed_out.png';data=[Convert]::ToBase64String([IO.File]::ReadAllBytes($image))}
      }
      return
    }
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
    if($nativeSave){$names=@('canvas_diagnostic.json','setup.json','control_cancel.json','process.json','proof.json','native_worker.json','native_worker.log','native_trace.ndjson','host_done.json','scope.json','server.log','ready.json','initial.png','agent_final.png','param_failure.png','save_failure.png','proof_final.png','projects/0001.3mf','proof/0001.3mf','exports/0001.gcode')}
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
  } -ArgumentList $guestSandbox,$WindowsMcpRunId,([bool]$NativeSave),([bool]$CloudLoginProbe)
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
