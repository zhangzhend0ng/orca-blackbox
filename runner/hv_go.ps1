# hv_go.ps1 — ONE-CLICK suite runner (HOST, elevated — run in admin window or via relay).
# Usage:
#   & runner\hv_go.ps1              # full suite from cases.py registry
#   & runner\hv_go.ps1 m3j_mixing_entry m3k_mixing_match   # subset
#   & runner\hv_go.ps1 -OnlyFailed  # rerun just the last batch's failures
# Cold start safe: powers the VM on if off, waits for autologon, then launches.
# Ported from C:\coil\vm_setup\hv_go.ps1 (un-versioned); parameters now come
# from runner\_common.ps1 (env-overridable). Case list comes from cases.py —
# do NOT hardcode case names here (see docs/STRUCTURING_PLAN.md).
param([string[]]$Cases = @(), [switch]$OnlyFailed)
. (Join-Path $PSScriptRoot '_common.ps1')

# default list: cases.py registry (host python; fall back to guest layout note)
if (-not $Cases) {
  $repoRoot = Split-Path $PSScriptRoot -Parent
  $py = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $py) { $py = $guestPython }  # guest binary as last resort on the host
  $reg = & $py -c "import sys; sys.path.insert(0, r'$repoRoot'); from cases import enabled_cases; print(' '.join(enabled_cases('regression')))" 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $reg) {
    throw "cannot read cases.py registry (host python missing?) — pass -Cases explicitly"
  }
  $Cases = @($reg -split '\s+' | Where-Object { $_ })
  Write-Host "[0] registry: $($Cases.Count) regression cases from cases.py"
}
if ($OnlyFailed) {
  $ff = Join-Path (Split-Path $PSScriptRoot -Parent) 'artifacts\failed_cases.txt'
  if (Test-Path $ff) {
    $fl = @(Get-Content $ff | Where-Object { $_.Trim() })
    if ($fl.Count) { $Cases = $fl; Write-Host "[0] only-failed: $($fl.Count) cases" }
  }
}

# 1) power on if needed
$v = Get-VM $vm
if ($v.State -ne 'Running') {
  Write-Host "[1] VM is $($v.State) — starting..."
  Start-VM $vm
} else { Write-Host "[1] VM already running" }

# 2) wait for guest + autologon (up to 6 min)
Write-Host "[2] waiting for guest autologon..."
$deadline = (Get-Date).AddMinutes(6)
do {
  Start-Sleep 15
  $q = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock { (quser 2>&1 | Out-String).Trim() } -ErrorAction SilentlyContinue
} while (-not ($q -match $guestUser) -and (Get-Date) -lt $deadline)
if ($q -notmatch $guestUser) { throw "guest not logged on after 6 min (autologon broken?)" }
Write-Host "    logged on."

# 3) push runner + launch INTERACTIVE task
Write-Host "[3] launching suite: $($Cases.Count) cases"
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($cases, $sb, $py)
  $list = ($cases | ForEach-Object { "'$_'" }) -join ','
  $runner = @"
`$cases = @($list)
`$sb = '$sb'
Set-Location `$sb
Remove-Item C:\coil\regress_progress.txt,C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
`$pass=0; `$fail=0; `$failed=@()
foreach (`$c in `$cases) {
  "=== `$c ===" | Add-Content C:\coil\regress_progress.txt
  `$env:PYTHONIOENCODING='utf-8'
  & "$py" "`$c.py" > "artifacts\regress_`$c.log" 2>&1
  if (`$LASTEXITCODE -eq 0) { `$pass++; "`$c GREEN" | Add-Content C:\coil\regress_progress.txt }
  else { `$fail++; `$failed += `$c; "`$c RED rc=`$LASTEXITCODE" | Add-Content C:\coil\regress_progress.txt }
}
"SUMMARY: PASS=`$pass FAIL=`$fail" | Set-Content C:\coil\regress_summary.txt
if (`$failed) { "FAILED: `$(`$failed -join ' ')" | Add-Content C:\coil\regress_summary.txt }
"@
  [IO.File]::WriteAllText('C:\coil\run_suite.ps1', $runner)
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_suite.ps1"
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId "INTERACTIVE"
  Register-ScheduledTask -TaskName "suite" -Action $a -Settings $st -Principal $p -Force | Out-Null
  Start-ScheduledTask -TaskName "suite"
  "suite launched: " + (Get-ScheduledTask suite).State
} -ArgumentList (,$Cases), $guestSandbox, $guestPython
Write-Host "[4] DONE. Poll progress any time (admin window):"
Write-Host "    Get-Content C:\coil\vm_setup\poll_rerun.txt | Set-Content C:\coil\vm_setup\relay_cmd.txt   # via relay"
Write-Host "    or in guest: Get-Content C:\coil\regress_progress.txt -Tail 5"
