# guest_run.ps1 — run ONE python script on the GUEST's interactive desktop
# (ad-hoc diag/small-batch sibling of hv_go.ps1's suite task). Host-side,
# elevated (run via the host relay). Usage:
#   powershell -File guest_run.ps1 -Script tests\m7a_boot_shutdown.py [-TimeoutS 900] [-PyArgs '--datadir X']
# Progress: polls the guest task; prints the log tail when done.
param([Parameter(Mandatory=$true)][string]$Script,
      [int]$TimeoutS = 900,
      [string]$PyArgs = '')
. (Join-Path $PSScriptRoot '_common.ps1')

$stem = [IO.Path]::GetFileNameWithoutExtension($Script)
$log = "artifacts\guest_$stem.log"

$start = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($script, $py, $sb, $log, $pyargs, $stem)
  $runner = @"
`$env:PYTHONIOENCODING='utf-8'
Set-Location '$sb'
& '$py' '$script' $pyargs 2>&1 | Out-File -FilePath '$log' -Encoding utf8
`$LASTEXITCODE | Set-Content C:\coil\diag_rc.txt
"@
  [IO.File]::WriteAllText('C:\coil\run_diag.ps1', $runner)
  Unregister-ScheduledTask -TaskName diagtask -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_diag.ps1' `
        -WorkingDirectory $sb
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
  # -Seconds TimeSpans landed as PT2M once (measured 09-08: every instance
  # killed at 2min, 0x41306), and a -Settings register ignored the limit on
  # the next run — re-assert via Set-ScheduledTask, the verified form.
  Register-ScheduledTask -TaskName diagtask -Action $a -Principal $p -Force | Out-Null
  Set-ScheduledTask -TaskName diagtask -Settings $st | Out-Null
  Remove-Item C:\coil\diag_rc.txt -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName diagtask
  'STARTED'
} -ArgumentList $Script, $guestPython, $guestSandbox, $log, $PyArgs, $stem
Write-Output "$start"

$t0 = Get-Date
do {
  Start-Sleep 20
  # PS Direct occasionally hiccups (transient) — a null reply must KEEP
  # polling, not end it (measured 09-08: one failed query exited the loop
  # while the guest task was still running).
  $q = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    @((Get-ScheduledTask -TaskName diagtask -ErrorAction SilentlyContinue).State,
      (Test-Path C:\coil\diag_rc.txt)) -join '|'
  } -ErrorAction SilentlyContinue
  if (-not $q) { continue }
  $parts = "$q".Split('|')
  Write-Output ("[{0:mm\:ss}] task={1} done={2}" -f ((Get-Date) - $t0), $parts[0], $parts[1])
  $done = $parts[1] -eq 'True'
} while (-not $done -and ((Get-Date) - $t0).TotalSeconds -lt $TimeoutS)

$tail = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($log, $sb)
  "RC: " + (Get-Content C:\coil\diag_rc.txt -ErrorAction SilentlyContinue)
  Get-Content (Join-Path $sb $log) -Tail 60 -ErrorAction SilentlyContinue
} -ArgumentList $log, $guestSandbox
$tail
