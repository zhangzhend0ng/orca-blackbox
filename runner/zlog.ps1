# zlog.ps1 <case> — fetch tail of a case log from the guest sandbox.
# Ported from C:\coil\vm_setup\zlog.ps1; parameters via _common.ps1.
param([string]$Case = "", [int]$Tail = 60)
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ArgumentList $Case, $Tail, $guestSandbox -ScriptBlock {
  param($Case, $Tail, $sb)
  $log = "$sb\artifacts\regress_$Case.log"
  "log_exists=" + (Test-Path $log)
  if (Test-Path $log) {
    "log_size=" + (Get-Item $log).Length
    Get-Content $log -Tail $Tail
  }
}
