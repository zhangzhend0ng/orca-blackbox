"""Run in the isolated Aqua session, or supervise its one-shot LaunchAgent over SSH."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback


WORK = Path(__file__).resolve().parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
SOURCE = WORK / "reference.3mf"
COPY = WORK / "layer-024-copy.3mf"
PHASES = ("edit", "reopen")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    suffix = f" --datadir {profile} {COPY}"
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
    desktop.check_session()
    require(not processes(), "Another Orca is running under the test login")
    seed(profile)
    try:
        desktop.check_session()
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP), "--args", "--datadir",
                        str(profile), str(COPY)], check=True, timeout=20)
        pid = exactly_one(wait_for(lambda: owned(profile), "New Orca process missing", 15))
        root = desktop.own(ax.application(pid))
        require(ax.set_timeout(root, 2) == 0, "Cannot set AX timeout")

        def main_window():
            windows = [w for w in desktop.children(root, "AXWindows")
                       if desktop.text(w, "AXSubrole") == "AXStandardWindow"
                       and desktop.text(w, "AXTitle") == COPY.stem]
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


def edit_and_save(desktop, pid, root, window, fields):
    import accessibility as ax

    upper, first_layer = fields
    desktop.act(pid, upper, "AXFocused", ax.true_value)
    desktop.act(pid, upper, "AXValue", desktop.string("0.24"))
    desktop.act(pid, upper, "AXConfirm")
    desktop.act(pid, first_layer, "AXFocused", ax.true_value)
    wait_for(lambda: desktop.text(window, "AXTitle") == "*" + COPY.stem, "Missing unsaved marker")
    require(read_values(desktop, fields) == ["0.24", "0.4"], "Edited fields mismatch")
    bar = desktop.attr(root, "AXMenuBar")
    file_menu = exactly_one(e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File")
    desktop.act(pid, file_menu, "AXPress")
    save = exactly_one(e for e in desktop.descendants(file_menu)
                       if desktop.text(e, "AXRole") == "AXMenuItem" and desktop.text(e, "AXTitle") == "Save Project")
    wait_for(lambda: desktop.enabled(save), "Save Project did not become available")
    desktop.act(pid, save, "AXPress")
    wait_for(lambda: desktop.text(window, "AXTitle") == COPY.stem and COPY.is_file() and digest(COPY) != digest(SOURCE),
             "Save did not update the named copy", 20)


def worker(report):
    import accessibility as ax

    require(ax.trusted(), "Accessibility permission is missing for the Aqua worker")
    console_uid = os.stat("/dev/console").st_uid
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
    report["console_uid"] = console_uid
    report["test_uid"] = os.getuid()
    source_hash = digest(SOURCE)
    with SOURCE.open("rb") as src, COPY.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    require(digest(COPY) == source_hash and not SOURCE.samefile(COPY), "Project copy mismatch")
    report["source_before"] = source_hash
    report["phases"] = {}
    for phase in PHASES:
        with ax.Desktop(console_uid) as desktop, open_copy(desktop, phase) as (pid, root, window):
            fields = wait_for(lambda: layer_fields(desktop, window), "Layer fields did not load")
            values = read_values(desktop, fields)
            report["phases"][phase] = {"pid": pid, "window": desktop.text(window, "AXTitle"), "layers": values}
            if phase == "edit":
                require(values == ["0.4", "0.4"], "Unexpected original layers")
                edit_and_save(desktop, pid, root, window, fields)
            else:
                require(values == ["0.24", "0.4"], "New process did not reopen the changed layers")
            desktop.check_session()
        if phase == "edit":
            report["saved_sha256"] = digest(COPY)
            COPY.chmod(0o400)
    report["source_after"] = digest(SOURCE)
    require(report["phases"]["edit"]["pid"] != report["phases"]["reopen"]["pid"], "Reopen reused a PID")
    require(report["source_after"] == source_hash and digest(COPY) == report["saved_sha256"], "File changed")
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()


def run_worker():
    report = {"ok": False, "run_id": (WORK / "run-id").read_text().strip()}
    try:
        # One case at a time per test login; SSH disconnects do not release the worker's lock.
        with (Path(tempfile.gettempdir()) / "orca-bb-project-copy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            worker(report)
        report["ok"] = True
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
    result = {"run_id": run_id, "ok": False}
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
        wait_for(result_file.is_file, "Mac worker timed out", 260)
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
        if not result["ok"]:
            result["remote_evidence"] = str(WORK)
    reply = {"report": result, "log": logfile.read_text(errors="replace")[-16000:] if logfile.exists() else ""}
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
