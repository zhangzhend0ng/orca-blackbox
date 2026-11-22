"""Run in the isolated Aqua session, or supervise its one-shot LaunchAgent over SSH."""
import base64
import contextlib
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback


WORK = Path(__file__).resolve().parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
SOURCE = WORK / "reference.3mf"
GOAL = (WORK / "goal").read_text().strip() if (WORK / "goal").is_file() else "layer"
COPY_NAME = (WORK / "copy-name").read_text().strip() if (WORK / "copy-name").is_file() else "layer-024-copy.3mf"
COPY = WORK / COPY_NAME
PAN_PRESSES = int((WORK / "pan-presses").read_text().strip()) if (WORK / "pan-presses").is_file() else 10
BASELINE = WORK / "baseline.3mf"
PHASES = ("baseline", "edit", "reopen")
PLATES = {"baseline": "baseline", "reopen": "edited"}
MAX_PLATE_BYTES = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_identity(pid):
    # Confirm the executable of the actual launched PID, independently of argv.
    get_path = ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath
    get_path.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    get_path.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(4096)
    require(get_path(pid, buffer, len(buffer)) > 0 and os.fsdecode(buffer.value) == EXE,
            "Running Orca executable does not match the selected bundle")
    metadata = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
    require(metadata["CFBundleExecutable"] == Path(EXE).name, "Unexpected bundle executable")
    version = metadata["CFBundleShortVersionString"]
    require(isinstance(version, str) and version, "Missing application version")
    hasher = hashlib.sha256()
    with open(EXE, "rb") as executable:
        for chunk in iter(lambda: executable.read(1024 * 1024), b""):
            hasher.update(chunk)
    sha = hasher.hexdigest()
    bundle_build = metadata.get("CFBundleVersion", "")
    return {"version": version, "build": bundle_build or "sha256:" + sha, "bundle_build": bundle_build,
            "build_source": "CFBundleVersion" if bundle_build else "executable_sha256", "executable_sha256": sha}


def wait_for(read, message, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = read()
        if value:
            return value
        time.sleep(0.25)
    raise TimeoutError(message)


def exactly_one(items):
    items = list(items)
    require(len(items) == 1, f"Expected one matching control, found {len(items)}")
    return items[0]


def processes():
    output = subprocess.check_output(
        ["/bin/ps", "-ww", "-U", str(os.getuid()), "-o", "pid=,command="], text=True)
    result = {}
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid, command = parts
        if command == EXE or command.startswith(EXE + " "):
            result[int(pid)] = command
    return result


def owned(profile):
    project = BASELINE if profile.name == "baseline" else COPY
    suffix = f" --datadir {profile} {project}"
    return [pid for pid, command in processes().items() if command.endswith(suffix)]


def close_owned(profile):
    for pid in owned(profile):
        try:
            os.kill(pid, signal.SIGTERM)
            try:
                wait_for(lambda: pid not in owned(profile), "Orca still running", 5)
            except TimeoutError:
                if pid in owned(profile):
                    os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    wait_for(lambda: not owned(profile), "Test process cleanup failed", 3)


def seed(profile):
    resources = APP / "Contents/Resources"
    system = profile / "system"
    system.mkdir(parents=True)
    for vendor in ("Snapmaker", "BBL"):
        shutil.copytree(resources / "profiles" / vendor, system / vendor)
        shutil.copy2(resources / "profiles" / (vendor + ".json"), system)
    shutil.copytree(resources / "printers", profile / "printers")
    shutil.copy2(WORK / "seed.conf", profile / "Snapmaker_Orca.conf")


@contextlib.contextmanager
def open_copy(desktop, phase):
    import accessibility as ax

    profile = WORK / phase
    project = BASELINE if phase == "baseline" else COPY
    desktop.check_session()
    require(not processes(), "Another Orca is running under the test login")
    seed(profile)
    try:
        desktop.check_session()
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP), "--args", "--datadir",
                        str(profile), str(project)], check=True, timeout=20)
        pid = exactly_one(wait_for(lambda: owned(profile), "New Orca process missing", 15))
        root = desktop.own(ax.application(pid))
        require(ax.set_timeout(root, 2) == 0, "Cannot set AX timeout")

        def main_window():
            windows = [w for w in desktop.children(root, "AXWindows")
                       if desktop.text(w, "AXSubrole") == "AXStandardWindow"
                       and desktop.text(w, "AXTitle") == project.stem]
            return exactly_one(windows) if windows else None

        window = wait_for(main_window, "Named project window did not open", 80)
        yield pid, root, window
    finally:
        close_owned(profile)


def layer_fields(desktop, window):
    fields = [e for e in desktop.descendants(window) if desktop.text(e, "AXRole") == "AXTextField"]
    if len(fields) < 2:
        return None
    require(len(fields) == 2, "Expected the two layer-height fields on the Quality tab")
    fields.sort(key=lambda e: desktop.position(e).y)
    first, second = (desktop.position(e) for e in fields)
    require(abs(first.x - second.x) <= 1 and 20 <= second.y - first.y <= 40, "Layer field layout changed")
    return fields


def read_values(desktop, fields):
    return [desktop.text(e, "AXValue") for e in fields]


def save_project(desktop, pid, root, window):
    bar = desktop.attr(root, "AXMenuBar")
    file_menu = exactly_one(e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File")
    desktop.act(pid, file_menu, "AXPress")
    save = exactly_one(e for e in desktop.descendants(file_menu)
                       if desktop.text(e, "AXRole") == "AXMenuItem" and desktop.text(e, "AXTitle") == "Save Project")
    wait_for(lambda: desktop.enabled(save), "Save Project did not become available")
    desktop.act(pid, save, "AXPress")
    wait_for(lambda: desktop.text(window, "AXTitle") == COPY.stem and COPY.is_file() and digest(COPY) != digest(SOURCE),
             "Save did not update the named copy", 20)


def edit_and_save(desktop, pid, root, window, fields, edit_height):
    import accessibility as ax

    upper, first_layer = fields
    desktop.act(pid, upper, "AXFocused", ax.true_value)
    desktop.act(pid, upper, "AXValue", desktop.string(edit_height))
    desktop.act(pid, upper, "AXConfirm")
    desktop.act(pid, first_layer, "AXFocused", ax.true_value)
    wait_for(lambda: desktop.text(window, "AXTitle") == "*" + COPY.stem, "Missing unsaved marker")
    require(read_values(desktop, fields) == [edit_height, "0.4"], "Edited fields mismatch")
    save_project(desktop, pid, root, window)


def open_tab(desktop, pid, window, name):
    hits = [e for e in desktop.descendants(window)
            if name in (desktop.text(e, "AXTitle"), desktop.text(e, "AXDescription"))]
    require(hits, f"No {name} tab candidate in the process panel")
    clickable = [e for e in hits if desktop.text(e, "AXRole") in ("AXButton", "AXRadioButton", "AXTabButton")]
    desktop.act(pid, exactly_one(clickable or hits), "AXPress")


def wall_field(desktop, window, value):
    # The Strength page lists Wall loops as its topmost text field (uia_param_wall_thin layout).
    fields = [e for e in desktop.descendants(window) if desktop.text(e, "AXRole") == "AXTextField"]
    if not fields:
        return None
    fields.sort(key=lambda e: desktop.position(e).y)
    return fields[0] if desktop.text(fields[0], "AXValue") == value else None


def edit_walls_and_save(desktop, pid, root, window):
    import accessibility as ax

    field = wait_for(lambda: wall_field(desktop, window, "2"), "Strength wall-loops field did not read 2")
    desktop.act(pid, field, "AXFocused", ax.true_value)
    desktop.act(pid, field, "AXValue", desktop.string("3"))
    desktop.act(pid, field, "AXConfirm")
    wait_for(lambda: desktop.text(window, "AXTitle") == "*" + COPY.stem, "Missing unsaved marker")
    require(desktop.text(field, "AXValue") == "3", "Wall-loops readback mismatch")
    save_project(desktop, pid, root, window)
    return desktop.text(field, "AXValue")


PAN_X, PAN_DEPTH, RIGHT_ARROW = 490, 420, 124


def pan_and_save(desktop, pid, root, window):
    # The cube fixture loads centred on the bed; the canvas click selects it and
    # focuses the OpenGL canvas, then each right arrow nudges the selection in +X.
    desktop.click_point(pid, root, window, COPY.stem, PAN_X, PAN_DEPTH)
    desktop.post_key(pid, root, window, COPY.stem, RIGHT_ARROW, PAN_PRESSES)
    wait_for(lambda: desktop.text(window, "AXTitle") == "*" + COPY.stem, "Missing unsaved marker")
    save_project(desktop, pid, root, window)


def open_plate(pid):
    """Identify the plate using this slicer's open descriptor, inode and private model directory."""
    output = subprocess.check_output(["/usr/sbin/lsof", "-n", "-P", "-p", str(pid), "-Ffin"],
                                     text=True, timeout=8)
    inode = None
    found = set()
    suffix = f"/Metadata/.{pid}.0.gcode"
    for line in output.splitlines():
        if line.startswith("f"):
            inode = None
        elif line.startswith("i"):
            inode = int(line[1:])
        elif line.startswith("n/") and line.endswith(suffix):
            found.add((Path(line[1:]).resolve(), inode))
    if not found:
        return None
    path, inode = exactly_one(found)
    model_root = Path(tempfile.gettempdir()).resolve() / "snapmaker_orca_model"
    require(path.is_relative_to(model_root) and path.parent.name == "Metadata"
            and f"#{pid}#" in path.parent.parent.name and inode is not None,
            "Open G-code does not belong to this plate/process")
    return path, inode


def slice_plate(desktop, pid, root, window, phase, project):
    bar = desktop.attr(root, "AXMenuBar")
    file_menu = exactly_one(e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File")
    export = exactly_one(e for e in desktop.descendants(file_menu) if desktop.text(e, "AXRole") == "AXMenuItem"
                         and desktop.text(e, "AXTitle").rstrip(".…") == "Export G-code")
    require(not desktop.enabled(export), "Export G-code was already enabled before slicing")
    start = time.time()
    window_id = desktop.click_slice(pid, root, window, project.stem)
    wait_for(lambda: desktop.enabled(export), "GUI slice did not enable Export G-code", 55)
    desktop.check_session()
    require(owned(WORK / phase) == [pid], "Slice process ownership changed")
    path, inode = wait_for(lambda: open_plate(pid), "Missing open G-code for the current plate", 12)
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_ino == inode
                and 0 < info.st_size <= MAX_PLATE_BYTES and start - 1 <= info.st_mtime <= time.time() + 1,
                "Slice file identity, size or timestamp mismatch")
        raw = stream.read(MAX_PLATE_BYTES + 1)
        require(len(raw) == info.st_size and info.st_mtime_ns == os.fstat(stream.fileno()).st_mtime_ns
                and b"; EXECUTABLE_BLOCK_END" in raw and b"; CONFIG_BLOCK_END" in raw,
                "Incomplete or changing plate data")
    with (WORK / (PLATES[phase] + ".gcode")).open("xb") as dest:
        dest.write(raw)
    return {"phase": phase, "pid": pid, "window_id": window_id, "source": "open_process_plate",
            "plate_file": path.name, "inode": inode, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "project_sha256": digest(project), "export_enabled_before": False, "export_enabled_after": True}


def worker(report):
    import accessibility as ax

    require(ax.trusted(), "Accessibility permission is missing for the Aqua worker")
    console_uid = os.stat("/dev/console").st_uid
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
    report["console_uid"] = console_uid
    report["test_uid"] = os.getuid()
    source_hash = digest(SOURCE)
    edit_height = (WORK / "edit-height").read_text().strip()
    require(GOAL in ("layer", "walls", "pan"), "Unexpected requested goal")
    if GOAL == "layer":
        require(edit_height in ("0.24", "0.32"), "Unexpected requested GUI edit")
    if GOAL == "pan":
        require(1 <= PAN_PRESSES <= 40, "Unexpected pan press count")
    for copy in (COPY, BASELINE):
        with SOURCE.open("rb") as src, copy.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        require(digest(copy) == source_hash and not SOURCE.samefile(copy), "Project copy mismatch")
    BASELINE.chmod(0o400)
    report["source_before"] = source_hash
    report["phases"] = {}
    report["slice_receipts"] = {}
    for phase in PHASES:
        report["failure_stage"] = phase + ".launch"
        with ax.Desktop(console_uid) as desktop, open_copy(desktop, phase) as (pid, root, window):
            report["failure_stage"] = phase + ".build_identity"
            sut = build_identity(pid)
            require(report.setdefault("sut", sut) == sut, "Orca build changed during this run")
            report["failure_stage"] = phase + ".fields"
            fields = wait_for(lambda: layer_fields(desktop, window), "Layer fields did not load")
            values = read_values(desktop, fields)
            entry = {"pid": pid, "window": desktop.text(window, "AXTitle"), "layers": values}
            report["phases"][phase] = entry
            expected = [edit_height if (GOAL == "layer" and phase == "reopen") else "0.4", "0.4"]
            require(values == expected, f"{phase}: expected layers {expected}, got {values}")
            if GOAL == "walls":
                report["failure_stage"] = phase + ".wall"
                open_tab(desktop, pid, window, "Strength")
                if phase == "edit":
                    report["failure_stage"] = "edit.wall_save"
                    entry["wall"] = edit_walls_and_save(desktop, pid, root, window)
                else:
                    wanted = "2" if phase == "baseline" else "3"
                    field = wait_for(lambda: wall_field(desktop, window, wanted),
                                     f"Strength wall-loops field mismatch in {phase}")
                    entry["wall"] = desktop.text(field, "AXValue")
            elif phase == "edit":
                if GOAL == "layer":
                    report["failure_stage"] = "edit.save"
                    edit_and_save(desktop, pid, root, window, fields, edit_height)
                else:
                    report["failure_stage"] = "edit.pan_save"
                    pan_and_save(desktop, pid, root, window)
            if phase in PLATES:
                report["failure_stage"] = phase + ".slice"
                project = BASELINE if phase == "baseline" else COPY
                report["slice_receipts"][PLATES[phase]] = slice_plate(desktop, pid, root, window, phase, project)
            desktop.check_session()
            report["failure_stage"] = phase + ".close"
        if phase == "edit":
            report["saved_sha256"] = digest(COPY)
            COPY.chmod(0o400)
    report["source_after"] = digest(SOURCE)
    report["failure_stage"] = "finalize"
    require(len({entry["pid"] for entry in report["phases"].values()}) == 3, "Reused a process identity")
    require(report["source_after"] == digest(BASELINE) == source_hash and digest(COPY) == report["saved_sha256"],
            "File changed")
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()


def run_worker():
    report = {"ok": False, "failure_stage": "preflight", "run_id": (WORK / "run-id").read_text().strip()}
    try:
        # One case at a time per test login; SSH disconnects do not release the worker's lock.
        with (Path(tempfile.gettempdir()) / "orca-bb-project-copy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            worker(report)
        report["ok"] = True
        report.pop("failure_stage")
    except Exception:
        report["error"] = traceback.format_exc()
    pending = WORK / "result.tmp"
    pending.write_text(json.dumps(report))
    pending.replace(WORK / "result.json")


def supervise():
    require(WORK.parent == Path(tempfile.gettempdir()).resolve()
            and re.fullmatch(r"orca-bb-copy\.[a-zA-Z0-9]{8}", WORK.name)
            and WORK.stat().st_uid == os.getuid() and WORK.stat().st_mode & 0o077 == 0,
            "Supervisor requires a fresh, private staging directory")
    run_id = (WORK / "run-id").read_text().strip()
    label = "local.orcabb.project-copy." + run_id
    domain = f"gui/{os.getuid()}"
    logfile = WORK / "worker.log"
    python = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    result = {"run_id": run_id, "ok": False, "failure_stage": "supervisor"}
    registered = False
    try:
        require(python.is_file(), "Select Xcode with its signed Python.app installed")
        job = {"Label": label, "LimitLoadToSessionType": "Aqua", "RunAtLoad": True,
               "ProgramArguments": [str(python), "-B", "-u", str(Path(__file__).resolve()), "--worker"],
               "WorkingDirectory": str(WORK), "StandardOutPath": str(logfile), "StandardErrorPath": str(logfile)}
        plist = WORK / "worker.plist"
        plist.write_bytes(plistlib.dumps(job))
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True, timeout=15)
        registered = True
        result_file = WORK / "result.json"
        wait_for(result_file.is_file, "Mac worker timed out", 510)
        result = json.loads(result_file.read_text())
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        failures = []
        if registered:
            try:
                subprocess.run(["launchctl", "bootout", domain + "/" + label], check=True, timeout=20)
                status = subprocess.run(["launchctl", "print", domain + "/" + label],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                require(status.returncode != 0, "LaunchAgent still registered")
            except Exception as error:
                failures.append(str(error))
        for phase in PHASES:
            try:
                close_owned(WORK / phase)
            except Exception as error:
                failures.append(str(error))
        result["cleanup_verified"] = not failures
        if failures:
            result.update(ok=False, cleanup_errors=failures)
            result.setdefault("failure_stage", "cleanup")
        if not result["ok"]:
            result["remote_evidence"] = str(WORK)
    reply = {"report": result, "log": logfile.read_text(errors="replace")[-16000:] if logfile.exists() else "",
             "gcodes": {}}
    for name in PLATES.values():
        plate = WORK / (name + ".gcode")
        if plate.is_file() and 0 < plate.stat().st_size <= MAX_PLATE_BYTES:
            reply["gcodes"][name] = base64.b64encode(plate.read_bytes()).decode("ascii")
    if COPY.is_file() and COPY.stat().st_size <= 16 * 1024 * 1024:
        reply["project"] = base64.b64encode(COPY.read_bytes()).decode("ascii")
    print(json.dumps(reply), flush=True)
    if result["ok"]:
        shutil.rmtree(WORK)


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        run_worker()
    elif sys.argv[1:] == ["--supervise"]:
        supervise()
    else:
        sys.exit("Use runner/macos_project_copy.py on the SSH host")
