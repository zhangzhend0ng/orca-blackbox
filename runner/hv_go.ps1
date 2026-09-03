# hv_go.ps1 — ONE-CLICK suite runner (HOST, elevated — run in admin window or via relay).
# Usage:
#   & runner\hv_go.ps1              # full suite from cases.py registry
#   & runner\hv_go.ps1 m3j_mixing_entry m3k_mixing_match   # subset
#   & runner\hv_go.ps1 -OnlyFailed  # rerun just the last batch's failures
# Cold start safe: powers the VM on if off, waits for autologon, then launches.
# Ported from C:\coil\vm_setup\hv_go.ps1 (un-versioned); parameters now come
# from runner\_common.ps1 (env-overridable). Case list comes from cases.py —
# do NOT hardcode case names here (see docs/STRUCTURING_PLAN.md).
param([string[]]$Cases = @(), [switch]$OnlyFailed, [switch]$NoWarmup, [switch]$Warmup, [switch]$NoSync)
. (Join-Path $PSScriptRoot '_common.ps1')

# Guest passthrough gate: ONLY caller-supplied selections (-Cases, -OnlyFailed)
# may go on the scheduled-task command line. A registry-derived default list
# must NOT: powershell.exe re-tokenizes "-File run_suite.ps1 <36 joined names>"
# into 36 positional args, and the guest runner's $args[0] then sees only the
# first one (measured 09-02 night run: "REGRESSION RUN: 1 cases"). Full runs
# pass nothing; the guest reads cases.py itself (single source of truth).

# powershell.exe -File binds only the FIRST positional token to
# [string[]]$Cases and leaves the rest in $args (in-session
# '& hv_go.ps1 a b c' binds all) — merge so both invocation forms
# see the full explicit list (measured 09-02 night: -File 5 names
# launched "1 cases").
$Cases = @($Cases + @($args)) | Where-Object { $_ }
$explicitCases = $PSBoundParameters.ContainsKey('Cases') -or @($args).Count -gt 0

# default list: cases.py registry (host python; fall back to guest layout note)
if (-not $Cases) {
  $repoRoot = Split-Path $PSScriptRoot -Parent
  $py = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $py) { $py = $guestPython }  # guest binary as last resort on the host
  $reg = & $py -c "import sys; sys.path.insert(0, r'$repoRoot'); from cases import enabled_cases; print(' '.join(enabled_cases('regression')))" 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $reg) {
    throw "cannot read cases.py registry (host python missing?) — pass -Cases explicitly"
  }
  $Cases = @($reg -split '\s+' | Where-Object { $_ })
  Write-Host "[0] registry: $($Cases.Count) regression cases from cases.py"
}
if ($OnlyFailed) {
  $ff = Join-Path (Split-Path $PSScriptRoot -Parent) 'artifacts\failed_cases.txt'
  if (Test-Path $ff) {
    $fl = @(Get-Content $ff | Where-Object { $_.Trim() })
    if ($fl.Count) { $Cases = $fl; $explicitCases = $true; Write-Host "[0] only-failed: $($fl.Count) cases" }
  }
}

# Cold-start warmup: after hours of guest idleness, the first GUI
# interactions of a batch lose clicks (WM_LBUTTONUP timeouts — measured
# 09-02 night: the first 5 of 36 cases RED, warm rerun 5/5 GREEN). Full
# runs therefore discard one throwaway pass of the first case before the
# real batch. Explicit subsets and -OnlyFailed reruns are warm by nature
# and skip it — computed AFTER the -OnlyFailed override so a failed-case
# rerun does not pay the throwaway pass.
$warmup = if ($Warmup) { $true } elseif ($NoWarmup) { $false } else { -not $explicitCases }

# 1) power on if needed
$v = Get-VM $vm
if ($v.State -ne 'Running') {
  Write-Host "[1] VM is $($v.State) — starting..."
  Start-VM $vm
} else { Write-Host "[1] VM already running" }

# 2) wait for guest + autologon (up to 6 min)
Write-Host "[2] waiting for guest autologon..."
$deadline = (Get-Date).AddMinutes(6)
do {
  Start-Sleep 15
  $q = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock { (quser 2>&1 | Out-String).Trim() } -ErrorAction SilentlyContinue
} while (-not ($q -match $guestUser) -and (Get-Date) -lt $deadline)
if ($q -notmatch $guestUser) { throw "guest not logged on after 6 min (autologon broken?)" }
Write-Host "    logged on."

# 2.5) sync the guest checkout — the guest tracks ORIGIN (git clone since
# 09-03), so unpushed host work never reaches it. Warn on host drift, pull
# the guest --ff-only, and refuse to launch on a dirty/diverged sandbox:
# silently running stale tests is exactly what this step exists to prevent.
Push-Location (Split-Path $PSScriptRoot -Parent)
# rev-parse does NOT do range semantics — on 'A..B' it prints BOTH endpoints
# (sha + ^sha), which once falsely reported "2 commits ahead"; rev-list counts.
$aheadCount = [int](git rev-list --count 'origin/main..HEAD' 2>$null)
# only tracked modifications count as drift — untracked files are never
# pushed and never executed (the runner's case list comes from the registry)
$dirty = @(git status --porcelain 2>$null | Where-Object { $_ -notmatch '^\?\?' })
Pop-Location
if ($aheadCount -gt 0) { Write-Warning "host is $aheadCount commit(s) ahead of origin/main — guest will NOT see them until pushed" }
if ($dirty) { Write-Warning "host worktree has $($dirty.Count) uncommitted entries — these do not reach the guest either" }
if (-not $NoSync) {
  Write-Host "[2.5] syncing guest checkout (git pull --ff-only)..."
  $sync = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($git, $sb)
    $dirty = @(& $git -C $sb status --porcelain |
      Where-Object { $_ -notmatch '^\?\?' })
    if ($dirty) { return "DIRTY: " + (($dirty | Select-Object -First 5) -join '; ') }
    $pull = (& $git -C $sb pull --ff-only 2>&1 | ForEach-Object { "$_" }) -join ' | '
    "PULLED: $pull HEAD: " + (& $git -C $sb log --oneline -1)
  } -ArgumentList $guestGit, $guestSandbox
  Write-Host "    $sync"
  if ("$sync" -match 'DIRTY|fatal|error|conflict|refusing') {
    throw "guest checkout sync failed — refusing to launch (pass -NoSync to override, e.g. deliberate bisect): $sync"
  }
}
else { Write-Host "[2.5] guest sync skipped (-NoSync)" }

# 3) push runner + launch INTERACTIVE task
# NOTE: the case LIST is computed ON THE GUEST from cases.py — passing a
# 36-element array through PS Direct collapsed it into ONE string in the
# field (measured 09-02: every case then "failed" instantly). The registry
# is the single source of truth; the guest reads it directly. Explicit
# -Cases/-OnlyFailed selections pass through (the guest runner aggregates
# ALL positional tokens, so command-line re-tokenization is safe).
Write-Host "[3] launching suite: $(if ($explicitCases) { $Cases.Count } else { 'full (guest reads cases.py)' }) cases (warmup=$warmup)"
$guestCaseStr = if ($explicitCases) { $Cases -join ' ' } else { '' }
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  # NOTE: this scriptblock runs ON THE GUEST — everything it needs must be
  # marshaled via param/-ArgumentList (host-side $warmup is not visible here;
  # measured 09-03 night: silent $false, warmup block never emitted).
  param($caseStr, $sb, $py, $warmup)
  # full run: the guest derives the list from cases.py itself (single
  # source of truth); explicit subset: split the passed string.
  # warmup fragment — the host-side decision ($warmup) must be baked into
  # the generated file HERE: run_suite.ps1 has no $warmup variable, so a
  # first cut that referenced it inside the template silently never ran.
  $warmupCode = ''
  if ($warmup) {
    $warmupCode = @"
if (`$cases.Count -gt 1) {
  "=== warmup (`$(`$cases[0]) result discarded) ===" | Add-Content C:\coil\regress_progress.txt
  & "$py" "tests\`$(`$cases[0]).py" 2>&1 | Out-File -FilePath "artifacts\regress_`$(`$cases[0]).log.warmup" -Encoding utf8
}
"@
  }
  $runner = @"
if (`$args) { `$cases = @((`$args -join ' ') -split '\s+' | Where-Object { `$_ }) }
else {
  `$reg = & '$py' -c "import sys; sys.path.insert(0, r'$sb'); from cases import enabled_cases; print(' '.join(enabled_cases('regression')))"
  if (-not `$reg) { 'REGISTRY_READ_FAILED' | Set-Content C:\coil\regress_summary.txt; exit 1 }
  `$cases = @(`$reg -split '\s+' | Where-Object { `$_ })
}
"REGRESSION RUN: `$(`$cases.Count) cases" | Set-Content C:\coil\regress_progress.txt
`$sb = '$sb'
Set-Location `$sb
New-Item -ItemType Directory -Force artifacts | Out-Null
Remove-Item C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
$warmupCode
`$pass=0; `$fail=0; `$failed=@(); `$batch=''
foreach (`$c in `$cases) {
  "=== `$c ===" | Add-Content C:\coil\regress_progress.txt
  `$env:PYTHONIOENCODING='utf-8'
  # PS 5.1 '>' writes UTF-16LE — junit_report reads UTF-8; route through
  # Out-File -Encoding utf8 or the emitter embeds mojibake (measured 09-03).
  & "$py" "tests\`$c.py" 2>&1 | Out-File -FilePath "artifacts\regress_`$c.log" -Encoding utf8
  if (`$LASTEXITCODE -eq 0) { `$pass++; "`$c GREEN" | Add-Content C:\coil\regress_progress.txt }
  else { `$fail++; `$failed += `$c; "`$c RED rc=`$LASTEXITCODE" | Add-Content C:\coil\regress_progress.txt }
  `$batch = "`$batch `$c|`$LASTEXITCODE|artifacts\regress_`$c.log"
}
"SUMMARY: PASS=`$pass FAIL=`$fail" | Set-Content C:\coil\regress_summary.txt
if (`$failed) { "FAILED: `$(`$failed -join ' ')" | Add-Content C:\coil\regress_summary.txt }
`$specs = `$batch.Split()
`$junit = & "$py" harness\junit_report.py --batch artifacts\junit.xml `$specs 2>&1
"junit: `$junit" | Add-Content C:\coil\regress_progress.txt
"@
  [IO.File]::WriteAllText('C:\coil\run_suite.ps1', $runner)
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_suite.ps1 " + $caseStr)
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId "INTERACTIVE"
  Register-ScheduledTask -TaskName "suite" -Action $a -Settings $st -Principal $p -Force | Out-Null
  Start-ScheduledTask -TaskName "suite"
  "suite launched: " + (Get-ScheduledTask suite).State
} -ArgumentList $guestCaseStr, $guestSandbox, $guestPython, $warmup
Write-Host "[4] DONE. Poll progress any time (admin window):"
Write-Host "    Get-Content C:\coil\vm_setup\poll_rerun.txt | Set-Content C:\coil\vm_setup\relay_cmd.txt   # via relay"
Write-Host "    or in guest: Get-Content C:\coil\regress_progress.txt -Tail 5"
