$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  foreach ($c in @('m7e_rotate45','m7f_scale120','m7g_arrange','m7j_change_filament','m7t73','m7t74')) {
    "##### $c"
    Get-Content ("C:\coil\orca-blackbox\artifacts\regress_" + $c + ".log") -Tail 14 -ErrorAction SilentlyContinue
  }
}
