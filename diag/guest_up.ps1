$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
$deadline = (Get-Date).AddMinutes(6)
do {
  Start-Sleep 15
  $q = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
    (quser 2>&1 | Out-String).Trim() + ' | PY:' + (Get-Process python -ErrorAction SilentlyContinue).Count
  } -ErrorAction SilentlyContinue
} while (-not ($q -match 'test') -and ((Get-Date) -lt $deadline))
$q
