"""Probe 13 (task A4): can a real wx search box materialize the parameter tree.

Hypothesis under test: a search box filters the hard-virtualizing parameter
outline so a small match set like "wall" materializes every matching row at
once, bypassing the dead scroll channels. Phase A targets the outline page's
own filter field ("Search plate, object and part.", the AXTextField above the
AXOutline — the only parameter-search exposure; the preset row is not
AX-visible in that view): click-focus, per-character keycode "wall", then the
untested commit channels — bare Return and Down+Return against the self-drawn
results dropdown — with an outline census plus a full-window element dump
after every step so materialization anywhere is caught, not only inside the
outline scope. Phase B re-tests the flat page's preset box ("Search in
preset...", the A2 channel) with the same clean method (click focus +
keycode taps) and flat censuses around it. Phase C (conditional on a
wall_loops row materializing) probes focus read-only (Tab, arrows, AXFocused
write); only a verifiably focused wall_loops value field gets "3" typed, with
the original value restored (keyboard first, AXValue+AXConfirm fallback).
Writes out/search_probe.json (+ per-state dumps) and result.json; 480 s fuse.
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
ROW_ROLES = {"AXTextField", "AXCheckBox", "AXStaticText", "AXComboBox",
             "AXPopUpButton", "AXSlider", "AXGroup", "AXOutline", "AXRow",
             "AXDisclosureTriangle", "AXColumn", "AXScrollArea", "AXScrollBar"}
KEYCODES = {"w": 13, "a": 0, "l": 37, "0": 29, "1": 18, "2": 19, "3": 20, "4": 21,
            "5": 23, "6": 22, "7": 26, "8": 28, "9": 25, ".": 47}
SPECIALS = {"tab": 48, "down": 125, "up": 126, "escape": 53, "backspace": 51, "return": 36}
CMD_FLAGS = 0x100
RESULT = {"ok": False}
number_type = ax.bind(ax.cf, "CFNumberGetTypeID", ct.c_ulong)
set_unicode = ax.bind(ax.cg, "CGEventKeyboardSetUnicodeString", None, ax.ptr, ct.c_ulong, ct.c_wchar_p)
set_flags = ax.bind(ax.cg, "CGEventSetFlags", None, ax.ptr, ct.c_uint64)


def note(key, value):
    RESULT[key] = value
    print(f"[probe13] {key}: {json.dumps(value)[:700]}", flush=True)


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


def focused_bool(desktop, element):
    value = desktop.attr(element, "AXFocused")
    return bool(value and ax.type_id(value) == ax.boolean_type and ax.bool_value(value))


def focused_element(desktop, root):
    # Best-effort identity of the app's AXFocusedUIElement (role + spot).
    element = desktop.attr(root, "AXFocusedUIElement")
    if not element:
        return None
    try:
        point = desktop.position(element)
        spot = [round(point.x, 1), round(point.y, 1)]
    except RuntimeError:
        spot = None
    return {"role": desktop.text(element, "AXRole"),
            "placeholder": desktop.text(element, "AXPlaceholderValue"),
            "value": desktop.text(element, "AXValue"),
            "help": (desktop.text(element, "AXHelp") or "")[:120], "spot": spot}


def census_outline(desktop, window, state):
    outline = None
    elements = safe_elements(desktop, window)
    for element in elements:
        if desktop.text(element, "AXRole") == "AXOutline":
            outline = element
            break
    page = {"state": state, "outline_found": outline is not None}
    if outline is not None:
        page["outline_counts"] = {name: num_value(desktop, outline, name)
                                  for name in ("AXRows", "AXVisibleRows", "AXColumns")}
    inside_set = set()
    if outline is not None:
        try:
            inside_set = {id(e) for e in safe_elements(desktop, outline, cap=400)}
        except RuntimeError:
            pass
    rows = []
    for element in elements:
        role = desktop.text(element, "AXRole")
        if role not in ROW_ROLES:
            continue
        try:
            point = desktop.position(element)
        except RuntimeError:
            continue
        if not (id(element) in inside_set or 700 <= point.y <= 800):
            continue
        rows.append(element_json(desktop, element, state))
    rows.sort(key=lambda row: (row["y"] or 0, row["x"] or 0))
    page["rows"] = rows
    return page


def census_flat(desktop, window, state):
    rows = []
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") not in ROW_ROLES:
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


def full_dump(desktop, window, tag):
    rows = [element_json(desktop, element, tag)
            for element in safe_elements(desktop, window)]
    (OUT / f"full_{tag}.json").write_text(json.dumps(rows, indent=1))
    return {"elements": len(rows),
            "wall_rows": [row for row in rows
                          if row.get("key") == "wall_loops"
                          or "wall_loops" in (row.get("help") or "")]}


def row_signature(row):
    return (row["role"], row["x"], row["y"], row.get("value"),
            row.get("value_num"), (row.get("help") or "")[:80])


def diff_rows(before, after):
    old = {row_signature(row) for row in before}
    new = {row_signature(row) for row in after}
    return {"baseline_rows": len(before), "rows_now": len(after),
            "added": len(new - old), "removed": len(old - new)}


def windows_snapshot(desktop, root):
    return [{"subrole": desktop.text(w, "AXSubrole"), "title": desktop.text(w, "AXTitle"),
             "role": desktop.text(w, "AXRole")} for w in desktop.children(root, "AXWindows")]


def dump_popups(desktop, root, tag):
    dumped = []
    for index, extra in enumerate(desktop.children(root, "AXWindows")):
        if desktop.text(extra, "AXSubrole") == "AXStandardWindow":
            continue
        tree = [element_json(desktop, element, tag)
                for element in safe_elements(desktop, extra, cap=300)]
        name = f"popup_{tag}_{index}.json"
        (OUT / name).write_text(json.dumps(tree, indent=1))
        dumped.append({"file": name, "subrole": desktop.text(extra, "AXSubrole"),
                       "elements": len(tree), "x": tree[0].get("x") if tree else None,
                       "y": tree[0].get("y") if tree else None,
                       "w": tree[0].get("w") if tree else None,
                       "h": tree[0].get("h") if tree else None})
    return dumped


def tap_key(pid, code, pause=0.12):
    for pressed in (True, False):
        event = ax.create_key(None, code, pressed)
        if not event:
            raise RuntimeError("Keyboard event is unavailable")
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(pause)


def tap_text(pid, text):
    for char in text:
        if char not in KEYCODES:
            raise RuntimeError(f"No keycode mapped for {char!r}")
        tap_key(pid, KEYCODES[char])


def tap_unicode(pid, text):
    for pressed in (True, False):
        event = ax.create_key(None, 0, pressed)
        if not event:
            raise RuntimeError("Keyboard event is unavailable")
        set_unicode(event, len(text), text)
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(0.5)


def tap_with_flags(pid, code, flags):
    for pressed in (True, False):
        event = ax.create_key(None, code, pressed)
        if not event:
            raise RuntimeError("Keyboard event is unavailable")
        set_flags(event, flags)
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(0.25)


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


def find_field_by_placeholder(desktop, window, needle, y_band=None):
    for element in safe_elements(desktop, window):
        if desktop.text(element, "AXRole") != "AXTextField":
            continue
        if needle not in desktop.text(element, "AXPlaceholderValue"):
            continue
        if y_band is not None:
            try:
                point = desktop.position(element)
            except RuntimeError:
                continue
            if not y_band[0] <= point.y <= y_band[1]:
                continue
        return element
    return None


def find_search_opener(desktop, window):
    # Any control whose tooltip names the preset-search entry (A2: the icon
    # at 752,729 on the flat page); prefer a button on the preset row.
    matches = []
    for element in safe_elements(desktop, window):
        if "Search in preset" in (desktop.text(element, "AXHelp") or ""):
            try:
                point = desktop.position(element)
            except RuntimeError:
                point = None
            matches.append((element, desktop.text(element, "AXRole"), point))
    if not matches:
        return None, 0
    for element, role, point in matches:
        if role == "AXButton" and point and 700 <= point.y <= 760:
            return element, len(matches)
    return matches[0][0], len(matches)


def click_element_center(desktop, pid, root, window, origin, element, entry):
    try:
        point = desktop.position(element)
    except RuntimeError as error:
        entry["error"] = f"position: {error}"
        return False
    size = desktop.attr(element, "AXSize")
    width_height = ax.Point()
    offset = (60, 10)
    if size and ax.read_point(size, 2, ct.byref(width_height)):
        offset = (max(4.0, min(width_height.x / 2, 240)), max(4.0, width_height.y / 2))
    local = (point.x + offset[0] - origin.x, point.y + offset[1] - origin.y)
    entry["click_local"] = [round(v, 1) for v in local]
    try:
        desktop.click_point(pid, root, window, PROJECT.stem, local[0], local[1])
    except RuntimeError as error:
        entry["error"] = str(error)
        return False
    return True


def wait_field_focus(desktop, element, root, seconds=1.5):
    end = time.monotonic() + seconds
    focused = focused_bool(desktop, element)
    while not focused and time.monotonic() < end:
        time.sleep(0.15)
        focused = focused_bool(desktop, element)
    return {"field_axfocused": focused,
            "app_focused": focused_element(desktop, root)}


def focus_and_type(desktop, pid, root, window, origin, field, tag):
    # Click-focus the field (CGEvent), confirm AXFocused, type "wall" with
    # per-character keycode taps at 120 ms cadence.
    entry = {"action": "click", "target": tag}
    if not click_element_center(desktop, pid, root, window, origin, field, entry):
        return {"error": entry.get("error")}, None
    focus = wait_field_focus(desktop, field, root)
    if not focus["field_axfocused"]:
        time.sleep(0.3)
    if not ax.post_allowed():
        return {"error": "event posting preflight failed", "focus": focus}, None
    tap_text(pid, "wall")
    time.sleep(0.5)
    return {"focus": focus, "actions": entry}, desktop.text(field, "AXValue")


def clear_search(pid, desktop, element):
    attempts = []
    for label, steps in (("escape", [(SPECIALS["escape"], 0)]),
                         ("cmd_a_backspace", [(KEYCODES["a"], CMD_FLAGS),
                                              (SPECIALS["backspace"], 0)])):
        for code, flags in steps:
            if flags:
                tap_with_flags(pid, code, flags)
            else:
                tap_key(pid, code, pause=0.2)
        time.sleep(0.3)
        value = desktop.text(element, "AXValue")
        attempts.append({"method": label, "value_after": value})
        if value == "":
            break
    return attempts


def wall_hits(rows):
    return [row for row in rows
            if row.get("key") == "wall_loops" or "wall_loops" in (row.get("help") or "")]


def focus_probes(desktop, pid, root, window, wall_rows):
    # Read-only focus hunting on the materialized wall_loops row; the "3"
    # write happens only if a wall_loops value field ends up verifiably
    # focused, and the original value is restored afterwards.
    log = []
    targets = [row for row in wall_rows
               if row["role"] in {"AXTextField", "AXComboBox", "AXStaticText"}]
    for row in targets[:1]:
        element = None
        for candidate in safe_elements(desktop, window):
            try:
                point = desktop.position(candidate)
            except RuntimeError:
                continue
            if (desktop.text(candidate, "AXRole") == row["role"]
                    and round(point.x, 1) == row["x"] and round(point.y, 1) == row["y"]):
                element = candidate
                break
        if element is None:
            log.append({"target": row["role"], "error": "element not re-found"})
            continue
        try:
            desktop.act(pid, element, "AXFocused", ax.true_value)
            log.append({"target": row["role"], "axfocused_write": None})
        except RuntimeError as error:
            log.append({"target": row["role"], "axfocused_write": str(error)})
        time.sleep(0.3)
        log.append({"state": "after_axfocused", "field_axfocused": focused_bool(desktop, element),
                    "app_focused": focused_element(desktop, root)})
    for label, code in (("tab", SPECIALS["tab"]), ("down", SPECIALS["down"])):
        tap_key(pid, code, pause=0.3)
        log.append({"state": f"after_{label}", "app_focused": focused_element(desktop, root)})
    focused = focused_element(desktop, root)
    log.append({"final_focused": focused})
    return log, focused


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
        note("entry", {"pid": pid, "version": version, "origin": [origin.x, origin.y]})

        # --- Advanced ON, then the outline (parameter tree) view ------------
        advanced = checkbox_at(desktop, window, 673, 689)
        actions.append({"action": "AXPress", "target": "advanced_checkbox",
                        "at": [673, 689], "error": None if advanced else "not found"})
        if advanced is not None:
            note("advanced_press", press_catching(desktop, pid, advanced))
        time.sleep(0.6)
        tree_box = checkbox_at(desktop, window, 453, 686)
        actions.append({"action": "AXPress", "target": "view_checkbox",
                        "at": [453, 686], "error": None if tree_box else "not found"})
        if tree_box is not None:
            note("tree_press", press_catching(desktop, pid, tree_box))
        time.sleep(1.2)
        baseline = census_outline(desktop, window, "outline_baseline")
        (OUT / "outline_baseline.json").write_text(json.dumps(baseline, indent=1))
        note("baseline", {"rows": len(baseline["rows"]),
                          "counts": baseline.get("outline_counts")})

        # --- phase A: the tree's own filter field + commit channels ---------
        filter_field = find_field_by_placeholder(desktop, window, "Search", y_band=(700, 735))
        note("filter_field", None if filter_field is None else
             element_json(desktop, filter_field, "phaseA_located"))
        phase_a = {}
        if filter_field is not None:
            typed, value = focus_and_type(desktop, pid, root, window, origin,
                                          filter_field, "phaseA_box")
            phase_a["typed"] = typed
            phase_a["field_value"] = value
            page = census_outline(desktop, window, "tree_keycode")
            (OUT / "tree_keycode.json").write_text(json.dumps(page, indent=1))
            full = full_dump(desktop, window, "tree_keycode")
            phase_a["snap_keycode"] = {"diff": diff_rows(baseline["rows"], page["rows"]),
                                       "wall_rows": len(wall_hits(page["rows"])),
                                       "popups": dump_popups(desktop, root, "tree_keycode"),
                                       "windows": windows_snapshot(desktop, root)}
            phase_a["full_keycode"] = {"elements": full["elements"],
                                       "wall_rows": len(full["wall_rows"])}
            (OUT / "tree_keycode_full_wall_rows.json").write_text(
                json.dumps(full["wall_rows"], indent=1))
            note("phase_a_typed", {"value": value, "snap": phase_a["snap_keycode"],
                                   "full": phase_a["full_keycode"]})

            # commit channel 1: bare Return on the open dropdown
            tap_key(pid, SPECIALS["return"], pause=0.6)
            page = census_outline(desktop, window, "tree_return")
            (OUT / "tree_return.json").write_text(json.dumps(page, indent=1))
            full = full_dump(desktop, window, "tree_return")
            phase_a["snap_return"] = {"diff": diff_rows(baseline["rows"], page["rows"]),
                                      "wall_rows": len(wall_hits(page["rows"])),
                                      "popups": dump_popups(desktop, root, "tree_return"),
                                      "app_focused": focused_element(desktop, root)}
            phase_a["full_return"] = {"elements": full["elements"],
                                      "wall_rows": len(full["wall_rows"])}
            (OUT / "tree_return_full_wall_rows.json").write_text(
                json.dumps(full["wall_rows"], indent=1))
            note("phase_a_return", {"snap": phase_a["snap_return"],
                                    "full": phase_a["full_return"]})

            # commit channel 2: Down (first match) then Return
            tap_key(pid, SPECIALS["down"], pause=0.3)
            tap_key(pid, SPECIALS["return"], pause=0.6)
            page = census_outline(desktop, window, "tree_down_return")
            (OUT / "tree_down_return.json").write_text(json.dumps(page, indent=1))
            full = full_dump(desktop, window, "tree_down_return")
            phase_a["snap_down_return"] = {"diff": diff_rows(baseline["rows"], page["rows"]),
                                           "wall_rows": len(wall_hits(page["rows"])),
                                           "popups": dump_popups(desktop, root, "tree_down_return"),
                                           "app_focused": focused_element(desktop, root)}
            phase_a["full_down_return"] = {"elements": full["elements"],
                                           "wall_rows": len(full["wall_rows"])}
            (OUT / "tree_down_return_full_wall_rows.json").write_text(
                json.dumps(full["wall_rows"], indent=1))
            note("phase_a_down_return", {"snap": phase_a["snap_down_return"],
                                         "full": phase_a["full_down_return"]})
            phase_a["final_field_value"] = desktop.text(filter_field, "AXValue")
            clear_search(pid, desktop, filter_field)

        # --- phase C (conditional): wall_loops materialized anywhere --------
        materialized = []
        for name in ("tree_keycode", "tree_return", "tree_down_return"):
            path = OUT / f"{name}_full_wall_rows.json"
            if path.exists():
                materialized += json.loads(path.read_text())
        note("materialized_wall_rows", len(materialized))
        if materialized:
            log, focused = focus_probes(desktop, pid, root, window, materialized)
            note("focus_probes", log)
            value_field = None
            if focused and focused.get("role") == "AXTextField" and focused.get("spot"):
                for element in safe_elements(desktop, window):
                    if desktop.text(element, "AXRole") != "AXTextField":
                        continue
                    try:
                        point = desktop.position(element)
                    except RuntimeError:
                        continue
                    if [round(point.x, 1), round(point.y, 1)] == focused["spot"] \
                            and key_from_help(desktop.text(element, "AXHelp")) == "wall_loops":
                        value_field = element
                        break
            if value_field is not None:
                original = desktop.text(value_field, "AXValue")
                tap_key(pid, KEYCODES["3"], pause=0.5)
                typed = desktop.text(value_field, "AXValue")
                # restore by keyboard when every char has a keycode; the
                # AXValue+AXConfirm channel (panel2-proven on materialized
                # fields) is the belt-and-suspenders fallback either way.
                try:
                    tap_with_flags(pid, KEYCODES["a"], CMD_FLAGS)
                    tap_key(pid, SPECIALS["backspace"], pause=0.3)
                    for char in original:
                        tap_key(pid, KEYCODES[char], pause=0.2)
                    tap_key(pid, SPECIALS["return"], pause=0.5)
                except RuntimeError as error:
                    note("restore_keyboard_error", str(error))
                restored = desktop.text(value_field, "AXValue")
                if restored != original:
                    desktop.act(pid, value_field, "AXValue", desktop.string(original))
                    desktop.act(pid, value_field, "AXConfirm")
                    time.sleep(0.4)
                    restored = desktop.text(value_field, "AXValue")
                note("value_write_probe", {"original": original, "after_3": typed,
                                           "restored": restored,
                                           "restored_ok": restored == original})
            else:
                note("value_write_probe", "skipped: no focused wall_loops value field")

        # --- phase B: flat page preset box, clean re-test --------------------
        phase_b = {}
        toggle = checkbox_at(desktop, window, 453, 686)
        if toggle is not None:
            note("flat_press", press_catching(desktop, pid, toggle))
            time.sleep(0.8)
            flat_before = census_flat(desktop, window, "flat_before")
            (OUT / "flat_before.json").write_text(json.dumps(flat_before, indent=1))
            opener, opener_matches = find_search_opener(desktop, window)
            preset_field = None
            if opener is not None:
                actions.append({"action": "AXPress", "target": "search_opener",
                                "help": (desktop.text(opener, "AXHelp") or "")[:60],
                                "tooltip_matches": opener_matches})
                note("opener_press", press_catching(desktop, pid, opener))
                time.sleep(1.0)
                preset_field = find_field_by_placeholder(desktop, window, "Search in preset")
            note("preset_field_flat", None if preset_field is None else
                 element_json(desktop, preset_field, "phaseB_located"))
            if preset_field is not None:
                typed, value = focus_and_type(desktop, pid, root, window, origin,
                                              preset_field, "phaseB_box")
                phase_b["typed"] = typed
                phase_b["field_value"] = value
                flat_after = census_flat(desktop, window, "flat_after")
                (OUT / "flat_after.json").write_text(json.dumps(flat_after, indent=1))
                phase_b["snap"] = {"diff": diff_rows(flat_before, flat_after),
                                   "wall_rows": len(wall_hits(flat_after)),
                                   "popups": dump_popups(desktop, root, "flat_after"),
                                   "windows": windows_snapshot(desktop, root)}
                note("phase_b", phase_b)
                clear_search(pid, desktop, preset_field)

        census = {
            "version": version,
            "baseline": {"rows": len(baseline["rows"]),
                         "counts": baseline.get("outline_counts")},
            "phase_a_tree_filter": phase_a,
            "phase_b_preset_box": phase_b,
            "actions": actions,
            "meta": {
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "window_origin": [origin.x, origin.y],
                "notes": [
                    "phase A: the outline page's own filter field ('Search plate, object and part.') with click-focus, per-char keycode 'wall', then Return and Down+Return commit channels; full-window dumps after every step",
                    "phase B: the flat page preset box ('Search in preset...') re-tested with the same clean click-focus + keycode method",
                    "read-only apart from the guarded value_write_probe (typed 3 then restored the original string)",
                ],
            },
        }
        (OUT / "search_probe.json").write_text(json.dumps(census, indent=1))
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
    print("[probe13] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
