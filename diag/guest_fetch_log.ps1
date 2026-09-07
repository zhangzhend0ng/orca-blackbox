$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  param($p)
  $raw = [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8)
  $sb = New-Object Text.StringBuilder
  foreach ($ch in $raw.ToCharArray()) { if ([int]$ch -lt 128) { [void]$sb.Append($ch) } else { [void]$sb.Append('?') } }
  $sb.ToString()
} -ArgumentList 'C:\coil\orca-blackbox\artifacts\guest_diag_m7_probe.log'
