$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  'TASK: ' + (Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue).State
  '--- PROGRESS ---'
  Get-Content C:\coil\regress_progress.txt -ErrorAction SilentlyContinue
  '--- SUMMARY ---'
  Get-Content C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
}
