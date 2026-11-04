# hv_go.ps1 — ONE-CLICK suite runner (HOST, elevated — run in admin window or via relay).
# Usage:
#   & runner\hv_go.ps1              # full suite from cases.py registry
#   & runner\hv_go.ps1 m3j_mixing_entry m3k_mixing_match   # subset
#   & runner\hv_go.ps1 -OnlyFailed  # rerun just the last batch's failures
# Cold start safe: powers the VM on if off, waits for autologon, then launches.
# Ported from C:\coil\vm_setup\hv_go.ps1 (un-versioned); parameters now come
# from runner\_common.ps1 (env-overridable). Case list comes from cases.py —
# do NOT hardcode case names here (see docs/STRUCTURING_PLAN.md).
param([string[]]$Cases = @(), [switch]$OnlyFailed, [switch]$NoWarmup, [switch]$Warmup, [switch]$NoSync, [string]$Suite = 'regression')
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
#
# The SECOND token is the nastier half of that quirk: `-Cases A B C` binds A to
# -Cases, B to the NEXT POSITIONAL parameter (here $Suite) and C.. to $args, so
# one case name disappeared and -Suite was silently poisoned (measured 09-24:
# 33 baseline names -> "REGRESSION RUN: 32 cases", m3e_preset_switch never ran).
# Repair it: a $Suite value that is not a known suite can only be a swallowed
# case name, so push it back onto the list.
$knownSuites = @('regression', 'baseline', 'smoke', 'all')
if ($Suite -and ($knownSuites -notcontains $Suite)) {
    Write-Warning ("hv_go: -Suite got '" + $Suite + "' (not a suite name) — repairing the " +
                   "-File parameter-swallow: treating it as a case name")
    $Cases = @($Cases) + $Suite
    $Suite = 'regression'
}
$Cases = @($Cases + @($args)) | Where-Object { $_ }
$explicitCases = $PSBoundParameters.ContainsKey('Cases') -or @($args).Count -gt 0

# default list: cases.py registry (host python; fall back to guest layout note)
if (-not $Cases) {
  $repoRoot = Split-Path $PSScriptRoot -Parent
  $py = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $py) { $py = $guestPython }  # guest binary as last resort on the host
  $reg = & $py -c "import sys; sys.path.insert(0, r'$repoRoot'); from cases import enabled_cases; print(' '.join(enabled_cases('$Suite')))" 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $reg) {
    throw "cannot read cases.py registry (host python missing?) — pass -Cases explicitly"
  }
  $Cases = @($reg -split '\s+' | Where-Object { $_ })
  Write-Host "[0] registry: $($Cases.Count) $Suite cases from cases.py"
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

# Batch discipline preflight — this block IS the PITFALLS_0901.md §15
# checklist printout (README top section points here; keep in sync by hand).
Write-Host "[preflight] PITFALLS 0901 §15 checklist:"
Write-Host "   (1) relay heartbeat: relay_alive.txt fresh (it refreshes on command completion only)"
Write-Host "   (2) guest orphan sweep: relay Stop-Process snapmaker-orca,python before the batch"
Write-Host "   (3) guest interactive resolution = 1920x1080 (hv_go -Cases setres_1080 to check)"
Write-Host "   (4) no residual 'suite' scheduled-task instance ((Get-ScheduledTask suite).State)"
Write-Host "   (5) long waits go to background tasks (single bash <= 10 min); recordings/large files via base64 relay"

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

# 2.6) pin the guest's interactive resolution. A VM restart — manual, or the
# self-heal path that resumes a dead session — degrades the Hyper-V console to
# 1024x768, and every pixel/OCR assertion then misreads (the calibration is
# built for 1920x1080). hv_go used to only PRINT a "should be 1920x1080"
# reminder, so a post-restart batch ran blind (measured 09-24: this bit us
# twice, once as a full wasted run). Pin it in the INTERACTIVE session and
# verify by reading the resolution back, refusing to launch on failure.
$res = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  (Get-CimInstance Win32_VideoController | Select-Object -First 1).CurrentHorizontalResolution
} -ErrorAction SilentlyContinue
if ("$res" -notmatch '^1920') {
  Write-Host "[2.6] guest resolution is '$res' — pinning 1920x1080 in the interactive session..."
  $pin = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($sb, $py)
    $inner = @"
Set-Location $sb
& '$py' $sb\setres_1080.py *>> C:\coil\setres_out.txt
"@
    [IO.File]::WriteAllText('C:\coil\run_setres.ps1', $inner)
    $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_setres.ps1'
    $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
    Register-ScheduledTask -TaskName 'setres' -Action $a -Settings $st -Principal $p -Force | Out-Null
    Start-ScheduledTask -TaskName 'setres'
    Start-Sleep -Seconds 30
    'width=' + (Get-CimInstance Win32_VideoController | Select-Object -First 1).CurrentHorizontalResolution
  } -ArgumentList $guestSandbox, $guestPython
  Write-Host "    $pin"
  if ("$pin" -notmatch 'width=1920') {
    throw "guest resolution pin failed ($pin) — refusing to launch a batch whose pixel assertions would misread"
  }
}
else { Write-Host "[2.6] guest resolution ok ($res)" }

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
  param($caseStr, $sb, $py, $warmup, $suite)
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
  & "$py" (Case-File `$(`$cases[0])) 2>&1 | Out-File -FilePath "artifacts\regress_`$(`$cases[0]).log.warmup" -Encoding utf8
}
"@
  }
  $runner = @"
if (`$args) { `$cases = @((`$args -join ' ') -split '\s+' | Where-Object { `$_ }) }
else {
  `$reg = & '$py' -c "import sys; sys.path.insert(0, r'$sb'); from cases import enabled_cases; print(' '.join(enabled_cases('$suite')))"
  if (-not `$reg) { 'REGISTRY_READ_FAILED' | Set-Content C:\coil\regress_summary.txt; exit 1 }
  `$cases = @(`$reg -split '\s+' | Where-Object { `$_ })
}
"REGRESSION RUN: `$(`$cases.Count) cases" | Set-Content C:\coil\regress_progress.txt
`$sb = '$sb'
Set-Location `$sb
New-Item -ItemType Directory -Force artifacts | Out-Null
Remove-Item C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
# Case scripts live under tests/<group>/ keyed by the Feishu baseline table's
# 二级分类, so the path comes from the registry (cases.py) instead of a hardcoded
# "tests\<case>.py".
function Case-File(`$c) {
  `$rel = & '$py' -c "import sys; sys.path.insert(0, r'$sb'); from cases import CASES; print(CASES[r'`$c']['file'])"
  if (-not `$rel) {
    # Fail LOUDLY: a silent fallback to the flat tests\<case>.py path makes a
    # broken registry look like "every case suddenly broke" (measured 09-21).
    "REGISTRY_READ_FAILED: no file for `$c" | Set-Content C:\coil\regress_summary.txt
    exit 1
  }
  return (Join-Path `$sb (`$rel -replace '/', '\'))
}
$warmupCode
`$pass=0; `$fail=0; `$failed=@(); `$batch=''
foreach (`$c in `$cases) {
  "=== `$c ===" | Add-Content C:\coil\regress_progress.txt
  `$env:PYTHONIOENCODING='utf-8'
  # PS 5.1 '>' writes UTF-16LE — junit_report reads UTF-8; route through
  # Out-File -Encoding utf8 or the emitter embeds mojibake (measured 09-03).
  & "$py" (Case-File `$c) 2>&1 | Out-File -FilePath "artifacts\regress_`$c.log" -Encoding utf8
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
} -ArgumentList $guestCaseStr, $guestSandbox, $guestPython, $warmup, $Suite
Write-Host "[4] DONE. Poll progress any time (admin window):"
Write-Host "    Get-Content C:\coil\vm_setup\poll_rerun.txt | Set-Content C:\coil\vm_setup\relay_cmd.txt   # via relay"
Write-Host "    or in guest: Get-Content C:\coil\regress_progress.txt -Tail 5"

# After-batch closeout reminders (README top section — batch discipline).
# hv_go only LAUNCHES the batch (it runs for hours on the guest); these
# lines fire at launch time so the closeout steps are not forgotten later.
Write-Host "[5] after-batch closeout (batch discipline, README top section):"
if ($aheadCount -gt 0) { Write-Warning "   host is $aheadCount commit(s) ahead of origin/main — commit+push results/fixes first" }
if ($dirty) { Write-Warning "   host worktree has $($dirty.Count) uncommitted entries — stage or commit them" }
Write-Host "   (1) pull results: & runner\hv_harvest.ps1"
Write-Host "   (2) feishu writeback (GREEN only, host lark-cli): python tools\feishu_writeback.py --help"
Write-Host "   (3) status stays honest: RED may be committed, never relabeled GREEN"
