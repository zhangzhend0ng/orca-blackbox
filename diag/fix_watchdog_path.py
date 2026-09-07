# -*- coding: utf-8 -*-
"""one-shot: repair the watchdog path bytes (VT strip + missing backslash-v)."""

p = r'C:\coil\Projects\orca-blackbox\runner\relay_watchdog.ps1'
data = open(p, 'rb').read()
i = data.find(b'wedgeFlag')
seg = data[i:i + 60]
print('BEFORE:', seg)

# normalize whatever mangled form into the correct PS path
data = data.replace(b"'C:\\coil\x0bm_setup\\wedge_recover.flag'",
                    b"'C:\\coil\\vm_setup\\wedge_recover.flag'")
data = data.replace(b"'C:\\coilm_setup\\wedge_recover.flag'",
                    b"'C:\\coil\\vm_setup\\wedge_recover.flag'")
open(p, 'wb').write(data)

data = open(p, 'rb').read()
i = data.find(b'wedgeFlag')
print('AFTER:', data[i:i + 60])
assert b'\x0b' not in data
assert b"vm_setup\\wedge_recover.flag" in data
print('REPAIR-OK')
