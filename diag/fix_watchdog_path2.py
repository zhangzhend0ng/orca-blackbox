# -*- coding: utf-8 -*-
"""final pass: replace the VT form with the correct vm_setup path."""

p = r'C:\coil\Projects\orca-blackbox\runner\relay_watchdog.ps1'
data = open(p, 'rb').read()
data = data.replace(b"'C:\\coil\x0bm_setup\\wedge_recover.done'",
                    b"'C:\\coil\\vm_setup\\wedge_recover.done'")
open(p, 'wb').write(data)

data = open(p, 'rb').read()
assert b'\x0b' not in data, 'VT still present'
assert data.count(b'wedge_recover.done') == 1
i = data.find(b'Set-Content')
print('NOW:', data[i:i + 66])
print('CLEAN')
