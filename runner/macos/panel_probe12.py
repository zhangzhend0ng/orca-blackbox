"""Probe 12 (task A3): read-mostly AX census of the Orca process parameter panel.

One boot, two views. (1) Flat list: default and Advanced-ON states, every
value-bearing control with the full AXHelp tooltip, AXValue (text + numeric),
AXDescription/AXIdentifier/AXPlaceholderValue when present. (2) Outline tree:
attribute-name dump of the AXOutline plus every row the hard-virtualizing
control materializes, across a bounded round of disclosure expansions and the
two outline tab entries. Any AXHelp line 'parameter name\\t: <key>' is lifted
into a top-level 'key' row field for the label->key crosswalk. Interactions
are view-state only (Advanced checkbox, view checkbox, tab band clicks,
triangle presses); no value writes, no focus grabs, no save. Writes
out/ax_census.json (+ per-state raw dumps) and result.json; 540 s hard fuse.
"""
import ctypes as ct
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import time

import accessibility as ax

WORK = Path(__file__).resolve().parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
PROJECT = WORK / "probe.3mf"
PROFILE = WORK / "datadir"
OUT = WORK / "out"
TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier",
              "AXPlaceholderValue", "AXValue", "AXRoleDescription")
CENSUS_ROLES = {"AXTextField", "AXCheckBox", "AXStaticText", "AXComboBox",
                "AXPopUpButton", "AXSlider", "AXGroup", "AXOutline", "AXRow",
                "AXDisclosureTriangle", "AXColumn", "AXScrollArea", "AXScrollBar"}
RESULT = {"ok": False}
FUSE_SECONDS = 540
STARTED = time.time()
number_type = ax.bind(ax.cf, "CFNumberGetTypeID", ct.c_ulong)
copy_attr_names = ax.bind(ax.ax, "AXUIElementCopyAttributeNames", ax.ptr, ax.ptr, ax.out)


def fused(limit=1.0):
    return time.time() - STARTED > FUSE_SECONDS * limit


def note(key, value):
    RESULT[key] = value
    print(f"[probe12] {key}: {json.dumps(value)[:700]}", flush=True)


def num_value(desktop, element, key):
    value = desktop.attr(element, key)
    if not value:
        return None
    kind = ax.type_id(value)
    if kind == ax.boolean_type:
        return ax.bool_value(value)
    if kind == number_type:
        buffer = ct.c_int()
        return buffer.value if ax.number_value(value, 3, ct.byref(buffer)) else None
    return None


def attr_names(desktop, element):
    names = ax.ptr()
    if element and copy_attr_names(element, ct.byref(names)) == 0 and names.value:
        array = desktop.own(names.value)
        out = []
        for index in range(ax.array_size(array)):
            try:
                out.append(desktop.cf_text(ax.array_item(array, index)))
            except Exception:
                out.append("<unreadable>")
        return out
    return None


def key_from_help(help_text):
    if not help_text:
        return None
    for line in help_text.splitlines():
        marker = line.find("parameter name")
        if marker >= 0:
            tail = line[marker + len("parameter name"):]
            tail = tail.lstrip(" \t:").strip()
            if tail:
                return tail.split()[0].rstrip(",;")
    return None


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


def element_json(desktop, element, state):
    item = {"state": state, "role": desktop.text(element, "AXRole")}
    for key in TEXT_ATTRS:
        item["help" if key == "AXHelp" else
             "value" if key == "AXValue" else
             "placeholder" if key == "AXPlaceholderValue" else
             "desc" if key == "AXDescription" else
             "ident" if key == "AXIdentifier" else
             "role_desc" if key == "AXRoleDescription" else "title"] = \
            desktop.text(element, key)
    item["value_num"] = num_value(desktop, element, "AXValue")
    enabled = desktop.attr(element, "AXEnabled")
    item["enabled"] = bool(enabled and ax.type_id(enabled) == ax.boolean_type
                           and ax.bool_value(enabled))
    try:
        point = desktop.position(element)
        item["x"], item["y"] = round(point.x, 1), round(point.y, 1)
    except RuntimeError:
        item["x"], item["y"] = None, None
    size = desktop.attr(element, "AXSize")
    width_height = ax.Point()
    if size and ax.read_point(size, 2, ct.byref(width_height)):
        item["w"], item["h"] = round(width_height.x, 1), round(width_height.y, 1)
    item["key"] = key_from_help(item.get("help"))
    return item


def census_flat(desktop, window, state):
    rows = []
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") not in CENSUS_ROLES:
            continue
        try:
            point = desktop.position(element)
        except RuntimeError:
            continue
        if point.y < 795:
            continue
        rows.append(element_json(desktop, element, state))
    rows.sort(key=lambda row: (row["y"] or 0, row["x"] or 0))
    return rows


def census_outline(desktop, window, state):
    outline = None
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") == "AXOutline":
            outline = element
            break
    page = {"state": state, "outline_found": outline is not None}
    if outline is not None:
        page["outline"] = element_json(desktop, outline, state)
        page["outline"]["attr_names"] = attr_names(desktop, outline)
        page["outline_counts"] = {}
        for name in ("AXRows", "AXVisibleRows", "AXColumns"):
            page["outline_counts"][name] = num_value(desktop, outline, name)
    rows = []
    for element in safe_elements(desktop, window):
        role = desktop.text(element, "AXRole")
        if role not in CENSUS_ROLES:
            continue
        try:
            point = desktop.position(element)
        except RuntimeError:
            continue
        inside = outline is not None and any(
            element is seen for seen in safe_elements(desktop, outline, cap=400))
        if not inside and not (700 <= point.y <= 800):
            continue
        rows.append(element_json(desktop, element, state))
    rows.sort(key=lambda row: (row["y"] or 0, row["x"] or 0))
    page["rows"] = rows
    return page


def row_signature(row):
    return (row["role"], row["x"], row["y"], row.get("value"), row.get("value_num"),
            row.get("ident"), (row.get("help") or "")[:80])


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
        try:
            point = desktop.position(element)
        except RuntimeError:
            continue
        if abs(point.x - x) <= slack and abs(point.y - y) <= slack:
            return element
    return None


def run():
    console_uid = os.stat("/dev/console").st_uid
    if not ax.trusted():
        raise RuntimeError("Accessibility permission is missing")
    info = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
    version = info.get("CFBundleShortVersionString")
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
        origin = desktop.position(window)
        actions = [{"action": "boot", "version": version, "pid": pid,
                    "origin": [origin.x, origin.y]}]
        note("entry", {"pid": pid, "version": version,
                       "origin": [origin.x, origin.y]})

        # --- flat page: default state, then Advanced ON -------------------
        flat_default = census_flat(desktop, window, "flat_default")
        advanced = checkbox_at(desktop, window, 673, 689)
        actions.append({"action": "AXPress", "target": "advanced_checkbox",
                        "at": [673, 689], "error": None if advanced else "not found"})
        if advanced is not None:
            note("advanced_press", press_catching(desktop, pid, advanced))
        time.sleep(0.6)
        flat_advanced = census_flat(desktop, window, "flat_advanced")
        note("flat_counts", {"default": len(flat_default), "advanced": len(flat_advanced)})

        # --- outline tree ---------------------------------------------------
        tree_box = checkbox_at(desktop, window, 453, 686)
        actions.append({"action": "AXPress", "target": "view_checkbox",
                        "at": [453, 686], "error": None if tree_box else "not found"})
        if tree_box is not None:
            note("tree_press", press_catching(desktop, pid, tree_box))
        time.sleep(1.2)
        outline_pages = [census_outline(desktop, window, "outline_tree")]
        note("outline_tree", {"rows": len(outline_pages[0]["rows"]),
                              "counts": outline_pages[0].get("outline_counts")})

        # bounded disclosure expansion rounds; rows only materialize 2-3 at
        # a time, so collect every distinct row the control ever shows.
        for round_index in range(5):
            if fused(0.7):
                actions.append({"action": "fuse", "at": "expansion"})
                break
            pressed = 0
            for element in safe_elements(desktop, window):
                if desktop.text(element, "AXRole") != "AXDisclosureTriangle":
                    continue
                value = num_value(desktop, element, "AXValue")
                if value is not None and value != 0:
                    continue
                if value is None and round_index > 0:
                    continue  # unreadable state: blind-press once, in round 0 only
                if press_catching(desktop, pid, element) is None:
                    pressed += 1
                time.sleep(0.15)
            time.sleep(0.5)
            page = census_outline(desktop, window, f"outline_expand{round_index}")
            outline_pages.append(page)
            note(f"expand{round_index}", {"pressed": pressed, "rows": len(page["rows"])})
            if pressed == 0:
                break

        # the second outline tab entry, then back to the flat tab.
        flat_return = []
        for label, x_abs in (("outline_tab_b", 525), ("flat_return", 390)):
            if fused(0.85):
                actions.append({"action": "fuse", "at": label})
                break
            entry = {"action": "click", "target": "tab_band", "at": [x_abs, 703]}
            actions.append(entry)
            try:
                desktop.click_point(pid, root, window, PROJECT.stem,
                                    x_abs - origin.x, 703 - origin.y)
            except RuntimeError as error:
                entry["error"] = str(error)
                continue
            time.sleep(0.8)
            if label.startswith("outline"):
                outline_pages.append(census_outline(desktop, window, label))
                note(label, {"rows": len(outline_pages[-1]["rows"])})
            else:
                flat_return = census_flat(desktop, window, label)
                note(label, {"rows": len(flat_return)})

        # --- assemble the census -------------------------------------------
        rows = []
        seen = {}
        for row in flat_default + flat_advanced + (flat_return or []):
            signature = row_signature(row)
            if signature in seen:
                if row["state"] not in seen[signature]["states"]:
                    seen[signature]["states"].append(row["state"])
                continue
            entry = dict(row)
            entry["states"] = [entry.pop("state")]
            seen[signature] = entry
            rows.append({"mode": "flat", "row": entry})
        outline_rows = {}
        for page in outline_pages:
            for row in page["rows"]:
                signature = row_signature(row)
                if signature in outline_rows:
                    if row["state"] not in outline_rows[signature]["states"]:
                        outline_rows[signature]["states"].append(row["state"])
                    continue
                entry = dict(row)
                entry["states"] = [entry.pop("state")]
                outline_rows[signature] = entry
        for entry in outline_rows.values():
            rows.append({"mode": "outline", "row": entry})
        value_roles = {"AXTextField", "AXCheckBox", "AXStaticText"}
        flat_core = [item["row"] for item in rows
                     if item["mode"] == "flat" and item["row"]["role"] in value_roles
                     and item["row"].get("help")]
        outline_core = [item["row"] for item in rows if item["mode"] == "outline"]
        census = {
            "version": version,
            "rows": rows,
            "meta": {
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "window_origin": [origin.x, origin.y],
                "window_size": [1200, 800],
                "flat_rows": len([item for item in rows if item["mode"] == "flat"]),
                "outline_rows": len(outline_rows),
                "flat_with_help": len(flat_core),
                "flat_with_key": len([row for row in flat_core if row.get("key")]),
                "outline_states": [page["state"] for page in outline_pages],
                "outline_attr_names": (outline_pages[0].get("outline") or {}).get("attr_names"),
                "outline_counts_by_state": {page["state"]: page.get("outline_counts")
                                            for page in outline_pages},
                "actions": actions,
                "notes": [
                    "read-only census: view-state switches only (Advanced checkbox, view checkbox, tab-band clicks, disclosure triangles); no AXValue writes, no project save",
                    "outline cells render via wxCustomRendererObject; their AXValue is a native pointer string, not readable text (Mac 2.4.1 hard virtualization)",
                    "flat-list rows stay fully AX-exposed offscreen; y coordinates exceed the 885 px window bottom on purpose",
                ],
            },
        }
        (OUT / "ax_census.json").write_text(json.dumps(census, indent=1))
        (OUT / "flat_default.json").write_text(json.dumps(flat_default, indent=1))
        (OUT / "flat_advanced.json").write_text(json.dumps(flat_advanced, indent=1))
        for page in outline_pages:
            (OUT / f"{page['state']}.json").write_text(json.dumps(page, indent=1))
        note("census", {k: census["meta"][k] for k in
                        ("flat_rows", "outline_rows", "flat_with_help", "flat_with_key")})
    note("ok", True)


def main():
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
    print("[probe12] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
