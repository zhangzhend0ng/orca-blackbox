$v = Get-VM -Name win11-test
Write-Output ('STATE: ' + $v.State)
if ($v.State -ne 'Running') {
  Start-VM -Name win11-test
  Write-OUTPUT ('STARTED: ' + (Get-VM -Name win11-test).State)
}
