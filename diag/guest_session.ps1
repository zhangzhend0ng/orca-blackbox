$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  'QUSER:'
  quser 2>&1 | Out-String
  'EXPLORER: ' + ((Get-Process explorer -ErrorAction SilentlyContinue).Count)
  'PYTHON: ' + ((Get-Process python -ErrorAction SilentlyContinue).Count)
  'DISKFREE-GB: ' + [math]::Round((Get-PSDrive C).Free/1GB,1)
  'MEMFREE-GB: ' + [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)
  'RUN_DIAG_MTIME: ' + (Get-Item C:\coil\run_diag.ps1).LastWriteTime
  'LOG_EXISTS: ' + (Test-Path C:\coil\orca-blackbox\artifacts\guest_diag_heartbeat.log)
}
