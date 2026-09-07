# relay_watchdog.ps1 — keep exactly one relay daemon (C:\coil\vm_setup\relay.ps1)
# alive on the host rig. Registered as the OrcaRelayWatchdog scheduled task by
# register_relay_watchdog.ps1 (logon trigger + 15-min repetition, RUNLEVEL
# HIGHEST — PS Direct needs an elevated token).
#
# --- ONE-SHOT VM RESET (09-08, flag-gated; guest remoting wedged) ----------
# Runs FIRST (before the Probe/exit below). Kill the wedged daemon, hard
# reset the guest VM, and leave a .done marker. Flag file = human consent.
$vmFlag = 'C:\coil\vm_setup\vm_reset.flag'
if (Test-Path $vmFlag) {
  Remove-Item $vmFlag -Force -ErrorAction SilentlyContinue
  Remove-Item 'C:\coil\vm_setup\relay_cmd.txt' -Force -ErrorAction SilentlyContinue
  Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -match 'relay\.ps1' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 3
  Stop-VM -Name win11-test -TurnOff -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 5
  Start-VM -Name win11-test -ErrorAction SilentlyContinue
  'VM-RESET ' + (Get-Date -Format T) |
    Set-Content 'C:\coil\vm_setup\vm_reset.done'
}
# ---------------------------------------------------------------------------
#
# Why: the relay is the only control channel to the guest, and a manual
# restart needs a console UAC click — the secure desktop does not punch
# through remote-control layers (measured 09-02 night: two auto-canceled
# prompts before a console-side approval).
#
# Deliberately NEVER kills a live-but-possibly-wedged daemon: one stuck
# inside Invoke-Expression may still have queued work on the relay_cmd
# mailbox, and auto-kill risks double execution. Wedge recovery stays manual
# (console UAC, confirm old instance gone, start fresh).
#
# Self-match safe: this script's path contains relay_watchdog.ps1, which the
# 'relay\.ps1' regex (literal "relay.ps1") cannot match.

function Probe {
  Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -match 'relay\.ps1' }
}

if (Probe) { exit 0 }
Start-Sleep -Seconds 3
if (Probe) { exit 0 }

Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
  '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'C:\coil\vm_setup\relay.ps1')
