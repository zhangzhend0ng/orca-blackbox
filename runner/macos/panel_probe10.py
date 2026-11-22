"""Probe 10: expand the AXOutline parameter tree and scroll it to wall_loops.

The tree page exposes a real outline: AXRow/AXDisclosureTriangle inside an
AXScrollArea. wall_loops lives in a collapsed group below the fold. This
probe (1) presses every disclosure triangle until the group count stabilizes,
(2) sweeps the scrollbar's numeric AXValue, and (3) tries the macOS
AXScrollToVisible action on rows, hunting at every step for an AXTextField
with value 2 and wall/perimeter help. A hit runs the business edit + save +
3MF verification. A 420 s fuse aborts cleanly with evidence.
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
number_create = ax.bind(ax.cf, "CFNumberCreate", ax.ptr, ax.ptr, ct.c_int, ct.c_void_p)
FUSE_SECONDS = 420
STARTED = time.time()


def cfint(value):
    buffer = ct.c_int(value)
    return number_create(None, 3, ct.byref(buffer))  # kCFNumberSInt32Type


def create_scroll_local(delta):
    """Pixel-unit scroll wheel event posted to the app (defined late to reuse ax binds)."""
    ax.cg.CGEventCreateScrollWheelEvent.restype = ax.ptr
    ax.cg.CGEventCreateScrollWheelEvent.argtypes = [ax.ptr, ct.c_uint32, ct.c_uint32, ct.c_int32]
    event = ax.cg.CGEventCreateScrollWheelEvent(None, 0, 1, delta)
    return event


def note(key, value):
    RESULT[key] = value
    print(f"[probe10] {key}: {json.dumps(value)[:700]}", flush=True)


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


def rows_and_fields(desktop, window):
    rows, fields, triangles = [], [], []
    for element in safe_elements(desktop, window):
        role = desktop.text(element, "AXRole")
        if role == "AXRow":
            rows.append(element)
        elif role == "AXTextField":
            fields.append(element)
        elif role == "AXDisclosureTriangle":
            triangles.append(element)
    return rows, fields, triangles


def wall_hits(desktop, fields):
    hits = []
    for element in fields:
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
        note("tree_mode", press_catching(desktop, pid, checkbox_at(desktop, window, 453, 686)))
        time.sleep(1.2)

        inventory = {}

        # Probe the outline's row attributes and focus-routed wheel scrolling.
        outline = None
        for element in safe_elements(desktop, window):
            if desktop.text(element, "AXRole") == "AXOutline":
                outline = element
                break
        rowsattr = {}
        if outline is not None:
            for key in ("AXRows", "AXVisibleRows"):
                try:
                    rowsattr[key] = len(desktop.children(outline, key))
                except RuntimeError as error:
                    rowsattr[key] = str(error)
            note("outline_rows_attrs", rowsattr)
        _, fields0, _0 = rows_and_fields(desktop, window)
        base_ys = sorted(round(desktop.position(f).y) for f in fields0)
        if fields0:
            try:
                desktop.act(pid, fields0[0], "AXFocused", ax.true_value)
            except RuntimeError:
                pass
            time.sleep(0.3)
        for _ in range(8):
            event = None
            try:
                event = create_scroll_local(-300)
            except Exception:
                pass
            if event is not None:
                ax.post_to_pid(pid, event)
            time.sleep(0.12)
        time.sleep(0.6)
        rows1, fields1, _t1 = rows_and_fields(desktop, window)
        ys1 = sorted(round(desktop.position(f).y) for f in fields1)
        note("wheel_focused", {"before": base_ys, "after": ys1,
                               "rows": len(rows1), "fields": len(fields1)})

        def hunt(tag):
            rows, fields, triangles = rows_and_fields(desktop, window)
            for element in fields:
                try:
                    key = (desktop.text(element, "AXValue"),
                           (desktop.text(element, "AXHelp") or "")[:70])
                    if not str(key[0]).startswith("<wx"):
                        inventory[key] = inventory.get(key, 0) + 1
                except RuntimeError:
                    pass
            note(tag, {"rows": len(rows), "fields": len(fields), "triangles": len(triangles)})
            hits = wall_hits(desktop, fields)
            return hits, len(rows), len(triangles)

        hits, row_count, triangle_count = hunt("top")
        # 1) expand disclosure triangles until the structure stops growing.
        for round_index in range(8):
            if time.time() - STARTED > FUSE_SECONDS * 0.5:
                break
            _, fields, triangles = rows_and_fields(desktop, window)
            pressed = 0
            for triangle in triangles:
                if press_catching(desktop, pid, triangle) is None:
                    pressed += 1
                time.sleep(0.2)
            time.sleep(0.6)
            hits, row_count, triangle_count = hunt(f"expand{round_index}")
            note(f"expand{round_index}_pressed", pressed)
            if len(hits) == 1:
                break
            _, fields2, triangles2 = rows_and_fields(desktop, window)
            if len(triangles2) == len(triangles) and pressed == 0:
                break
        if len(hits) != 1:
            # 2) sweep the scrollbar value.
            scrollbar = None
            for element in safe_elements(desktop, window):
                if desktop.text(element, "AXRole") == "AXScrollBar":
                    scrollbar = element
                    break
            note("scrollbar", element_json(desktop, scrollbar) if scrollbar else None)
            if scrollbar is not None:
                for value in list(range(0, 1201, 60)) + list(range(1200, -1, -120)):
                    if time.time() - STARTED > FUSE_SECONDS * 0.8:
                        break
                    try:
                        desktop.act(pid, scrollbar, "AXValue", cfint(value))
                    except RuntimeError as error:
                        note("scroll_set_error", str(error))
                        break
                    time.sleep(0.25)
                    hits = wall_hits(desktop, rows_and_fields(desktop, window)[1])
                    if len(hits) == 1:
                        note("scroll_hit_at", value)
                        break
                    rows, fields, _ = rows_and_fields(desktop, window)
                    for element in fields:
                        key = (desktop.text(element, "AXValue"),
                               (desktop.text(element, "AXHelp") or "")[:70])
                        if not str(key[0]).startswith("<wx"):
                            inventory[key] = inventory.get(key, 0) + 1
        if len(hits) != 1:
            # 3) AXScrollToVisible on rows.
            rows, fields, _ = rows_and_fields(desktop, window)
            errors = 0
            for element in rows[:40]:
                if time.time() - STARTED > FUSE_SECONDS:
                    break
                try:
                    desktop.act(pid, element, "AXScrollToVisible")
                    time.sleep(0.3)
                except RuntimeError:
                    errors += 1
            note("scrollto", {"rows": len(rows), "errors": errors})
            hits = wall_hits(desktop, rows_and_fields(desktop, window)[1])

        (OUT / "inventory.json").write_text(json.dumps(
            [{"value": v, "help": h} for (v, h) in sorted(inventory, key=lambda t: (t[1], t[0]))],
            indent=1))
        (OUT / "tree_final.json").write_text(json.dumps(
            [element_json(desktop, e) for e in safe_elements(desktop, window, cap=800)]))
        note("distinct", len(inventory))
        if len(hits) == 1:
            return business_edit(desktop, pid, root, window, hits[0])
        note("outcome", {"hits": len(hits)})
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
    print("[probe10] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
