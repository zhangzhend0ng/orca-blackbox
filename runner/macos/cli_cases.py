"""Command-line controls of the File-menu cases on macOS Orca, run over SSH: no window.

  cli_cases.py             in a private staging directory made by the bootstrap

Not the GUI action of the Feishu row and not its coverage. The same product binary does the same
business step through its command line, so that the business criteria can be read on macOS
2.4.2 while the test session's windows cannot be driven (console locked, native panels).

  stl227    the empty-plate template (0 objects, U1 0.8 mm) and cube_20mm.stl  -> --export-3mf
  gcode236  feishu_std_cube.3mf  -> --slice 1 --export-3mf plate.gcode.3mf, then --export-slicedata
  stl233    the standard cube and the standard sphere  -> --arrange 1 --export-3mf --export-stl

The profile is seeded as project_copy.seed does for the GUI (the app's bundled Snapmaker and BBL
vendor profiles, its printers, the run's Snapmaker_Orca.conf) under a private --datadir. Every
command is recorded with its argv, exit code, seconds and output; the reply carries the files the
product wrote.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import time
import traceback

import project_copy as pc

WORK = Path(__file__).resolve().parent
CASE = (WORK / "case").read_text().strip()
PROFILE = WORK / "profile"
FUSE = 480
KEEP = {".3mf", ".stl", ".gcode", ".json", ".png", ".log"}
FILE_LIMIT = 48 * 1024 * 1024
TOTAL_LIMIT = 96 * 1024 * 1024
INPUTS = {"template.3mf", "baseline.3mf", "cube.3mf", "sphere.3mf", "import/cube_20mm.stl"}


def identity():
    bundle = plistlib.loads((pc.APP / "Contents/Info.plist").read_bytes())
    return {"app": str(pc.APP), "version": bundle.get("CFBundleShortVersionString"),
            "bundle_version": bundle.get("CFBundleVersion"), "executable_sha256": pc.digest(Path(pc.EXE))}


def run(label, arguments):
    """One product command: argv, exit code, seconds, where its output was kept."""
    started = time.monotonic()
    timed_out = None
    try:
        done = subprocess.run([pc.EXE, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=FUSE)
        code, output = done.returncode, done.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as error:
        timed_out, code, output = FUSE, None, (error.stdout or b"").decode("utf-8", errors="replace")
    (WORK / f"{label}.log").write_text(output)
    return {"step": label, "argv": [Path(pc.EXE).name, *arguments], "exit": code, "timed_out_after": timed_out,
            "seconds": round(time.monotonic() - started, 3), "output_lines": len(output.splitlines()),
            "output_head": output[:1500], "output_tail": output[-2000:]}


def commands():
    common = ["--datadir", str(PROFILE)]
    if CASE == "stl227":
        return [("export-3mf", common + ["--export-3mf", str(WORK / "imported.3mf"), str(WORK / "template.3mf"),
                                         str(WORK / "import" / "cube_20mm.stl")])]
    if CASE == "gcode236":
        return [("slice-export-3mf", common + ["--slice", "1", "--export-3mf", str(WORK / "plate.gcode.3mf"),
                                               str(WORK / "baseline.3mf")]),
                ("slice-export-slicedata", common + ["--slice", "1", "--export-slicedata", str(WORK / "slicedata"),
                                                     str(WORK / "baseline.3mf")])]
    if CASE == "stl233":
        return [("arrange-export-3mf-export-stl", common + [
            "--arrange", "1", "--export-3mf", str(WORK / "arranged.3mf"), "--export-stl", str(WORK / "all-objects.stl"),
            str(WORK / "cube.3mf"), str(WORK / "sphere.3mf")])]
    raise ValueError(f"Unexpected case {CASE!r}")


def sweep():
    """End every Orca of this login that was started from the staging directory."""
    def mine():
        return [pid for pid, command in pc.processes().items() if str(WORK) in command]
    for pid in mine():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    while mine() and time.monotonic() < deadline:
        time.sleep(0.25)
    return not mine()


def written():
    """The files the product wrote: everything outside the profile and the inputs."""
    total, files = 0, {}
    for path in sorted(WORK.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.suffix not in KEEP:
            continue
        relative = path.relative_to(WORK).as_posix()
        if relative in INPUTS or relative.startswith("profile/") or relative in {"result.json", "commands.json"}:
            continue
        size = path.stat().st_size
        files[relative] = {"bytes": size, "sha256": pc.digest(path), "returned": 0 < size <= FILE_LIMIT and total + size <= TOTAL_LIMIT}
        total += size
    return files


def main():
    report = {"case": CASE, "mode": "CLI", "ok": False, "run_id": (WORK / "run-id").read_text().strip(),
              "commit": (WORK / "commit").read_text().strip() if (WORK / "commit").is_file() else None,
              "started": time.strftime("%Y-%m-%d %H:%M:%S %z"), "commands": []}
    try:
        report["sut"] = identity()
        pc.seed(PROFILE)
        report["seed"] = {"profile": PROFILE.name, "conf_sha256": pc.digest(PROFILE / "Snapmaker_Orca.conf"),
                          "system_vendors": sorted(p.name for p in (PROFILE / "system").iterdir() if p.is_dir())}
        report["orca_processes_before"] = sorted(pc.processes())
        for label, arguments in commands():
            reading = run(label, arguments)
            report["commands"].append(reading)
            if reading["exit"] != 0:
                break
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        report["cleanup_verified"] = sweep()
        report["orca_processes_after"] = sorted(pc.processes())
        report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
        report["files"] = written()
        report["ok"] = bool(report["commands"]) and all(c["exit"] == 0 for c in report["commands"]) and "error" not in report
        (WORK / "result.json").write_text(json.dumps(report, indent=1))
    reply = {"report": report, "artifacts": {}}
    for name, facts in report["files"].items():
        if facts["returned"]:
            reply["artifacts"][name] = base64.b64encode((WORK / name).read_bytes()).decode("ascii")
    print(json.dumps(reply), flush=True)
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
