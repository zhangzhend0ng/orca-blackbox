#!/usr/bin/env python3
"""push_verify.py <localFile> <guestPath> — push a file into the guest AND
verify it byte-for-byte, in one step. Exit 0 only on MD5 match.

WHY (measured 09-01): send_to_guest.ps1 can silently deliver nothing or a
stale version (bash quoting turning $var into a literal, races over
relay_cmd.txt, relay-pickup timing), and a stale push masquerades as "the
fix didn't work" for hours. Always verify.

Ported from C:\\coil\\vm_setup\\push_verify.py (un-versioned). Guest/relay
parameters come from env (see runner/_common.ps1 for the full list):
ORCA_BB_VM_SETUP, ORCA_BB_VM, ORCA_BB_GUEST_USER, ORCA_BB_GUEST_PASS."""
import hashlib
import os
import subprocess
import sys
import time

VM_SETUP = os.environ.get("ORCA_BB_VM_SETUP", r"C:\coil\vm_setup")
GUEST_VM = os.environ.get("ORCA_BB_VM", "win11-test")
GUEST_USER = os.environ.get("ORCA_BB_GUEST_USER", "test")
GUEST_PASS = os.environ.get("ORCA_BB_GUEST_PASS", "123456")
RELAY_CMD = os.path.join(VM_SETUP, "relay_cmd.txt")
RELAY_OUT = os.path.join(VM_SETUP, "relay_out.txt")
CRED = (f'New-Object System.Management.Automation.PSCredential("{GUEST_USER}",'
        f'(ConvertTo-SecureString "{GUEST_PASS}" -AsPlainText -Force))')


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def relay_transact(cmd, timeout_s=180):
    """Send a command through the relay; return its output section. Waits
    for (a) the OUT header to CHANGE from the pre-send one, (b) a DONE
    marker, (c) a stable size — the DONE marker alone races with the
    previous command's leftover output."""
    try:
        with open(RELAY_OUT, "r", errors="replace") as f:
            prev_header = f.readline().strip()
    except OSError:
        prev_header = ""
    with open(RELAY_CMD, "w") as f:
        f.write(cmd)
    t0 = time.time()
    last, stable = -1, 0
    raw = ""
    while time.time() - t0 < timeout_s:
        time.sleep(1.0)
        try:
            with open(RELAY_OUT, "r", errors="replace") as f:
                header = f.readline().strip()
                raw = f.read()
        except OSError:
            continue
        if header == prev_header or "=== RUN" not in header:
            continue
        if "=== DONE" not in raw:
            continue
        if len(raw) == last:
            stable += 1
            if stable >= 1:
                return raw
        else:
            stable, last = 0, len(raw)
    raise TimeoutError(f"relay timeout after {timeout_s}s")


def main():
    local, guest = sys.argv[1], sys.argv[2]
    local_md5 = md5_of(local)

    # 1) push (send_to_guest builds the base64 relay command itself)
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy",
                        "Bypass", "-File",
                        os.path.join(VM_SETUP, "send_to_guest.ps1"),
                        local, guest],
                       capture_output=True, text=True)
    if p.returncode != 0:
        print("push spawn failed:", p.stderr[:300])
        return 1
    # wait until the relay CONSUMES the queued push command (it deletes
    # relay_cmd.txt on pickup) — otherwise the verify transaction below
    # overwrites the queued push and it is silently lost (measured 09-01)
    for _ in range(60):
        if not os.path.exists(RELAY_CMD):
            break
        time.sleep(0.2)
    time.sleep(2.0)  # give the push command time to finish executing

    # 2) verify: ask the guest for the file's MD5
    verify = (CRED + f'; Invoke-Command -VMName {GUEST_VM} -Credential $cred '
              '-ScriptBlock { (Get-FileHash "' + guest +
              '" -Algorithm MD5).Hash }')
    raw = relay_transact(verify, timeout_s=90)
    hashes = [ln.strip() for ln in raw.splitlines()
              if len(ln.strip()) == 32 and
              all(ch in "0123456789abcdefABCDEF" for ch in ln.strip())]
    if not hashes:
        print("VERIFY FAILED: no hash in relay output")
        return 1
    guest_md5 = hashes[0].lower()
    local_md5_l = local_md5.lower()
    ok = guest_md5 == local_md5_l
    print(f"local  {local_md5_l}\nguest  {guest_md5}\n"
          f"{'MATCH' if ok else 'MISMATCH'}  {local}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
