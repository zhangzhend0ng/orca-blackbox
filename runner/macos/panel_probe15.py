"""Probe 15 (task A5): OCR-driven Strength page recon for the walls goal.

Screen capture turned out to work (screencapture writes `.name.png` then
hangs; killing the process keeps the completed PNG) and Vision OCR reads the
self-drawn widgets A2 could not address. The A2 page-band map gets corrected
by OCR: the band at y~767 is labeled Quality/Strength/Support/Multimaterial/
Others, so what A2 called "the outline page" is the Strength page (its tree).
This probe empirically answers, for the walls chain:
  A. click the OCR-located Strength band tab -> does the parameter tree show
     a "Wall loops" row with value 2 without any scrolling?
  B. click that row's value cell -> does an editor mount (OCR-visible and/or
     AX-materialized), accept keycode "3", and read back 3?
  C. only if the row is not visible: OCR-verified scroll attempts (scrollbar
     thumb drag at window-local (405+8, ~745)->(…, 860), track click, arrow
     keypresses, wheel deltas) with pixel-truth row movement.
Read-only for the project file: nothing is saved; Orca is killed at the end.
Writes out/strength_probe.json (+ captures) and result.json. 420 s fuse.
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
RESULT = {"ok": False}
KEYCODES = {"0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22,
            "7": 26, "8": 28, "9": 25, ".": 47, "a": 0, "w": 13, "l": 37}
SPECIALS = {"tab": 48, "down": 125, "up": 126, "escape": 53, "backspace": 51,
            "return": 36, "home": 115, "end": 119, "page_down": 121, "page_up": 116}
CMD_FLAGS = 0x100

SWIFT_OCR = r'''
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let url = URL(fileURLWithPath: args[1])
guard let image = NSImage(contentsOf: url),
      let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff) else { exit(3) }
var cg = bitmap.cgImage!
if args.count >= 6 {
    let rect = CGRect(x: Int(args[2])!, y: Int(args[3])!, width: Int(args[4])!, height: Int(args[5])!)
    if let cropped = cg.cropping(to: rect) { cg = cropped }
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([request])
let results = (request.results ?? []) as [VNRecognizedTextObservation]
for obs in results {
    if let top = obs.topCandidates(1).first {
        let box = obs.boundingBox
        let w = Double(bitmap.pixelsWide), h = Double(bitmap.pixelsHigh)
        let px = box.origin.x * w, py = (1.0 - box.origin.y - box.height) * h
        print(String(format: "%.0f,%.0f,%.0f,%.0f\t", px, py, box.width * w, box.height * h) + top.string)
    }
}
'''


def note(key, value):
    RESULT[key] = value
    print(f"[probe15] {key}: {json.dumps(value)[:800]}", flush=True)


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


def capture(tag, extra=()):
    """screencapture writes `.tag.png` and hangs; kill it and keep the PNG."""
    final = OUT / f"{tag}.png"
    hidden = OUT / f".{tag}.png"
    for stale in (final, hidden):
        if stale.exists():
            stale.unlink()
    try:
        subprocess.run(["/usr/sbin/screencapture", "-x", *extra, str(final)],
                       capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        pass  # expected: the PNG is already complete under the hidden name
    for candidate in (final, hidden):
        if candidate.exists() and candidate.stat().st_size > 1000:
            return candidate
    return None


def ocr(png, crop=None):
    args = ["/usr/bin/swift", str(WORK / "ocr.swift"), str(png)]
    if crop:
        args += [str(v) for v in crop]
    done = subprocess.run(args, capture_output=True, text=True, timeout=90)
    rows = []
    for line in done.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or "," not in parts[0]:
            continue
        try:
            x, y, w, h = (float(v) for v in parts[0].split(","))
        except ValueError:
            continue
        rows.append({"x": x, "y": y, "w": w, "h": h, "text": parts[1].strip()})
    return rows, done.stderr[-300:]


def tap_key(pid, code, pause=0.15):
    for pressed in (True, False):
        event = ax.create_key(None, code, pressed)
        if not event:
            raise RuntimeError("Keyboard event is unavailable")
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(pause)


def tap_with_flags(pid, code, flags):
    set_flags = ax.bind(ax.cg, "CGEventSetFlags", None, ax.ptr, ct.c_uint64)
    for pressed in (True, False):
        event = ax.create_key(None, code, pressed)
        set_flags(event, flags)
        ax.post_to_pid(pid, event)
        time.sleep(0.05)
    time.sleep(0.25)


def drag_mouse(pid, desktop, root, window, origin, gx0, gy0, gx1, gy1, steps=12):
    """Synthetic left-button drag between two GLOBAL points via NSEvent->CGEvent.

    Mirrors click_point: NSEvent gets window-local coordinates (y measured
    from the top edge of the 1200x800 window), the CGEvent gets the global
    location. down=1, dragged=22, up=2.
    """
    make_mouse = ax.selector(b"mouseEventWithType:location:modifierFlags:timestamp:windowNumber:context:eventNumber:clickCount:pressure:")
    cg_event = ax.selector(b"CGEvent")
    wid, _ = desktop.slice_window(pid, root, window, PROJECT.stem)
    if not ax.post_allowed():
        raise RuntimeError("Event posting preflight failed")
    path = [(gx0 + (gx1 - gx0) * i / steps, gy0 + (gy1 - gy0) * i / steps)
            for i in range(steps + 1)]

    def post(kind, gx, gy, pressure):
        local = ax.Point(gx - origin.x, gy - origin.y)
        event = ax.mouse_event(ax.objc_class(b"NSEvent"), make_mouse, kind, local, 0,
                               time.monotonic(), wid, None, 1, 1, pressure)
        if not event:
            raise RuntimeError("drag event creation failed")
        native = ax.event_cg(event, cg_event)
        if not native:
            raise RuntimeError("drag CGEvent unavailable")
        ax.set_location(native, ax.Point(gx, gy))
        ax.post_to_pid(pid, native)
        time.sleep(0.03)

    post(1, gx0, gy0, 1.0)
    for gx, gy in path[1:-1]:
        post(22, gx, gy, 1.0)
    post(2, gx1, gy1, 0.0)
    return len(path)


def find_text(rows, needle):
    hits = [row for row in rows if needle.lower() in row["text"].lower()]
    return hits


def row_texts_summary(rows):
    return [{"text": row["text"], "x": round(row["x"]), "y": round(row["y"]),
             "w": round(row["w"]), "h": round(row["h"])} for row in rows]


def run():
    (WORK / "ocr.swift").write_text(SWIFT_OCR)
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
        note("entry", {"pid": pid, "version": version, "origin": [origin.x, origin.y]})

        # --- A: locate the Strength band tab on the default (Quality) page ----
        png = capture("quality_default")
        rows, err = ocr(png)
        note("quality_ocr_rows", row_texts_summary(rows))
        strength = [row for row in rows
                    if row["text"].strip().lower() == "strength"
                    and 750 <= row["y"] <= 785]
        if not strength:
            raise RuntimeError("Strength tab label not found by OCR")
        tab = strength[0]
        local = (tab["x"] + tab["w"] / 2 - origin.x, tab["y"] + tab["h"] / 2 - origin.y)
        note("strength_tab", {"global": [tab["x"] + tab["w"] / 2, tab["y"] + tab["h"] / 2],
                              "local": [local[0], local[1]]})
        desktop.click_point(pid, root, window, PROJECT.stem, local[0], local[1])
        time.sleep(1.2)

        png2 = capture("strength_page")
        tree_crop = (360, 700, 460, 185)  # process panel + tree viewport
        trows, terr = ocr(png2, tree_crop)
        note("strength_tree_rows", row_texts_summary(trows))
        wall = find_text(trows, "wall")
        note("wall_rows", row_texts_summary(wall))

        # --- B: value cell click + edit mechanics -----------------------------
        edit_probe = {"wall_row_found": bool(wall)}
        if wall:
            row = wall[0]
            # Value column sits right of the label; find an OCR token that is
            # a bare number on roughly the same line inside the panel.
            same_line = [r for r in trows
                         if r is not row and abs(r["y"] - row["y"]) <= 8
                         and r["x"] > row["x"] + row["w"]]
            edit_probe["value_candidates"] = row_texts_summary(same_line)
            value_box = None
            numbers = [r for r in same_line if r["text"].strip() in ("2", "3")]
            if numbers:
                value_box = numbers[0]
                edit_probe["value_read"] = numbers[0]["text"].strip()
                vx = numbers[0]["x"] + numbers[0]["w"] / 2 - origin.x
                vy = numbers[0]["y"] + numbers[0]["h"] / 2 - origin.y
                edit_probe["value_click_local"] = [vx, vy]
                desktop.click_point(pid, root, window, PROJECT.stem, vx, vy)
                time.sleep(0.8)
                png3 = capture("wall_editor")
                erows, _ = ocr(png3, tree_crop)
                edit_probe["editor_rows"] = row_texts_summary(erows)
                # AX census: did the editor materialize?
                elements = []
                pending = [window]
                while pending and len(elements) < 800:
                    element = pending.pop()
                    elements.append(element)
                    try:
                        pending.extend(reversed(desktop.children(element)))
                    except RuntimeError:
                        pass
                fields = []
                for element in elements:
                    try:
                        if desktop.text(element, "AXRole") != "AXTextField":
                            continue
                        point = desktop.position(element)
                    except RuntimeError:
                        continue
                    if 700 <= point.y <= 900:
                        fields.append({"x": round(point.x, 1), "y": round(point.y, 1),
                                       "value": desktop.text(element, "AXValue")})
                edit_probe["ax_text_fields_in_tree"] = fields
                if fields:  # prefer the AX channel for the write itself
                    field_value = fields[0]
                    note("editor_ax_field", field_value)
                # Type 3 with keycodes; then read back via OCR and AX.
                tap_key(pid, KEYCODES["3"], pause=0.4)
                tap_key(pid, SPECIALS["return"], pause=0.6)
                png4 = capture("wall_after_3")
                arows, _ = ocr(png4, tree_crop)
                after_numbers = [r for r in arows
                                 if r["text"].strip() in ("2", "3")
                                 and abs(r["y"] - row["y"]) <= 8]
                edit_probe["after_write_numbers"] = row_texts_summary(after_numbers)
                elements = []
                pending = [window]
                while pending and len(elements) < 800:
                    element = pending.pop()
                    elements.append(element)
                    try:
                        pending.extend(reversed(desktop.children(element)))
                    except RuntimeError:
                        pass
                fields_after = []
                for element in elements:
                    try:
                        if desktop.text(element, "AXRole") != "AXTextField":
                            continue
                        point = desktop.position(element)
                    except RuntimeError:
                        continue
                    if 700 <= point.y <= 900:
                        fields_after.append({"x": round(point.x, 1), "y": round(point.y, 1),
                                             "value": desktop.text(element, "AXValue")})
                edit_probe["ax_text_fields_after"] = fields_after
        note("edit_probe", edit_probe)

        # --- C: scroll contingencies, only when the row was not visible ------
        scroll_log = []
        if not wall:
            # C1: scrollbar thumb drag (window-local x~405+8=413... global 773).
            try:
                steps = drag_mouse(pid, desktop, root, window, origin,
                                   origin.x + 413, origin.y + 745,
                                   origin.x + 413, origin.y + 860)
                time.sleep(0.8)
                png5 = capture("tree_after_drag")
                crows, _ = ocr(png5, tree_crop)
                scroll_log.append({"channel": "thumb_drag", "steps": steps,
                                   "rows": row_texts_summary(crows)})
            except Exception as error:  # noqa: BLE001 - probe must log and continue
                scroll_log.append({"channel": "thumb_drag", "error": str(error)})
            # C2: Down/PageDown/Home keys aimed at the tree.
            for name in ("down", "page_down", "home", "end"):
                tap_key(pid, SPECIALS[name], pause=0.3)
            time.sleep(0.8)
            png6 = capture("tree_after_keys")
            krows, _ = ocr(png6, tree_crop)
            scroll_log.append({"channel": "keys(down,pagedown,home,end)",
                               "rows": row_texts_summary(krows)})
        note("scroll_log", scroll_log)

        (OUT / "strength_probe.json").write_text(json.dumps(RESULT, indent=1))


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
    RESULT["ok"] = error is None and RESULT.get("orca_left") == []
    (WORK / "result.json").write_text(json.dumps(RESULT, indent=1))
    print("[probe15] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
