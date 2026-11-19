# guest_progress.ps1 — relay-safe GUEST-side progress probe: reads the
# regression progress/summary files, the perf jsonl dir and the suite task
# state via PS Direct. The relay daemon executes commands ON THE HOST, so a
# bare "Get-Content C:\coil\..." via relay reads the HOST filesystem — this
# wrapper exists because exactly that misread happened (2026-11-20 night:
# polls came back empty while the guest task was actually running).
#
# Relay-safe BY CONSTRUCTION: no exit/return/throw.
. (Join-Path $PSScriptRoot '_common.ps1')
$out = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  $lines = @()
  $st = Get-ScheduledTask suite -ErrorAction SilentlyContinue
  $lines += 'task_state=' + $(if ($st) { $st.State } else { 'MISSING' })
  $lines += 'progress_exists=' + (Test-Path C:\coil\regress_progress.txt)
  if (Test-Path C:\coil\regress_progress.txt) {
    $lines += '--- progress tail ---'
    $lines += @(Get-Content C:\coil\regress_progress.txt | Select-Object -Last 6)
  }
  if (Test-Path C:\coil\regress_summary.txt) {
    $lines += '--- summary ---'
    $lines += @(Get-Content C:\coil\regress_summary.txt)
  }
  $perf = "$using:guestSandbox\artifacts\perf"
  $lines += '--- perf dir ---'
  if (Test-Path $perf) {
    $lines += @(Get-ChildItem $perf | ForEach-Object { $_.Name + ' ' + $_.Length + 'B' } | Select-Object -First 6)
  } else { $lines += '(missing)' }
  $lines
} 
Write-Host ($out -join "`n")
