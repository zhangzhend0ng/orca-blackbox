# -*- coding: utf-8 -*-
"""farm_runner.py — deterministic per-case wrapper for the multi-instance GUI farm.

Runs ONE blackbox case on ONE display-2 slot, enforces a hard timeout, kills the
whole process tree on exit, prints a machine-readable FARM_RESULT line.

Exit codes: 0=GREEN 1=RED 2=TIMEOUT 3=ERROR
Self-test:  python farm_runner.py --selftest   (no GUI involved)
"""
import argparse
from contextlib import contextmanager
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

from harness import perf_monitor
from harness.win32_job import OwnedJobProcess

HERE = Path(__file__).resolve().parent
VENV_PY = HERE / ".venv" / "Scripts" / "python.exe"
EXE = r"C:\Users\snapmaker\Documents\Snapmaker_Orca241\snapmaker-orca.exe"


def run_case(case: str, datadir: str, slot: str, timeout_s: int, log_path: Path,
             perf_label: str | None = None) -> dict:
    env = dict(os.environ)
    env["ORCA_BB_ALLOW_HOST"] = "1"
    env["ORCA_VISION_APP_EXE"] = EXE
    env["ORCA_BB_OWNED_PROFILE"] = "1"
    if perf_label:
        env["ORCA_BB_PERF"] = "1"
        env["ORCA_BB_PERF_LABEL"] = perf_label
    if perf_monitor.env_enabled(env):
        env["ORCA_BB_PERF_RUN_ID"] = uuid4().hex
        env["ORCA_BB_PERF_JOB"] = "1"
    env["ORCA_BB_CONF_EXTRA"] = json.dumps(
        {"app": {"window_mainframe": slot, "show_splash_screen": False}})
    python = VENV_PY if VENV_PY.is_file() else Path(sys.executable)
    print(f"[farm] case={case} datadir={datadir} slot={slot} "
          f"perf_run={env.get('ORCA_BB_PERF_RUN_ID', '-')}", flush=True)
    started = time.monotonic()
    process = OwnedJobProcess.start([str(python), case, "--datadir", datadir],
                                    cwd=HERE, env=env, log_path=log_path)
    try:
        deadline = started + timeout_s
        while time.monotonic() < deadline:
            rc, active = process.poll()
            if rc is not None and active == 0:
                break
            time.sleep(0.25)
        else:
            rc, verdict = 2, "TIMEOUT"
            return {"case": case, "verdict": verdict, "rc": rc,
                    "seconds": round(time.monotonic() - started, 1), "log": str(log_path)}
        verdict = "GREEN" if rc == 0 else "RED"
        return {"case": case, "verdict": verdict, "rc": int(rc),
                "seconds": round(time.monotonic() - started, 1), "log": str(log_path)}
    finally:
        if process.poll()[1]:
            process.terminate()
            cleanup_deadline = time.monotonic() + 5
            while process.poll()[1] and time.monotonic() < cleanup_deadline:
                time.sleep(0.1)
        process.close()


@contextmanager
def datadir_lease(datadir: str):
    import msvcrt

    path = Path(datadir).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / (path.name + ".farm.lock")
    with lock_path.open("a+b") as stream:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        # The OS releases the lock with this file handle. Keep the path so a
        # second caller can never replace a locked file with a new inode.
        yield


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--datadir", default=None)
    ap.add_argument("--slot", default="1960; 40; 900; 500; 0")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--perf", action="store_true",
                    help="enable metric sampling (harness/perf_monitor.py jsonl)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        # fake 3-second case that prints GREEN (rc 0), via python -c
        fake = HERE / "artifacts" / "_selftest_case.py"
        fake.parent.mkdir(exist_ok=True)
        fake.write_text("import time,sys\nprint('boot');time.sleep(2)\nprint('[fake] GREEN')\nsys.exit(0)\n", encoding="utf-8")
        r = run_case(str(fake), str(HERE / "artifacts" / "_selftest_dd"),
                     a.slot, 30, HERE / "artifacts" / f"_selftest_{uuid4().hex}.log")
        print("FARM_RESULT " + json.dumps(r, ensure_ascii=False))
        return r["rc"]

    if not a.case or not a.datadir:
        print("FARM_RESULT " + json.dumps({"case": "?", "verdict": "ERROR", "rc": 3,
                                           "seconds": 0, "log": ""}))
        return 3
    a.datadir = str(Path(a.datadir).resolve())  # Native save requires an absolute path.

    Path(HERE / "artifacts").mkdir(exist_ok=True)
    stem = Path(a.case).stem
    ts = uuid4().hex
    log_path = HERE / "artifacts" / f"wf_{stem}_{ts}.log"
    perf_label = (f"{stem}__slot{re.sub(r'[^0-9A-Za-z_-]+', '_', a.slot)[:20]}"
                  if a.perf else None)
    if perf_label:
        print(f"[farm] perf sampling on: label={perf_label}", flush=True)

    try:
        with datadir_lease(a.datadir):
            r = run_with_retry(a.case, a.datadir, a.slot, a.timeout, log_path, perf_label)
    except (OSError, RuntimeError) as error:
        r = {"case": a.case, "verdict": "ERROR", "rc": 3, "log": str(log_path)}
        print(f"[farm] {error}", file=sys.stderr)

    print("FARM_RESULT " + json.dumps(r, ensure_ascii=False))
    return r["rc"]


def run_with_retry(case, datadir, slot, timeout, log_path, perf_label):
    r = run_case(case, datadir, slot, timeout, log_path, perf_label)
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
            log2 = log_path.with_name(log_path.stem + "_retry.log")
            r = run_case(case, datadir, slot, timeout, log2, perf_label)

    return r


if __name__ == "__main__":
    sys.exit(main())
