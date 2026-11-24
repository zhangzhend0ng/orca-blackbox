"""The gate before anything is merged or synced to a machine under test: every
offline check in one command, one line each, exit 1 when any failed.

    python tools/pre_merge.py [repo-root]

Runs, in this order: the engine suite (tools/test_param_engine_sim.py), the
unit tests, the ops-vs-atlas checker, the ops red proofs. Each check's output
goes to a file under the system temp dir (orca-bb-pre_merge-<time>/); only
its own last line is printed here. A failed check's output is scanned for
secret-shaped strings before anything else happens to it (a failing pytest
once dumped the environment, tokens included - 2026-11-24): the COUNT is
printed, never the content, and the file is deleted when the count is not
zero.

Why one command: on the night of 2026-11-24 the engine suite was run after
every change and the unit tests were not - two of them had been red for
hours - and each of the four checks was typed by hand before ten merges.
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
PY = [sys.executable, "-B"]
SECRET = re.compile(
    r"(api[_-]?key|secret|token|password)[\"' ]*[:=][\"' ]*[A-Za-z0-9_\-]{16,}"
    r"|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9._\-]{20,}", re.I)

CHECKS = [
    ("engine suite", PY + ["tools/test_param_engine_sim.py", ROOT], ("checks, 0 failed",)),
    ("unit tests", PY + ["-m", "pytest", "-q", "unit_tests", "-p", "no:cacheprovider"], (" passed",)),
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
    out_dir = os.path.join(os.environ.get("TEMP") or os.path.dirname(ROOT), "orca-bb-pre_merge-" + time.strftime("%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    failed = 0
    for index, (name, command, must_contain) in enumerate(CHECKS, 1):
        path = os.path.join(out_dir, "%d-%s.log" % (index, name.replace(" ", "_")))
        started = time.monotonic()
        with open(path, "wb") as stream:
            code = subprocess.call(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        seconds = time.monotonic() - started
        tail = last_lines(path)
        ok = code == 0 and all(any(need in line for line in tail) for need in must_contain)
        line = "%-15s %s  %5.1f s  %s" % (name, "PASS" if ok else "FAIL", seconds, tail[-1][:90] if tail else "")
        if not ok:
            failed += 1
            hits = secret_count(path)
            if hits:
                os.remove(path)
                line += "  | output held %d secret-shaped string(s): deleted, nothing printed" % hits
            else:
                line += "  | log: " + path
        print(line, flush=True)
    print("gate:", "PASS" if not failed else "FAIL (%d of %d)" % (failed, len(CHECKS)),
          "| logs under", out_dir, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
