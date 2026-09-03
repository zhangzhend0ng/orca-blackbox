# relay_watchdog.ps1 — keep exactly one relay daemon (C:\coil\vm_setup\relay.ps1)
# alive on the host rig. Registered as the OrcaRelayWatchdog scheduled task by
# register_relay_watchdog.ps1 (logon trigger + 15-min repetition, RUNLEVEL
# HIGHEST — PS Direct needs an elevated token).
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

# A single empty probe is NOT proof of death: WMI transiently returns nothing
# under process churn (measured 09-03 night: one empty query between healthy
# ones). Require two consecutive empty probes 3s apart before starting a
# daemon — a false start here means two daemons fighting over relay_cmd.txt.
if (Probe) { exit 0 }
Start-Sleep -Seconds 3
if (Probe) { exit 0 }

Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
  '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'C:\coil\vm_setup\relay.ps1')
