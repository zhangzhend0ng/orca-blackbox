# zshots.ps1 <case> — list the case's evidence frames (newest last).
# Ported from C:\coil\vm_setup\zshots.ps1; parameters via _common.ps1.
param([string]$Case = "")
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ArgumentList $Case, $guestSandbox -ScriptBlock {
  param($Case, $sb)
  $d = "$sb\artifacts\shots\$Case"
  "dir_exists=" + (Test-Path $d)
  if (Test-Path $d) {
    Get-ChildItem $d | Sort-Object Name | ForEach-Object { $_.Name + " " + $_.Length }
  }
}
