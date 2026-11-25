"""Command-line controls of the File-menu cases on macOS Orca, run over SSH: no window.

  cli_cases.py             in a private staging directory made by the bootstrap

Not the GUI action of the Feishu row and not its coverage. The same product binary does the same
business step through its command line, so that the business criteria can be read on macOS
2.4.2 while the test session's windows cannot be driven (console locked, native panels).

  stl227    cube_20mm.stl -> --export-3mf, twice: with whatever the command line selects on
            its own, and with the template's printer, process and filament preset files
            (--load-settings, --load-filaments)
  gcode236  feishu_std_cube.3mf  -> --slice 1 --export-3mf plate.gcode.3mf, then --export-slicedata
  stl233    the standard sphere -> --export-stl, then the standard cube and that sphere STL
            -> --export-stl (one STL per object) and --export-3mf

The profile is seeded as project_copy.seed does for the GUI (the app's bundled Snapmaker and BBL
vendor profiles, its printers, the run's Snapmaker_Orca.conf) under a private --datadir.

Read off the 2.4.2 command line (2026-11-26): a project file without objects is refused ("The
supplied file couldn't be read because it's empty", exit 250); an STL on its own is exported with
the slicer's built-in defaults whatever presets the profile's config selects (0.4 mm nozzle,
0.20 mm layers); the bundled vendor presets are one JSON file per preset under
Contents/Resources/profiles/<vendor>/{machine,process,filament}/ and those files are what
--load-settings and --load-filaments read.

Every command is recorded with its argv, exit code, seconds and output; the reply carries the
files the product wrote.
"""
import base64
import json
import os
from pathlib import Path
import plistlib
import re
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
PRESETS = pc.APP / "Contents/Resources/profiles/Snapmaker"
FUSE = 480
KEEP = {".3mf", ".stl", ".gcode", ".json", ".png", ".log"}
FILE_LIMIT = 48 * 1024 * 1024
TOTAL_LIMIT = 96 * 1024 * 1024
INPUTS = {"baseline.3mf", "cube.3mf", "sphere.3mf", "import/cube_20mm.stl", "presets.json", "seed.conf"}


def identity():
    bundle = plistlib.loads((pc.APP / "Contents/Info.plist").read_bytes())
    return {"app": str(pc.APP), "version": bundle.get("CFBundleShortVersionString"),
            "bundle_version": bundle.get("CFBundleVersion"), "executable_sha256": pc.digest(Path(pc.EXE))}


def preset_file(kind, name, report):
    """The bundled preset file named `name`. Presets were renamed between versions ("0.40
    Standard" became "0.40mm Standard"), so a name that differs only by that "mm" is accepted
    and the name actually used is written down."""
    folder = PRESETS / kind
    renamed = lambda text: re.sub(r"^(\d+(?:\.\d+)?)mm\b", r"\1", text)  # noqa: E731
    for path in sorted(folder.glob("*.json")):
        try:
            found = json.loads(path.read_text()).get("name")
        except (OSError, ValueError):
            continue
        if found == name:
            return path
        if renamed(found or "") == renamed(name):
            report.setdefault("renamed_presets", {})[name] = found
            return path
    raise FileNotFoundError(f"{kind} preset {name!r} is not in the bundle")


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


def commands(report):
    """[(step, builder)]: the builder gives the argv when its turn comes, so a later command can
    use what an earlier one wrote."""
    common = ["--datadir", str(PROFILE)]
    if CASE == "stl227":
        stl = str(WORK / "import" / "cube_20mm.stl")
        wanted = json.loads((WORK / "presets.json").read_text())
        settings = ";".join(str(preset_file(kind, wanted[key], report))
                            for kind, key in (("machine", "machine"), ("process", "process")))
        filament = str(preset_file("filament", wanted["filament"], report))
        return [("export-3mf-default", lambda: common + ["--export-3mf", str(WORK / "imported.3mf"), stl]),
                ("export-3mf-template-presets", lambda: common + [
                    "--load-settings", settings, "--load-filaments", filament,
                    "--export-3mf", str(WORK / "imported-u1.3mf"), stl])]
    if CASE == "gcode236":
        return [("slice-export-3mf", lambda: common + [
                    "--slice", "1", "--export-3mf", str(WORK / "plate.gcode.3mf"), str(WORK / "baseline.3mf")]),
                ("slice-export-slicedata", lambda: common + [
                    "--slice", "1", "--export-slicedata", str(WORK / "slicedata"), str(WORK / "baseline.3mf")])]
    if CASE == "stl233":
        # A second 3MF is refused (CLI_FILELIST_INVALID_ORDER, exit 252: only the first file may
        # be a project), so the sphere is turned into an STL first. --export-stl takes no value
        # and writes obj_<n>_<name>.stl into <outputdir>/stl, which has to exist. With
        # --outputdir set, --export-3mf's name is taken relative to it even when it is absolute
        # (an absolute path is appended to the output directory and the export fails, exit 243),
        # so the project is named by its bare file name.
        for folder in (WORK / "sphere-out" / "stl", WORK / "out" / "stl"):
            folder.mkdir(parents=True, exist_ok=True)

        def sphere_stl():
            found = sorted((WORK / "sphere-out" / "stl").glob("*.stl"))
            if len(found) != 1:
                raise RuntimeError(f"{len(found)} STL files under sphere-out/stl, expected the sphere")
            return str(found[0])
        return [("export-sphere-stl", lambda: common + ["--outputdir", str(WORK / "sphere-out"), "--export-stl",
                                                        str(WORK / "sphere.3mf")]),
                ("export-cube-and-sphere", lambda: common + [
                    "--outputdir", str(WORK / "out"), "--export-stl", "--export-3mf", "exported.3mf",
                    str(WORK / "cube.3mf"), sphere_stl()])]
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
        for label, build in commands(report):
            reading = run(label, build())
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
