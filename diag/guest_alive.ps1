$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
try {
  $r = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock { 'ALIVE ' + (Get-Date -Format T) } -ErrorAction Stop
  Write-Output $r
} catch {
  Write-Output ('DEAD: ' + $_.Exception.Message)
}
