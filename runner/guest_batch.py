#!/usr/bin/env python3
"""guest_batch.py <case> [<case>...] — run m7 cases sequentially on the
guest's interactive desktop, collecting verdicts. Host-side driver over
guest_run.ps1's diagtask: fire, poll, fetch the log via fetch_file, grep
the verdict, move on. Results append to artifacts/guest_batch_results.txt
and per-case logs to artifacts/batch_<case>.log."""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "runner"))
from relay_run import relay_transact  # noqa: E402
from fetch_file import ic  # noqa: E402

GRUN = r"C:\coil\Projects\orca-blackbox\runner\guest_run.ps1"
RESULTS = HERE / "artifacts" / "guest_batch_results.txt"
GUEST_LOG = "C:/coil/orca-blackbox/artifacts/guest_{stem}.log"
HOST_LOG = HERE / "artifacts" / "batch_{stem}.log"
GRUN_OUT = r"C:\coil\vm_setup\grun_out.txt"
GRUN_ERR = r"C:\coil\vm_setup\grun_err.txt"


def fire(case: str, timeout_s: int):
    cmd = (f"Start-Process powershell -ArgumentList '-NoProfile "
           f"-ExecutionPolicy Bypass -File {GRUN} -Script tests\\{case}.py "
           f"-TimeoutS {timeout_s}' -RedirectStandardOutput {GRUN_OUT} "
           f"-RedirectStandardError {GRUN_ERR} -WindowStyle Hidden")
    out = relay_transact(cmd + "; Write-Output FIRED", timeout_s=90)
    return out is not None and "FIRED" in out


def wait_done(timeout_s: int) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s + 240:
        time.sleep(30)
        out = relay_transact(ic("Test-Path C:\\coil\\diag_rc.txt"), 60)
        if out and "True" in out:
            time.sleep(5)
            relay_transact(ic("Remove-Item C:\\coil\\diag_rc.txt -Force"), 60)
            return True
    return False


def run_one(case: str, timeout_s: int) -> str:
    if not fire(case, timeout_s):
        return "FIRE-FAILED"
    if not wait_done(timeout_s):
        return "POLL-TIMEOUT"
    guest = GUEST_LOG.format(stem=case)
    host = HERE / "artifacts" / f"batch_{case}.log"
    subprocess.run([sys.executable, str(HERE / "runner" / "fetch_file.py"),
                    guest, str(host)], capture_output=True)
    text = host.read_text(encoding="utf-8", errors="replace") \
        if host.exists() else ""
    tail = text[-400:]
    if "[m7] GREEN" in text:
        return "GREEN"
    if "[m7] RED" in text:
        return f"RED | ...{tail}"
    return f"NO-VERDICT | ...{tail}"


def main():
    cases = sys.argv[1:]
    RESULTS.parent.mkdir(exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as rf:
        rf.write(f"=== batch {time.strftime('%m-%d %H:%M')}: "
                 f"{' '.join(cases)} ===\n")
    for case in cases:
        verdict = run_one(case, timeout_s=900)
        line = f"{case}: {verdict}"
        print(line, flush=True)
        with RESULTS.open("a", encoding="utf-8") as rf:
            rf.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
