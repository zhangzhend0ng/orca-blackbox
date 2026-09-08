$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
$r = Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  Get-Content C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
}
Write-Output ("RESULT:" + ($r -join '; '))
Write-Output ("ERR:" + $Error[0])
