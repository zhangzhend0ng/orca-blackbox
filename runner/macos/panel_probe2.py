"""Probe 2: open the process-preset editor dialog and locate wall_loops.

Boot Orca on a writable fixture copy, press the y=729 preset-row icon at
x~372 (the only unscanned control there; the printer/filament analogues carry
help 'Click to edit preset'), dump every dialog that appears with full
attributes, then look for an AXTextField whose help mentions walls/perimeters
with value 2. If found, attempt the complete business edit in-dialog:
set 3, confirm, close the dialog, File > Save Project, and verify the saved
3MF carries wall_loops=3 with everything else preserved.
"""
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


def note(key, value):
    RESULT[key] = value
    print(f"[probe2] {key}: {json.dumps(value)[:500]}", flush=True)


def element_json(desktop, element):
    item = {"role": desktop.text(element, "AXRole")}
    for key in TEXT_ATTRS:
        item[key] = desktop.text(element, key)
    for key in ("AXEnabled", "AXFocused"):
        value = desktop.attr(element, key)
        item[key] = bool(value and ax.type_id(value) == ax.boolean_type and ax.bool_value(value))
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


def button_at(desktop, window, x, y, slack=15):
    hits = []
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXButton":
            continue
        point = desktop.position(element)
        if abs(point.x - x) <= slack and abs(point.y - y) <= slack:
            hits.append(element)
    return hits


def press_catching(desktop, pid, element):
    try:
        desktop.act(pid, element, "AXPress")
        return None
    except RuntimeError as error:
        # -25204: the press opened a modal and the AX reply timed out.
        return str(error)


def new_dialogs(desktop, root, before, main_title):
    current = windows_snapshot(desktop, root)
    strangers = []
    for window_info in current:
        if window_info in before:
            continue
        if window_info.get("subrole") == "AXStandardWindow" and window_info.get("title") == main_title:
            continue
        strangers.append(window_info)
    return strangers, current


def dump_dialog(desktop, root, info, name):
    for window in desktop.children(root, "AXWindows"):
        if (desktop.text(window, "AXSubrole") == info.get("subrole")
                and desktop.text(window, "AXTitle") == info.get("title")
                and desktop.text(window, "AXRole") == info.get("role")):
            payload = tree(desktop, window)
            (OUT / name).write_text(json.dumps(payload))
            return window, payload
    return None, None


def find_wall_field(payload):
    for index, element in enumerate(payload):
        if element.get("role") != "AXTextField":
            continue
        help_text = (element.get("AXHelp") or "").lower()
        if ("wall" in help_text or "perimeter" in help_text or "shell loop" in help_text) \
                and element.get("AXValue") == "2":
            return index, element
    return None, None


def confirm_button(payload):
    # Prefer an explicit OK/confirm affordance, else the rightmost button in
    # the dialog's bottom band.
    best = None
    for element in payload:
        if element.get("role") != "AXButton":
            continue
        label = (element.get("AXHelp") or "") + (element.get("AXTitle") or "")
        if any(word in label.lower() for word in ("ok", "confirm", "save")) \
                and "cancel" not in label.lower():
            return element
        if best is None or element.get("x", 0) > best.get("x", 0):
            best = element
    return best


def save_project(desktop, pid, root, window):
    bar = desktop.attr(root, "AXMenuBar")
    file_menu = [e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File"]
    desktop.act(pid, file_menu[0], "AXPress")
    save = [e for e in desktop.descendants(file_menu[0])
            if desktop.text(e, "AXRole") == "AXMenuItem" and desktop.text(e, "AXTitle") == "Save Project"]
    end = time.monotonic() + 5
    while time.monotonic() < end and not desktop.enabled(save[0]):
        time.sleep(0.2)
    desktop.act(pid, save[0], "AXPress")
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if desktop.text(window, "AXTitle") == PROJECT.stem and PROJECT.stat().st_mtime > STARTED:
            return True
        time.sleep(0.4)
    return False


def run():
    global STARTED
    STARTED = time.time()
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
        note("entry", {"pid": pid, "title": desktop.text(window, "AXTitle")})
        press_advanced(desktop, pid, window)

        before = windows_snapshot(desktop, root)
        attempts = []
        dialog_window = None
        dialog_payload = None
        # 1) AXPress the unscanned preset-row icon at (372, 729).
        for x, y in ((372, 729),):
            for element in button_at(desktop, window, x, y):
                attempts.append({"target": [x, y], "press_error": press_catching(desktop, pid, element)})
        time.sleep(1.5)
        strangers, after = new_dialogs(desktop, root, before, PROJECT.stem)
        attempts.append({"after_press_windows": after})
        # 2) Coordinate clicks along the preset row as fallback.
        fallbacks = ((700, 729), (714, 729), (688, 729))
        for x, y in fallbacks:
            if strangers:
                break
            origin = desktop.position(window)
            try:
                desktop.click_point(pid, root, window, PROJECT.stem, x - origin.x, y - origin.y)
            except RuntimeError as error:
                attempts.append({"click": [x, y], "error": str(error)})
            time.sleep(1.2)
            strangers, after = new_dialogs(desktop, root, before, PROJECT.stem)
            attempts.append({"click": [x, y], "windows": after})
        note("open_attempts", attempts)

        for index, info in enumerate(strangers):
            handle, payload = dump_dialog(desktop, root, info, f"dialog{index}.json")
            if payload is None:
                continue
            wall_index, wall = find_wall_field(payload)
            note(f"dialog{index}", {"info": info, "elements": len(payload),
                                    "wall_field_index": wall_index,
                                    "wall": wall})
            if wall is not None and dialog_window is None:
                dialog_window, dialog_payload = handle, payload

        if dialog_window is None:
            note("outcome", "no dialog exposing a wall field with value 2")
            return
        # 3) Perform the business edit inside the preset dialog.
        fields = [e for e in desktop.descendants(dialog_window)
                  if desktop.text(e, "AXRole") == "AXTextField"
                  and (desktop.text(e, "AXHelp") or "").lower().find("wall") >= 0
                  and desktop.text(e, "AXValue") == "2"]
        if len(fields) != 1:
            note("edit", {"error": "wall field count", "count": len(fields)})
            return
        field = fields[0]
        desktop.act(pid, field, "AXFocused", ax.true_value)
        desktop.act(pid, field, "AXValue", desktop.string("3"))
        desktop.act(pid, field, "AXConfirm")
        time.sleep(0.5)
        readback = desktop.text(field, "AXValue")
        dirty = desktop.text(window, "AXTitle")
        note("edit", {"value_after": readback, "main_title_after_edit": dirty})
        if readback != "3":
            return
        ok = confirm_button(dialog_payload)
        if ok is None:
            note("confirm", "no button in dialog payload")
            return
        handles = [e for e in desktop.descendants(dialog_window)
                   if desktop.text(e, "AXRole") == "AXButton"]
        target = None
        for element in handles:
            point = desktop.position(element)
            if abs(point.x - ok.get("x", -1)) <= 2 and abs(point.y - ok.get("y", -1)) <= 2:
                target = element
                break
        if target is None:
            note("confirm", {"error": "button handle not refound", "chosen": ok})
            return
        note("confirm", {"press_error": press_catching(desktop, pid, target), "chosen": ok})
        time.sleep(1.5)
        note("after_confirm", {"windows": windows_snapshot(desktop, root),
                               "main_title": desktop.text(window, "AXTitle")})
        if desktop.text(window, "AXTitle") != "*" + PROJECT.stem:
            note("outcome", "project not dirty after dialog confirm")
            return
        saved = save_project(desktop, pid, root, window)
        note("saved", saved)
        if not saved:
            return
        with zipfile.ZipFile(PROJECT) as archive:
            config = json.loads(archive.read("Metadata/project_settings.config"))
        with zipfile.ZipFile(WORK / "probe-original.3mf") as archive:
            original = json.loads(archive.read("Metadata/project_settings.config"))
        changed = {key: [original.get(key), config.get(key)] for key in config
                   if key in original and config[key] != original[key]}
        added = [key for key in config if key not in original]
        removed = [key for key in original if key not in config]
        note("outcome", {"wall_loops": config.get("wall_loops"), "changed": changed,
                         "added": added[:20], "removed": removed[:20]})
    note("ok", RESULT.get("outcome") is not None and isinstance(RESULT.get("outcome"), dict)
         and RESULT["outcome"].get("wall_loops") == "3")


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
    print("[probe2] result:", json.dumps(RESULT)[:800], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
