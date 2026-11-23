"""Probe 16 (task A5): prove the wall_loops edit mechanics end to end.

Probe 15 established (OCR, global coords): Strength band tab (478,776),
"Walls" section (y~803), "Wall loops" row (y~835) with its value token
"=2" at (608,833) -- all visible without scrolling. This probe fixes the
OCR crop-coordinate scaling (Vision boxes were multiplied by the full-image
dims; now scaled by the cropped image and offset to global) and proves:
  1. click the value cell left of any spinner arrows -> does an editor mount
     (OCR-visible and/or an AXTextField materializing in the tree band)?
  2. keycode select-all + "3" + Return -> does the committed value read 3
     by OCR and by the tree's AX exposure?
  3. revert to 2 the same way, verify, and leave nothing saved.
Writes out/edit_probe.json + captures; result.json; 420 s fuse.
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
            "7": 26, "8": 28, "9": 25, ".": 47, "a": 0}
SPECIALS = {"escape": 53, "backspace": 51, "return": 36}
CMD_FLAGS = 0x100

# Global coords, scale 1.0 (1920x1080 display); see probe15 evidence.
TREE_CROP = (360, 700, 460, 190)

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
var ox = 0, oy = 0
if args.count >= 6 {
    let x = Int(args[2])!, y = Int(args[3])!, w = Int(args[4])!, h = Int(args[5])!
    if let cropped = cg.cropping(to: CGRect(x: x, y: y, width: w, height: h)) {
        cg = cropped
        ox = x; oy = y
    }
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
        let w = Double(cg.width), h = Double(cg.height)
        let px = box.origin.x * w + Double(ox), py = (1.0 - box.origin.y - box.height) * h + Double(oy)
        print(String(format: "%.0f,%.0f,%.0f,%.0f\t", px, py, box.width * w, box.height * h) + top.string)
    }
}
'''


def note(key, value):
    RESULT[key] = value
    print(f"[probe16] {key}: {json.dumps(value)[:800]}", flush=True)


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


def capture(tag):
    """screencapture writes `.tag.png` and hangs; kill it and keep the PNG."""
    final = OUT / f"{tag}.png"
    hidden = OUT / f".{tag}.png"
    for stale in (final, hidden):
        if stale.exists():
            stale.unlink()
    try:
        subprocess.run(["/usr/sbin/screencapture", "-x", str(final)],
                       capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        pass
    for candidate in (final, hidden):
        if candidate.exists() and candidate.stat().st_size > 1000:
            return candidate
    return None


def ocr(png, crop=None):
    args = ["/usr/bin/swift", str(WORK / "ocr.swift"), str(png)]
    if crop:
        args += [str(v) for v in crop]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
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
    return rows


def digits_of(text):
    return "".join(ch for ch in text if ch.isdigit())


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
    time.sleep(0.3)


def ax_fields_in_band(desktop, window, y0=700, y1=905):
    elements, pending = [], [window]
    while pending and len(elements) < 900:
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
        if y0 <= point.y <= y1:
            fields.append({"x": round(point.x, 1), "y": round(point.y, 1),
                           "value": desktop.text(element, "AXValue"),
                           "help_tail": (desktop.text(element, "AXHelp") or "")[-90:]})
    fields.sort(key=lambda f: f["y"])
    return fields


def find_row(rows, needle):
    for row in rows:
        if needle.lower() in row["text"].lower():
            return row
    return None


def value_token(rows, label_row):
    same_line = [r for r in rows
                 if abs(r["y"] - label_row["y"]) <= 9 and r["x"] > label_row["x"] + label_row["w"] - 5]
    numbered = [r for r in same_line if digits_of(r["text"])]
    return numbered, same_line


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

        # Strength tab (OCR-located on the default page).
        png = capture("default")
        band = [r for r in ocr(png) if r["text"].strip().lower() == "strength"]
        if not band:
            raise RuntimeError("Strength tab not found")
        tab = band[0]
        desktop.click_point(pid, root, window, PROJECT.stem,
                            tab["x"] + tab["w"] / 2 - origin.x,
                            tab["y"] + tab["h"] / 2 - origin.y)
        time.sleep(1.2)

        rows = ocr(capture("strength"), TREE_CROP)
        note("strength_rows", [{"text": r["text"], "x": round(r["x"]), "y": round(r["y"]),
                                "w": round(r["w"])} for r in rows])
        label = find_row(rows, "wall loops")
        if label is None:
            raise RuntimeError("Wall loops row not visible on the Strength page")
        numbered, same_line = value_token(rows, label)
        note("wall_row", {"label": {"text": label["text"], "x": round(label["x"]),
                                    "y": round(label["y"]), "w": round(label["w"])},
                          "same_line": [{"text": r["text"], "x": round(r["x"]),
                                         "y": round(r["y"])} for r in same_line]})
        if not numbered:
            raise RuntimeError("No numeric value token on the wall-loops row")
        token = numbered[0]
        initial = digits_of(token["text"])
        note("initial_value", {"token": token["text"], "value": initial})

        def set_value(new_text):
            """Click the value cell, select-all, type, Return; return evidence."""
            click_x = token["x"] + min(12, token["w"] / 2)  # left of spinner arrows
            click_y = token["y"] + token["h"] / 2
            desktop.click_point(pid, root, window, PROJECT.stem,
                                click_x - origin.x, click_y - origin.y)
            time.sleep(0.8)
            editor_png = capture("editor_open")
            editor_rows = ocr(editor_png, TREE_CROP)
            fields = ax_fields_in_band(desktop, window)
            evidence = {"click_global": [round(click_x), round(click_y)],
                        "editor_rows": [{"text": r["text"], "x": round(r["x"]),
                                         "y": round(r["y"])} for r in editor_rows],
                        "ax_fields": fields}
            tap_with_flags(pid, KEYCODES["a"], CMD_FLAGS)  # select all (a keycode 0)
            for char in new_text:
                tap_key(pid, KEYCODES[char], pause=0.25)
            tap_key(pid, SPECIALS["return"], pause=0.7)
            after_rows = ocr(capture("after_commit"), TREE_CROP)
            after_numbered, _ = value_token(after_rows, find_row(after_rows, "wall loops")
                                            or label)
            evidence["after_rows_numbers"] = [{"text": r["text"], "x": round(r["x"]),
                                               "y": round(r["y"])} for r in after_numbered]
            evidence["after_digits"] = digits_of(after_numbered[0]["text"]) if after_numbered else None
            evidence["ax_fields_after"] = ax_fields_in_band(desktop, window)
            return evidence

        edit3 = set_value("3")
        note("edit_3", edit3)
        revert2 = None
        if edit3["after_digits"] == "3":
            revert2 = set_value("2")
            note("revert_2", revert2)
        note("verdict", {"edit_to_3_ocr": edit3["after_digits"],
                         "revert_to_2_ocr": None if revert2 is None else revert2["after_digits"],
                         "ax_editor_materialized": bool(edit3["ax_fields"])})
        (OUT / "edit_probe.json").write_text(json.dumps(RESULT, indent=1))


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
    print("[probe16] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
