# hv_go.ps1 — ONE-CLICK suite runner (HOST, elevated — run in admin window or via relay).
# Usage:
#   & runner\hv_go.ps1              # full 35-case suite
#   & runner\hv_go.ps1 m3j_mixing_entry m3k_mixing_match   # subset
# Cold start safe: powers the VM on if off, waits for autologon, then launches.
# Ported from C:\coil\vm_setup\hv_go.ps1 (un-versioned); parameters now come
# from runner\_common.ps1 (env-overridable).
param([string[]]$Cases = @(
  'm3j_mixing_entry','m3k_mixing_match','m3l_mixing_delta','m3m_mixing_filaments','m3n_mixing_cancel',
  'm3o_mixing_nomodel','m3p_mixing_persist','m3q_mixing_view','m3r_mixing_progress','m3s_mixing_hover',
  'm3t_mixing_add_ratio','m3u_mixing_ratio_flow','m3v_mixing_cycle_input','m3w_mixing_cycle_flow',
  'm3x_mixing_match','m3y_mixing_gradient','m3z_mixing_compat','m4a_mixing_gates','m4b_batch_manual',
  'm4c_mixing_panel','m4d_mixing_filops','m4e_mixing_paint','m4f_mixing_cap64','m4g_mixing_sublayer',
  'm4h_mixing_templates','m4i_mixing_slice','m4j_mixing_samecolor',
  'm5a_preset_cycle','m5b_quality_params','m5c_strength_infill','m5d_support_enable',
  'm5e_combo_params','m5f_negative_params','m5g_preset_manage','m5h_ironing_combos'))
. (Join-Path $PSScriptRoot '_common.ps1')

# 1) power on if needed
$v = Get-VM $vm
if ($v.State -ne 'Running') {
  Write-Host "[1] VM is $($v.State) — starting..."
  Start-VM $vm
} else { Write-Host "[1] VM already running" }

# 2) wait for guest + autologon (up to 6 min)
Write-Host "[2] waiting for guest autologon..."
$deadline = (Get-Date).AddMinutes(6)
do {
  Start-Sleep 15
  $q = Invoke-Command -VMName $vm -Credential $cred -ScriptBlock { (quser 2>&1 | Out-String).Trim() } -ErrorAction SilentlyContinue
} while (-not ($q -match $guestUser) -and (Get-Date) -lt $deadline)
if ($q -notmatch $guestUser) { throw "guest not logged on after 6 min (autologon broken?)" }
Write-Host "    logged on."

# 3) push runner + launch INTERACTIVE task
Write-Host "[3] launching suite: $($Cases.Count) cases"
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  param($cases, $sb, $py)
  $list = ($cases | ForEach-Object { "'$_'" }) -join ','
  $runner = @"
`$cases = @($list)
`$sb = '$sb'
Set-Location `$sb
Remove-Item C:\coil\regress_progress.txt,C:\coil\regress_summary.txt -ErrorAction SilentlyContinue
`$pass=0; `$fail=0; `$failed=@()
foreach (`$c in `$cases) {
  "=== `$c ===" | Add-Content C:\coil\regress_progress.txt
  `$env:PYTHONIOENCODING='utf-8'
  & "$py" "`$c.py" > "artifacts\regress_`$c.log" 2>&1
  if (`$LASTEXITCODE -eq 0) { `$pass++; "`$c GREEN" | Add-Content C:\coil\regress_progress.txt }
  else { `$fail++; `$failed += `$c; "`$c RED rc=`$LASTEXITCODE" | Add-Content C:\coil\regress_progress.txt }
}
"SUMMARY: PASS=`$pass FAIL=`$fail" | Set-Content C:\coil\regress_summary.txt
if (`$failed) { "FAILED: `$(`$failed -join ' ')" | Add-Content C:\coil\regress_summary.txt }
"@
  [IO.File]::WriteAllText('C:\coil\run_suite.ps1', $runner)
  Unregister-ScheduledTask -TaskName suite -Confirm:$false -ErrorAction SilentlyContinue
  $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\coil\run_suite.ps1"
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  $p = New-ScheduledTaskPrincipal -GroupId "INTERACTIVE"
  Register-ScheduledTask -TaskName "suite" -Action $a -Settings $st -Principal $p -Force | Out-Null
  Start-ScheduledTask -TaskName "suite"
  "suite launched: " + (Get-ScheduledTask suite).State
} -ArgumentList (,$Cases), $guestSandbox, $guestPython
Write-Host "[4] DONE. Poll progress any time (admin window):"
Write-Host "    Get-Content C:\coil\vm_setup\poll_rerun.txt | Set-Content C:\coil\vm_setup\relay_cmd.txt   # via relay"
Write-Host "    or in guest: Get-Content C:\coil\regress_progress.txt -Tail 5"
