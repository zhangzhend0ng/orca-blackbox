# Fast-forward the guest v3 checkout (C:\coil\orca-blackbox-v3-r1) to an exact
# host commit via a SHA-256-verified Git bundle over PS Direct — the same
# contract as v3_project_batch_phase.ps1's setup_bundle stage, reusable for
# ad-hoc native runs whose launch.ps1 verifies guest HEAD == host HEAD.
#
# Usage (elevated host, or through the relay):
#   .\runner\guest_v3_bundle_sync.ps1 -Head <full-sha> [-Base <full-sha>]
# Base defaults to the guest's current HEAD (bundle range Base..Head).
param([Parameter(Mandatory = $true)][string]$Head,
      [string]$Base = '')
. (Join-Path $PSScriptRoot '_common.ps1')
$bundlePath = Join-Path $env:TEMP ("orca_v3_sync_" + $Head.Substring(0, 8) + '.bundle')
if (-not $Base) {
  $Base = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($git, $sb) (& $git -C $sb rev-parse HEAD).Trim()
  } -ArgumentList $guestGit, $guestSandbox
}
$repo = Join-Path $PSScriptRoot '..'
# A raw sha range (A..<sha>) carries no ref name and git refuses it as an
# empty bundle; bundle with HEAD and verify the checkout is at -Head first.
$actualHead = (git -C $repo rev-parse HEAD).Trim()
if ($actualHead -cne $Head) { throw "repo_head_is_$actualHead" }
git -C $repo bundle create $bundlePath "$Base..HEAD"
if ($LASTEXITCODE -ne 0) { throw "bundle_create_failed ($Base..$Head)" }
$sha = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant()
$encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($bundlePath))
$out = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($sb, $git, $encoded, $sha, $head)
  # 2026-11-22: 'Stop' here turned git's harmless stderr line ("bundle is
  # okay") into a terminating NativeCommandError under PS Direct, aborting
  # the sync before fetch/merge (relay-invoked run left guest at old HEAD).
  # Every failure path below checks $LASTEXITCODE explicitly, so 'Continue'
  # is safe.
  $ErrorActionPreference = 'Continue'
  if (@(Get-ScheduledTask | Where-Object { $_.TaskName -eq 'suite' -and $_.State -eq 'Running' }).Count) { return 'DESKTOP_BUSY' }
  if (@(Get-Process snapmaker-orca -ErrorAction SilentlyContinue).Count) { return 'GUEST_APP_RUNNING' }
  $dirty = & $git -C $sb status --porcelain
  if ($dirty) { return "GUEST_DIRTY: $dirty" }
  $file = 'C:\coil\v3_sync.bundle'
  if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
  [IO.File]::WriteAllBytes($file, [Convert]::FromBase64String($encoded))
  if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sha) { return 'BUNDLE_HASH_MISMATCH' }
  & $git -C $sb bundle verify $file 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { return 'BUNDLE_VERIFY_FAILED' }
  & $git -C $sb fetch $file HEAD 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { return 'FETCH_FAILED' }
  & $git -C $sb merge --ff-only $head 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { return 'FF_FAILED' }
  $h = (& $git -C $sb rev-parse HEAD).Trim()
  if ($h -cne $head) { return "HEAD_MISMATCH: $h" }
  Remove-Item -LiteralPath $file -Force
  return "SYNC_OK: $h"
} -ArgumentList $guestSandbox, $guestGit, $encoded, $sha, $Head
Remove-Item -LiteralPath $bundlePath -Force -ErrorAction SilentlyContinue
Write-Output $out
if ("$out" -notmatch '^SYNC_OK:') { exit 1 }
