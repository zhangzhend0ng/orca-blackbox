"""Probe 5: sweep the unclicked band above the parameter list for the tab row.

The prior grid covered y 748-796 only. The remaining space between the
Process header (689), preset row (729) and the first field (832) is
y 698-747. Also presses the unlabeled checkbox at (453, 686) to identify it.
Hit criterion: any AXTextField reading '2' with wall/perimeter help appears;
on a hit the probe runs the full business edit and 3MF verification.
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
STARTED = time.time()


def note(key, value):
    RESULT[key] = value
    print(f"[probe5] {key}: {json.dumps(value)[:600]}", flush=True)


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
    fields, checks, statics = [], [], []
    for element in desktop.descendants(window):
        role = desktop.text(element, "AXRole")
        if role == "AXTextField":
            fields.append((round(desktop.position(element).y), desktop.text(element, "AXValue")))
        elif role == "AXCheckBox":
            checks.append(round(desktop.position(element).y))
        elif role == "AXStaticText":
            statics.append(desktop.text(element, "AXValue"))
    fields.sort()
    return {"fields": fields, "checks": sorted(checks), "statics": sorted(statics)}


def wall_candidates(desktop, window):
    hits = []
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXTextField":
            continue
        help_text = (desktop.text(element, "AXHelp") or "").lower()
        if desktop.text(element, "AXValue") == "2" and ("wall" in help_text or "perimeter" in help_text):
            hits.append(element)
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


def checkbox_at(desktop, window, x, y, slack=12):
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXCheckBox":
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
        # Advanced ON so the list is the known 24-field baseline.
        advanced = checkbox_at(desktop, window, 673, 689)
        note("advanced_press", press_catching(desktop, pid, advanced) if advanced else "missing")
        time.sleep(0.6)
        baseline = signature(desktop, window)
        note("baseline", {"fields": len(baseline["fields"])})

        # Mystery checkbox at (453, 686): identify it, then restore.
        mystery = checkbox_at(desktop, window, 453, 686)
        if mystery is not None:
            note("mystery_press", press_catching(desktop, pid, mystery))
            time.sleep(1.0)
            after = signature(desktop, window)
            note("mystery_effect", {"fields": len(after["fields"]),
                                    "changed": after != baseline})
            hits = wall_candidates(desktop, window)
            if after != baseline:
                (OUT / "tree_mystery_on.json").write_text(json.dumps(tree(desktop, window)))
                note("mystery_hits", len(hits))
                if len(hits) == 1:
                    return business_edit(desktop, pid, root, window, hits[0])
                desktop.act(pid, mystery, "AXPress")
                time.sleep(0.6)
                note("mystery_restored", signature(desktop, window) == baseline)

        # Grid over the unswept band y 703-747 (and re-check 750-760).
        origin = desktop.position(window)
        changes = []
        hit = None
        for y in (703, 710, 717, 724, 733, 740, 747, 753):
            for x in range(390, 651, 15):
                try:
                    desktop.click_point(pid, root, window, PROJECT.stem, x - origin.x, y - origin.y)
                except RuntimeError as error:
                    continue  # modal appeared or layout guard; skip
                time.sleep(0.25)
                current = signature(desktop, window)
                if current != baseline:
                    entry = {"x": x, "y": y, "fields": len(current["fields"]),
                             "values": [v for _, v in current["fields"]]}
                    changes.append(entry)
                    hits = wall_candidates(desktop, window)
                    if hits:
                        hit = {"x": x, "y": y, "hits": len(hits)}
                        break
            if hit:
                break
        note("grid", {"changes": changes[:12], "hit": hit})
        if not hit:
            hits = wall_candidates(desktop, window)
            if len(hits) == 1:
                hit = {"late": True, "hits": 1}
        if hit and len(wall_candidates(desktop, window)) == 1:
            (OUT / "tree_strength.json").write_text(json.dumps(tree(desktop, window)))
            return business_edit(desktop, pid, root, window, wall_candidates(desktop, window)[0])
        note("outcome", "no wall field surfaced")
    note("ok", False)


def business_edit(desktop, pid, root, window, field):
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
    print("[probe5] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
