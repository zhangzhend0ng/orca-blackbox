$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  Set-ScheduledTask -TaskName diagtask -Settings $st | Out-Null
  'AFTER: ' + ((Get-ScheduledTask -TaskName diagtask).Settings.ExecutionTimeLimit)
  (Export-ScheduledTask -TaskName diagtask | Select-String 'ExecutionTimeLimit').Line.Trim()
}
