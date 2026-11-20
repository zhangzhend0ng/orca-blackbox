# Coordinator-only N3 injection. No parameters, retries, deletion, or overwrites.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = 'C:\coil\Projects\SnapmakerOrca\external\orca-blackbox'
$run = '053062a751b74a49b1911dc495a75c5d'
$hostRoot = Join-Path $repo ('artifacts\v3_host\' + $run)
$request = Join-Path $hostRoot 'fault_injection_request.json'
$ackPath = Join-Path $hostRoot 'fault_injection_ack.json'
# Local byte check: production FaultProbeModel module _once(value) wrote a temp
# request; read_bytes() returned 343 bytes ending CRLF with this SHA256.
# Windows-only raw-file binding: reconstructing JSON with LF gives a different hash.
$requestSha = '7397d53fcbcd25749b6cf54622ee3a3211fa44b0ffdfa2efd37172017f7a535e'
function SafePath([string]$path) {
  $probe = [IO.Path]::GetFullPath($path)
  while ($probe) {
    if ((Test-Path -LiteralPath $probe) -and ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'reparse_rejected' }
    $parent = [IO.Path]::GetDirectoryName($probe); if ($parent -eq $probe) { break }; $probe = $parent
  }
}
SafePath $request; SafePath $ackPath
$planPath = Join-Path $repo 'artifacts\v3_eval\layer_faults_20261116_01\plan.json'; SafePath $planPath
if ((Get-Item -LiteralPath $planPath).Length -gt 65536) { throw 'plan_size' }
$plan = [IO.File]::ReadAllText($planPath) | ConvertFrom-Json
$entry = @($plan.runs | Where-Object { $_.run_id -ceq $run })
if ($plan.batch_id -cne 'layer_faults_20261116_01' -or $plan.guest_source_head -cne 'ac0306a8697b45ffdc7264ec3929ac57dc2a1226' -or $entry.Count -ne 1 -or $entry[0].fault -cne 'export_collision' -or $entry[0].source -cne 'fault_probe_export_collision') { throw 'plan_identity' }
if ((Test-Path -LiteralPath $ackPath) -or (Test-Path -LiteralPath ($ackPath + '.pending'))) { throw 'ack_exists' }
if ((Get-Item -LiteralPath $request).Length -gt 4096 -or (Get-FileHash -LiteralPath $request -Algorithm SHA256).Hash.ToLowerInvariant() -cne $requestSha) { throw 'request_not_exact_frozen_schema' }
. (Join-Path $repo 'runner\_common.ps1')
if ($vm -cne 'win11-test') { throw 'vm_identity' }
$ack = Invoke-Command -VMName $vm -Credential $cred -ErrorAction Stop -ScriptBlock {
  param([string]$requestSha)
  $ErrorActionPreference = 'Stop'; Set-StrictMode -Version Latest
  if ($requestSha -cne '7397d53fcbcd25749b6cf54622ee3a3211fa44b0ffdfa2efd37172017f7a535e') { throw 'request_identity' }
  $run = '053062a751b74a49b1911dc495a75c5d'; $checkout = 'C:\coil\orca-blackbox-v3-r1'
  $root = Join-Path $checkout ('artifacts\v3\' + $run); $art = Join-Path $root 'artifacts'
  $contractSha = 'a84be6d0070374966f50ae053a41fe8779ed483f7863fd2055ce75ce99e81114'
  $sentinelSha = '4cf9a39ebecd994965f4a78505383bf804da98713c9e87e580e22d58a9eb1230'
  function SafePath([string]$path) {
    $probe = [IO.Path]::GetFullPath($path)
    while ($probe) {
      if ((Test-Path -LiteralPath $probe) -and ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'reparse_rejected' }
      $parent = [IO.Path]::GetDirectoryName($probe); if ($parent -eq $probe) { break }; $probe = $parent
    }
  }
  function Json([string]$path) { SafePath $path; if ((Get-Item -LiteralPath $path).Length -gt 65536) { throw 'json_size' }; [IO.File]::ReadAllText($path) | ConvertFrom-Json }
  function Once([string]$path, [byte[]]$bytes) { SafePath $path; $s = [IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None); try { $s.Write($bytes,0,$bytes.Length); $s.Flush($true) } finally { $s.Dispose() } }
  SafePath $art
  if ((Resolve-Path -LiteralPath $root).Path -cne $root) { throw 'canonical_root' }
  $gitExe = 'C:\coil\tools\mingit\cmd\git.exe'
  if (-not (Test-Path -LiteralPath $gitExe -PathType Leaf)) { throw 'guest_git_missing' }
  $head = & $gitExe -C $checkout rev-parse HEAD
  if ($LASTEXITCODE -ne 0 -or $head -cne 'ac0306a8697b45ffdc7264ec3929ac57dc2a1226') { throw 'guest_source_version' }
  $m = Json (Join-Path $root 'manifest.json'); $r = Json (Join-Path $art 'ready.json')
  $contractPath = Join-Path $root 'contract.json'; $c = Json $contractPath
  if ($m.run_id -cne $run -or $m.case_id -cne 'm3d_param_reslice' -or $m.executor -cne 'agent_mcp' -or $m.contract_sha256 -cne $contractSha) { throw 'manifest_identity' }
  if ($c.case_id -cne $m.case_id -or $c.contract_version -cne 'ai-layer-1' -or $c.executor -cne 'agent_mcp' -or (Get-FileHash -LiteralPath $contractPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $contractSha) { throw 'contract_identity' }
  if ($r.run_id -cne $run -or $r.case_id -cne $m.case_id -or $r.contract_sha256 -cne $contractSha -or $r.app_pid -isnot [int] -or $r.driver_pid -isnot [int] -or $r.app_pid -le 0 -or $r.driver_pid -le 0) { throw 'ready_identity' }
  # PSDirect checks process/file identity only; worker evidence owns GUI identity.
  $apps = @(Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId = ' + $r.app_pid) -ErrorAction Stop)
  $drivers = @(Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId = ' + $r.driver_pid) -ErrorAction Stop)
  if ($apps.Count -ne 1 -or $drivers.Count -ne 1) { throw 'process_not_live' }
  $app = $apps[0]; $driver = $drivers[0]; $profile = Join-Path $art 'profile'
  if ($app.Name -cne 'snapmaker-orca.exe' -or $driver.Name -notin @('python.exe','pythonw.exe') -or $app.ParentProcessId -ne $r.driver_pid -or $app.SessionId -eq 0 -or $app.SessionId -ne $driver.SessionId) { throw 'process_identity' }
  $datadirPattern = '(?:^|\s)--datadir\s+"?' + [regex]::Escape($profile) + '"?(?:\s|$)'
  if ([string]::IsNullOrEmpty($app.CommandLine) -or [string]::IsNullOrEmpty($driver.CommandLine) -or $app.CommandLine -notmatch $datadirPattern -or $driver.CommandLine -notmatch ('(?:^|\s)--run-id\s+' + $run + '(?:\s|$)')) { throw 'run_process_arguments' }
  $response = Json (Join-Path $art 'mailbox\response_0005.json')
  if ($response.run_id -cne $run -or $response.seq -isnot [int] -or $response.seq -ne 5 -or $response.tool -cne 'slice' -or $response.is_error -isnot [bool] -or $response.is_error -or $null -ne $response.error_code -or $response.finished -ne $false) { throw 'slice_response' }
  if ($response.observation.id -cne ($run + '_0005') -or $response.observation.window.hwnd -ne $r.hwnd -or $response.observation.window.pid -ne $r.app_pid -or $response.observation.window.dpi -ne 96) { throw 'latest_observation' }
  $target = Join-Path $art 'exports\0002.gcode'; $receipt = Join-Path $art 'fault_injection.json'
  SafePath $target; SafePath $receipt; SafePath (Join-Path $art 'exports\0001.gcode')
  if (-not (Test-Path -LiteralPath (Join-Path $art 'exports\0001.gcode') -PathType Leaf)) { throw 'baseline_export_missing' }
  foreach ($p in @($target,$receipt,(Join-Path $art 'mailbox\request_0006.json'),(Join-Path $art 'control_cancel.json'),(Join-Path $art 'process.json'),(Join-Path $root 'result.json'))) { if (Test-Path -LiteralPath $p) { throw 'run_not_awaiting_injection_or_target_exists' } }
  $bytes = [Text.Encoding]::ASCII.GetBytes("orca-v3-export-collision-v1`n")
  Once $target $bytes
  if ((Get-Item -LiteralPath $target).Length -ne 28 -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sentinelSha) { throw 'sentinel_readback' }
  $audit = [ordered]@{schema_version=1;run_id=$run;fault='export_collision';source='fault_probe_export_collision';path='exports/0002.gcode';sha256=$sentinelSha;size_bytes=28;created_new=$true;request_sha256=$requestSha;case_id='m3d_param_reslice';contract_sha256=$contractSha;observation_id=($run+'_0005');created_at_ns=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()*[long]1000000)}
  Once $receipt ([Text.Encoding]::UTF8.GetBytes(($audit | ConvertTo-Json -Compress) + "`n"))
  [pscustomobject]@{schema_version=1;run_id=$run;fault='export_collision';path='exports/0002.gcode';sha256=$sentinelSha;size_bytes=28;created_new=$true}
} -ArgumentList $requestSha
if (@($ack).Count -ne 1 -or $ack.schema_version -isnot [int] -or $ack.schema_version -ne 1 -or $ack.run_id -cne $run -or $ack.fault -cne 'export_collision' -or $ack.path -cne 'exports/0002.gcode' -or $ack.sha256 -cne '4cf9a39ebecd994965f4a78505383bf804da98713c9e87e580e22d58a9eb1230' -or $ack.size_bytes -isnot [int] -or $ack.size_bytes -ne 28 -or $ack.created_new -isnot [bool] -or -not $ack.created_new) { throw 'guest_ack_not_confirmed' }
$wire = [ordered]@{schema_version=1;run_id=$run;fault='export_collision';path='exports/0002.gcode';sha256=$ack.sha256;size_bytes=28;created_new=$true}
$pending = $ackPath + '.pending'; SafePath $pending; SafePath $ackPath
$raw = [Text.Encoding]::UTF8.GetBytes(($wire | ConvertTo-Json -Compress) + "`n")
$s = [IO.File]::Open($pending,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $s.Write($raw,0,$raw.Length); $s.Flush($true) } finally { $s.Dispose() }
[IO.File]::Move($pending,$ackPath)
Write-Output '{"status":"collision_created_and_acknowledged","ai_trial":false}'
