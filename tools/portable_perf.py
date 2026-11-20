"""Single-file Windows entry point for the two-project Orca benchmark."""

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from tempfile import TemporaryDirectory
import traceback
from uuid import uuid4
from zipfile import ZipFile

# These dependencies are also used by the bundled test scripts loaded by path.
import cv2
import numpy as np
import pytesseract  # noqa: F401

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
for path in (ROOT, ROOT / "tests", ROOT / "tests" / "engine"):
    sys.path.insert(0, str(path))

from harness import host_guard, winutil
from tools.portable_perf_report import build_report

MESA_FILES = ("opengl32.dll", "libgallium_wgl.dll", "libGLESv1_CM.dll", "libGLESv2.dll")


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def load_build():
    manifest = json.loads((ROOT / "portable" / "build.json").read_text(encoding="utf-8"))
    if not isinstance(manifest.get("files"), dict):
        raise RuntimeError("Invalid packaged build manifest")
    return manifest


def stage_build(home, manifest, mesa_dir):
    app_zip = ROOT / "portable" / "orca.zip"
    providers = {name: mesa_dir / name for name in MESA_FILES} if mesa_dir else {}
    provider_hashes = {name: sha256(path) for name, path in providers.items()}
    identity = hashlib.sha256(json.dumps([manifest, provider_hashes], sort_keys=True).encode()).hexdigest()[:20]
    builds = home / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    app = builds / identity
    files = manifest["files"] | provider_hashes
    if not app.is_dir():
        if sha256(app_zip) != manifest["archive_sha256"]:
            raise RuntimeError("Packaged Orca archive differs from its manifest")
        with TemporaryDirectory(prefix="stage-", dir=builds) as scratch:
            unpacked = Path(scratch) / "app"
            with ZipFile(app_zip) as bundle:
                bundle.extractall(unpacked)
            for name, path in providers.items():
                shutil.copyfile(path, unpacked / name)
            for name, expected in files.items():
                if sha256(unpacked / name) != expected:
                    raise RuntimeError(f"Packaged binary differs from manifest: {name}")
            unpacked.rename(app)
    for name, expected in files.items():
        if sha256(app / name) != expected:
            raise RuntimeError(f"Cached binary differs from manifest: {app / name}")
    if not mesa_dir and (app / "opengl32.dll").exists():
        raise RuntimeError(f"Unexpected software OpenGL override: {app / 'opengl32.dll'}")
    return app / "snapmaker-orca.exe"


@contextmanager
def desktop_lock():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateMutexW(None, False, r"Local\OrcaBlackboxPortablePerf")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if ctypes.get_last_error() == 183:
            raise RuntimeError("Another portable Orca test is already active in this session")
        yield
    finally:
        kernel.CloseHandle(handle)


def check_bundle(output):
    suite = importlib.import_module("m2_perf_showcase")
    assert Path(suite.__file__).is_file(), suite.__file__
    manifest = load_build()
    archive_path = ROOT / "portable" / "orca.zip"
    if sha256(archive_path) != manifest["archive_sha256"]:
        raise RuntimeError("Packaged Orca archive differs from its manifest")
    with ZipFile(archive_path) as archive:
        for name, expected in manifest["files"].items():
            with archive.open(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise RuntimeError(f"Invalid packaged {name}")
        if not any(v.startswith("resources/profiles/") for v in archive.namelist()):
            raise RuntimeError("Orca profile resources are missing")
    for fixture in ("agent_layer_cube.3mf", "snapmates_nonmixed.3mf"):
        with ZipFile(ROOT / "fixtures" / fixture) as archive:
            if not archive.namelist():
                raise RuntimeError(f"Empty model fixture: {fixture}")
    for name in ("PresentMon", "ffmpeg"):
        if sha256(ROOT / "portable" / f"{name}.exe") != manifest[f"{name.lower()}_sha256"]:
            raise RuntimeError(f"Packaged {name} differs from its manifest")
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temp:
        video = Path(temp) / "codec.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 8, (128, 96))
        try:
            if not writer.isOpened():
                raise RuntimeError("Packaged MP4 encoder is unavailable")
            writer.write(np.zeros((96, 128, 3), dtype=np.uint8))
        finally:
            writer.release()
        reader = cv2.VideoCapture(str(video))
        try:
            if not reader.read()[0]:
                raise RuntimeError("Packaged MP4 failed round-trip decoding")
        finally:
            reader.release()
    print("PORTABLE_CHECK_OK", manifest["orca_source"], flush=True)


def configure(output, exe, manifest):
    for key in ("ORCA_BB_PERF_JOB", "ORCA_BB_FRAME_TRACE_FILE"):
        os.environ.pop(key, None)
    os.environ.update({
        "ORCA_VISION_APP_EXE": str(exe),
        "ORCA_BB_PERF": "1",
        "ORCA_BB_PERF_BATCH_DIR": str(output),
        "ORCA_BB_PERF_OUT": str(output),
        "ORCA_BB_PERF_VIEWPORT": "1",
        "ORCA_BB_PERF_CYCLES": "2",
        "ORCA_BB_FRAME_TRACE": "1",
        "ORCA_BB_PERF_RUN_ID": output.name,
        "ORCA_BB_PERF_COMMIT": manifest["runner_commit"],
        "ORCA_BB_PRESENTMON_EXE": str(ROOT / "portable" / "PresentMon.exe"),
        "ORCA_BB_OWNED_PROFILE": "1",
    })
    if not host_guard.in_guest():
        # Launching this dedicated desktop executable is the operator's
        # explicit local-run choice. The normal harness guard stays installed.
        os.environ["ORCA_BB_ALLOW_HOST"] = "1"


def interactive_display():
    winutil.make_dpi_aware()
    user = winutil.user32
    resolution = [user.GetSystemMetrics(i) for i in (0, 1)]
    dpi = user.GetDpiForSystem()
    if not user.GetShellWindow():
        raise RuntimeError("Sign in to a Windows desktop before running the GUI benchmark")
    if resolution[0] < 1280 or resolution[1] < 900 or dpi != 96:
        raise RuntimeError(f"Display is {resolution[0]}x{resolution[1]} at {dpi} DPI. "
                           "Use 1920x1080 at 100% scaling for the bundled templates.")
    return {"resolution": resolution, "dpi": dpi}


def run_benchmark(home, output, mesa_dir):
    try:
        output.mkdir(parents=True)
    except FileExistsError:
        # hv_go writes its manifest before launching the packaged worker.
        if {child.name for child in output.iterdir()} != {"batch.json"}:
            raise
        batch = json.loads((output / "batch.json").read_text(encoding="utf-8-sig"))
        if batch.get("schema") != 1 or batch.get("batch_id") != output.name:
            raise ValueError("Benchmark output is not a fresh runner batch")
    manifest = load_build()
    machine = {"node": platform.node(), "os": platform.platform(), "build": manifest,
               "started": datetime.now().astimezone().isoformat(), "software_gl_override": bool(mesa_dir),
               "scope": "guest" if host_guard.in_guest() else "local diagnostic"}
    result = 1
    with (output / "run.log").open("w", encoding="utf-8", buffering=1) as log:
        try:
            machine["display"] = interactive_display()
            exe = stage_build(home, manifest, mesa_dir)
            configure(output, exe, manifest)
            os.chdir(output)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            suite = importlib.import_module("m2_perf_showcase")
            if getattr(sys, "frozen", False):
                # The app and collectors must resolve their own native DLLs.
                ctypes.windll.kernel32.SetDllDirectoryW(None)
                paths = os.environ.get("PATH", "").split(os.pathsep)
                os.environ["PATH"] = os.pathsep.join(
                    path for path in paths
                    if path and not Path(path.strip('"')).resolve().is_relative_to(ROOT))
            with redirect_stdout(log), redirect_stderr(log):
                result = suite.main()
        except Exception as error:
            machine["error"] = str(error)
            traceback.print_exc(file=log)
        finally:
            machine["exit_code"] = result
            (output / "run.json").write_text(json.dumps(machine, ensure_ascii=False, indent=2), encoding="utf-8")
    build_report(output, ROOT / "portable" / "ffmpeg.exe")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check packaged dependencies without launching Orca")
    parser.add_argument("--stage", action="store_true", help="Extract the packaged Orca build without launching it")
    parser.add_argument("--report", type=Path, help="Generate a report from an existing run folder")
    parser.add_argument("--output", type=Path, help="Explicit output folder")
    parser.add_argument("--no-open", action="store_true", help="Do not open the local HTML report")
    parser.add_argument("--mesa-dir", type=Path, help="Explicitly use existing Mesa DLLs on a software-rendered test PC")
    args = parser.parse_args()
    home = Path(os.environ["LOCALAPPDATA"]) / "OrcaPerfRunner"
    output = args.output.resolve() if args.output else home / "runs" / uuid4().hex
    if args.check:
        check_bundle(output)
        return 0
    if args.report:
        encoder = ROOT / "portable" / "ffmpeg.exe"
        build_report(args.report.resolve(), encoder if encoder.is_file() else None)
        return 0
    mesa = args.mesa_dir.resolve() if args.mesa_dir else None
    if args.stage:
        with desktop_lock():
            print("PORTABLE_STAGED", stage_build(home, load_build(), mesa), flush=True)
        return 0
    print("Orca performance test: keep the Windows desktop available during the run.", flush=True)
    print(f"Run folder: {output}", flush=True)
    with desktop_lock():
        result = run_benchmark(home, output, mesa)
    report = output / "index.html"
    print(f"Result: {result}. Report: {report}", flush=True)
    if not args.no_open:
        os.startfile(str(report))
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Orca performance runner: {error}", file=sys.stderr)
        if len(sys.argv) == 1 and sys.stderr.isatty():
            try:
                input("Press Enter to close.")
            except EOFError:
                pass
        raise SystemExit(2) from error
