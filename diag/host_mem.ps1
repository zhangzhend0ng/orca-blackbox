$os = Get-CimInstance Win32_OperatingSystem
'FREE-GB: ' + [math]::Round($os.FreePhysicalMemory/1MB, 1)
'TOTAL-GB: ' + [math]::Round($os.TotalVisibleMemorySize/1MB, 1)
'COMMIT: ' + [math]::Round(($os.TotalVirtualMemorySize - $os.FreeVirtualMemory)/1MB, 1) + ' / ' + [math]::Round($os.TotalVirtualMemorySize/1MB, 1) + ' GB'
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 |
  ForEach-Object { '{0} {1} {2}MB' -f $_.Id, $_.ProcessName, [math]::Round($_.WorkingSet64/1MB) }
