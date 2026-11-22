"""Probe 4: type into the preset search field with real key events.

The search field exposed by 'Search in preset' accepts AXValue writes but
they do not fire wxEVT_TEXT, so the parameter list never filters. This probe
focuses the field and types 'wall' via CGEventKeyboardSetUnicodeString posted
to the Orca pid (the same channel post_key uses), then looks for a
wall-loops field (value 2, wall/perimeter help) in every window including
the popup. On a hit it runs the full business edit and 3MF verification.
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
set_unicode = ax.bind(ax.cg, "CGEventKeyboardSetUnicodeString", None, ax.ptr, ct.c_ulong, ct.c_wchar_p)
STARTED = time.time()


def note(key, value):
    RESULT[key] = value
    print(f"[probe4] {key}: {json.dumps(value)[:700]}", flush=True)


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


def type_text(pid, text):
    for pressed in (True, False):
        event = ax.create_key(None, 0, pressed)
        if not event:
            raise RuntimeError("Keyboard event is unavailable")
        set_unicode(event, len(text), text)
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(0.4)


def all_fields(desktop, root):
    fields = []
    for window in desktop.children(root, "AXWindows"):
        for element in desktop.descendants(window):
            if desktop.text(element, "AXRole") == "AXTextField":
                fields.append((window, element))
    fields.sort(key=lambda pair: desktop.position(pair[1]).y)
    return fields


def windows_snapshot(desktop, root):
    return [{"subrole": desktop.text(w, "AXSubrole"), "title": desktop.text(w, "AXTitle"),
             "role": desktop.text(w, "AXRole")} for w in desktop.children(root, "AXWindows")]


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


def press_advanced(desktop, pid, window):
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXCheckBox":
            continue
        point = desktop.position(element)
        if abs(point.x - 673) <= 40 and abs(point.y - 689) <= 25:
            desktop.act(pid, element, "AXPress")
            time.sleep(0.6)
            return
    raise RuntimeError("Advanced checkbox not found")


def button_at(desktop, window, x, y, slack=12):
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXButton":
            continue
        point = desktop.position(element)
        if abs(point.x - x) <= slack and abs(point.y - y) <= slack:
            return element
    return None


def press_catching(desktop, pid, element):
    try:
        desktop.act(pid, element, "AXPress")
        return None
    except RuntimeError as error:
        return str(error)


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


def find_search_field(desktop, window):
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXTextField":
            continue
        if "Search in preset" in desktop.text(element, "AXPlaceholderValue"):
            return element
    return None


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
        press_advanced(desktop, pid, window)

        search_button = button_at(desktop, window, 752, 729)
        if search_button is None:
            note("error", "search button not found")
            return
        note("search_press", press_catching(desktop, pid, search_button))
        time.sleep(1.0)
        search_field = find_search_field(desktop, window)
        if search_field is None:
            note("outcome", "search field not exposed")
            return
        note("search_field", element_json(desktop, search_field))

        # Type the filter with real key events so wxEVT_TEXT fires.
        desktop.act(pid, search_field, "AXFocused", ax.true_value)
        type_text(pid, "wall")
        time.sleep(1.2)
        note("search_value", desktop.text(search_field, "AXValue"))
        note("windows_typed", windows_snapshot(desktop, root))
        (OUT / "tree_filtered.json").write_text(json.dumps(tree(desktop, window)))
        for extra in desktop.children(root, "AXWindows"):
            if desktop.text(extra, "AXSubrole") != "AXStandardWindow":
                (OUT / ("popup_" + (desktop.text(extra, "AXTitle") or "none") + ".json")
                 ).write_text(json.dumps(tree(desktop, extra)))

        fields = [(w, e) for w, e in all_fields(desktop, root)
                  if e is not search_field]
        catalog = [{"window": desktop.text(w, "AXTitle") or desktop.text(w, "AXSubrole"),
                    "y": round(desktop.position(e).y), "value": desktop.text(e, "AXValue"),
                    "help": (desktop.text(e, "AXHelp") or "")[:70]} for w, e in fields]
        note("fields_after_filter", catalog)
        wall = [e for w, e in fields
                if desktop.text(e, "AXValue") == "2"
                and ("wall" in (desktop.text(e, "AXHelp") or "").lower()
                     or "perimeter" in (desktop.text(e, "AXHelp") or "").lower())]
        if len(wall) != 1:
            note("outcome", {"wall_candidates": len(wall)})
            return

        # Business edit in the filtered sidebar.
        field = wall[0]
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
    note("ok", isinstance(RESULT.get("outcome"), dict) and RESULT["outcome"].get("wall_loops") == "3")


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
    print("[probe4] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
