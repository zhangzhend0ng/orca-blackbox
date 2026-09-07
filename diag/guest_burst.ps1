# guest_burst.ps1 — ONE-PS-Direct-call autonomous guest batch.
# The host's PS Direct channel wedges after a few calls (09-08), so this
# script does EVERYTHING guest-side in a single call:
#   1. git pull --ff-only (brings the round-2 case code from origin)
#   2. write C:\coil\run_m7_suite.ps1 (sequential runner, hv_go conventions)
#   3. register + start the INTERACTIVE 'suite' task
# Everything after that is autonomous on the guest; the host only reads
# C:\coil\regress_progress.txt / regress_summary.txt later.
$cred = New-Object System.Management.Automation.PSCredential('test', (ConvertTo-SecureString '123456' -AsPlainText -Force))
Invoke-Command -VMName 'win11-test' -Credential $cred -ScriptBlock {
  $git = 'C:\coil\tools\mingit\cmd\git.exe'
  $sb = 'C:\coil\orca-blackbox'
  'PULL: ' + ((& $git -C $sb pull --ff-only 2>&1 | Select-Object -Last 1))
  $py = 'C:\Python311\python.exe'
  $cases = @('m7h_context_delete',
             'm7b_new_project', 'm7e_rotate45', 'm7f_scale120',
             'm7g_arrange', 'm7i_add_primitive', 'm7j_change_filament',
             'm7t73', 'm7t74', 'm7t75', 'm7t77', 'm7t78',
             'm7t81', 'm7t82', 'm7t84', 'm7t86', 'm7t88', 'm7t89', 'm7t109')
  $caseList = $cases -join ' '
  $runner = @"
if (`$args) { `$cases = @((`$args -join ' ') -split '\s+' | Where-Object { `$_ }) }
`$env:PYTHONIOENCODING = 'utf-8'
`$sb = '$sb'
Set-Location `$sb
New-Item -ItemType Directory -Force artifacts | Out-Null
Remove-Item C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
'REGRESSION RUN: ' + `$cases.Count + ' cases' | Set-Content C:\coil\regress_progress.txt
`$pass = 0; `$fail = 0; `$failed = @()
foreach (`$c in `$cases) {
  '=== ' + `$c + ' ===' | Add-Content C:\coil\regress_progress.txt
  & '$py' ('tests\' + `$c + '.py') 2>&1 |
    Out-File -FilePath ('artifacts\regress_' + `$c + '.log') -Encoding utf8
  if (`$LASTEXITCODE -eq 0) { `$pass++; 'GREEN ' + `$c | Add-Content C:\coil\regress_progress.txt }
  else { `$fail++; 'RED ' + `$c + ' rc=' + `$LASTEXITCODE | Add-Content C:\coil\regress_progress.txt }
}
'SUMMARY: PASS=' + `$pass + ' FAIL=' + `$fail | Set-Content C:\coil\regress_summary.txt
if (`$failed) { 'FAILED: ' + (`$failed -join ' ') | Add-Content C:\coil\regress_summary.txt }
"@
  [IO.File]::WriteAllText('C:\coil\run_m7_suite.ps1', $runner)
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_m7_suite.ps1 ' + $caseList) `
        -WorkingDirectory $sb
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId 'INTERACTIVE'
  Register-ScheduledTask -TaskName suite -Action $a -Settings $st -Principal $p -Force | Out-Null
  Set-ScheduledTask -TaskName suite -Settings $st | Out-Null
  Remove-Item C:\coil\regress_progress.txt -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName suite
  'SUITE-LAUNCHED ' + (Get-ScheduledTask suite).State
}
