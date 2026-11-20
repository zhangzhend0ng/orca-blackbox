# Switch an idle guest checkout to the named origin branch without resetting
# local history. hv_go itself fetches that branch explicitly on every sync.
param([Parameter(Mandatory = $true)][string]$Branch)
. (Join-Path $PSScriptRoot '_common.ps1')
$out = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($git, $sb, $branch)
  & $git -C $sb check-ref-format --branch $branch 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { 'GIT_ERR invalid branch' }
  elseif ((Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue).State -eq 'Running') {
    'GIT_ERR suite is running'
  }
  else {
    $cur = & $git -C $sb symbolic-ref --quiet --short HEAD 2>&1
    $dirty = @(& $git -C $sb status --porcelain --untracked-files=no 2>&1)
    if ($LASTEXITCODE -ne 0) { "GIT_ERR status: $dirty" }
    elseif ($dirty.Count) { "DIRTY: $($dirty -join '; ')" }
    else {
      $fetch = & $git -C $sb fetch origin "refs/heads/$branch" 2>&1
      if ($LASTEXITCODE -ne 0) { "GIT_ERR fetch: $fetch" }
      else {
        $tip = & $git -C $sb rev-parse FETCH_HEAD
        & $git -C $sb show-ref --verify --quiet "refs/heads/$branch"
        $exists = $LASTEXITCODE -eq 0
        if ($exists) {
          & $git -C $sb merge-base --is-ancestor "refs/heads/$branch" $tip
          $safe = $LASTEXITCODE -eq 0
        } else { $safe = $true }
        if (-not $safe) { 'GIT_ERR local branch has commits absent from origin' }
        else {
          $switch = if ($exists) {
            & $git -C $sb switch $branch 2>&1
          } else {
            & $git -C $sb switch -c $branch $tip 2>&1
          }
          if ($LASTEXITCODE -ne 0) { "GIT_ERR switch: $switch" }
          else {
            $merge = & $git -C $sb merge --ff-only $tip 2>&1
            $head = & $git -C $sb rev-parse HEAD
            if ($head -cne $tip) { "GIT_ERR fast-forward: $merge" }
            else {
              [IO.File]::WriteAllText('C:\coil\git_branch_prev.txt', "$cur")
              "SWITCH_OK prev=$cur HEAD=$head"
            }
          }
        }
      }
    }
  }
} -ArgumentList $guestGit, $guestSandbox, $Branch
Write-Host $out
