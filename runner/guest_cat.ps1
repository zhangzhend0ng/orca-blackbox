# guest_cat.ps1 -Path <guest path> [-Tail N] [-Total N] — relay-safe GUEST
# file reader via PS Direct (the relay daemon itself runs on the HOST; a bare
# Get-Content through relay reads host files — see guest_progress.ps1 note).
# Relay-safe BY CONSTRUCTION: no exit/return/throw.
param([Parameter(Mandatory = $true)][string]$Path, [int]$Tail = 0, [int]$Total = 0)
. (Join-Path $PSScriptRoot '_common.ps1')
$out = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($p, $tail, $total)
  if (-not (Test-Path $p)) { "MISSING: $p" }
  elseif ($tail -gt 0) { Get-Content $p -Tail $tail }
  elseif ($total -gt 0) { Get-Content $p -TotalCount $total }
  else { Get-Content $p }
} -ArgumentList $Path, $Tail, $Total
Write-Host ($out -join "`n")
