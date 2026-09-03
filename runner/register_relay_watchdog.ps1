# register_relay_watchdog.ps1 — register the OrcaRelayWatchdog scheduled task.
# Idempotent (-Force re-register). MUST run elevated: a medium-integrity
# caller gets "Access is denied" from Register-ScheduledTask (measured
# 09-02 night). Two elevated routes:
#   - via the relay daemon (it already holds the elevated token):
#       & C:\coil\Projects\orca-blackbox\runner\register_relay_watchdog.ps1
#   - or an admin PowerShell window.
#
# Task shape: at this user's logon + every 15 min, run relay_watchdog.ps1 at
# RUNLEVEL HIGHEST as an interactive process. No exit/return statements —
# the relay route means Invoke-Expression in the daemon's runspace.
# MultipleInstances=IgnoreNew + the watchdog's own live-daemon check guard
# against double daemons fighting over the relay_cmd mailbox.

$ErrorActionPreference = 'Stop'

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\coil\Projects\orca-blackbox\runner\relay_watchdog.ps1'
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# logon trigger + repetition: Win11 accepts repetition on AtLogOn only via
# the property-copy trick; RepetitionDuration needs a finite span (3650 days
# is the practical "forever").
$triggerLogon.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 15) `
  -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
# a Once trigger with its own repetition starts ticking at registration and
# covers daemon death mid-session — a logon-only task reports NextRunTime=()
# until the NEXT logon, so its repetition does not help the current session
# (measured 09-03 night).
$triggerCycle = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 15) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName 'OrcaRelayWatchdog' -Action $action -Trigger $triggerLogon, $triggerCycle `
  -Principal $principal -Settings $settings -Force | Out-Null

$t = Get-ScheduledTask -TaskName 'OrcaRelayWatchdog'
"REGISTERED: OrcaRelayWatchdog state=$($t.State) runlevel=$($t.Principal.RunLevel) trigger=logon+15min"
