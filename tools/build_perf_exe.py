"""Build a Windows x64 one-file Orca benchmark using a verified instrumented DLL."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "tests" / "engine"
MESA_FILES = {"opengl32.dll", "libgallium_wgl.dll", "libglesv1_cm.dll", "libglesv2.dll"}


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def payload(args, directory):
    identity = json.loads(args.identities.read_text(encoding="utf-8"))
    exe = args.release / "snapmaker-orca.exe"
    dll = args.release / "Snapmaker_Orca.dll"
    for file, key in ((exe, "base_exe"), (dll, "base_dll"), (args.instrumented, "instrumented_dll")):
        if digest(file) != identity[key].lower():
            raise SystemExit(f"File does not match the declared build: {file}")
    runtime = {artifact.name: artifact for artifact in args.runtime.glob("*.dll")}
    if not {"vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"} <= set(runtime):
        raise SystemExit("Select the Visual C++ x64 app-local redistributable directory")
    files = {p.name: p for p in args.release.iterdir()
             if p.is_file() and p.suffix.lower() in {".exe", ".dll", ".json", ".ini", ".manifest"}
             and p.name.lower() not in MESA_FILES}
    files.update(runtime)
    files[dll.name] = args.instrumented
    release_resources = args.release / "resources"
    if not (release_resources / "profiles").is_dir():
        raise SystemExit("Base Orca installation has no resources/profiles")
    with ZipFile(directory / "orca.zip", "w", compression=ZIP_STORED) as archive:
        for name, path in files.items():
            archive.write(path, name)
        for path in sorted(release_resources.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(args.release).as_posix())
    manifest = {
        "orca_source": args.orca_source,
        "archive_sha256": digest(directory / "orca.zip"),
        "runner_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": {name: digest(path) for name, path in sorted(files.items())},
        "runner_sha256": {name: digest(ROOT / "tools" / name)
                          for name in ("portable_perf.py", "portable_perf_report.py")},
        "presentmon_sha256": digest(args.presentmon),
        "ffmpeg_sha256": digest(args.ffmpeg),
    }
    (directory / "build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (directory / "PresentMon.exe").write_bytes(args.presentmon.read_bytes())
    (directory / "ffmpeg.exe").write_bytes(args.ffmpeg.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release", "instrumented", "identities", "runtime", "presentmon", "ffmpeg", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--orca-source", required=True)
    args = parser.parse_args()
    for name in ("release", "instrumented", "identities", "runtime", "presentmon", "ffmpeg", "output"):
        setattr(args, name, getattr(args, name).resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / "artifacts" / "portable-perf"
    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="build-", dir=cache) as scratch:
        workspace = Path(scratch)
        data = workspace / "portable"
        data.mkdir()
        payload(args, data)
        paths = [
            (data, "portable"),
            (ROOT / "resource", "resource"),
            (ROOT / "resources", "resources"),
            *[(ROOT / "fixtures" / name, "fixtures")
              for name in ("agent_layer_cube.3mf", "snapmates_nonmixed.3mf")],
            *[(ENGINE / f"{name}.py", "tests/engine") for name in
              ("m2_perf_showcase", "m2_perf_scenarios", "m2_slice_chain", "m3f_multi_plate", "m1_minimal_loop")],
            *[(ROOT / "tests" / f"{name}.py", "tests") for name in ("m3_common", "m7_common")],
        ]
        command = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--console", "--noupx",
            "--name", "OrcaPerfRunner", "--distpath", str(args.output),
            "--workpath", str(workspace / "work"), "--specpath", str(workspace),
            "--paths", str(ROOT), "--paths", str(ROOT / "tests"), "--paths", str(ENGINE),
            "--hidden-import", "m2_perf_showcase", "--hidden-import", "harness.native_frame_trace",
            "--exclude-module", "pandas", "--exclude-module", "scipy", "--exclude-module", "matplotlib",
        ]
        for source, destination in paths:
            command.extend(("--add-data", f"{source};{destination}"))
        command.append(str(ROOT / "tools" / "portable_perf.py"))
        subprocess.run(command, cwd=ROOT, check=True)
    print(args.output / "OrcaPerfRunner.exe")


if __name__ == "__main__":
    main()
