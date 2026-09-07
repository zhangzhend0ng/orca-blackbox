$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  'TASK: ' + (Get-ScheduledTask -TaskName diagtask -ErrorAction SilentlyContinue).State
  'TASKINFO: ' + (Get-ScheduledTaskInfo -TaskName diagtask -ErrorAction SilentlyContinue | ForEach-Object { $_.LastTaskResult.ToString() + ' ' + $_.LastRunTime })
  'RUNDIAG: ' + (Test-Path C:\coil\run_diag.ps1)
  Get-Content C:\coil\run_diag.ps1 -ErrorAction SilentlyContinue
  'PYPROC: ' + ((Get-Process python -ErrorAction SilentlyContinue).Count)
  'ORCAPROC: ' + ((Get-Process snapmaker-orca -ErrorAction SilentlyContinue).Count)
  'LOGSZ: ' + (Get-Item C:\coil\orca-blackbox\artifacts\guest_diag_m7_probe.log -ErrorAction SilentlyContinue).Length
  Get-Content C:\coil\orca-blackbox\artifacts\guest_diag_m7_probe.log -Tail 15 -ErrorAction SilentlyContinue
}
