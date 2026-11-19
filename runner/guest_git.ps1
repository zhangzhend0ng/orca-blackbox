# guest_git.ps1 -Branch <name> — switch the guest sandbox checkout to a
# branch (fetch + checkout -B tracking origin/<branch>) via PS Direct, from
# the relay daemon's elevated host context. Records the previous branch to
# the guest's C:\coil\git_branch_prev.txt so a later run can restore it.
#
# Relay-safe BY CONSTRUCTION: no exit/return/throw — the relay daemon runs
# command strings via Invoke-Expression in its own runspace (PITFALLS_0901.md
# 18.6); script-termination keywords there would kill the daemon. Errors are
# reported via output; the script always ends naturally.
#
# Usage (via relay): & '<repo>\runner\guest_git.ps1' -Branch glm
param([Parameter(Mandatory = $true)][string]$Branch)
. (Join-Path $PSScriptRoot '_common.ps1')
$out = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($git, $sb, $branch)
  $cur = & $git -C $sb rev-parse --abbrev-ref HEAD 2>&1
  if ($LASTEXITCODE -ne 0) { "GIT_ERR rev-parse: $($cur -join ' ')" }
  else {
    [IO.File]::WriteAllText('C:\coil\git_branch_prev.txt', "$cur")
    $dirty = @(& $git -C $sb status --porcelain | Where-Object { $_ -notmatch '^\?\?' })
    if ($dirty) { "DIRTY: " + (($dirty | Select-Object -First 5) -join '; ') }
    else {
      $fetch = & $git -C $sb fetch origin 2>&1
      if ($LASTEXITCODE -ne 0) { "GIT_ERR fetch: $($fetch -join ' ')" }
      else {
        $co = & $git -C $sb checkout -B $branch "origin/$branch" 2>&1
        if ($LASTEXITCODE -ne 0) { "GIT_ERR checkout: $($co -join ' ')" }
        else {
          $head = & $git -C $sb log --oneline -1
          "SWITCH_OK prev=$cur HEAD: $head"
        }
      }
    }
  }
} -ArgumentList $guestGit, $guestSandbox, $Branch
Write-Host $out
