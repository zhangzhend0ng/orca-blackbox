# zfind.ps1 <name> — find files/dirs by name under the guest datadir.
# Ported from C:\coil\vm_setup\zfind.ps1; parameters via _common.ps1.
param([string]$Name = "")
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ArgumentList $Name, $guestSandbox -ScriptBlock {
  param($Name, $sb)
  $root = "$sb\artifacts\m3_profile"
  "root subdirs:"
  Get-ChildItem $root -Directory | ForEach-Object { "  " + $_.Name }
  "matches for '$Name':"
  Get-ChildItem $root -Recurse -Filter "*$Name*" -ErrorAction SilentlyContinue | ForEach-Object { "  " + $_.FullName.Replace($root, "") + " " + $_.Length }
}
