# zraw.ps1 <ps snippet file> — run an arbitrary guest-side script file
# (pushed via push_verify) through PS Direct and return its output.
# Ported from C:\coil\vm_setup\zraw.ps1; parameters via _common.ps1.
param([string]$GuestScript = "zprobe.ps1")
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ArgumentList $guestTools, $GuestScript -ScriptBlock {
  param($tools, $script)
  $p = "$tools\$script"
  if (Test-Path $p) { & $p } else { "MISSING $p" }
}
