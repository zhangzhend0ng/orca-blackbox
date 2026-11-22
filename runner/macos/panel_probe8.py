"""Probe 8: find a working scroll channel on the tree page, then hunt walls.

The tree page (checkbox 453,686) virtualizes its parameter rows and the
channels tried so far (scrollbar-arrow AXPress, session wheel) did not move
it. This probe A/B-tests five channels against an objective detector (the
y position of the chip row at (379,742) plus the exposed field inventory):
wheel events, both bottom-corner buttons, PageDown keys after focusing a
field, and a direct AXValue set on the scrollbar. The first channel that
moves the page walks the full list hunting the value-2 wall/perimeter
field; a hit runs the business edit and 3MF verification.
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
create_systemwide = ax.bind(ax.ax, "AXUIElementCreateSystemWide", ax.ptr)
PAGE_DOWN, TAB_KEY = 125, 48
STARTED = time.time()


def note(key, value):
    RESULT[key] = value
    print(f"[probe8] {key}: {json.dumps(value)[:700]}", flush=True)


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


def safe_elements(desktop, scope, cap=3000):
    out, pending = [], [scope]
    while pending and len(out) < cap:
        element = pending.pop()
        out.append(element)
        try:
            pending.extend(reversed(desktop.children(element)))
        except RuntimeError:
            pass
    return out


def fields_now(desktop, window):
    rows = []
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") == "AXTextField":
            try:
                rows.append((element, desktop.text(element, "AXValue"),
                             (desktop.text(element, "AXHelp") or "").lower(),
                             round(desktop.position(element).y)))
            except RuntimeError:
                pass
    return rows


def probe_y(desktop, window):
    """y of the first custom chip field, or None."""
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") != "AXTextField":
            continue
        try:
            point = desktop.position(element)
        except RuntimeError:
            continue
        if abs(point.x - 379) <= 6 and abs(point.y - 742) <= 30:
            return point.y
    return None


def wall_hits(rows):
    return [e for e, value, help_text, _ in rows
            if value == "2" and ("wall" in help_text or "perimeter" in help_text)]


def wheel(pid, delta, x=600.0, y=830.0):
    event = create_scroll(None, 0, 1, delta)
    if event:
        ax.set_location(event, ax.Point(x, y))
        ax.post_to_pid(pid, event)


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
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") != "AXCheckBox":
            continue
        point = desktop.position(element)
        if abs(point.x - x) <= slack and abs(point.y - y) <= slack:
            return element
    return None


def key(pid, code):
    for pressed in (True, False):
        event = ax.create_key(None, code, pressed)
        if event:
            ax.post_to_pid(pid, event)
            time.sleep(0.04)
    time.sleep(0.15)


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
        note("advanced", press_catching(desktop, pid, checkbox_at(desktop, window, 673, 689)))
        time.sleep(0.6)
        tree_mode = checkbox_at(desktop, window, 453, 686)
        note("tree_mode", press_catching(desktop, pid, tree_mode))
        time.sleep(1.2)
        rows = fields_now(desktop, window)
        note("tree_top", [{"y": y, "value": v[:20], "help": h[:40]} for _, v, h, y in rows])
        (OUT / "tree_top.json").write_text(json.dumps(
            [element_json(desktop, e) for e in safe_elements(desktop, window, cap=600)]))

        # A/B the scroll channels against the chip-row y detector.
        channels = {}
        base_y = probe_y(desktop, window)
        # a) wheel down
        for _ in range(5):
            wheel(pid, -400)
            time.sleep(0.12)
        time.sleep(0.5)
        channels["wheel"] = {"before": base_y, "after": probe_y(desktop, window),
                             "fields": len(fields_now(desktop, window))}
        if probe_y(desktop, window) == base_y:
            # b) the two bottom-corner buttons
            for label, (bx, by) in (("b878", (766, 878)), ("b856", (766, 856))):
                pressed = 0
                for element in safe_elements(desktop, window):
                    if desktop.text(element, "AXRole") != "AXButton":
                        continue
                    try:
                        point = desktop.position(element)
                    except RuntimeError:
                        continue
                    if abs(point.x - bx) <= 4 and abs(point.y - by) <= 4:
                        press_catching(desktop, pid, element)
                        pressed += 1
                        time.sleep(0.25)
                        if pressed >= 5:
                            break
                time.sleep(0.5)
                channels[label] = {"pressed": pressed, "after": probe_y(desktop, window),
                                   "fields": len(fields_now(desktop, window))}
                if probe_y(desktop, window) != base_y:
                    break
        if probe_y(desktop, window) == base_y:
            # c) PageDown with a field focused
            first = fields_now(desktop, window)
            if first:
                desktop.act(pid, first[0][0], "AXFocused", ax.true_value)
                for _ in range(5):
                    key(pid, PAGE_DOWN)
                time.sleep(0.5)
                channels["pagedown"] = {"after": probe_y(desktop, window),
                                        "fields": len(fields_now(desktop, window))}
        if probe_y(desktop, window) == base_y:
            # d) scrollbar AXValue jump
            for element in safe_elements(desktop, window):
                if desktop.text(element, "AXRole") != "AXScrollBar":
                    continue
                try:
                    desktop.act(pid, element, "AXValue", ax.ptr(100))
                    channels["scrollbar_set"] = {"after": probe_y(desktop, window),
                                                 "fields": len(fields_now(desktop, window))}
                except RuntimeError as error:
                    channels["scrollbar_set"] = str(error)
                break
        note("channels", channels)
        moved = probe_y(desktop, window) != base_y or any(
            isinstance(v, dict) and v.get("fields") != channels["wheel"]["fields"]
            for v in channels.values() if isinstance(v, dict))

        # Hunt: repeatedly apply whichever channel changed the field set.
        hits = wall_hits(fields_now(desktop, window))
        seen = {}
        rounds = 0
        while not hits and rounds < 120:
            before = {(v, h[:40]) for _, v, h, _ in fields_now(desktop, window)}
            wheel(pid, -400)
            key(pid, PAGE_DOWN)
            rounds += 1
            time.sleep(0.15)
            if rounds % 4:
                continue
            rows = fields_now(desktop, window)
            for _, value, help_text, _ in rows:
                seen[(value, help_text[:70])] = True
            hits = wall_hits(rows)
            current = {(v, h[:40]) for _, v, h, _ in rows}
            if current == before and rounds > 12:
                # nothing new for a full probe cycle of both channels
                stale = seen.get("__stale__", 0) + 1
                seen["__stale__"] = stale
                if stale >= 3:
                    break
            else:
                seen["__stale__"] = 0
        note("hunt", {"rounds": rounds, "distinct": len([k for k in seen if isinstance(k, tuple)])})
        (OUT / "hunt_inventory.json").write_text(json.dumps(
            [{"value": v, "help": h} for (v, h) in sorted(
                [k for k in seen if isinstance(k, tuple)], key=lambda t: (t[1], t[0]))
             if not str(v).startswith("<wx")], indent=1))
        if len(hits) == 1:
            (OUT / "tree_hit.json").write_text(json.dumps(
                [element_json(desktop, e) for e in safe_elements(desktop, window, cap=600)]))
            return business_edit(desktop, pid, root, window, hits[0])
        note("outcome", {"hits": len(hits), "moved": moved})
    note("ok", False)


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
    print("[probe8] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
