"""File-menu export of G-code (#236) and import of a binary STL (#227) in the inactive test login.

  file_io.py --supervise    over SSH: check the private staging directory, run the one-shot
                            LaunchAgent, print one JSON reply, remove the staging directory
  file_io.py --worker       inside the test login's Aqua session

Both cases open WORK/baseline.3mf through project_copy.open_copy, so launch, process ownership,
slicing and cleanup keep the proven helpers. This module adds the File-menu submenus and reads
the native file panels they open.

  preflight  trust, event-posting and session facts only; nothing is launched
  gcode236   Slice plate, wait for Export G-code, File > Export > Export G-code..., the save
             panel, <the app's remembered export directory>/plate.gcode
  stl227     select the template cube and delete it, Save Project (0 objects),
             File > Import > Import 3MF/STL/STEP/SVG/OBJ/AMF..., the open panel, cube_20mm.stl,
             Save Project in place (1 object)

WORK/case names the case. WORK/seed.conf is the app config the profile is seeded with; the
supervisor points its remembered export directory and last opened folder at this run's own
directories before the worker starts.

A native panel whose Save / Open button stays disabled is recorded (every element, every
attempt, the files written) and then cancelled: `outcome` says BLOCKED_*, `ok` stays True because
the script did all it was written to do.
"""
import base64
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

import project_copy as pc

WORK = Path(__file__).resolve().parent
CASE = (WORK / "case").read_text().strip()
OUT = WORK / "out"
IMPORT = WORK / "import"
STL = IMPORT / "cube_20mm.stl"
EXPORT_NAME = "plate.gcode"
MODEL = "3D/3dmodel.model"
PANEL_WAIT = 25
FUSE = {"preflight": 30, "gcode236": 420, "stl227": 420}
PANEL_IDS = ("OKButton", "CancelButton", "saveAsNameTextField", "where popup", "NewFolderButton")
SHOT_LIMIT = 8 * 1024 * 1024
PNG = (b"\x89PNG\r\n\x1a\n", b"IEND\xaeB\x60\x82")
require, wait_for, exactly_one = pc.require, pc.wait_for, pc.exactly_one
array_type = None  # bound in the worker: CFArrayGetTypeID
ax = None  # bound in the worker, as project_copy does
STARTED = time.monotonic()


def log(message):
    print(f"[{time.monotonic() - STARTED:7.1f}s] {message}", flush=True)


def stage(report, name):
    report.setdefault("stages", []).append({"name": name, "seconds": round(time.monotonic() - STARTED, 3)})
    report["failure_stage"] = name
    log(f"stage {name}")


def wait_soft(read, seconds):
    """wait_for that answers None instead of raising."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = read()
        if value:
            return value
        time.sleep(0.25)
    return None


# --- ApplicationServices reading. Only array attributes go through children(); a single-element
# attribute read as an array makes the target process raise NSException (2026-11-25). ---


def children(desktop, element, key="AXChildren"):
    value = desktop.attr(element, key)
    if not value or ax.type_id(value) != array_type:
        return []
    return [ax.array_item(value, i) for i in range(ax.array_size(value))]


def tree(desktop, root, limit=400):
    """Every element under root, depth first: role, title, value, identifier, subrole, enabled, box."""
    rows, pending = [], [root]
    while pending and len(rows) < limit:
        element = pending.pop()
        enabled = desktop.attr(element, "AXEnabled")
        box = desktop.box(element)
        rows.append({"element": element, "role": desktop.text(element, "AXRole"),
                     "title": desktop.text(element, "AXTitle"), "value": desktop.text(element, "AXValue"),
                     "id": desktop.text(element, "AXIdentifier"), "subrole": desktop.text(element, "AXSubrole"),
                     "enabled": bool(ax.bool_value(enabled)) if enabled is not None
                     and ax.type_id(enabled) == ax.boolean_type else None,
                     "box": [round(v) for v in box] if box else None})
        pending.extend(reversed(children(desktop, element)))
    return rows


def public(row):
    return {key: value for key, value in row.items() if key != "element"}


def identify(rows):
    found = {}
    for row in rows:
        if row["id"] in PANEL_IDS and row["id"] not in found:
            found[row["id"]] = row
    return found


def state(desktop, found):
    """What the panel's named controls show right now (None when the panel has no such control)."""
    def text(key):
        return desktop.text(found[key]["element"], "AXValue") if key in found else None

    def enabled(key):
        return desktop.enabled(found[key]["element"]) if key in found else None
    return {"name": text("saveAsNameTextField"), "where": text("where popup"),
            "ok_enabled": enabled("OKButton"), "cancel_enabled": enabled("CancelButton"),
            "new_folder_enabled": enabled("NewFolderButton")}


def panel_of(desktop, root):
    for window in children(desktop, root, "AXWindows"):
        if desktop.text(window, "AXRole") == "AXWindow" and desktop.text(window, "AXIdentifier").endswith("-panel"):
            return window
    return None


def window_titles(desktop, root):
    return [[desktop.text(w, "AXRole"), desktop.text(w, "AXSubrole"), desktop.text(w, "AXTitle"),
             desktop.text(w, "AXIdentifier")] for w in children(desktop, root, "AXWindows")]


def file_menu_of(desktop, root):
    bar = desktop.attr(root, "AXMenuBar")
    return exactly_one(e for e in desktop.children(bar) if desktop.text(e, "AXTitle") == "File")


def find_item(desktop, menu, label):
    """The one menu item under `menu` whose title is `label` before its trailing dots."""
    def matches(title):
        return title.rstrip(".\u2026") == label
    return find_menu_item(desktop, menu, matches)


def find_item_starting(desktop, menu, prefix):
    """The one menu item under `menu` whose title starts with `prefix` (labels grow between
    builds: the import item lists the formats)."""
    def matches(title):
        return title.rstrip(".\u2026").startswith(prefix)
    return find_menu_item(desktop, menu, matches)


def find_menu_item(desktop, menu, matches):
    pending, hits = [menu], []
    while pending:
        element = pending.pop()
        if desktop.text(element, "AXRole") == "AXMenuItem" and matches(desktop.text(element, "AXTitle")):
            hits.append(element)
        pending.extend(children(desktop, element))
    return exactly_one(hits)


def window_number(desktop, pid, window):
    """The on-screen window of one of the test process's AX windows, matched by its bounds."""
    box = desktop.box(window)
    windows = desktop.own(ax.window_info(0, 0))
    if not box or not windows:
        return None

    def number(info, key):
        obj = ax.dict_value(info, desktop.string(key))
        value = ct.c_int64()
        return value.value if obj and ax.number_value(obj, 4, ct.byref(value)) else None

    matches = []
    for index in range(ax.array_size(windows)):
        info = ax.array_item(windows, index)
        bounds = ax.Rect()
        obj = ax.dict_value(info, desktop.string("kCGWindowBounds"))
        if (number(info, "kCGWindowOwnerPID") == pid and number(info, "kCGWindowLayer") == 0 and obj
                and ax.decode_bounds(obj, ct.byref(bounds))
                and all(abs(a - b) <= 0.5 for a, b in zip(box, (bounds.origin.x, bounds.origin.y,
                                                                 bounds.size.x, bounds.size.y)))):
            matches.append(number(info, "kCGWindowNumber"))
    return matches[0] if len(matches) == 1 and matches[0] else None


def shot(desktop, pid, window, name):
    """Capture one window of the test process. This session writes the PNG and then hangs, so
    the process is killed on timeout and the image is taken from either of its two names."""
    target = WORK / (name + ".png")
    hidden = target.with_name("." + target.name)
    wid = window_number(desktop, pid, window)
    for stale in (target, hidden):
        if stale.exists():
            stale.unlink()
    if wid:
        try:
            subprocess.run(["/usr/sbin/screencapture", "-x", "-o", "-l", str(wid), str(target)],
                           capture_output=True, timeout=8)
        except subprocess.TimeoutExpired:
            pass
    for path in (target, hidden):
        if path.is_file() and 0 < path.stat().st_size <= SHOT_LIMIT:
            blob = path.read_bytes()
            if blob.startswith(PNG[0]) and blob.endswith(PNG[1]):
                if path != target:
                    path.replace(target)
                return {"file": target.name, "bytes": len(blob), "window": wid}
    return {"file": None, "window": wid}


def full_shot(name):
    path = pc.screen_capture(name)
    return {"file": path.name if path else None, "bytes": path.stat().st_size if path else None}


def key_to_process(pid, key_code):
    for pressed in (True, False):
        event = ax.create_key(None, key_code, pressed)
        if not event:
            raise RuntimeError("Keyboard event is unavailable")
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(0.3)


def click_in_panel(desktop, pid, panel, wid, panel_box, target_box, clicks):
    """A left click at the centre of one element of the panel, posted to the process only."""
    x = target_box[0] - panel_box[0] + target_box[2] / 2
    y = target_box[1] - panel_box[1] + target_box[3] / 2
    make_mouse = ax.selector(b"mouseEventWithType:location:modifierFlags:timestamp:"
                             b"windowNumber:context:eventNumber:clickCount:pressure:")
    events = ((1, 1.0), (2, 0.0)) + (((3, 1.0), (4, 0.0)) if clicks == 2 else ())
    for number, (kind, pressure) in enumerate(events):
        desktop.check_owned(pid, panel)
        event = ax.mouse_event(ax.objc_class(b"NSEvent"), make_mouse, kind, ax.Point(x, panel_box[3] - y), 0,
                               time.monotonic(), wid, None, number + 1, 1 if number < 2 else 2, pressure)
        if not event or ax.event_window(event, ax.selector(b"windowNumber")) != wid:
            raise RuntimeError("Pointer event has no matching panel window")
        native = ax.event_cg(event, ax.selector(b"CGEvent"))
        if not native:
            raise RuntimeError("Pointer event is unavailable")
        ax.set_location(native, ax.Point(panel_box[0] + x, panel_box[1] + y))
        ax.post_to_pid(pid, native)
        time.sleep(0.16)
    return [round(panel_box[0] + x), round(panel_box[1] + y), clicks]


def open_submenu_panel(desktop, pid, root, window, submenu, label, trace):
    """File > <submenu> > <label>...: the leaf pressed straight from the opened File menu and,
    when no panel came, through the opened submenu title. Escape closes the menu between them.
    `label` is the start of the item's title."""
    def panel():
        for candidate in children(desktop, root, "AXWindows"):
            if desktop.text(candidate, "AXRole") == "AXWindow" and desktop.text(candidate, "AXIdentifier").endswith("-panel"):
                return candidate
        return None

    routes = ("leaf pressed from the opened File menu", "leaf pressed from the opened submenu title")
    for route in routes:
        file_menu = file_menu_of(desktop, root)
        desktop.act(pid, file_menu, "AXPress")
        parent = file_menu
        if "submenu title" in route:
            parent = find_item(desktop, file_menu, submenu)
            desktop.act(pid, parent, "AXPress")
        item = find_item_starting(desktop, parent, label)
        wait_for(lambda: desktop.enabled(item), f"{label} stayed disabled")
        trace.setdefault("menu", []).append({"route": route, "title": desktop.text(item, "AXTitle"),
                                             "enabled": desktop.enabled(item)})
        desktop.act(pid, item, "AXPress")
        found = wait_soft(panel, PANEL_WAIT)
        if found:
            return found
        trace["menu"][-1].update(panel=f"none within {PANEL_WAIT} s", windows=window_titles(desktop, root))
        desktop.post_key(pid, root, window, desktop.text(window, "AXTitle"), 53, 1)
    raise RuntimeError(f"File > {submenu} > {label} opened no native panel: {window_titles(desktop, root)}")


def attempt(desktop, pid, root, trace, label, action, found, directory):
    """Run one panel action and write down what the panel and the directory did. The AX answer of
    a disabled control is a reading, not a crash."""
    try:
        answer = action()
    except Exception as error:
        answer = f"{type(error).__name__}: {error}"
    time.sleep(1.2)
    opened = panel_of(desktop, root) is not None
    written = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else None
    reading = {"step": label, "answer": answer, "panel_open": opened, "written": written,
               "state": state(desktop, found) if opened else None}
    trace["attempts"].append(reading)
    log(f"attempt {label}: {answer!r} panel_open={opened} written={written} state={reading['state']}")
    return reading


def last_attempt(trace):
    """(panel still open?, Open / Save enabled?) after the attempts that ran."""
    reading = trace["attempts"][-1] if trace["attempts"] else None
    return bool(reading and reading["panel_open"]), bool(reading and reading["state"] and reading["state"]["ok_enabled"])


def model_facts(project):
    """Object, build item and triangle counts of a saved project, read on this machine. Orca
    keeps each mesh in its own *.model entry and the names in model_settings.config."""
    with zipfile.ZipFile(project) as archive:
        xml = archive.read(MODEL).decode("utf-8")
        settings = archive.read("Metadata/model_settings.config").decode("utf-8")
        triangles = sum(len(re.findall(r"<triangle\b", archive.read(name).decode("utf-8")))
                        for name in archive.namelist() if name.endswith(".model"))
    return {"objects": len(re.findall(r"<object\b", xml)), "items": len(re.findall(r"<item\b", xml)),
            "triangles": triangles,
            "names": list(dict.fromkeys(re.findall(r'<metadata key="name" value="([^"]*)"', settings)))[:8],
            "sha256": pc.digest(project), "bytes": project.stat().st_size}


def save_in_place(desktop, pid, root, window, project):
    """File > Save Project on the project opened from disk: the file itself is rewritten."""
    before = pc.digest(project)
    file_menu = file_menu_of(desktop, root)
    desktop.act(pid, file_menu, "AXPress")
    save = find_item(desktop, file_menu, "Save Project")
    wait_for(lambda: desktop.enabled(save), "Save Project did not become available")
    desktop.act(pid, save, "AXPress")
    wait_for(lambda: project.is_file() and pc.digest(project) != before
             and not desktop.text(window, "AXTitle").startswith("*"),
             "Save Project did not rewrite the opened project", 30)
    return {"sha256": pc.digest(project), "bytes": project.stat().st_size, "title": desktop.text(window, "AXTitle")}


def remembered_export_directory():
    """app.last_export_path as the app keeps it; a finished export rewrites it."""
    try:
        text = (WORK / "baseline" / "Snapmaker_Orca.conf").read_text()
        return json.loads(text[:text.rindex("}") + 1]).get("app", {}).get("last_export_path")
    except (OSError, ValueError, AttributeError):
        return None


def wait_for_export(target):
    def finished():
        if not target.is_file():
            return None
        info = target.stat()
        if not 0 < info.st_size <= pc.MAX_PLATE_BYTES or time.time() - info.st_mtime < 3:
            return None
        with target.open("rb") as stream:
            raw = stream.read(pc.MAX_PLATE_BYTES + 1)
        complete = b"; EXECUTABLE_BLOCK_END" in raw and b"; CONFIG_BLOCK_END" in raw
        return ({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "complete_markers": True}
                if len(raw) == info.st_size and complete else None)
    return wait_soft(finished, 90)


def select(desktop, pid, element):
    """Select the file row: AXSelected on the entry, else on its parent or grandparent."""
    answers, node = [], element
    for _ in range(3):
        try:
            desktop.act(pid, node, "AXSelected", ax.true_value)
            answers.append("set")
            break
        except Exception as error:
            answers.append(str(error))
        node = desktop.attr(node, "AXParent")
        if not node:
            break
    return answers


# --- the cases ---


def session_facts(desktop):
    session = ax.current_session()
    if not session:
        return None

    def flag(key):
        value = ax.dict_value(session, desktop.string(key))
        return bool(ax.bool_value(value)) if value and ax.type_id(value) == ax.boolean_type else None

    def number(key):
        obj = ax.dict_value(session, desktop.string(key))
        value = ct.c_int()
        return value.value if obj and ax.number_value(obj, 3, ct.byref(value)) else None
    try:
        return {"on_console": flag("kCGSessionOnConsoleKey"), "login_done": flag("kCGSessionLoginDoneKey"),
                "uid": number("kCGSessionUserIDKey"), "screen_locked": flag("CGSSessionScreenIsLocked")}
    finally:
        ax.release(session)


def console_locked():
    output = subprocess.check_output(["/usr/sbin/ioreg", "-n", "Root", "-d1"], text=True, timeout=10)
    found = re.search(r'"IOConsoleLocked"\s*=\s*(\w+)', output)
    require(found, "IOConsoleLocked not reported by ioreg")
    return found.group(1)


def executable_sha256():
    hasher = hashlib.sha256()
    with (pc.APP / "Contents/MacOS" / "Snapmaker_Orca").open("rb") as executable:
        for chunk in iter(lambda: executable.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def preflight(desktop, report):
    """Everything the two cases depend on, read without launching anything. The GUI cases can
    run only while the front login's console is unlocked."""
    stage(report, "preflight")
    bundle = plistlib.loads((pc.APP / "Contents/Info.plist").read_bytes())
    facts = {
        "ax_trusted": ax.trusted(), "post_allowed": ax.post_allowed(),
        "console_uid": os.stat("/dev/console").st_uid, "test_uid": os.getuid(),
        "console_locked": report["console_locked"], "session": report["session"],
        "app": str(pc.APP), "version": bundle.get("CFBundleShortVersionString"),
        "bundle_version": bundle.get("CFBundleVersion"), "executable_sha256": executable_sha256(),
        "orca_processes": sorted(pc.processes())}
    facts["gui_cases_runnable"] = bool(facts["ax_trusted"] and facts["post_allowed"] and facts["console_locked"] == "No")
    report["preflight"] = facts
    report["outcome"] = "PREFLIGHT"
    log(f"preflight {facts}")


def export_gcode(desktop, report):
    trace = report["export"] = {"attempts": []}
    with pc.open_copy(desktop, "baseline") as (pid, root, window):
        report["pid"] = pid
        report["sut"] = pc.build_identity(pid)
        title = desktop.text(window, "AXTitle")
        report["window_title"] = title
        report["shots"] = {"before": shot(desktop, pid, window, "before")}
        stage(report, "slice")
        # Writes WORK/baseline.gcode: the plate file the slicing process itself keeps open,
        # kept as a witness of the slice; it is not the export.
        report["slice"] = pc.slice_plate(desktop, pid, root, window, "baseline", pc.BASELINE)
        report["shots"]["sliced"] = shot(desktop, pid, window, "sliced")
        stage(report, "export.menu")
        panel = open_submenu_panel(desktop, pid, root, window, "Export", "Export G-code", trace)
        stage(report, "export.panel")
        trace["panel"] = {"title": desktop.text(panel, "AXTitle"), "identifier": desktop.text(panel, "AXIdentifier"),
                          "subrole": desktop.text(panel, "AXSubrole"), "windows": window_titles(desktop, root)}
        rows = tree(desktop, panel)
        trace["panel_tree"] = [public(row) for row in rows]
        found = identify(rows)
        trace["as_opened"] = state(desktop, found)
        log(f"save panel as opened: {trace['as_opened']}")
        require({"OKButton", "CancelButton", "saveAsNameTextField"} <= set(found),
                "The save panel does not expose Save, Cancel and the name field")
        report["shots"]["export-dialog"] = shot(desktop, pid, panel, "export-dialog")
        stage(report, "export.name")
        desktop.act(pid, found["saveAsNameTextField"]["element"], "AXValue", desktop.string(EXPORT_NAME))
        time.sleep(1.0)
        trace["named"] = state(desktop, found)
        log(f"save panel named {EXPORT_NAME}: {trace['named']}")
        if not trace["named"]["ok_enabled"]:
            stage(report, "export.confirm")
            ok_box, wid = desktop.box(found["OKButton"]["element"]), window_number(desktop, pid, panel)
            confirm = [("AXConfirm on the name field",
                        lambda: desktop.act(pid, found["saveAsNameTextField"]["element"], "AXConfirm")),
                       ("Return key posted to the process", lambda: key_to_process(pid, 36)),
                       ("AXPress on the Save button as read",
                        lambda: desktop.act(pid, found["OKButton"]["element"], "AXPress"))]
            if wid and ok_box:
                confirm.append(("pointer click on the Save button",
                                lambda: click_in_panel(desktop, pid, panel, wid, desktop.box(panel), ok_box, 1)))
            for label, action in confirm:
                reading = attempt(desktop, pid, root, trace, label, action, found, OUT)
                if not reading["panel_open"] or reading["written"]:
                    break
        stage(report, "export.result")
        directory = Path(remembered_export_directory() or OUT)
        target = directory / EXPORT_NAME
        trace["directory"] = str(directory)
        # Read the panel again: an attempt's reading is already more than a second old.
        opened = panel_of(desktop, root) is not None
        if not opened:
            # The panel is gone: the confirm was taken and the export is running.
            trace["file"] = wait_for_export(target)
        if trace.get("file") is None and target.is_file():
            trace["file"] = wait_for_export(target)
        if trace.get("file"):
            wait_for(lambda: panel_of(desktop, root) is None, "The save panel stayed open", 20)
            report["shots"]["exported"] = shot(desktop, pid, window, "exported")
            report["outcome"] = "EXPORTED"
            trace["status"] = "exported"
            return
        if not opened:
            report["outcome"] = "NO_FILE_AFTER_PANEL_CLOSED"
            trace["status"] = "no file"
            trace["missing"] = {"target": str(target), "written": sorted(p.name for p in directory.iterdir())
                                if directory.is_dir() else None}
            return
        report["outcome"] = "BLOCKED_SAVE_DISABLED"
        trace["status"] = "blocked"
        report["shots"]["export-dialog"] = shot(desktop, pid, panel, "export-dialog")
        report["shots"]["export-full"] = full_shot("export-full")
        trace["blocked"] = {"ok_enabled_after_every_attempt": [r["state"]["ok_enabled"] if r["state"] else None
                                                             for r in trace["attempts"]],
                            "target": str(target), "exists": target.exists(),
                            "written": sorted(p.name for p in directory.iterdir()) if directory.is_dir() else None}
        desktop.act(pid, found["CancelButton"]["element"], "AXPress")
        wait_for(lambda: panel_of(desktop, root) is None, "Cancel did not close the save panel", 15)
        trace["cancelled"] = True
        trace["after_cancel"] = window_titles(desktop, root)
        report["shots"]["after-cancel"] = shot(desktop, pid, window, "after-cancel")


def import_stl(desktop, report):
    trace = report["import"] = {"attempts": []}
    require(STL.is_file() and pc.digest(STL) == (WORK / "cube_20mm.sha256").read_text().strip(),
            "cube_20mm.stl is missing or changed")
    trace["stl_sha256"] = pc.digest(STL)
    with pc.open_copy(desktop, "baseline") as (pid, root, window):
        report["pid"] = pid
        report["sut"] = pc.build_identity(pid)
        title = desktop.text(window, "AXTitle")
        report["window_title"] = title
        report["shots"] = {"before": shot(desktop, pid, window, "before")}
        stage(report, "prepare.delete")
        # The template cube loads centred on the bed (project_copy.pan_and_save): the canvas
        # click selects it, the Delete key of the main block removes the selection.
        desktop.click_point(pid, root, window, title, 490, 420)
        desktop.post_key(pid, root, window, title, 51, 1)
        wait_for(lambda: desktop.text(window, "AXTitle") == "*" + title, "Delete did not mark the project modified", 10)
        stage(report, "prepare.save")
        report["empty"] = save_in_place(desktop, pid, root, window, pc.BASELINE)
        report["empty"].update(model_facts(pc.BASELINE))
        log(f"empty plate: {report['empty']}")
        require(report["empty"]["objects"] == 0 and report["empty"]["items"] == 0,
                f"The plate is not empty after the delete: {report['empty']}")
        report["shots"]["empty-plate"] = shot(desktop, pid, window, "empty-plate")
        stage(report, "import.menu")
        panel = open_submenu_panel(desktop, pid, root, window, "Import", "Import 3MF/STL/STEP/SVG/OBJ/AMF", trace)
        stage(report, "import.panel")
        trace["panel"] = {"title": desktop.text(panel, "AXTitle"), "identifier": desktop.text(panel, "AXIdentifier"),
                          "subrole": desktop.text(panel, "AXSubrole"), "windows": window_titles(desktop, root)}
        rows = tree(desktop, panel)
        trace["panel_tree"] = [public(row) for row in rows]
        found = identify(rows)
        trace["as_opened"] = state(desktop, found)
        texts = []
        for row in rows:
            for text in (row["title"], row["value"]):
                if text and text not in texts:
                    texts.append(text)
        trace["panel_text"] = texts
        trace["stl_filter_text"] = [text for text in texts if ".stl" in text.lower()]
        entries = [row for row in rows if (row["value"] or row["title"]) in (STL.name, STL.stem)]
        trace["file_entries"] = [public(row) for row in entries]
        log(f"open panel as opened: {trace['as_opened']} entries={trace['file_entries']}")
        report["shots"]["open-panel"] = shot(desktop, pid, panel, "open-panel")
        stage(report, "import.select")
        if entries:
            # The browser lists a file as a text field; any other element carrying the name is a fallback.
            entry = ([row for row in entries if row["role"] == "AXTextField"] or entries)[0]
            trace["entry"] = public(entry)
            wid, panel_box = window_number(desktop, pid, panel), desktop.box(panel)
            strategies = [("AXSelected on the file row", lambda: select(desktop, pid, entry["element"]))]
            if wid and panel_box and entry["box"]:
                strategies.append(("pointer click on the file row",
                                  lambda: click_in_panel(desktop, pid, panel, wid, panel_box, entry["box"], 1)))
            strategies.append(("AXOpen on the file row", lambda: desktop.act(pid, entry["element"], "AXOpen")))
            if wid and panel_box and entry["box"]:
                strategies.append(("pointer double-click on the file row",
                                  lambda: click_in_panel(desktop, pid, panel, wid, panel_box, entry["box"], 2)))
            for label, action in strategies:
                reading = attempt(desktop, pid, root, trace, label, action, found, IMPORT)
                if not reading["panel_open"] or (reading["state"] and reading["state"]["ok_enabled"]):
                    break
            opened, enabled = last_attempt(trace)
            if opened and enabled:
                desktop.act(pid, found["OKButton"]["element"], "AXPress")
                wait_for(lambda: panel_of(desktop, root) is None, "Open did not close the panel", 20)
                trace["open_pressed"] = True
        stage(report, "import.result")
        if panel_of(desktop, root) is not None:
            report["outcome"] = "BLOCKED_OPEN_DISABLED" if entries else "BLOCKED_FILE_NOT_LISTED"
            trace["status"] = "blocked"
            report["shots"]["open-panel"] = shot(desktop, pid, panel, "open-panel")
            report["shots"]["import-full"] = full_shot("import-full")
            if "CancelButton" in found:
                desktop.act(pid, found["CancelButton"]["element"], "AXPress")
                wait_for(lambda: panel_of(desktop, root) is None, "Cancel did not close the open panel", 15)
                trace["cancelled"] = True
            trace["after_cancel"] = {"windows": window_titles(desktop, root), "project": model_facts(pc.BASELINE)}
            report["shots"]["after-cancel"] = shot(desktop, pid, window, "after-cancel")
            return
        wait_for(lambda: desktop.text(window, "AXTitle") == "*" + title, "The import did not mark the project modified", 30)
        time.sleep(2.0)
        report["shots"]["imported"] = shot(desktop, pid, window, "imported")
        stage(report, "import.save")
        report["saved"] = save_in_place(desktop, pid, root, window, pc.BASELINE)
        report["saved"].update(model_facts(pc.BASELINE))
        trace["status"] = "imported"
        report["outcome"] = "IMPORTED"
        log(f"saved after import: {report['saved']}")


def run_case(report):
    global ax, array_type
    import accessibility
    ax = accessibility
    array_type = ax.bind(ax.cf, "CFArrayGetTypeID", ct.c_ulong)()
    require(CASE in FUSE, f"Unexpected case {CASE!r}")
    report["case"] = CASE
    report["commit"] = (WORK / "commit").read_text().strip() if (WORK / "commit").is_file() else None
    require(ax.trusted(), "Accessibility permission is missing for the Aqua worker")
    require(ax.post_allowed(), "Posting input events is not allowed for the Aqua worker")
    report["console_locked"] = console_locked()
    console_uid = os.stat("/dev/console").st_uid
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
        report["session"] = session_facts(desktop)
        if CASE == "preflight":
            preflight(desktop, report)
            return
        # While the front login's console is locked, every AX window of this session reads as a
        # placeholder titled with the application name (2026-11-25, ninehour mac/README.md).
        require(report["console_locked"] == "No", "The front login's console is locked: no named window will open")
        stage(report, "launch")
        {"gcode236": export_gcode, "stl227": import_stl}[CASE](desktop, report)
        desktop.check_session()


def run_worker():
    import fcntl

    report = {"ok": False, "failure_stage": "preflight", "run_id": (WORK / "run-id").read_text().strip(),
              "started": time.strftime("%Y-%m-%d %H:%M:%S %z"), "worker_sha256": pc.digest(Path(__file__))}
    try:
        # One case at a time per test login (the lock project_copy's worker takes); an SSH
        # disconnect does not release it.
        with (Path(tempfile.gettempdir()) / "orca-bb-project-copy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run_case(report)
        report["ok"] = True
        report.pop("failure_stage", None)
    except Exception:
        report["error"] = traceback.format_exc()
    report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    pending = WORK / "result.tmp"
    pending.write_text(json.dumps(report))
    pending.replace(WORK / "result.json")


def pin_directories():
    """Point the app's remembered export directory (gcode236) and last opened folder (stl227) at
    this run's directories, in the JSON config the profile is seeded with."""
    text = (WORK / "seed.conf").read_text()
    config = json.loads(text[:text.rindex("}") + 1])
    if CASE == "gcode236":
        OUT.mkdir(exist_ok=True)
        config.setdefault("app", {})["last_export_path"] = str(OUT)
    elif CASE == "stl227":
        require(IMPORT.is_dir(), "The staging directory has no import/ folder")
        config["recent"] = {"last_opened_folder": str(IMPORT)}
    else:
        return
    body = json.dumps(config, indent=4, ensure_ascii=False)
    (WORK / "seed.conf").write_text(body + "\n# MD5 checksum "
                                     + hashlib.md5((body + "\n").encode("utf-8")).hexdigest().upper() + "\n")


def sweep():
    """End every Orca of this test login that was started from the staging directory."""
    def mine():
        return [pid for pid, command in pc.processes().items() if str(WORK) in command]
    for pid in mine():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if wait_soft(lambda: not mine(), 6) is None:
        for pid in mine():
            os.kill(pid, signal.SIGKILL)
    require(wait_soft(lambda: not mine(), 5), "Test Orca started from the staging directory is still running")


def supervise():
    require(WORK.parent == Path(tempfile.gettempdir()).resolve()
            and re.fullmatch(r"orca-bb-copy\.[a-zA-Z0-9]{8}", WORK.name)
            and WORK.stat().st_uid == os.getuid() and WORK.stat().st_mode & 0o077 == 0,
            "Supervisor requires a fresh, private staging directory")
    require(CASE in FUSE, f"Unexpected case {CASE!r}")
    run_id = (WORK / "run-id").read_text().strip()
    label = "local.orcabb.file-io." + run_id
    domain = f"gui/{os.getuid()}"
    logfile = WORK / "worker.log"
    python = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    result = {"run_id": run_id, "case": CASE, "ok": False, "failure_stage": "supervisor"}
    registered = False
    try:
        pin_directories()
        require(python.is_file(), "Select Xcode with its signed Python.app installed")
        job = {"Label": label, "LimitLoadToSessionType": "Aqua", "RunAtLoad": True,
               "ProgramArguments": [str(python), "-B", "-u", str(Path(__file__).resolve()), "--worker"],
               "WorkingDirectory": str(WORK), "StandardOutPath": str(logfile),
               "StandardErrorPath": str(logfile)}
        plist = WORK / "worker.plist"
        plist.write_bytes(plistlib.dumps(job))
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True, timeout=15)
        registered = True
        wait_for((WORK / "result.json").is_file, "Mac worker timed out", FUSE[CASE])
        result = json.loads((WORK / "result.json").read_text())
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        failures = []
        if registered:
            try:
                subprocess.run(["launchctl", "bootout", domain + "/" + label], check=True, timeout=20)
                status = subprocess.run(["launchctl", "print", domain + "/" + label],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                require(status.returncode != 0, "LaunchAgent still registered")
            except Exception as error:
                failures.append(str(error))
        try:
            sweep()
        except Exception as error:
            failures.append(str(error))
        result["cleanup_verified"] = not failures
        result["orca_processes_after"] = sorted(pc.processes())
        if failures:
            result.update(ok=False, cleanup_errors=failures)
            result.setdefault("failure_stage", "cleanup")
    reply = {"report": result, "log": logfile.read_text(errors="replace")[-24000:] if logfile.exists() else "",
             "evidence": str(WORK), "artifacts": {}}
    for path in sorted(WORK.rglob("*")):
        if (path.is_file() and not path.name.startswith(".") and path.suffix in {".png", ".gcode", ".3mf", ".stl"}
                and 0 < path.stat().st_size <= 16 * 1024 * 1024):
            reply["artifacts"][path.relative_to(WORK).as_posix()] = base64.b64encode(path.read_bytes()).decode("ascii")
    print(json.dumps(reply), flush=True)
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        run_worker()
    elif sys.argv[1:] == ["--supervise"]:
        supervise()
    else:
        sys.exit("Use the host driver of the elevenhour_1125 Mac line")
