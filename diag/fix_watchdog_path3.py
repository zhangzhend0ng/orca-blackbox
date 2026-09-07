# -*- coding: utf-8 -*-
"""round-2 recovery: also kill the wedged daemon, clean the mailbox, and
let the watchdog's normal logic start a fresh relay."""

p = r'C:\coil\Projects\orca-blackbox\runner\relay_watchdog.ps1'
data = open(p, 'rb').read()

old = (b"  Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" |\r\n"
       b"    Where-Object { $_.CommandLine -match 'guest_run\\.ps1' } |\r\n"
       b"    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\r\n")
new = (b"  Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" |\r\n"
       b"    Where-Object { $_.CommandLine -match 'guest_run\\.ps1' } |\r\n"
       b"    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\r\n"
       b"  # round-2 (09-08): the daemon itself stayed wedged after the child\r\n"
       b"  # died (pipe-handle wait) - kill it too; the mailbox is cleared first\r\n"
       b"  # and the normal watchdog logic below starts a fresh daemon.\r\n"
       b"  Remove-Item 'C:\\coil\\vm_setup\\relay_cmd.txt' -Force -ErrorAction SilentlyContinue\r\n"
       b"  Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" |\r\n"
       b"    Where-Object { $_.CommandLine -match 'relay\\.ps1' } |\r\n"
       b"    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\r\n")
assert old in data, 'anchor not found'
data = data.replace(old, new)
open(p, 'wb').write(data)
print('RECOVERY-ROUND2-WRITTEN')
