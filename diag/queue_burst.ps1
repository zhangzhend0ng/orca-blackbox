# queue the burst command into the relay mailbox directly (the file IS the API)
Set-Content -Path 'C:\coil\vm_setup\relay_cmd.txt' -Value "powershell -NoProfile -ExecutionPolicy Bypass -File C:\coil\Projects\orca-blackbox\diag\guest_burst.ps1" -Encoding ASCII
Write-Output QUEUED
