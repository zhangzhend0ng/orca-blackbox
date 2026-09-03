# hv_blocker_check.ps1 — sync the guest checkout, then register + start the
# INTERACTIVE scheduled task 'blocker_check' that runs
# runner\blocker_sweep_check.py in the guest desktop session (window
# enumeration needs the interactive desktop — PITFALLS_0901.md 18.7).
#
# Relay-safe BY CONSTRUCTION: no exit/return/throw (18.6); progress goes to
# the pipeline as Write-Output — the daemon does NOT capture Write-Host.
#
# Usage (via relay): & 'C:\coil\Projects\orca-blackbox\runner\hv_blocker_check.ps1'
# Output on guest: C:\coil\blocker_check_task.log

. (Join-Path $PSScriptRoot '_common.ps1')

Write-Output "[1] syncing guest checkout (same gate as hv_go 2.5)..."
$sync = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($git, $sb)
  $dirty = @(& $git -C $sb status --porcelain | Where-Object { $_ -notmatch '^\?\?' })
  if ($dirty) { return "DIRTY: " + (($dirty | Select-Object -First 5) -join '; ') }
  $pull = (& $git -C $sb pull --ff-only 2>&1 | ForEach-Object { "$_" }) -join ' | '
  "PULLED: $pull HEAD: " + (& $git -C $sb log --oneline -1)
} -ArgumentList $guestGit, $guestSandbox
Write-Output "    $sync"
if ("$sync" -match 'DIRTY|fatal|error|conflict|refusing') {
  Write-Output "RESULT: guest checkout NOT synced — check would run stale code; NOT launching."
}
else {
  Write-Output "[2] registering + starting INTERACTIVE task 'blocker_check'..."
  $launch = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb, $py)
    $runner = @"
`$env:PYTHONIOENCODING='utf-8'
Set-Location '$sb'
& '$py' 'runner\blocker_sweep_check.py' 2>&1 | Out-File -FilePath 'C:\coil\blocker_check_task.log' -Encoding utf8
"@
    [IO.File]::WriteAllText('C:\coil\run_blocker_check.ps1', $runner)
    Unregister-ScheduledTask -TaskName blocker_check -Confirm:$false -ErrorAction SilentlyContinue
    $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_blocker_check.ps1"
    $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
    $p = New-ScheduledTaskPrincipal -GroupId "INTERACTIVE"
    Register-ScheduledTask -TaskName "blocker_check" -Action $a -Settings $st -Principal $p -Force | Out-Null
    Start-ScheduledTask -TaskName "blocker_check"
    "blocker_check task: " + (Get-ScheduledTask blocker_check).State
  } -ArgumentList $guestSandbox, $guestPython
  Write-Output "    $launch"
}
Write-Output "[3] poll: Get-Content C:\coil\blocker_check_task.log -Encoding UTF8 (~1 min, two synthetic-dialog phases)"
