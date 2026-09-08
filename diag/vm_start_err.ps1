try {
  Start-VM -Name win11-test -ErrorAction Stop
  'START-OK'
} catch {
  'START-ERR: ' + $_.Exception.Message
}
Get-VM win11-test | Select-Object -ExpandProperty State
Get-EventLog -LogName 'Microsoft-Windows-Hyper-V-VMMS-Admin' -Newest 5 -ErrorAction SilentlyContinue |
  ForEach-Object { $_.TimeCreated.ToString('HH:mm:ss') + ' ' + $_.EntryType + ' ' + $_.Message.Substring(0, [Math]::Min(120, $_.Message.Length)) }
