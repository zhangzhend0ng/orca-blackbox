"""The gate before anything is merged or synced to a machine under test: every
offline check in one command, one line each, exit 1 when any failed.

    python tools/pre_merge.py [repo-root]

Runs, in this order: the engine suite (tools/test_param_engine_sim.py), the
unit tests, the ops-vs-atlas checker, the ops red proofs. Each check's output
goes to a file under the system temp dir (orca-bb-pre_merge-<unique>/); only
a passing check prints its last line. A failed check's output is scanned for
secret-shaped strings before anything else happens to it (a failing pytest
once dumped the environment, tokens included - 2026-11-24): the COUNT is
printed, never the content, and the file is deleted when the count is not
zero.

Why one command: on the night of 2026-11-24 the engine suite was run after
every change and the unit tests were not - two of them had been red for
hours - and each of the four checks was typed by hand before ten merges.

The gate leaves nothing behind but its four logs: pytest's scratch goes to
<its temp dir>/pytest and is deleted at the end (three earlier runs had left
6.7 GB under pytest-of-snapmaker when the disk filled up on 2026-11-24, and
37 tests failed with "No space left on device"). The free space of that disk
is printed with the verdict.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
PY = [sys.executable, "-B"]
SECRET = re.compile(
    r"(api[_-]?key|secret|token|password)[\"' ]*[:=][\"' ]*[A-Za-z0-9_\-]{16,}"
    r"|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9._\-]{20,}", re.I)
LOW_FREE_GB = 20

CHECKS = [
    ("engine suite", PY + ["tools/test_param_engine_sim.py", ROOT], ("checks, 0 failed",)),
    ("unit tests", PY + ["-m", "pytest", "-q", "unit_tests", "-p", "no:cacheprovider", "--basetemp=<basetemp>"],
     (" passed",)),
    ("ops vs atlas", PY + ["tools/check_ops_against_atlas.py", ROOT], ("all ops validate",)),
    ("ops red proofs", PY + ["tools/check_ops_red_proof.py"], ()),
]


def secret_count(path):
    try:
        with open(path, "rb") as stream:
            return len(SECRET.findall(stream.read().decode("utf-8", "replace")))
    except OSError:
        return -1


def last_lines(path, n=3):
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            lines = [l.rstrip() for l in stream if l.strip()]
        return lines[-n:] if lines else ["(no output)"]
    except OSError:
        return ["(no output)"]


def main():
    out_dir = tempfile.mkdtemp(prefix="orca-bb-pre_merge-", dir=os.environ.get("TEMP") or os.path.dirname(ROOT))
    basetemp = os.path.join(out_dir, "pytest")
    failed = 0
    for index, (name, command, must_contain) in enumerate(CHECKS, 1):
        command = [part.replace("<basetemp>", basetemp) for part in command]
        path = os.path.join(out_dir, "%d-%s.log" % (index, name.replace(" ", "_")))
        started = time.monotonic()
        with open(path, "wb") as stream:
            code = subprocess.call(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        seconds = time.monotonic() - started
        ok = code == 0
        tail = last_lines(path)
        ok = ok and all(any(need in item for item in tail) for need in must_contain)
        line = "%-15s %s  %5.1f s  %s" % (name, "PASS" if ok else "FAIL", seconds,
                                         tail[-1][:90] if ok and tail else "")
        if not ok:
            failed += 1
            if any("No space left on device" in item for item in tail):
                line += "  | THE DISK IS FULL - not a code verdict"
            hits = secret_count(path)
            if hits != 0:
                reason = "scan unsafe" if hits < 0 else f"{hits} secret-shaped string(s)"
                try:
                    os.remove(path)
                    action = "log removed"
                except OSError:
                    action = "log removal failed"
                line += f"  | {action}; output not printed ({reason})"
            else:
                line += "  | log: " + path
        print(line, flush=True)
    shutil.rmtree(basetemp, ignore_errors=True)
    free_gb = shutil.disk_usage(out_dir).free / 2 ** 30
    print("gate:", "PASS" if not failed else "FAIL (%d of %d)" % (failed, len(CHECKS)),
          "| logs under", out_dir, flush=True)
    print("disk: %.1f GB free%s" % (free_gb, "" if free_gb >= LOW_FREE_GB else
                                    "  LOW (under %d GB): a full disk fails the tests, and the guest's disk only grows" % LOW_FREE_GB),
          flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
