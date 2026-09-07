$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
$out = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  $lines = @()
  $lines += 'HOSTNAME: ' + $env:COMPUTERNAME
  $lines += 'SANDBOX: ' + (Test-Path C:\coil\orca-blackbox\cases.py)
  $lines += 'PY311: ' + (Test-Path C:\Python311\python.exe)
  $lines += 'EXE: ' + (Test-Path C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe)
  $lines += 'ORCA_PROC: ' + ((Get-Process snapmaker-orca -ErrorAction SilentlyContinue).Count)
  $lines += 'RELAY_ALIVE: ' + (Get-Content C:\coil\vm_setup_guest\relay_alive.txt -ErrorAction SilentlyContinue)
  if (Test-Path C:\coil\tools\mingit\cmd\git.exe) {
    $lines += 'GIT: ' + (C:\coil\tools\mingit\cmd\git.exe -C C:\coil\orca-blackbox log --oneline -1)
    $lines += 'GITDIRTY: ' + ((C:\coil\tools\mingit\cmd\git.exe -C C:\coil\orca-blackbox status --porcelain | Measure-Object -Line).Lines)
  }
  $lines -join "`n"
}
$out
