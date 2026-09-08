Start-VM -Name win11-test -ErrorAction SilentlyContinue
Start-Sleep 10
'VM: ' + (Get-VM -Name win11-test).State
try { Start-VM -Name win11-test -ErrorAction Stop; 'START-CALLED' } catch { 'ERR: ' + $_.Exception.Message.Substring(0,80) }
