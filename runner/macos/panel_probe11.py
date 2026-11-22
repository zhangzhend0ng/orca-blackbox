"""Probe 11 (final, 330 s fuse): context menus, dropdown, keyboard walk.

Remaining candidate channels to reach wall_loops on this build:
right-click context menus on the process preset row (wx menus are real
NSMenus, AX-exposed), the tree-page combobox dropdown, and outline keyboard
navigation. A wall-field hit runs the business edit + save + 3MF verify.
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
TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier",
              "AXPlaceholderValue", "AXValue", "AXRoleDescription")
RESULT = {"ok": False}
DOWN_KEY = 125
FUSE_SECONDS = 330
STARTED = time.time()


def note(key, value):
    RESULT[key] = value
    print(f"[probe11] {key}: {json.dumps(value)[:800]}", flush=True)


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


def safe_elements(desktop, scope, cap=2500):
    out, pending = [], [scope]
    while pending and len(out) < cap:
        element = pending.pop()
        out.append(element)
        try:
            pending.extend(reversed(desktop.children(element)))
        except RuntimeError:
            pass
    return out


def all_windows(desktop, root):
    return [w for w in desktop.children(root) if desktop.text(w, "AXRole") == "AXWindow"]


def wall_hits(desktop, root):
    hits = []
    for window in all_windows(desktop, root):
        for element in safe_elements(desktop, window):
            if desktop.text(element, "AXRole") != "AXTextField":
                continue
            help_text = (desktop.text(element, "AXHelp") or "").lower()
            if desktop.text(element, "AXValue") == "2" and ("wall" in help_text or "perimeter" in help_text):
                hits.append((window, element))
    return hits


def right_click(desktop, pid, root, window, title, x, depth):
    wid, origin = desktop.slice_window(pid, root, window, title)
    make_mouse = ax.selector(b"mouseEventWithType:location:modifierFlags:timestamp:windowNumber:context:eventNumber:clickCount:pressure:")
    for kind in (25, 26):  # rightMouseDown / rightMouseUp
        desktop.check_owned(pid, window)
        event = ax.mouse_event(ax.objc_class(b"NSEvent"), make_mouse, kind, ax.Point(x, 800 - depth),
                               0, time.monotonic(), wid, None, 1, 1, 1.0 if kind == 25 else 0.0)
        native = ax.event_cg(event, ax.selector(b"CGEvent"))
        ax.set_location(native, ax.Point(origin.x + x, origin.y + depth))
        ax.post_to_pid(pid, native)
        time.sleep(0.16)


def menus_now(desktop, root):
    found = []
    for child in desktop.children(root):
        if desktop.text(child, "AXRole") in ("AXMenu", "AXUnknown"):
            items = []
            for item in safe_elements(desktop, child, cap=120):
                title = desktop.text(item, "AXTitle")
                if title:
                    items.append(title)
            found.append({"role": desktop.text(child, "AXRole"),
                          "title": desktop.text(child, "AXTitle"), "items": items})
    return found


def key(pid, code, presses=1):
    for _ in range(presses):
        for pressed in (True, False):
            event = ax.create_key(None, code, pressed)
            if event:
                ax.post_to_pid(pid, event)
                time.sleep(0.04)
        time.sleep(0.12)


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
        if ax.set_timeout(root, 2) != 0:
            raise RuntimeError("Cannot set AX timeout")
        window = wait_window(desktop, root, PROJECT.stem)
        OUT.mkdir()
        note("entry", {"pid": pid})
        note("advanced", press_catching(desktop, pid, checkbox_at(desktop, window, 673, 689)))
        time.sleep(0.6)

        origin = desktop.position(window)
        # 1) right-click context menus on the process preset row.
        for rx, ry in ((500, 729), (726, 729), (752, 729)):
            if time.time() - STARTED > FUSE_SECONDS * 0.45:
                break
            try:
                right_click(desktop, pid, root, window, PROJECT.stem, rx - origin.x, ry - origin.y)
            except RuntimeError as error:
                note(f"rc{rx}_{ry}", str(error))
                continue
            time.sleep(0.9)
            menus = menus_now(desktop, root)
            note(f"rc{rx}_{ry}_menus", menus)
            edit_items = []
            for child in desktop.children(root):
                if desktop.text(child, "AXRole") != "AXMenu":
                    continue
                for item in safe_elements(desktop, child, cap=120):
                    title = desktop.text(item, "AXTitle")
                    if title and ("edit" in title.lower() or "编辑" in title):
                        edit_items.append(item)
            if edit_items:
                note("edit_item", [desktop.text(e, "AXTitle") for e in edit_items])
                press_catching(desktop, pid, edit_items[0])
                time.sleep(1.5)
                for index, stranger in enumerate(all_windows(desktop, root)):
                    info = {"title": desktop.text(stranger, "AXTitle"),
                            "elements": len(safe_elements(desktop, stranger, cap=30))}
                    if index:
                        (OUT / f"dialog_rc{index}.json").write_text(json.dumps(
                            [element_json(desktop, e) for e in safe_elements(desktop, stranger, cap=400)]))
                    note(f"window{index}", info)
                hits = wall_hits(desktop, root)
                if len(hits) == 1:
                    return business_edit(desktop, pid, root, window, hits[0][0], hits[0][1])
                key(pid, 53)  # Esc
                time.sleep(0.5)
            else:
                key(pid, 53)
                time.sleep(0.3)

        # 2) tree page combobox dropdown.
        note("tree_mode", press_catching(desktop, pid, checkbox_at(desktop, window, 453, 686)))
        time.sleep(1.0)
        combo = None
        for element in safe_elements(desktop, window):
            if desktop.text(element, "AXRole") != "AXTextField":
                continue
            try:
                point = desktop.position(element)
            except RuntimeError:
                continue
            if abs(point.x - 387) <= 10 and abs(point.y - 718) <= 12:
                combo = element
                break
        if combo is not None:
            note("combo_press", press_catching(desktop, pid, combo))
            time.sleep(1.0)
            note("combo_menus", menus_now(desktop, root))
            key(pid, 53)
            time.sleep(0.4)

        # 3) keyboard walk of the outline.
        rows = [e for e in safe_elements(desktop, window) if desktop.text(e, "AXRole") == "AXRow"]
        if rows:
            try:
                desktop.act(pid, rows[0], "AXFocused", ax.true_value)
            except RuntimeError as error:
                note("row_focus", str(error))
            for burst in range(6):
                key(pid, DOWN_KEY, 5)
                time.sleep(0.3)
                rows = [e for e in safe_elements(desktop, window) if desktop.text(e, "AXRole") == "AXRow"]
                note(f"kb{burst}", {"rows": len(rows),
                                    "ys": [round(desktop.position(r).y) for r in rows]})
                hits = wall_hits(desktop, root)
                if len(hits) == 1:
                    return business_edit(desktop, pid, root, window, hits[0][0], hits[0][1])
        note("outcome", "no channel reached a wall field")
    note("ok", False)


def business_edit(desktop, pid, root, window, owner_window, field):
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
    print("[probe11] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
