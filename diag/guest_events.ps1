$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  try {
    Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational'} -MaxEvents 40 -ErrorAction Stop |
      Where-Object { $_.Message -match 'diagtask' } |
      ForEach-Object { $_.TimeCreated.ToString('HH:mm:ss') + ' id=' + $_.Id + ' ' + ($_.Message -replace "`r`n", ' ') }
  } catch { 'EVTLOG: ' + $_.Exception.Message }
}
