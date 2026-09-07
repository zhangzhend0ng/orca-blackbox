$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  taskkill /F /IM python.exe 2>&1 | Out-Null
  taskkill /F /IM snapmaker-orca.exe 2>&1 | Out-Null
  Unregister-ScheduledTask -TaskName diagtask -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item C:\coil\diag_rc.txt -Force -ErrorAction SilentlyContinue
  'GUEST-CLEAN'
}
