"""One-shot AX recon of the Orca process parameter panel (runs in the test login).

Read-mostly: boots Orca on a throwaway datadir with the cube fixture, then
(1) dumps the menu bar and the panel tree with every readable AX attribute,
(2) tries System Events and screencapture for alternate channels,
(3) AXPresses every icon button around the Process preset row (dialog hunt),
(4) grid-clicks the blank band below the preset row (self-drawn tab-bar hunt)
    with "a text field reading 2 appears" as the Strength-tab hit criterion,
(5) verifies offscreen (virtualized) fields accept focus + value writes.

Writes out/*.json next to this script and a result.json verdict for the driver.
"""
import json
import os
from pathlib import Path
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
ESC = 53
TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier",
              "AXPlaceholderValue", "AXValue", "AXRoleDescription")


def note(key, value):
    RESULT[key] = value
    print(f"[probe] {key}: {json.dumps(value)[:400]}", flush=True)


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
    size = desktop.attr(element, "AXSize")
    width_height = ax.Point()
    if size and ax.read_point(size, 2, ax.ct.byref(width_height)):
        item["w"], item["h"] = round(width_height.x, 1), round(width_height.y, 1)
    return item


def tree(desktop, root_element, cap=800):
    out = []
    for element in desktop.descendants(root_element):
        out.append(element_json(desktop, element))
        if len(out) >= cap:
            out.append({"role": "TRUNCATED", "count": len(out)})
            break
    return out


def menu_dump(desktop, root):
    bar = desktop.attr(root, "AXMenuBar")
    menus = []
    if bar:
        for item in desktop.children(bar):
            entry = {"title": desktop.text(item, "AXTitle")}
            try:
                entry["items"] = [desktop.text(child, "AXTitle")
                                  for child in desktop.descendants(item)]
            except RuntimeError as error:
                entry["error"] = str(error)
            menus.append(entry)
    return menus


def windows_snapshot(desktop, root):
    out = []
    for window in desktop.children(root, "AXWindows"):
        out.append({"subrole": desktop.text(window, "AXSubrole"),
                    "title": desktop.text(window, "AXTitle"),
                    "role": desktop.text(window, "AXRole")})
    return out


def send_esc(pid):
    if not ax.post_allowed():
        return
    for pressed in (True, False):
        event = ax.create_key(None, ESC, pressed)
        if event:
            ax.post_to_pid(pid, event)
            time.sleep(0.04)


def field_signature(desktop, window):
    fields = [element for element in desktop.descendants(window)
              if desktop.text(element, "AXRole") == "AXTextField"]
    fields.sort(key=lambda element: desktop.position(element).y)
    return [desktop.text(element, "AXValue") for element in fields], fields


def run():
    console_uid = os.stat("/dev/console").st_uid
    if not ax.trusted():
        raise RuntimeError("Accessibility permission is missing")
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
        seed()
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP), "--args", "--datadir",
                        str(PROFILE), str(PROJECT)], check=True, timeout=20)
        pid = wait_for_orca(desktop)
        root = desktop.own(ax.application(pid))
        if ax.set_timeout(root, 2) != 0:
            raise RuntimeError("Cannot set AX timeout")
        window = wait_for_window(desktop, root)
        OUT.mkdir()
        origin = desktop.position(window)
        note("entry", {"pid": pid, "title": desktop.text(window, "AXTitle"),
                       "origin": [origin.x, origin.y],
                       "size": element_json(desktop, window).get("w", None)})

        # 1-2: menu bar + full-attribute simple tree.
        note("menubar", menu_dump(desktop, root))
        (OUT / "tree_simple.json").write_text(json.dumps(tree(desktop, window)))

        # 3: System Events alternate channel.
        note("sysevents", system_events())

        # 4: screencapture alternate channel.
        note("screencapture", try_screencapture())

        # 5: Advanced ON, full-attribute dump of the 24-field flat list.
        press_advanced(desktop, pid, window)
        time.sleep(0.6)
        (OUT / "tree_advanced.json").write_text(json.dumps(tree(desktop, window)))
        baseline, _ = field_signature(desktop, window)
        note("advanced_values", baseline)

        # 6: AXPress sweep over icon buttons (dialog hunt).
        button_sweep(desktop, pid, root, window)

        # 7: tab-band grid click (Strength hunt).
        tab_grid(desktop, pid, root, window, origin, baseline)

        # 8: offscreen focus + value write on a virtualized field.
        offscreen_write(desktop, pid, window)
    note("ok", True)


def seed():
    resources = APP / "Contents/Resources"
    system = PROFILE / "system"
    system.mkdir(parents=True)
    for vendor in ("Snapmaker", "BBL"):
        shutil.copytree(resources / "profiles" / vendor, system / vendor)
        shutil.copy2(resources / "profiles" / (vendor + ".json"), system)
    shutil.copytree(resources / "printers", PROFILE / "printers")
    shutil.copy2(WORK / "seed.conf", PROFILE / "Snapmaker_Orca.conf")


def orca_processes():
    output = subprocess.check_output(["/bin/ps", "-ww", "-U", str(os.getuid()), "-o", "pid=,command="],
                                     text=True)
    found = {}
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and (parts[1] == EXE or parts[1].startswith(EXE + " ")):
            found[int(parts[0])] = parts[1]
    return found


def wait_for_orca(desktop):
    end = time.monotonic() + 25
    while time.monotonic() < end:
        matches = [pid for pid, command in orca_processes().items()
                   if command.endswith(f"--datadir {PROFILE} {PROJECT}")]
        if len(matches) == 1:
            return matches[0]
        time.sleep(0.4)
    raise TimeoutError("Orca probe process missing")


def wait_for_window(desktop, root):
    end = time.monotonic() + 80
    while time.monotonic() < end:
        windows = [w for w in desktop.children(root, "AXWindows")
                   if desktop.text(w, "AXSubrole") == "AXStandardWindow"
                   and desktop.text(w, "AXTitle") == PROJECT.stem]
        if len(windows) == 1:
            return windows[0]
        time.sleep(0.4)
    raise TimeoutError("Probe project window did not open")


def system_events():
    script = (
        'tell application "System Events"\n'
        '  tell process "%s"\n'
        '    set nam to name of every window\n'
        '    set tfv to value of every text field of window 1\n'
        '    set tfh to help of every text field of window 1\n'
        '    set uir to role description of every UI element of window 1\n'
        '    return (nam as text) & "|" & (count of tfv as text) & "|" & '
        '(tfh as text) & "|" & (uir as text)\n'
        '  end tell\n'
        'end tell')
    for name in ("Snapmaker Orca", "Snapmaker_Orca"):
        try:
            done = subprocess.run(["/usr/bin/osascript", "-e", script % name],
                                  capture_output=True, text=True, timeout=20)
            return {"process": name, "rc": done.returncode,
                    "out": done.stdout[-2000:], "err": done.stderr[-500:]}
        except subprocess.TimeoutExpired:
            return {"process": name, "error": "osascript timed out (20 s)"}
    return {"error": "no process name matched"}


def try_screencapture():
    target = WORK / "out" / "screen.png"
    try:
        done = subprocess.run(["/usr/sbin/screencapture", "-x", str(target)],
                              capture_output=True, text=True, timeout=6)
        return {"rc": done.returncode, "err": done.stderr[-300:],
                "bytes": target.stat().st_size if target.exists() else 0}
    except subprocess.TimeoutExpired:
        return {"error": "screencapture timed out (6 s)"}


def press_advanced(desktop, pid, window):
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXCheckBox":
            continue
        point = desktop.position(element)
        if abs(point.x - 673) <= 40 and abs(point.y - 689) <= 25:
            desktop.act(pid, element, "AXPress")
            return True
    raise RuntimeError("Advanced checkbox not found near (673, 689)")


def button_sweep(desktop, pid, root, window):
    before = windows_snapshot(desktop, root)
    main_title = desktop.text(window, "AXTitle")
    # (x0, x1, y0, y1) bands: printer header icons, filament preset icons,
    # process header icons and the process preset row icons.
    bands = ((700, 780, 168, 182), (690, 780, 450, 466), (700, 780, 682, 698),
             (700, 780, 722, 738))
    pressed = []
    for element in desktop.descendants(window):
        if desktop.text(element, "AXRole") != "AXButton":
            continue
        point = desktop.position(element)
        if point.x > 760 and point.y > 780:  # scrollbar arrows: known, skip
            continue
        if not any(x0 <= point.x <= x1 and y0 <= point.y <= y1 for x0, x1, y0, y1 in bands):
            continue
        entry = {"x": round(point.x), "y": round(point.y)}
        try:
            desktop.act(pid, element, "AXPress")
            time.sleep(1.0)
            after = windows_snapshot(desktop, root)
            entry["windows"] = after
            newcomers = [w for w in after if w not in before
                         and not (w.get("subrole") == "AXStandardWindow" and w.get("title") == main_title)]
            if newcomers:
                for index, stranger in enumerate(newcomers):
                    handle = [w for w in desktop.children(root, "AXWindows")
                              if desktop.text(w, "AXRole") == stranger.get("role")
                              and desktop.text(w, "AXTitle") == stranger.get("title")]
                    if handle:
                        entry[f"dialog{index}"] = tree(desktop, handle[0], cap=400)
                send_esc(pid)
                time.sleep(0.8)
                entry["after_esc"] = windows_snapshot(desktop, root)
        except RuntimeError as error:
            entry["error"] = str(error)
            send_esc(pid)
            time.sleep(0.5)
        pressed.append(entry)
        try:
            desktop.check_owned(pid, window)
        except RuntimeError:
            note("button_sweep_aborted", {"pressed": pressed, "window_lost": True})
            return pressed
    note("button_sweep", pressed)
    return pressed


def tab_grid(desktop, pid, root, window, origin, baseline):
    tried = []
    changes = []
    found = None
    for y in (748, 760, 772, 784, 796):
        for x in range(390, 651, 20):
            label = {"x": x, "y": y}
            try:
                desktop.click_point(pid, root, window, PROJECT.stem,
                                    x - origin.x, y - origin.y)
            except RuntimeError as error:
                message = str(error)
                label["error"] = message
                send_esc(pid)
                time.sleep(0.6)
                tried.append(label)
                continue
            time.sleep(0.3)
            try:
                values, fields = field_signature(desktop, window)
            except RuntimeError as error:
                label["sig_error"] = str(error)
                send_esc(pid)
                time.sleep(0.5)
                tried.append(label)
                continue
            if values != baseline:
                label["values"] = values
                changes.append(label)
                if "2" in values:
                    found = {"x": x, "y": y, "values": values}
                    (OUT / "tree_strength.json").write_text(json.dumps(tree(desktop, window)))
                    note("tab_hit", found)
                    break
            tried.append(label)
        if found:
            break
    note("tab_grid", {"tried": len(tried), "changes": changes})
    if not found:
        send_esc(pid)
    return found


def offscreen_write(desktop, pid, window):
    values, fields = field_signature(desktop, window)
    target = None
    original = None
    for element, value in zip(fields, values):
        if desktop.position(element).y > 1400 and value not in ("", None):
            target, original = element, value
            break
    if target is None:
        note("offscreen_write", {"skipped": "no offscreen field with a value"})
        return
    entry = {"original": original, "y": round(desktop.position(target).y)}
    try:
        desktop.act(pid, target, "AXFocused", ax.true_value)
        desktop.act(pid, target, "AXValue", desktop.string("101"))
        time.sleep(0.3)
        entry["after_set"] = desktop.text(target, "AXValue")
        desktop.act(pid, target, "AXValue", desktop.string(original))
        time.sleep(0.2)
        entry["after_restore"] = desktop.text(target, "AXValue")
    except RuntimeError as error:
        entry["error"] = str(error)
    note("offscreen_write", entry)


RESULT = {"ok": False}


def main():
    end = time.monotonic() + 780
    error = None
    try:
        run()
    except BaseException:  # keep evidence even on aborts; driver still harvests
        import traceback
        error = traceback.format_exc()
        RESULT["error"] = error
    RESULT["finished_at"] = time.time()
    # Close Orca regardless.
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
    print("[probe] result:", json.dumps(RESULT)[:600], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
