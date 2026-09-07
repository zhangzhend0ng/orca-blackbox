# -*- coding: utf-8 -*-
"""host process census: find the wedged relay chain."""
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  ForEach-Object {
    $cl = $_.CommandLine
    if ($cl -and $cl.Length -gt 150) { $cl = $cl.Substring(0, 150) }
    '{0}  {1}' -f $_.ProcessId, $cl
  }
