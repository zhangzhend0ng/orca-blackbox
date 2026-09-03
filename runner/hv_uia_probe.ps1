# hv_uia_probe.ps1 — install pywinauto on the guest, sync the guest checkout,
# then register + start the INTERACTIVE scheduled task 'uia_probe' that runs
# runner\uia_probe.py in the guest desktop session (PS Direct cannot see the
# desktop — PITFALLS_0901.md 18.7; UIA needs the interactive window station).
#
# Relay-safe BY CONSTRUCTION: no exit/return/throw — the relay daemon runs
# command strings via Invoke-Expression in its own runspace (PITFALLS_0901.md
# 18.6). Errors are reported via output; the script always ends naturally.
#
# Usage (via relay): & 'C:\coil\Projects\orca-blackbox\runner\hv_uia_probe.ps1'
# Outputs on guest: C:\coil\uia_probe_out.json / _compact.json / _report.txt
#                   C:\coil\uia_probe_task.log (stdout trace of the probe)

. (Join-Path $PSScriptRoot '_common.ps1')

Write-Host "[1] pywinauto on guest python..."
$inst = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($py)
  $out = & $py -m pip install --quiet --disable-pip-version-check pywinauto 2>&1
  "pip rc=$LASTEXITCODE last: $($out | Select-Object -Last 1)"
} -ArgumentList $guestPython
Write-Host "    $inst"

Write-Host "[2] syncing guest checkout (same gate as hv_go 2.5)..."
$sync = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($git, $sb)
  $dirty = @(& $git -C $sb status --porcelain | Where-Object { $_ -notmatch '^\?\?' })
  if ($dirty) { return "DIRTY: " + (($dirty | Select-Object -First 5) -join '; ') }
  $pull = (& $git -C $sb pull --ff-only 2>&1 | ForEach-Object { "$_" }) -join ' | '
  "PULLED: $pull HEAD: " + (& $git -C $sb log --oneline -1)
} -ArgumentList $guestGit, $guestSandbox
Write-Host "    $sync"
if ("$sync" -match 'DIRTY|fatal|error|conflict|refusing') {
  Write-Warning "guest checkout NOT synced — probe would run stale code; NOT launching. Fix the sandbox and rerun."
  # fall through without launching; report what the guest is stuck on
}
else {
  Write-Host "[3] registering + starting INTERACTIVE task 'uia_probe'..."
  $launch = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb, $py)
    $runner = @"
`$env:PYTHONIOENCODING='utf-8'
Set-Location '$sb'
& '$py' 'runner\uia_probe.py' 2>&1 | Out-File -FilePath 'C:\coil\uia_probe_task.log' -Encoding utf8
"@
    [IO.File]::WriteAllText('C:\coil\run_uia_probe.ps1', $runner)
    Unregister-ScheduledTask -TaskName uia_probe -Confirm:$false -ErrorAction SilentlyContinue
    $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_uia_probe.ps1"
    $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    $p = New-ScheduledTaskPrincipal -GroupId "INTERACTIVE"
    Register-ScheduledTask -TaskName "uia_probe" -Action $a -Settings $st -Principal $p -Force | Out-Null
    Start-ScheduledTask -TaskName "uia_probe"
    "uia_probe task: " + (Get-ScheduledTask uia_probe).State
  } -ArgumentList $guestSandbox, $guestPython
  Write-Host "    $launch"
}

Write-Host "[4] poll when done (report appears in ~2-5 min; probe caps itself at 30 min):"
Write-Host "    Get-Content C:\coil\uia_probe_report.txt / check task state: (Get-ScheduledTask uia_probe).State"
