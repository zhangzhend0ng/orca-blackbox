"""Probe 7: wheel-scroll the full parameter tree to wall_loops, then close.

The (453, 686) checkbox toggles the sidebar from the 24-field flat page to
the full parameter tree (real AXTextFields with value + tooltip help, e.g.
skirt angle, spiral). The scrollbar arrows are inert on that page, so this
probe drives it with CGEventCreateScrollWheelEvent posted to the Orca pid at
the panel location, walking the whole list top-to-bottom while inventorying
every field. On finding the value-2 wall/perimeter field it performs the
business edit, saves and verifies the 3MF diff.
"""
import ctypes as ct
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import zipfile

import accessibility as ax

WORK = Path(__file__).resolve().parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
PROJECT = WORK / "probe.3mf"
PROFILE = WORK / "datadir"
OUT = WORK / "out"
TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier",
              "AXPlaceholderValue", "AXValue", "AXRoleDescription")
RESULT = {"ok": False}
create_scroll = ax.bind(ax.cg, "CGEventCreateScrollWheelEvent", ax.ptr, ax.ptr,
                        ct.c_uint32, ct.c_uint32, ct.c_int32)
STARTED = time.time()
PANEL_POINT = (600.0, 850.0)  # absolute; inside the parameter viewport


def note(key, value):
    RESULT[key] = value
    print(f"[probe7] {key}: {json.dumps(value)[:700]}", flush=True)


def element_json(desktop, element):
    item = {"role": desktop.text(element, "AXRole")}
    for key in TEXT_ATTRS:
        item[key] = desktop.text(element, key)
    try:
        point = desktop.position(element)
        item["x"], item["y"] = round(point.x, 1), round(point.y, 1)
    except RuntimeError:
        pass
    return item


def tree(desktop, root_element, cap=1200):
    out = []
    for element in desktop.descendants(root_element):
        out.append(element_json(desktop, element))
        if len(out) >= cap:
            out.append({"role": "TRUNCATED", "count": len(out)})
            break
    return out


def wheel(pid, delta):
    event = create_scroll(None, 0, 1, delta)  # kCGScrollEventUnitPixel
    if not event:
        raise RuntimeError("Scroll event is unavailable")
    ax.set_location(event, ax.Point(PANEL_POINT[0], PANEL_POINT[1]))
    ax.post_to_pid(pid, event)


def inventory(desktop, window):
    rows = []
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXTextField":
            continue
        rows.append((element, desktop.text(element, "AXValue"),
                     (desktop.text(element, "AXHelp") or "").lower()))
    return rows


def wall_field(rows):
    hits = [e for e, value, help_text in rows
            if value == "2" and ("wall" in help_text or "perimeter" in help_text)]
    return hits


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


def press_catching(desktop, pid, element):
    try:
        desktop.act(pid, element, "AXPress")
        return None
    except RuntimeError as error:
        return str(error)


def checkbox_at(desktop, window, x, y, slack=12):
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXCheckBox":
            continue
        point = desktop.position(element)
        if abs(point.x - x) <= slack and abs(point.y - y) <= slack:
            return element
    return None


def save_project(desktop, pid, root, window):
    bar = desktop.attr(root, "AXMenuBar")
    file_menu = [e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File"][0]
    desktop.act(pid, file_menu, "AXPress")
    save = [e for e in desktop.descendants(file_menu)
            if desktop.text(e, "AXRole") == "AXMenuItem" and desktop.text(e, "AXTitle") == "Save Project"][0]
    end = time.monotonic() + 5
    while time.monotonic() < end and not desktop.enabled(save):
        time.sleep(0.2)
    desktop.act(pid, save, "AXPress")
    end = time.monotonic() + 25
    while time.monotonic() < end:
        if desktop.text(window, "AXTitle") == PROJECT.stem and PROJECT.stat().st_mtime > STARTED:
            return True
        time.sleep(0.4)
    return False


def run():
    console_uid = os.stat("/dev/console").st_uid
    if not ax.trusted():
        raise RuntimeError("Accessibility permission is missing")
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
        seed()
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP), "--args", "--datadir",
                        str(PROFILE), str(PROJECT)], check=True, timeout=20)
        pid = wait_orca()
        root = desktop.own(ax.application(pid))
        if ax.set_timeout(root, 5) != 0:
            raise RuntimeError("Cannot set AX timeout")
        window = wait_window(desktop, root, PROJECT.stem)
        OUT.mkdir()
        note("entry", {"pid": pid})
        advanced = checkbox_at(desktop, window, 673, 689)
        note("advanced", press_catching(desktop, pid, advanced) if advanced else "missing")
        time.sleep(0.6)
        tree_mode = checkbox_at(desktop, window, 453, 686)
        if tree_mode is None:
            note("error", "tree-mode checkbox not found at (453, 686)")
            return
        note("tree_mode_press", press_catching(desktop, pid, tree_mode))
        time.sleep(1.0)

        # Wheel up hard first: page into a known top state.
        for _ in range(12):
            wheel(pid, 600)
            time.sleep(0.05)
        time.sleep(0.6)
        seen = {}
        stable = 0
        ticks = 0
        hit = None
        while ticks < 220 and stable < 6 and hit is None:
            wheel(pid, -240)
            ticks += 1
            time.sleep(0.09)
            if ticks % 3:
                continue
            rows = inventory(desktop, window)
            key = tuple(sorted((round(desktop.position(e).y), v, h[:40]) for e, v, h in rows))
            if key == seen.get("last"):
                stable += 1
            else:
                stable = 0
            seen["last"] = key
            for element, value, help_text in rows:
                tag = (value, help_text[:60])
                seen[tag] = seen.get(tag, 0) + 1
            hits = wall_field(rows)
            if len(hits) == 1:
                hit = hits[0]
                break
            if len(hits) > 1:
                note("ambiguous", len(hits))
                break
        entries = [k for k in seen if isinstance(k, tuple)]
        note("walk", {"ticks": ticks, "distinct_fields": len(entries)})
        (OUT / "tree_page.json").write_text(json.dumps(tree(desktop, window)))
        (OUT / "inventory.json").write_text(json.dumps(
            [{"value": v, "help": h} for (v, h) in sorted(entries, key=lambda t: (t[1], t[0]))
             if not str(v).startswith("<wx")], indent=1))
        if hit is None:
            note("outcome", "wall field not found during wheel walk")
            return
        return business_edit(desktop, pid, root, window, hit)


def business_edit(desktop, pid, root, window, field):
    note("wall_field", element_json(desktop, field))
    desktop.act(pid, field, "AXFocused", ax.true_value)
    desktop.act(pid, field, "AXValue", desktop.string("3"))
    desktop.act(pid, field, "AXConfirm")
    time.sleep(0.6)
    readback = desktop.text(field, "AXValue")
    title = desktop.text(window, "AXTitle")
    note("edit", {"value_after": readback, "title": title})
    if readback != "3" or title != "*" + PROJECT.stem:
        note("outcome", "edit did not take or project not dirty")
        return
    note("saved", save_project(desktop, pid, root, window))
    with zipfile.ZipFile(PROJECT) as archive:
        config = json.loads(archive.read("Metadata/project_settings.config"))
    with zipfile.ZipFile(WORK / "probe-original.3mf") as archive:
        original = json.loads(archive.read("Metadata/project_settings.config"))
    changed = {key: [original.get(key), config.get(key)] for key in config
               if key in original and config[key] != original[key]}
    note("outcome", {"wall_loops": config.get("wall_loops"), "changed": changed})
    RESULT["ok"] = isinstance(RESULT.get("outcome"), dict) and RESULT["outcome"].get("wall_loops") == "3"


def main():
    shutil.copy2(PROJECT, WORK / "probe-original.3mf")
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
    (WORK / "result.json").write_text(json.dumps(RESULT, indent=1))
    print("[probe7] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
