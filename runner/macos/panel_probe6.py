"""Probe 6: walk every sidebar tab and scroll each page hunting wall_loops.

Evidence so far: the tab strip sits at y~703 (clicks at x 465/495/525/555
switch pages; x 390-450 is the already-selected flat page). Non-flat pages
expose only the visible slice of their list, so each page is walked with the
scrollbar's bottom arrow. Hit criterion: an AXTextField with value '2' and
wall/perimeter help; on a hit the probe edits to 3, saves the project and
verifies the 3MF diff (wall_loops 2->3 only).
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
TAB_Y = 703
TAB_XS = (400, 465, 495, 525, 555, 585, 615, 645)
RESULT = {"ok": False}
STARTED = time.time()


def note(key, value):
    RESULT[key] = value
    print(f"[probe6] {key}: {json.dumps(value)[:700]}", flush=True)


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


def signature(desktop, window):
    fields = []
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") == "AXTextField":
            fields.append((round(desktop.position(element).y), desktop.text(element, "AXValue")[:30]))
    fields.sort()
    return fields


def wall_candidates(desktop, window):
    hits = []
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXTextField":
            continue
        help_text = (desktop.text(element, "AXHelp") or "").lower()
        if desktop.text(element, "AXValue") == "2" and ("wall" in help_text or "perimeter" in help_text):
            hits.append(element)
    return hits


def scroll_arrow(desktop, window):
    """Bottom arrow of the panel scrollbar (largest y among small arrows)."""
    best = None
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXButton":
            continue
        description = desktop.text(element, "AXRoleDescription")
        if "arrow" not in description:
            continue
        point = desktop.position(element)
        if best is None or point.y > best[0]:
            best = (point.y, element)
    return best[1] if best else None


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
        advanced = None
        for element in desktop.descendants(window):
            if desktop.text(element, "AXRole") == "AXCheckBox":
                point = desktop.position(element)
                if abs(point.x - 673) <= 40 and abs(point.y - 689) <= 25:
                    advanced = element
        note("advanced", press_catching(desktop, pid, advanced) if advanced else "missing")
        time.sleep(0.6)
        origin = desktop.position(window)
        baseline = signature(desktop, window)
        note("baseline_fields", len(baseline))

        tab_map = []
        for tab_x in TAB_XS[1:]:
            # Reset to the flat page, then open the target tab.
            for attempt in range(2):
                try:
                    desktop.click_point(pid, root, window, PROJECT.stem,
                                        TAB_XS[0] - origin.x, TAB_Y - origin.y)
                except RuntimeError:
                    return note("outcome", "reset click failed")
                time.sleep(0.45)
                if signature(desktop, window) == baseline:
                    break
            try:
                desktop.click_point(pid, root, window, PROJECT.stem, tab_x - origin.x, TAB_Y - origin.y)
            except RuntimeError as error:
                tab_map.append({"x": tab_x, "error": str(error)})
                continue
            time.sleep(0.7)
            page = {"x": tab_x, "top": signature(desktop, window)}
            hits = wall_candidates(desktop, window)
            steps = 0
            arrow = scroll_arrow(desktop, window)
            stable = 0
            while not hits and arrow is not None and steps < 60 and stable < 2:
                press_catching(desktop, pid, arrow)
                time.sleep(0.22)
                steps += 1
                current = signature(desktop, window)
                if current == page.get("last"):
                    stable += 1
                else:
                    stable = 0
                page["last"] = current
                hits = wall_candidates(desktop, window)
            page["steps"] = steps
            page["wall_hits"] = len(hits)
            tab_map.append({k: v for k, v in page.items() if k != "last"})
            if len(hits) == 1:
                (OUT / "tree_strength.json").write_text(json.dumps(tree(desktop, window)))
                note("tab_map", tab_map)
                return business_edit(desktop, pid, root, window, hits[0], tab_x)
            if len(hits) > 1:
                note("ambiguous_hits", len(hits))
        note("tab_map", tab_map)
        note("outcome", "no wall field on any walked tab page")
    note("ok", False)


def business_edit(desktop, pid, root, window, field, tab_x):
    note("wall_field", element_json(desktop, field))
    desktop.act(pid, field, "AXFocused", ax.true_value)
    desktop.act(pid, field, "AXValue", desktop.string("3"))
    desktop.act(pid, field, "AXConfirm")
    time.sleep(0.6)
    readback = desktop.text(field, "AXValue")
    title = desktop.text(window, "AXTitle")
    note("edit", {"value_after": readback, "title": title, "tab_x": tab_x})
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
    print("[probe6] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
