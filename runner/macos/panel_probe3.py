"""Probe 3: filter the sidebar via 'Search in preset', then edit wall_loops.

Press the process-row search icon (752, 729; help 'Search in preset'), find
the search field it exposes (AX dump + system-wide focused element), set it
to 'wall', and check whether the flat parameter list then exposes a
wall-loops text field with value 2. If it does: run the complete business
edit (set 3, confirm, dirty check, File > Save Project) and verify the saved
3MF changed wall_loops 2->3 with everything else preserved.
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
ESC = 53
TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier",
              "AXPlaceholderValue", "AXValue", "AXRoleDescription")
RESULT = {"ok": False}
create_systemwide = ax.bind(ax.ax, "AXUIElementCreateSystemWide", ax.ptr)
STARTED = time.time()


def note(key, value):
    RESULT[key] = value
    print(f"[probe3] {key}: {json.dumps(value)[:600]}", flush=True)


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


def text_fields(desktop, scope):
    fields = [e for e in desktop.descendants(scope) if desktop.text(e, "AXRole") == "AXTextField"]
    fields.sort(key=lambda e: desktop.position(e).y)
    return fields


def focused_element(desktop, pid):
    systemwide = create_systemwide()
    handle = desktop.attr(systemwide, "AXFocusedUIElement")
    if handle:
        try:
            desktop.check_owned(pid, handle)
            return element_json(desktop, handle)
        except RuntimeError:
            return {"outside": element_json(desktop, handle)}
    return None


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
        before_fields = [(round(desktop.position(f).y), desktop.text(f, "AXValue"))
                         for f in text_fields(desktop, window)]
        note("fields_before", len(before_fields))

        # 1) open the preset search.
        search_button = button_at(desktop, window, 752, 729)
        if search_button is None:
            note("error", "search button not found at (752, 729)")
            return
        note("search_press", press_catching(desktop, pid, search_button))
        time.sleep(1.2)
        note("windows_after", windows_snapshot(desktop, root))
        note("focused_after", focused_element(desktop, pid))
        (OUT / "tree_after_search.json").write_text(json.dumps(tree(desktop, window)))
        candidates = [e for e in desktop.descendants(window)
                      if desktop.text(e, "AXRole") == "AXTextField"
                      and (round(desktop.position(e).y), desktop.text(e, "AXValue")) not in before_fields]
        note("new_fields", [element_json(desktop, e) for e in candidates])

        # 2) search in a popup window too, if one appeared.
        search_field = candidates[0] if len(candidates) == 1 else None
        if search_field is None:
            for extra in desktop.children(root, "AXWindows"):
                if desktop.text(extra, "AXSubrole") == "AXStandardWindow":
                    continue
                popup_fields = text_fields(desktop, extra)
                if popup_fields:
                    (OUT / "popup_tree.json").write_text(json.dumps(tree(desktop, extra)))
                    if len(popup_fields) == 1:
                        search_field = popup_fields[0]
                        note("search_field_in_popup", element_json(desktop, search_field))
                        break
        if search_field is None:
            note("outcome", "no search field exposed after pressing Search in preset")
            return

        # 3) type the filter and look for the wall-loops field.
        desktop.act(pid, search_field, "AXFocused", ax.true_value)
        desktop.act(pid, search_field, "AXValue", desktop.string("wall"))
        desktop.act(pid, search_field, "AXConfirm")
        time.sleep(1.0)
        (OUT / "tree_filtered.json").write_text(json.dumps(tree(desktop, window)))
        fields = [(e, desktop.text(e, "AXValue"), (desktop.text(e, "AXHelp") or "").lower())
                  for e in text_fields(desktop, window)]
        note("fields_filtered", [{"y": round(desktop.position(e).y), "value": v, "help": h[:60]}
                                 for e, v, h in fields])
        wall = [e for e, v, h in fields if v == "2" and ("wall" in h or "perimeter" in h)]
        if len(wall) != 1:
            note("outcome", {"wall_candidates": len(wall)})
            return

        # 4) business edit in the sidebar.
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
    print("[probe3] result:", json.dumps(RESULT)[:800], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
