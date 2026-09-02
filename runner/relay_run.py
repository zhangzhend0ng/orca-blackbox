#!/usr/bin/env python3
"""relay_run.py '<powershell>' — send one command through the host relay
and print its output section. Encapsulates the response-parsing rules of
PITFALLS 0901 §16 (new RUN header + DONE marker + stable size), so callers
never read a stale reply. Exit 1 on timeout.

Ported from C:\\coil\\vm_setup\\relay_run.py (un-versioned). The relay dir
(host side, holds relay_cmd.txt / relay_out.txt) defaults to C:\\coil\\vm_setup
and is overridable via ORCA_BB_VM_SETUP."""
import os
import sys
import time

VM_SETUP = os.environ.get("ORCA_BB_VM_SETUP", r"C:\coil\vm_setup")
RELAY_CMD = os.path.join(VM_SETUP, "relay_cmd.txt")
RELAY_OUT = os.path.join(VM_SETUP, "relay_out.txt")


def relay_transact(cmd, timeout_s=300):
    with open(RELAY_OUT, "r", errors="replace") as f:
        prev_header = f.readline().strip()
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
                # raw already EXCLUDES the header line (readline above):
                # splitting on "\n" again would silently drop the first
                # BODY line (measured 09-02 — single-line replies read as
                # empty). Just cut at the DONE marker.
                return raw.rsplit("=== DONE", 1)[0].strip()
        else:
            stable = 0
            last = len(raw)
    return None


if __name__ == "__main__":
    out = relay_transact(" ".join(sys.argv[1:]))
    if out is None:
        print("RELAY TIMEOUT")
        sys.exit(1)
    print(out)
