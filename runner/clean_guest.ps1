# clean_guest.ps1 — kill orphan app/python in the guest before a suite run.
# Ported from C:\coil\vm_setup\clean_guest.ps1; parameters via _common.ps1.
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  Get-Process snapmaker-orca,python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep 2
  "python left: " + (@(Get-Process python -ErrorAction SilentlyContinue).Count)
}
