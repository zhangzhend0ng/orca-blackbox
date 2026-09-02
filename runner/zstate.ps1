# zstate.ps1 — one-shot guest state probe (task/run_suite/progress/log).
# Ported from C:\coil\vm_setup\zstate.ps1; parameters via _common.ps1.
param([string]$Case = "")
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ArgumentList $Case, $guestSandbox -ScriptBlock {
  param($Case, $sb)
  $t = Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue
  "task_exists=" + [bool]$t
  if ($t) { "task_state=" + $t.State }
  "run_suite_exists=" + (Test-Path C:\coil\run_suite.ps1)
  "progress_exists=" + (Test-Path C:\coil\regress_progress.txt)
  if (Test-Path C:\coil\regress_progress.txt) { "progress_tail=" + (Get-Content C:\coil\regress_progress.txt -Raw).Replace("`r"," ").Replace("`n"," | ") }
  "summary_exists=" + (Test-Path C:\coil\regress_summary.txt)
  if (Test-Path C:\coil\regress_summary.txt) { "summary=" + (Get-Content C:\coil\regress_summary.txt -Raw).Trim() }
  $log = "$sb\artifacts\regress_$Case.log"
  "log_exists=" + (Test-Path $log)
  if (Test-Path $log) { "log_size=" + (Get-Item $log).Length; "log_mtime=" + (Get-Item $log).LastWriteTime }
  $py = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddHours(-2) })
  "py_recent_2h=" + $py.Count
  $orca = @(Get-Process snapmaker-orca -ErrorAction SilentlyContinue)
  "orca=" + $orca.Count
}
