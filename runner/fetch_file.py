#!/usr/bin/env python3
"""fetch_file.py <guestPath> <hostPath> — chunked, verified file pull.

fetch_mp4.py's single-shot relay read corrupted large payloads twice
(09-08: 420KB png and 76KB jpg both landed ~0.1% short — a truncated
b64 stream). This fetcher instead asks the guest to write a MIME-wrapped
base64 of the file, then pulls it in LINE RANGES via PS Direct, each
range carried as its own relay transaction (small => reliable), with a
final MD5 comparison. Slower (~1s/8KB) but byte-exact."""
import base64
import hashlib
import os
import subprocess
import sys

VM_SETUP = os.environ.get("ORCA_BB_VM_SETUP", r"C:\coil\vm_setup")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relay_run import relay_transact  # noqa: E402

CRED = ("New-Object System.Management.Automation.PSCredential('test',"
        "(ConvertTo-SecureString '123456' -AsPlainText -Force))")


def ic(cmd: str) -> str:
    inner = cmd.replace('$', '`$')  # the relay daemon Invoke-Expression's
    # the command: an unescaped $var inside the -Command "..." is expanded
    # (to empty) on the HOST before the guest ever sees it (measured 09-08)
    return (f'powershell -NoProfile -Command "Invoke-Command -VMName win11-test '
            f'-Credential ({CRED}) -ScriptBlock {{ {inner} }}"')


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main():
    guest, host = sys.argv[1], sys.argv[2]
    b64f = guest + ".b64"
    prep = ic(f"& C:\\Python311\\python.exe C:\\coil\\orca-blackbox\\diag\\guest_b64.py "
              f"'{guest}' '{b64f}'")
    out = relay_transact(prep, timeout_s=120)
    if out is None:
        print("PREP TIMEOUT"); return 1
    nlines = None
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.isdigit():
            nlines = None  # file size line — keep scanning
    # simpler: ask for the line count explicitly
    out = relay_transact(ic(f"(Get-Content '{b64f}').Count"), timeout_s=120)
    if out is None:
        print("COUNT TIMEOUT"); return 1
    nlines = int([l for l in out.splitlines() if l.strip().isdigit()][-1])
    print(f"b64 lines: {nlines}")

    lines = []
    STEP = 400
    i = 0
    while i < nlines:
        j = min(i + STEP, nlines)
        q = ic(f"$c = Get-Content '{b64f}'; $c[{i}..{j-1}] -join ''")
        out = relay_transact(q, timeout_s=120)
        if out is None:
            print(f"CHUNK TIMEOUT at {i}"); return 1
        lines.append("".join(out.split()))
        i = j
        print(f"\rchunk {i}/{nlines}", end="", flush=True)
    print()
    raw = base64.b64decode("".join(lines))
    with open(host, "wb") as f:
        f.write(raw)
    lm, gm = md5_of(host), None
    out = relay_transact(ic(f"(Get-FileHash '{guest}' -Algorithm MD5).Hash"),
                         timeout_s=120)
    if out:
        for ln in out.splitlines():
            ln = ln.strip()
            if len(ln) == 32 and all(c in "0123456789abcdefABCDEF" for c in ln):
                gm = ln.upper()
    print(f"local {lm} guest {gm} -> {'MATCH' if gm == lm else 'MISMATCH'}")
    return 0 if gm == lm else 1


if __name__ == "__main__":
    sys.exit(main())
