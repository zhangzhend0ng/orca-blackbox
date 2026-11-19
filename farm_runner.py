# -*- coding: utf-8 -*-
"""farm_runner.py — deterministic per-case wrapper for the multi-instance GUI farm.

Runs ONE blackbox case on ONE display-2 slot, enforces a hard timeout, kills the
whole process tree on exit, prints a machine-readable FARM_RESULT line.

Exit codes: 0=GREEN 1=RED 2=TIMEOUT 3=ERROR
Self-test:  python farm_runner.py --selftest   (no GUI involved)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = HERE / ".venv" / "Scripts" / "python.exe"
EXE = r"C:\Users\snapmaker\Documents\Snapmaker_Orca241\snapmaker-orca.exe"


def run_case(case: str, datadir: str, slot: str, timeout_s: int, log_path: Path) -> dict:
    env = dict(os.environ)
    env["ORCA_BB_ALLOW_HOST"] = "1"
    env["ORCA_VISION_APP_EXE"] = EXE
    env["ORCA_BB_CONF_EXTRA"] = json.dumps(
        {"app": {"window_mainframe": slot, "show_splash_screen": False}})
    logf = open(log_path, "w", encoding="utf-8", errors="replace")
    try:
        logf.write(f"[farm] case={case} datadir={datadir} slot={slot}\n")
        logf.flush()
        p = subprocess.Popen([str(VENV_PY), case, "--datadir", datadir], cwd=str(HERE),
                             env=env, stdout=logf, stderr=subprocess.STDOUT)
        t0 = time.time()
        timed_out = False
        while True:
            rc = p.poll()
            if rc is not None:
                break
            if time.time() - t0 > timeout_s:
                timed_out = True
                break
            time.sleep(1.0)
        if timed_out:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            verdict = "TIMEOUT"
            rc = 2
        else:
            verdict = "GREEN" if rc == 0 else "RED"
        return {"case": case, "verdict": verdict, "rc": int(rc),
                "seconds": round(time.time() - t0, 1), "log": str(log_path)}
    finally:
        logf.close()
        # belt: never leave the tree alive
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--datadir", default=None)
    ap.add_argument("--slot", default="1960; 40; 900; 500; 0")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        # fake 3-second case that prints GREEN (rc 0), via python -c
        fake = HERE / "artifacts" / "_selftest_case.py"
        fake.parent.mkdir(exist_ok=True)
        fake.write_text("import time,sys\nprint('boot');time.sleep(2)\nprint('[fake] GREEN')\nsys.exit(0)\n", encoding="utf-8")
        r = run_case(str(fake), str(HERE / "artifacts" / "_selftest_dd"),
                     a.slot, 30, HERE / "artifacts" / "_selftest.log")
        print("FARM_RESULT " + json.dumps(r, ensure_ascii=False))
        return r["rc"]

    a.datadir = os.path.abspath(a.datadir)  # ABS: cases derive export paths from datadir; relative paths wedge the native save dialog
    if not a.case or not a.datadir:
        print("FARM_RESULT " + json.dumps({"case": "?", "verdict": "ERROR", "rc": 3,
                                           "seconds": 0, "log": ""}))
        return 3

    Path(HERE / "artifacts").mkdir(exist_ok=True)
    stem = Path(a.case).stem
    ts = time.strftime("%H%M%S")
    log_path = HERE / "artifacts" / f"wf_{stem}_{ts}.log"

    r = run_case(a.case, a.datadir, a.slot, a.timeout, log_path)

    # one retry on the known transient boot failure (instant-death / no main window)
    if r["verdict"] == "RED":
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError:
            pass
        if "no stable main window" in tail or "Did not find a window" in tail:
            print("[farm] transient boot failure, retrying once", flush=True)
            time.sleep(8)
            log2 = HERE / "artifacts" / f"wf_{stem}_{ts}_retry.log"
            r = run_case(a.case, a.datadir, a.slot, a.timeout, log2)

    print("FARM_RESULT " + json.dumps(r, ensure_ascii=False))
    return r["rc"]


if __name__ == "__main__":
    sys.exit(main())
