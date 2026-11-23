"""Probe 17 (task A5 control): characterize save-time config migration noise.

The first judged walls run (ffe0c6e4) completed the whole GUI chain but the
host oracle rejected the saved 3MF: beside wall_loops 2->3 the SUT's save
rewrote the config schema (2.3.6 -> 2.4.1, new keys, vector migrations,
renamed preset, refreshed template gcode). To prove that noise is
edit-independent, this control performs ONE different, fully predicted edit
-- initial_layer_print_height 0.4 -> 0.44 on the default Quality page via
the plain AX field channel (no OCR needed there) -- and saves. The host then
defines the noise set as {keys the control changed} minus that one edit:
any key the judged walls run changes must either be in that noise set with
the identical value, or be wall_loops itself. A net-zero roundtrip was tried
first and cannot work: reverting the value clears the dirty flag and leaves
Save Project disabled (control_save2/3_a5 evidence). The harvested
probe.3mf + result.json become the committed baseline-of-record for the Mac
walls differential oracle. 420 s fuse.
"""
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

import accessibility as ax

WORK = Path(__file__).resolve().parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
PROJECT = WORK / "probe.3mf"
PROFILE = WORK / "datadir"
CONTROL_VALUE = "0.44"
RESULT = {"ok": False}


def note(key, value):
    RESULT[key] = value
    print(f"[probe17] {key}: {json.dumps(value)[:600]}", flush=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exactly_one(items):
    items = list(items)
    if len(items) != 1:
        raise RuntimeError(f"Expected one matching control, found {len(items)}")
    return items[0]


def orca_processes():
    output = subprocess.check_output(["/bin/ps", "-ww", "-U", str(os.getuid()), "-o", "pid=,command="],
                                     text=True)
    return {int(p): c for p, c in
            (line.strip().split(None, 1) for line in output.splitlines())
            if c == EXE or c.startswith(EXE + " ")}


def wait_orca():
    end = time.monotonic() + 25
    while time.monotonic() < end:
        found = [pid for pid, command in orca_processes().items()
                 if command.endswith(f"--datadir {PROFILE} {PROJECT}")]
        if len(found) == 1:
            return found[0]
        time.sleep(0.4)
    raise TimeoutError("Orca probe process missing")


def wait_window(desktop, root, title):
    end = time.monotonic() + 80
    while time.monotonic() < end:
        windows = [w for w in desktop.children(root, "AXWindows")
                   if desktop.text(w, "AXSubrole") == "AXStandardWindow"
                   and desktop.text(w, "AXTitle") == title]
        if len(windows) == 1:
            return windows[0]
        time.sleep(0.4)
    raise TimeoutError("Project window did not open")


def seed():
    resources = APP / "Contents/Resources"
    system = PROFILE / "system"
    system.mkdir(parents=True)
    for vendor in ("Snapmaker", "BBL"):
        shutil.copytree(resources / "profiles" / vendor, system / vendor)
        shutil.copy2(resources / "profiles" / (vendor + ".json"), system)
    shutil.copytree(resources / "printers", PROFILE / "printers")
    shutil.copy2(WORK / "seed.conf", PROFILE / "Snapmaker_Orca.conf")


def wait_for(read, message, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = read()
        if value:
            return value
        time.sleep(0.25)
    raise TimeoutError(message)


def layer_fields(desktop, window):
    fields = [e for e in desktop.descendants(window) if desktop.text(e, "AXRole") == "AXTextField"]
    if len(fields) != 2:
        return None
    fields.sort(key=lambda e: desktop.position(e).y)
    return fields


def run():
    console_uid = os.stat("/dev/console").st_uid
    if not ax.trusted():
        raise RuntimeError("Accessibility permission is missing")
    info = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
    hasher = hashlib.sha256()
    with open(EXE, "rb") as executable:
        for chunk in iter(lambda: executable.read(1024 * 1024), b""):
            hasher.update(chunk)
    exe_sha = hasher.hexdigest()
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
        seed()
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP), "--args", "--datadir",
                        str(PROFILE), str(PROJECT)], check=True, timeout=20)
        pid = wait_orca()
        root = desktop.own(ax.application(pid))
        if ax.set_timeout(root, 2) != 0:
            raise RuntimeError("Cannot set AX timeout")
        window = wait_window(desktop, root, PROJECT.stem)
        before = digest(PROJECT)
        note("entry", {"pid": pid, "version": info.get("CFBundleShortVersionString"),
                       "bundle_build": info.get("CFBundleVersion", ""),
                       "executable_sha256": exe_sha, "fixture_before": before})
        fields = wait_for(lambda: layer_fields(desktop, window), "Layer fields did not load")
        values = [desktop.text(e, "AXValue") for e in fields]
        if values != ["0.4", "0.4"]:
            raise RuntimeError(f"Unexpected layer fields {values}")
        initial = fields[1]
        desktop.act(pid, initial, "AXFocused", ax.true_value)
        desktop.act(pid, initial, "AXValue", desktop.string(CONTROL_VALUE))
        desktop.act(pid, initial, "AXConfirm")
        wait_for(lambda: desktop.text(window, "AXTitle") == "*" + PROJECT.stem,
                 "Missing unsaved marker after the control edit")
        if desktop.text(initial, "AXValue") != CONTROL_VALUE:
            raise RuntimeError("Control edit readback mismatch")
        note("control_edit", {"field": "initial_layer_print_height",
                              "from": "0.4", "to": desktop.text(initial, "AXValue")})

        bar = desktop.attr(root, "AXMenuBar")
        file_menu = exactly_one(e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File")
        desktop.act(pid, file_menu, "AXPress")
        save = exactly_one(e for e in desktop.descendants(file_menu)
                           if desktop.text(e, "AXRole") == "AXMenuItem"
                           and desktop.text(e, "AXTitle") == "Save Project")
        wait_for(lambda: desktop.enabled(save), "Save Project did not become available")
        desktop.act(pid, save, "AXPress")
        after = wait_for(lambda: digest(PROJECT) if digest(PROJECT) != before else None,
                         "Save did not rewrite the project copy", 30)
        note("saved", {"fixture_after": after, "bytes": PROJECT.stat().st_size,
                       "title_after_save": desktop.text(window, "AXTitle")})


def main():
    error = None
    try:
        run()
    except BaseException:
        import traceback
        error = traceback.format_exc()
        RESULT["error"] = error
    RESULT["finished_at"] = time.time()
    for attempt_pid, _ in list(orca_processes().items()):
        try:
            os.kill(attempt_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 8
    while orca_processes() and time.monotonic() < deadline:
        time.sleep(0.4)
    RESULT["orca_left"] = sorted(orca_processes())
    RESULT["ok"] = error is None and RESULT.get("orca_left") == []
    (WORK / "result.json").write_text(json.dumps(RESULT, indent=1))
    print("[probe17] result:", json.dumps(RESULT)[:700], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
