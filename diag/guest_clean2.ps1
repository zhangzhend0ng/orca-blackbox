$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Write-Output 'STEP1: querying guest'
$r = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  'PY:' + (Get-Process python -ErrorAction SilentlyContinue).Count
}
Write-Output $r
Write-Output 'STEP2: killing'
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  Stop-Process -Name python -Force -ErrorAction SilentlyContinue
  Stop-Process -Name snapmaker-orca -Force -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName diagtask -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item C:\coil\diag_rc.txt -Force -ErrorAction SilentlyContinue
  'PY-AFTER:' + (Get-Process python -ErrorAction SilentlyContinue).Count
}
