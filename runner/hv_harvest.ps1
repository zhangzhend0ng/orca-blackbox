# hv_harvest.ps1 — pull the last guest batch's failed-case list into
# artifacts\failed_cases.txt, closing the only-failed loop:
#   batch -> hv_harvest.ps1 -> hv_go.ps1 -OnlyFailed
#
# Needs PS Direct (elevated) — run via the relay or an admin window:
#   & runner\hv_harvest.ps1
# Relay-safe by construction: no exit/return statements (the daemon runs
# command strings via Invoke-Expression in its own runspace).
#
# Source of truth is the guest's C:\coil\regress_summary.txt:
#   "FAILED: <name> <name> ..."  -> names written one per line
#   "SUMMARY: PASS=n FAIL=0"     -> host list cleared (no stale reruns)
#   no summary file              -> host list untouched (unknown state)
param([switch]$V3)
. (Join-Path $PSScriptRoot '_common.ps1')

$repo = Split-Path $PSScriptRoot -Parent
$artifacts = Join-Path $repo 'artifacts'
New-Item -ItemType Directory -Force $artifacts | Out-Null
$ff = Join-Path $artifacts 'failed_cases.txt'

if ($V3) {
  $payload = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb)
    $file = Join-Path $sb 'artifacts\v3_suite.json'
    if (Test-Path $file) { Get-Content $file -Raw -Encoding UTF8 }
  } -ArgumentList $guestSandbox
  if (-not $payload) { throw 'V3 suite result missing; no legacy result substituted' }
  $data = $payload | ConvertFrom-Json
  if ($data.schema_version -ne 1 -or $data.mode -notin @('script_shadow', 'agent_shadow') -or $data.release_eligible -ne $false) {
    throw 'Unexpected V3 suite result schema'
  }
  $payload | Set-Content (Join-Path $artifacts 'v3_suite.json') -Encoding UTF8
  'V3 SHADOW suite report harvested; legacy JUnit and failed list unchanged'
}
else {
$remote = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($sb)
  $s = if (Test-Path C:\coil\regress_summary.txt) { Get-Content C:\coil\regress_summary.txt -Raw } else { '' }
  $j = if (Test-Path (Join-Path $sb 'artifacts\junit.xml')) { Get-Content (Join-Path $sb 'artifacts\junit.xml') -Raw -Encoding UTF8 } else { '' }
  [pscustomobject]@{ summary = $s; junit = $j }
} -ArgumentList $guestSandbox
$summary = $remote.summary

$failedLine = @($summary -split "`n" | Where-Object { $_ -match '^FAILED:' })[0]
if ($failedLine) {
  $names = @(($failedLine -replace '^FAILED:\s*', '') -split '\s+' | Where-Object { $_ })
  $names | Set-Content $ff
  "harvested $($names.Count) failed case(s) -> $ff"
  $names | ForEach-Object { "  $_" }
}
elseif ($summary -match 'SUMMARY: PASS=(\d+) FAIL=0') {
  Remove-Item $ff -ErrorAction SilentlyContinue
  "no failures (PASS=$($Matches[1])) — cleared $ff"
}
else {
  "no summary on guest (mid-run or never started) — $ff left untouched"
}

if ($remote.junit) {
  $remote.junit | Set-Content (Join-Path $artifacts 'junit.xml') -Encoding UTF8
  "junit.xml pulled -> $(Join-Path $artifacts 'junit.xml')"
}
}
