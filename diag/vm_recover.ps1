Restart-Service vmms -Force
Start-Sleep 10
'SVC: ' + (Get-Service vmms).Status
Start-VM -Name win11-test -ErrorAction SilentlyContinue
Start-Sleep 8
'VM: ' + (Get-VM -Name win11-test).State
