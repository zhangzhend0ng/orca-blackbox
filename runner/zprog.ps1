# zprog.ps1 — suite progress: which case is running + greens so far.
# Ported from C:\coil\vm_setup\zprog.ps1; parameters via _common.ps1.
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
  if (Test-Path C:\coil\regress_progress.txt) {
    $lines = Get-Content C:\coil\regress_progress.txt
    $done = @($lines | Where-Object { $_ -match "GREEN|RED" })
    "done=" + $done.Count
    "last=" + ($done | Select-Object -Last 1)
    $red = @($done | Where-Object { $_ -match "RED" })
    "red=" + $red.Count + " " + ($red -join ",")
  } else { "no progress" }
}
