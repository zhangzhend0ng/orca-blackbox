# hv_go_detached.ps1 [hv_go args] — spawn hv_go.ps1 as a hidden child
# (stdout/stderr -> artifacts\hv_go_detached*.log) and return immediately.
#
# WHY THIS EXISTS: the relay daemon executes commands with Invoke-Expression,
# so a launch transaction that wedges in a PS Direct teardown (measured
# 09-02 night: daemon silent for hours) takes the whole control channel down
# with it. Detaching puts the PS Direct session in a throwaway child process
# and frees the daemon in ~2s.
#
# Relay-safe BY CONSTRUCTION: no exit/return statements — the daemon runs
# command strings via Invoke-Expression in its own runspace, and script-
# termination keywords there would kill the daemon itself. Never add one.
#
# Usage:
#   & runner\hv_go_detached.ps1                    # full suite (guest reads cases.py)
#   & runner\hv_go_detached.ps1 -Cases m3o_mixing_nomodel
#   & runner\hv_go_detached.ps1 -OnlyFailed
# All args pass through verbatim to hv_go.ps1 (positional binding across
# powershell -File is handled by hv_go's $args merge).

$repo = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force (Join-Path $repo 'artifacts') | Out-Null
$out = Join-Path $repo 'artifacts\hv_go_detached.log'
$err = Join-Path $repo 'artifacts\hv_go_detached.err.log'

# one child at a time: a second launch while one is running would fight the
# guest "suite" scheduled task (Unregister/Register -Force in hv_go step 3).
$childArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', (Join-Path $PSScriptRoot 'hv_go.ps1')) + @($args)
$p = Start-Process powershell -WindowStyle Hidden -PassThru `
       -RedirectStandardOutput $out -RedirectStandardError $err `
       -ArgumentList $childArgs
"detached: pid=$($p.Id) log=$out args=[$($args -join ' ')]"
