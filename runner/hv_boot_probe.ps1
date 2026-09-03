# hv_boot_probe.ps1 — install nothing; sync the guest checkout, then register
# + start the INTERACTIVE scheduled task 'boot_probe' that runs
# runner\boot_probe.py in the guest desktop session (PITFALLS_0901.md 18.7:
# PS Direct cannot see the desktop; popup windows live in the interactive
# window station).
#
# Relay-safe BY CONSTRUCTION: no exit/return/throw — the relay daemon runs
# command strings via Invoke-Expression in its own runspace (PITFALLS_0901.md
# 18.6). Errors are reported via output; the script always ends naturally.
#
# Usage (via relay): & 'C:\coil\Projects\orca-blackbox\runner\hv_boot_probe.ps1'
#                    & '...\hv_boot_probe.ps1' a b c   (phase subset)
# Outputs on guest: C:\coil\boot_probe_report.txt / boot_probe_events.json
#                   C:\coil\boot_probe_task.log + shots under C:\coil\boot_probe_shots\
#
# NOTE: the probe needs NO pip installs (stdlib http.server + repo harness).

param([string[]]$Phases = @())
. (Join-Path $PSScriptRoot '_common.ps1')
$phaseStr = ($Phases + $args) -join ' '

Write-Host "[1] syncing guest checkout (same gate as hv_go 2.5)..."
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
}
else {
  Write-Host "[2] registering + starting INTERACTIVE task 'boot_probe' (phases: $phaseStr)..."
  $launch = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb, $py, $ph)
    $runner = @"
`$env:PYTHONIOENCODING='utf-8'
Set-Location '$sb'
& '$py' 'runner\boot_probe.py' $ph 2>&1 | Out-File -FilePath 'C:\coil\boot_probe_task.log' -Encoding utf8
"@
    [IO.File]::WriteAllText('C:\coil\run_boot_probe.ps1', $runner)
    Unregister-ScheduledTask -TaskName boot_probe -Confirm:$false -ErrorAction SilentlyContinue
    $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_boot_probe.ps1"
    $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 40)
    $p = New-ScheduledTaskPrincipal -GroupId "INTERACTIVE"
    Register-ScheduledTask -TaskName "boot_probe" -Action $a -Settings $st -Principal $p -Force | Out-Null
    Start-ScheduledTask -TaskName "boot_probe"
    "boot_probe task: " + (Get-ScheduledTask boot_probe).State
  } -ArgumentList $guestSandbox, $guestPython, $phaseStr
  Write-Host "    $launch"
}

Write-Host "[3] poll when done (~4 phases x ~3 min + boot overhead; task caps at 40 min):"
Write-Host "    Get-Content C:\coil\boot_probe_report.txt | Out-String"
Write-Host "    (or via relay: Get-Content C:\coil\boot_probe_report.txt / task state: (Get-ScheduledTask boot_probe).State)"
