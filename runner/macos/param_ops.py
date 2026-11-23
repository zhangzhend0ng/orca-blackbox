"""Five parameter-page operations on macOS Orca 2.4.1 (Feishu param-case port, step 1).

Subcommands, each printing ONE JSON line (ok, readback, screenshot paths):
  switch_tab    [--tabs a,b,...]        click each page tab once and read the page back
  find_row      --tab T [--group G] --label L
                                       OCR a row label inside a group, return screen coords
  set_float     --tab T [--group G] --label L --value V
  set_checkbox  --tab T [--group G] --label L
  pick_combo    --tab T [--group G] --label L --target X

From an ordinary shell a subcommand only supervises: the GUI work runs in the
test login's Aqua session (gui/<uid>, the session every Mac probe so far used)
through a one-shot LaunchAgent running the signed Python.app - the channel of
the A5 walls probes. Addressing reuses the walls method: screencapture + Vision
OCR locate the self-drawn tabs and rows, clicking a value cell materializes an
AXTextField, the value is then written and confirmed through AX.
"""
import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import zipfile
import zlib

import accessibility as ax

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
PROJECT = WORK / "probe.3mf"
PROFILE = WORK / "datadir"
OUT = WORK / "out"
EVIDENCE = ROOT / "docs/runs/evidence/mac-param-ops-2026-11-23"
LOCAL_SHOTS = ROOT / "artifacts/mac_param_ops/2026-11-23"
TRUSTED_PYTHON = Path("/Applications/Xcode.app/Contents/Developer/Library/Frameworks/"
                      "Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python")
TABS = ("Quality", "Strength", "Speed", "Support", "Multimaterial", "Others")
# Words the first lines of each page paint on Orca 2.4.1 (A3/A5 OCR evidence).
LANDMARKS = {"Quality": ("layer height",), "Strength": ("wall loops", "walls"),
             "Speed": ("speed",), "Support": ("support",),
             "Multimaterial": ("tower", "ooze", "wipe", "flush"),
             "Others": ("skirt", "special", "sequence", "g-code", "spiral")}
PANEL_WIDTH = 470  # left settings column, px at scale 1.0
TITLE_X = 26       # group titles start left of this offset, row labels right of it
VALUE_X = 253      # value column: numbers, and the faint square of a bool row
IEND = b"IEND\xaeB\x60\x82"
MAKE_MOUSE = ax.selector(b"mouseEventWithType:location:modifierFlags:timestamp:"
                         b"windowNumber:context:eventNumber:clickCount:pressure:")
create_value = ax.bind(ax.ax, "AXValueCreate", ax.ptr, ct.c_uint32, ax.ptr)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def wait_for(read, message, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = read()
        if value:
            return value
        time.sleep(0.25)
    raise TimeoutError(message)


def exactly_one(items):
    items = list(items)
    require(len(items) == 1, f"Expected one matching control, found {len(items)}")
    return items[0]


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def digits_of(text):
    return "".join(ch for ch in text if ch.isdigit() or ch == ".").strip(".")


def log(message):
    print(f"[param-ops] {message}", flush=True)


def brief(error, size=400):
    return f"{type(error).__name__}: {str(error)[:size]}"


# --- Orca process / fixture plumbing (same as the A5 probes) ---

def processes():
    output = subprocess.check_output(["/bin/ps", "-ww", "-U", str(os.getuid()), "-o", "pid=,command="],
                                     text=True)
    result = {}
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and (parts[1] == EXE or parts[1].startswith(EXE + " ")):
            result[int(parts[0])] = parts[1]
    return result


def owned(directory, project):
    suffix = f" --datadir {directory} {project}"
    return [pid for pid, command in processes().items() if command.endswith(suffix)]


def close_owned(directory, project):
    for pid in owned(directory, project):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    wait_for(lambda: not owned(directory, project), "Test process cleanup failed", 6)


def seed():
    resources = APP / "Contents/Resources"
    system = PROFILE / "system"
    system.mkdir(parents=True)
    for vendor in ("Snapmaker", "BBL"):
        shutil.copytree(resources / "profiles" / vendor, system / vendor)
        shutil.copy2(resources / "profiles" / (vendor + ".json"), system)
    shutil.copytree(resources / "printers", PROFILE / "printers")
    shutil.copy2(WORK / "seed.conf", PROFILE / "Snapmaker_Orca.conf")


def wait_window(desktop, root, title):
    def main_window():
        windows = [w for w in desktop.children(root, "AXWindows")
                   if desktop.text(w, "AXSubrole") == "AXStandardWindow" and desktop.text(w, "AXTitle") == title]
        return exactly_one(windows) if windows else None
    return wait_for(main_window, "Project window did not open", 80)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settings_of(project):
    with zipfile.ZipFile(project) as archive:
        return json.loads(archive.read("Metadata/project_settings.config"))


# --- screen channel: capture, OCR, pixels ---

def capture(tag):
    """screencapture writes `.tag.png` and then hangs in this session: poll for a
    complete stable file, kill it, and keep a visible copy."""
    final, hidden = OUT / f"{tag}.png", OUT / f".{tag}.png"
    for stale in (final, hidden):
        if stale.exists():
            stale.unlink()
    proc = subprocess.Popen(["/usr/sbin/screencapture", "-x", str(final)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + 8
    seen, same, png = {}, 0, None
    try:
        while time.monotonic() < end and png is None:
            sizes = {c: (c.stat().st_size if c.exists() else 0) for c in (final, hidden)}
            ready = [c for c, size in sizes.items() if size > 1000 and seen.get(c) == size]
            same = same + 1 if ready else 0
            seen = sizes
            if same >= 2:
                png = ready[0]
                if not png.read_bytes().endswith(IEND):
                    png, same = None, 0
            time.sleep(0.25)
    finally:
        proc.kill()
        proc.wait()
    if png is None:
        return None
    if png != final:
        shutil.copy2(png, final)
        png.unlink()
    return final


def ocr_rows(png, crop=None):
    tool = [str(WORK / "ocr")] if (WORK / "ocr").is_file() else ["/usr/bin/swift", str(WORK / "ocr.swift")]
    args = tool + [str(png)] + ([str(int(v)) for v in crop] if crop else [])
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


def crop_png(src, dst, rect):
    x, y, w, h = (int(round(v)) for v in rect)
    subprocess.run(["/usr/bin/sips", "-c", str(h), str(w), "--cropOffset", str(y), str(x),
                    str(src), "--out", str(dst)], check=True, capture_output=True, timeout=20)


def png_pixels(path):
    """RGB(A) 8-bit non-interlaced PNG -> (width, height, channels, rows of bytes)."""
    raw = Path(path).read_bytes()
    require(raw[:8] == b"\x89PNG\r\n\x1a\n", "Not a PNG")
    pos, idat, head = 8, [], None
    while pos + 8 <= len(raw):
        length, kind = struct.unpack(">I4s", raw[pos:pos + 8])
        body = raw[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    require(head is not None, "PNG has no IHDR")
    width, height, depth, ctype, _, _, interlace = head
    require(depth == 8 and ctype in (2, 6) and interlace == 0, f"Unsupported PNG {head}")
    channels = 3 if ctype == 2 else 4
    data = zlib.decompress(b"".join(idat))
    stride = width * channels
    rows, prev = [], bytearray(stride)
    for y in range(height):
        offset = y * (stride + 1)
        kind = data[offset]
        line = bytearray(data[offset + 1:offset + 1 + stride])
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up = prev[i]
            corner = prev[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        rows.append(line)
        prev = line
    return width, height, channels, rows


def pixel_diff(first, second):
    """Pixels whose strongest channel moved by more than 40 (0..255)."""
    w1, h1, c1, a = png_pixels(first)
    w2, h2, c2, b = png_pixels(second)
    require((w1, h1, c1) == (w2, h2, c2), "Pixel crops differ in shape")
    changed = 0
    for y in range(h1):
        ra, rb = a[y], b[y]
        for i in range(0, w1 * c1, c1):
            if max(abs(ra[i] - rb[i]), abs(ra[i + 1] - rb[i + 1]), abs(ra[i + 2] - rb[i + 2])) > 40:
                changed += 1
    return changed


# --- the addressed panel ---

def cf_scalar(desktop, value):
    if value is None:
        return None
    kind = ax.type_id(value)
    if kind == ax.boolean_type:
        return bool(ax.bool_value(value))
    if kind == ax.string_type:
        return desktop.cf_text(value)
    number = ct.c_int64()
    return number.value if ax.number_value(value, 4, ct.byref(number)) else None


class Panel:
    def __init__(self, desktop, pid, root, window):
        self.desktop, self.pid, self.root, self.window = desktop, pid, root, window
        self.shots, self.last_notes = {}, []

    def geometry(self):
        point = self.desktop.position(self.window)
        value = self.desktop.attr(self.window, "AXSize")
        size = ax.Point()
        require(value and ax.read_point(value, 2, ct.byref(size)), "Missing window size")
        return point, size

    @property
    def title(self):
        return self.desktop.text(self.window, "AXTitle")

    @property
    def dirty(self):
        return self.title.startswith("*")

    def modal_open(self):
        for candidate in self.desktop.children(self.root, "AXWindows"):
            if (self.desktop.text(candidate, "AXSubrole") in {"AXDialog", "AXSystemDialog"}
                    or self.desktop.text(candidate, "AXIdentifier") == "save-panel"
                    or self.desktop.children(candidate, "AXSheets")):
                return self.desktop.text(candidate, "AXTitle") or self.desktop.text(candidate, "AXSubrole")
        return None

    def resize(self, width, height):
        value = create_value(2, ct.byref(ax.Point(width, height)))
        error = ax.set_attr(self.window, self.desktop.string("AXSize"), value)
        ax.release(value)
        require(error == 0, f"AXSize set failed with AX error {error}")
        time.sleep(1.2)
        return self.geometry()

    def window_id(self, point, size):
        windows = self.desktop.own(ax.window_info(0, 0))
        matches = []
        for index in range(ax.array_size(windows)):
            info = ax.array_item(windows, index)

            def number(key):
                obj = ax.dict_value(info, self.desktop.string(key))
                result = ct.c_int64()
                return result.value if obj and ax.number_value(obj, 4, ct.byref(result)) else None

            if number("kCGWindowOwnerPID") != self.pid or number("kCGWindowLayer") != 0:
                continue
            bounds = ax.Rect()
            obj = ax.dict_value(info, self.desktop.string("kCGWindowBounds"))
            if (obj and ax.decode_bounds(obj, ct.byref(bounds))
                    and (point.x, point.y, size.x, size.y)
                    == (bounds.origin.x, bounds.origin.y, bounds.size.x, bounds.size.y)):
                matches.append(number("kCGWindowNumber"))
        require(len(matches) == 1 and matches[0], f"Cannot match a unique Orca window (matches={len(matches)})")
        return matches[0]

    def click(self, gx, gy, guard=True):
        """Targeted pointer click at a global point (screen px)."""
        point, size = self.geometry()
        if guard:
            modal = self.modal_open()
            require(modal is None, f"A modal dialog is covering the project: {modal}")
        wid = self.window_id(point, size)
        require(ax.post_allowed(), "Targeted input requires event posting permission")
        for kind in (1, 2):
            self.desktop.check_owned(self.pid, self.window)
            event = ax.mouse_event(ax.objc_class(b"NSEvent"), MAKE_MOUSE, kind,
                                   ax.Point(gx - point.x, size.y - (gy - point.y)), 0,
                                   time.monotonic(), wid, None, 1, 1, 1.0 if kind == 1 else 0.0)
            require(event and ax.event_window(event, ax.selector(b"windowNumber")) == wid,
                    "Pointer event has no matching target window")
            native = ax.event_cg(event, ax.selector(b"CGEvent"))
            require(native, "Pointer event is unavailable")
            ax.set_location(native, ax.Point(gx, gy))
            ax.post_to_pid(self.pid, native)
            time.sleep(0.12)

    def shot(self, tag):
        png = capture(tag)
        require(png is not None, f"Screen capture failed for {tag}")
        self.shots[tag] = png.name
        try:
            point, size = self.geometry()
            crop_png(png, OUT / f"{tag}.panel.png", (point.x, point.y, PANEL_WIDTH, size.y))
        except Exception as error:  # the crop is review material only
            log(f"panel crop {tag} skipped: {brief(error, 120)}")
        return png

    def read(self, tag, full=False):
        """Capture `tag` and OCR it; the settings column unless `full`."""
        png = self.shot(tag)
        crop = None
        if not full:
            point, size = self.geometry()
            crop = (point.x, point.y, PANEL_WIDTH, size.y)
        return ocr_rows(png, crop)

    # -- OCR addressing --

    def tab_band(self, rows):
        names = {name.lower(): name for name in TABS}
        hits = [{"tab": names[norm(r["text"])], **r} for r in rows if norm(r["text"]) in names]
        if not hits:
            return []
        top = min(h["y"] for h in hits)
        return [h for h in hits if h["y"] <= top + 30]

    def tabs_seen(self, rows):
        return [h["tab"] for h in sorted(self.tab_band(rows), key=lambda h: (h["y"], h["x"]))]

    def locate_tab(self, rows, name):
        band = self.tab_band(rows)
        exact = next((h for h in band if h["tab"] == name), None)
        if exact:
            return exact
        # Vision sometimes glues neighbouring tab words into one token: take the
        # name's share of that token's box.
        near = [r for r in rows if band and abs(r["y"] - band[0]["y"]) <= 10]
        for r in near:
            text = r["text"].lower()
            start = text.find(name.lower())
            if start >= 0 and not text[start + len(name):start + len(name) + 1].isalpha():
                x0 = r["x"] + r["w"] * start / len(text)
                x1 = r["x"] + r["w"] * (start + len(name)) / len(text)
                return {"tab": name, "x": x0, "y": r["y"], "w": x1 - x0, "h": r["h"], "text": r["text"]}
        return None

    def page_rows(self, rows):
        band = self.tab_band(rows)
        require(band, "Tab band not found by OCR")
        top = max(h["y"] + h["h"] for h in band) + 4
        return [r for r in rows if r["y"] > top]

    def page_text(self, rows):
        seen, text = set(), []
        for r in self.page_rows(rows):
            key = norm(r["text"])
            if key and key not in seen:
                seen.add(key)
                text.append(key)
        return text

    def find_row(self, rows, group, label):
        """The row `label` painted inside group `group` (None = whole page)."""
        point = self.geometry()[0]
        page = self.page_rows(rows)
        titles = [r for r in page if r["x"] - point.x < TITLE_X]
        start, end = -1e9, 1e9
        if group:
            wanted = norm(group)
            hit = next((t for t in titles if norm(t["text"]) and (wanted in norm(t["text"])
                                                                 or norm(t["text"]) in wanted)), None)
            require(hit, f"Group title {group!r} not visible; titles seen: {[t['text'] for t in titles]}")
            start = hit["y"]
            following = next((t for t in titles if t["y"] > hit["y"] + 5), None)
            end = following["y"] if following else 1e9
        wanted = norm(label)
        labels = [r for r in page if start < r["y"] < end and r["x"] - point.x >= TITLE_X
                  and wanted in norm(r["text"])]
        require(labels, f"Row {label!r} not visible in group {group!r}; page reads: {self.page_text(rows)}")
        labels.sort(key=lambda r: (norm(r["text"]) != wanted, r["y"]))
        return labels[0]

    def line_values(self, rows, row):
        """Tokens painted right of `row` on its line, left to right."""
        right = row["x"] + row["w"] - 5
        return sorted((r for r in rows if abs(r["y"] - row["y"]) <= 10 and r["x"] > right), key=lambda r: r["x"])

    def click_tab(self, name, rows):
        tab = self.locate_tab(rows, name)
        require(tab, f"{name} tab label not found by OCR; tabs seen: {self.tabs_seen(rows)}")
        self.click(tab["x"] + tab["w"] / 2, tab["y"] + tab["h"] / 2)
        time.sleep(1.0)
        return [round(tab["x"] + tab["w"] / 2), round(tab["y"] + tab["h"] / 2)]

    # -- Advanced mode (the Speed tab and the thin-wall row are Advanced-only) --

    def checkboxes(self):
        point, size = self.geometry()
        found = []
        for element in self.desktop.descendants(self.window):
            if self.desktop.text(element, "AXRole") != "AXCheckBox":
                continue
            try:
                at = self.desktop.position(element)
            except RuntimeError:
                continue
            if point.x <= at.x <= point.x + PANEL_WIDTH and point.y <= at.y <= point.y + size.y:
                words = " ".join(filter(None, (self.desktop.text(element, key) or "" for key in
                                                ("AXTitle", "AXDescription", "AXHelp"))))
                found.append({"element": element, "x": at.x, "y": at.y, "words": words[:90],
                              "value": cf_scalar(self.desktop, self.desktop.attr(element, "AXValue"))})
        return found

    def ensure_advanced(self, tag):
        """Switch the Process header's Advanced checkbox on; Speed in the tab band proves it."""
        rows = self.read(tag)
        if "Speed" in self.tabs_seen(rows):
            return {"already_on": True, "tabs": self.tabs_seen(rows)}
        note = {"already_on": False, "tabs_before": self.tabs_seen(rows), "attempts": []}
        boxes = None
        for attempt in ("ax", "box", "label", "left"):
            taken, box = None, None
            if attempt in ("ax", "box"):
                # The Advanced box carries no AX title/help: it is the AXCheckBox
                # painted at the right end of its OCR label (A2 map: 673,689).
                if boxes is None:
                    boxes = self.checkboxes()
                    note["checkboxes"] = [{k: v for k, v in b.items() if k != "element"} for b in boxes]
                text = next((r for r in rows if norm(r["text"]) == "advanced"), None)
                right = text["x"] + text["w"] if text else None
                near = [b for b in boxes if right is not None and abs(b["y"] - text["y"]) <= 12
                        and -6 <= b["x"] - right <= 40]
                named = next((b for b in boxes if "advanced" in b["words"].lower()), None)
                box = (min(near, key=lambda b: abs(b["x"] - right)) if near else None) or named
                if box is None:
                    note["attempts"].append({"how": attempt, "skipped": "no AX checkbox at the Advanced label"})
                    continue
                taken = {"how": attempt, "value_before": box["value"], "box": [box["x"], box["y"]]}
                if attempt == "ax":
                    self.desktop.act(self.pid, box["element"], "AXPress")
                else:
                    self.click(box["x"] + 8, box["y"] + 8)
            else:
                text = next((r for r in rows if norm(r["text"]) == "advanced"), None)
                if text is None:
                    note["attempts"].append({"how": attempt, "skipped": "Advanced label not OCR-read"})
                    continue
                x = text["x"] + text["w"] / 2 if attempt == "label" else text["x"] - 9
                self.click(x, text["y"] + text["h"] / 2)
                taken = {"how": attempt, "click": [round(x), round(text["y"] + text["h"] / 2)]}
            # The mode switch rebuilds the page: poll the band instead of trusting
            # one early read, and never toggle a second time once the box reads 1.
            seen = []
            for poll in range(4):
                time.sleep(1.2)
                rows = self.read(f"{tag}-{attempt}-{poll}")
                seen.append(self.tabs_seen(rows))
                if "Speed" in seen[-1]:
                    break
            taken["tabs_after"] = seen
            if box is not None and attempt in ("ax", "box"):
                taken["value_after"] = cf_scalar(self.desktop, self.desktop.attr(box["element"], "AXValue"))
            note["attempts"].append(taken)
            if "Speed" in seen[-1] or taken.get("value_after") == 1:
                note["turned_on_by"] = attempt
                note["speed_seen"] = "Speed" in seen[-1]
                return note
            rows = self.read(f"{tag}-{attempt}-later")
        raise RuntimeError(f"Advanced mode did not switch on: {json.dumps(note)[:700]}")

    def locate_row(self, tab, group, label, prefix):
        """Open `tab` and find the row; fall back to Advanced mode and a taller
        window. Returns (rows, row, notes, tag of the page shot)."""
        note = self.last_notes = []

        def attempt(tag):
            rows = self.read(f"{prefix}-{tag}-locate")
            note.append({"tab_click": self.click_tab(tab, rows)})
            rows = self.read(f"{prefix}-{tag}")
            return rows, self.find_row(rows, group, label), f"{prefix}-{tag}"

        try:
            rows, row, tag = attempt("page")
            return rows, row, note, tag
        except RuntimeError as error:
            note.append({"standard_mode": brief(error)})
        note.append({"advanced": self.ensure_advanced(f"{prefix}-advanced")})
        try:
            rows, row, tag = attempt("page-adv")
            return rows, row, note, tag
        except RuntimeError as error:
            note.append({"advanced_mode": brief(error)})
        note.append({"widened": self.widen(f"{prefix}-widen")})
        try:
            rows, row, tag = attempt("page-wide")
            return rows, row, note, tag
        except RuntimeError as error:
            note.append({"wide_window": brief(error)})
        point, size = self.geometry()
        grown = self.resize(size.x, min(960, 1080 - point.y - 15))
        note.append({"resized_to": [grown[1].x, grown[1].y]})
        rows, row, tag = attempt("page-tall")
        return rows, row, note, tag

    def widen(self, tag):
        """Collapse the Printer and Filaments sections: the Process page then owns
        the settings column's height (its viewport is three lines otherwise)."""
        note = {"collapsed": []}
        for index in range(2):
            rows = self.read(f"{tag}-{index}")
            point = self.geometry()[0]
            process = next((r for r in rows if norm(r["text"]) == "process"), None)
            headers = [] if process is None else [
                r for r in rows if r["y"] < process["y"] - 20 and r["x"] - point.x < 40
                and norm(r["text"]).endswith(("printer", "filaments"))]
            if not headers:
                note["process_header_y"] = process["y"] if process else None
                break
            header = max(headers, key=lambda r: r["y"])
            at = (header["x"] + header["w"] / 2, header["y"] + header["h"] / 2)
            self.click(*at)
            time.sleep(1.2)
            note["collapsed"].append({"header": header["text"], "click": [round(at[0]), round(at[1])]})
        process = next((r for r in self.read(f"{tag}-after") if norm(r["text"]) == "process"), None)
        note["process_header_y_after"] = process["y"] if process else None
        return note


# --- operations (each returns the fields of its JSON line) ---

def op_switch_tab(panel, ns):
    tabs = [t.strip() for t in ns["tabs"].split(",") if t.strip()]
    require(tabs and all(t in TABS for t in tabs), f"Unknown tab in {ns['tabs']!r}")
    evidence = {}
    try:
        evidence["advanced"] = panel.ensure_advanced("switch-advanced")
    except Exception as error:
        evidence["advanced_error"] = brief(error, 700)
    steps = []
    for name in tabs:
        step = {"tab": name, "ok": False}
        try:
            rows = panel.read(f"switch-{name.lower()}-before")
            before = panel.page_text(rows)
            step["click"] = panel.click_tab(name, rows)
            after_rows = panel.read(f"switch-{name.lower()}-after")
            after = panel.page_text(after_rows)
            landmark = [k for k in LANDMARKS[name] if any(k in line for line in after)]
            changed = after != before
            step.update({"tabs_seen": panel.tabs_seen(after_rows), "landmark": landmark, "page_changed": changed,
                         "page_text": after[:12], "ok": bool(landmark) or (changed and bool(after)),
                         "verified_by": "landmark" if landmark else "page_text_changed" if changed and after else None})
        except Exception as error:
            step["error"] = brief(error)
        steps.append(step)
    return {"ok": all(s["ok"] for s in steps),
            "readback": [{"tab": s["tab"], "ok": s["ok"], "page_text": s.get("page_text", [])[:5]} for s in steps],
            "evidence": {"steps": steps, **evidence}}


def op_find_row(panel, ns):
    rows, row, note, tag = panel.locate_row(ns["tab"], ns.get("group"), ns["label"], "find")
    values = panel.line_values(rows, row)
    center = (row["x"] + row["w"] / 2, row["y"] + row["h"] / 2)
    point = panel.geometry()[0]
    return {"readback": {"tab": ns["tab"], "group": ns.get("group"), "label": row["text"],
                         "center": [round(center[0]), round(center[1])],
                         "window_local_center": [round(center[0] - point.x), round(center[1] - point.y)],
                         "box": {k: round(row[k]) for k in ("x", "y", "w", "h")},
                         "value_text": " ".join(v["text"] for v in values), "screenshot": tag + ".png"},
            "evidence": {"notes": note, "page_text": panel.page_text(rows)[:20]}}


def op_set_float(panel, ns):
    value = ns["value"]
    rows, row, note, tag = panel.locate_row(ns["tab"], ns.get("group"), ns["label"], "float")
    numbered = [t for t in panel.line_values(rows, row) if any(ch.isdigit() for ch in t["text"])]
    require(numbered, f"No numeric value token on the row: {row}")
    before_text = " ".join(t["text"] for t in numbered)
    token = numbered[0]
    gx, gy = token["x"] + 3, token["y"] + token["h"] / 2
    panel.click(gx, gy)
    time.sleep(0.8)

    def editor():
        best = None
        for element in panel.desktop.descendants(panel.window):
            if panel.desktop.text(element, "AXRole") != "AXTextField":
                continue
            try:
                at = panel.desktop.position(element)
            except RuntimeError:
                continue
            if abs(at.y - gy) > 30:
                continue
            distance = abs(at.y - gy) * 4 + abs(at.x - gx)
            if best is None or distance < best[0]:
                best = (distance, element, at)
        return best

    found = wait_for(editor, "Value-cell editor (AXTextField) did not materialize after the cell click")
    field = found[1]
    help_text = panel.desktop.text(field, "AXHelp") or ""
    panel.desktop.act(panel.pid, field, "AXFocused", ax.true_value)
    panel.desktop.act(panel.pid, field, "AXValue", panel.desktop.string(value))
    panel.desktop.act(panel.pid, field, "AXConfirm")
    time.sleep(0.6)
    ax_value = panel.desktop.text(field, "AXValue")
    rows = panel.read("float-after")
    again = panel.find_row(rows, ns.get("group"), ns["label"])
    painted = " ".join(t["text"] for t in panel.line_values(rows, again) if any(ch.isdigit() for ch in t["text"]))
    ok = ax_value == value and digits_of(painted) == digits_of(value) and panel.dirty
    return {"ok": ok,
            "readback": {"tab": ns["tab"], "label": again["text"], "before": before_text, "ax_value": ax_value,
                         "painted": painted, "title": panel.title, "expected": value},
            "evidence": {"parameter": help_text.split("parameter name")[-1].strip(" :\t\n"),
                         "click": [round(gx), round(gy)], "notes": note,
                         "screenshots": {"before": tag + ".png", "after": "float-after.png"}}}


def save_settings(panel):
    before = digest(PROJECT)
    bar = panel.desktop.attr(panel.root, "AXMenuBar")
    file_menu = exactly_one(e for e in panel.desktop.children(bar) if panel.desktop.text(e, "AXTitle") == "File")
    panel.desktop.act(panel.pid, file_menu, "AXPress")
    item = exactly_one(e for e in panel.desktop.descendants(file_menu)
                       if panel.desktop.text(e, "AXRole") == "AXMenuItem"
                       and panel.desktop.text(e, "AXTitle") == "Save Project")
    wait_for(lambda: panel.desktop.enabled(item), "Save Project did not become available")
    panel.desktop.act(panel.pid, item, "AXPress")
    wait_for(lambda: digest(PROJECT) != before, "Save did not rewrite the project", 30)
    time.sleep(0.5)
    return settings_of(PROJECT)


def checkbox_strip(panel, row, tag):
    """The whole pixel line of the row, cut from shot `tag` (review + diff material)."""
    point = panel.geometry()[0]
    mid = row["y"] + row["h"] / 2
    crop_png(OUT / f"{tag}.png", OUT / f"{tag}.cell.png", (point.x, mid - 11, PANEL_WIDTH - 8, 22))
    return OUT / f"{tag}.cell.png"


def op_set_checkbox(panel, ns):
    key = ns.get("key") or "detect_thin_wall"
    group, label = ns.get("group"), ns["label"]
    rows, row, note, tag = panel.locate_row(ns["tab"], group, label, "check")
    base = checkbox_strip(panel, row, tag)
    outcome, attempts, saved = {}, [], {}
    for turn in ("check", "uncheck"):
        if turn == "uncheck":  # re-address: the first save may re-layout the page
            row = panel.find_row(panel.read("check-before-uncheck"), group, label)
        # A bool row paints a faint checkbox square in the value column (x 606..620
        # at window x 360, run 230815 pixel scan), not beside its label.
        gy = row["y"] + row["h"] / 2
        spots = [("cell", panel.geometry()[0].x + VALUE_X), ("label", row["x"] + row["w"] / 2),
                 ("left", row["x"] - 11)]
        for how, gx in spots:
            name = f"check-{turn}-{how}"
            panel.click(gx, gy)
            time.sleep(0.9)
            panel.shot(name)
            changed = pixel_diff(checkbox_strip(panel, row, name), base)
            attempt = {"turn": turn, "how": how, "click": [round(gx), round(gy)], "title": panel.title,
                       "dirty": panel.dirty, "pixels_changed_vs_before": changed,
                       "screenshot": name + ".png"}
            attempts.append(attempt)
            # Either click leaves the project dirty: the first edit, then the edit
            # against the saved checked state. The pixels tell the two apart.
            if panel.dirty and (changed > 8 if turn == "check" else changed <= 8):
                outcome[turn] = attempt
                break
        require(turn in outcome, f"Checkbox did not {turn}: {json.dumps(attempts)[-900:]}")
        try:
            value = save_settings(panel).get(key)
            saved[turn] = {"key": key, "value": None if value is None else str(value), "title_after_save": panel.title}
        except Exception as error:
            saved[turn] = {"key": key, "error": brief(error, 300)}
    ok = (saved.get("check", {}).get("value") == "1" and saved.get("uncheck", {}).get("value") == "0")
    return {"ok": ok,
            "readback": {"tab": ns["tab"], "label": label, "checked": saved.get("check"), "unchecked": saved.get("uncheck"),
                         "title_when_checked": outcome["check"]["title"], "title_when_unchecked": outcome["uncheck"]["title"]},
            "evidence": {"notes": note, "attempts": attempts,
                         "screenshots": {"before": tag + ".png", "after_check": outcome["check"]["screenshot"],
                                         "after_uncheck": outcome["uncheck"]["screenshot"]}}}


def op_pick_combo(panel, ns):
    target = ns["target"]
    rows, row, note, tag = panel.locate_row(ns["tab"], ns.get("group"), ns["label"], "combo")
    tokens = panel.line_values(rows, row)
    require(tokens, f"No value token on the row: {row['text']}")
    token = tokens[0]
    painted_before = " ".join(t["text"] for t in tokens)
    cy = token["y"] + token["h"] / 2
    plans = [("cell", token["x"] + min(8, token["w"] / 2), cy, 1),
             ("cell-again", token["x"] + min(8, token["w"] / 2), cy, 1),
             ("cell-double", token["x"] + min(8, token["w"] / 2), cy, 2),
             ("right-edge", token["x"] + token["w"] + 16, cy, 1)]
    attempts, chosen = [], None
    for index, (how, gx, gy, clicks) in enumerate(plans):
        name = f"combo-{index}-{how}"
        for _ in range(clicks):
            panel.click(gx, gy, guard=False)
            time.sleep(0.12)
        time.sleep(0.9)
        popup_rows = panel.read(f"{name}-popup", full=True)
        popup = [r for r in popup_rows if norm(r["text"]) == norm(target)]
        attempt = {"how": how, "click": [round(gx), round(gy)],
                   "popup_entries_seen": sorted({r["text"] for r in popup_rows
                                                 if r["y"] > row["y"] - 5 and norm(r["text"]) in
                                                 ("by layer", "by object")})}
        attempts.append(attempt)
        if not popup:
            continue
        entry = popup[0]
        attempt["clicked_entry"] = [round(entry["x"] + entry["w"] / 2), round(entry["y"] + entry["h"] / 2)]
        panel.click(entry["x"] + entry["w"] / 2, entry["y"] + entry["h"] / 2, guard=False)
        time.sleep(0.9)
        after = panel.read(f"{name}-after")
        try:
            again = panel.find_row(after, ns.get("group"), ns["label"])
            painted = " ".join(t["text"] for t in panel.line_values(after, again))
        except RuntimeError as error:
            painted = f"<row lost: {brief(error, 160)}>"
        attempt.update({"painted_after": painted, "title": panel.title,
                        "screenshot_after": f"{name}-after.png", "screenshot_popup": f"{name}-popup.png"})
        if norm(painted) == norm(target):
            chosen = attempt
        break
    return {"ok": chosen is not None,
            "readback": {"tab": ns["tab"], "label": row["text"], "before": painted_before,
                         "after": chosen["painted_after"] if chosen else None, "expected": target},
            "evidence": {"notes": note, "attempts": attempts,
                         "screenshots": {"before": tag + ".png", "popup": f"combo-0-cell-popup.png",
                                         "after": chosen["screenshot_after"] if chosen else None}}}


OPS = {"switch_tab": op_switch_tab, "find_row": op_find_row, "set_float": op_set_float,
       "set_checkbox": op_set_checkbox, "pick_combo": op_pick_combo}


# --- Aqua-session worker ---

def dismiss_dialogs(panel):
    """Press 'Got It' on any exception dialog Orca raised over its home page
    (run pick_combo-231341 painted 'Error Code: 0002 1330 0000 0001 / Foreign
    Object Detected' and no project window), then raise the project window."""
    pressed = []
    for _ in range(3):
        found = []
        for window in panel.desktop.children(panel.root, "AXWindows"):
            if "Exception" not in panel.desktop.text(window, "AXTitle"):
                continue
            for element in panel.desktop.descendants(window):
                if (panel.desktop.text(element, "AXRole") == "AXButton"
                        and panel.desktop.text(element, "AXTitle") in ("Got It", "OK")):
                    found.append(element)
        if not found:
            break
        for element in found:
            item = {"button": panel.desktop.text(element, "AXTitle"),
                    "at": list(panel.desktop.position(element))[:2]}
            try:
                panel.desktop.act(panel.pid, element, "AXPress")
            except Exception as error:
                item["error"] = brief(error, 200)
            pressed.append(item)
        time.sleep(1.0)
    try:
        panel.desktop.act(panel.pid, panel.window, "AXRaise")
    except Exception as error:
        pressed.append({"raise_error": brief(error, 200)})
    return pressed


def run_worker(ns):
    OUT.mkdir(exist_ok=True)
    console_uid = os.stat("/dev/console").st_uid
    require(ax.trusted(), "Accessibility permission is missing for the Aqua worker")
    info = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
    result = {"op": ns["op"], "ok": True, "sut": {"version": info.get("CFBundleShortVersionString")},
              "console_uid": console_uid, "test_uid": os.getuid()}
    with ax.Desktop(console_uid) as desktop:
        desktop.check_session()
        seed()
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP), "--args", "--datadir",
                        str(PROFILE), str(PROJECT)], check=True, timeout=20)
        pid = exactly_one(wait_for(lambda: owned(PROFILE, PROJECT), "New Orca process missing", 15))
        root = desktop.own(ax.application(pid))
        require(ax.set_timeout(root, 2) == 0, "Cannot set AX timeout")
        window = wait_window(desktop, root, PROJECT.stem)
        panel = Panel(desktop, pid, root, window)
        entry = {"dialogs": None}

        def entry_band():
            if entry["dialogs"] is None:
                entry["dialogs"] = dismiss_dialogs(panel)
            rows = panel.read("entry")
            entry["rows"] = brief([(r["x"], r["y"], r["text"]) for r in rows], 1500)
            return panel.tab_band(rows)

        try:
            wait_for(entry_band, "tab band absent", 40)
        except TimeoutError:
            raise RuntimeError(f"Process tab band did not paint; entry: {brief(entry, 1600)}") from None
        result["entry"] = {"dialogs": entry["dialogs"]}
        try:
            result.update(OPS[ns["op"]](panel, ns))
        except Exception:
            result["evidence"] = {"error": traceback.format_exc()[-1800:]}
        finally:  # keep the addressing trail and frames when an operation fails
            result["shots"] = dict(panel.shots)
            result["notes"] = panel.last_notes
            result["ok"] = bool(result["ok"]) and "error" not in result["evidence"]
        point, size = panel.geometry()
        result["geometry"] = {"origin": [point.x, point.y], "size": [size.x, size.y]}
    return result


def worker_main(ns):
    result, error = {"op": ns["op"], "ok": False}, None
    started = time.time()
    try:
        result = run_worker(ns)
    except Exception:
        error = traceback.format_exc()
        result["evidence"] = {"error": error[-1800:]}
    try:
        close_owned(PROFILE, PROJECT)
    except Exception as failure:
        result["cleanup_error"] = brief(failure, 300)
    result["orca_left"] = sorted(owned(PROFILE, PROJECT))
    result["ok"] = bool(result["ok"]) and error is None and not result["orca_left"]
    result["finished_at"] = time.time()
    result["seconds"] = round(result["finished_at"] - started, 1)
    (WORK / "result.json").write_text(json.dumps(result, indent=1))
    log("result: " + json.dumps(result)[:900])
    return 0 if result["ok"] else 1


# --- supervisor: stage, LaunchAgent, harvest ---

def stage(work):
    sys.path.insert(0, str(ROOT))
    from harness.agent_protocol import LAYER_FIXTURE
    from harness.profile import MINIMAL_CONF, write_conf

    config = {**MINIMAL_CONF, "app": dict(MINIMAL_CONF["app"])}
    for key in ("orca_upgrade_url", "profile_upgrade_url", "flutter_upgrade_url"):
        config["app"][key] = "http://127.0.0.1:1/version.json"
    write_conf(work / "seed.conf", config)
    for name in ("param_ops.py", "accessibility.py", "ocr.swift"):
        shutil.copy2(WORK / name, work / name)
    shutil.copy2(ROOT / LAYER_FIXTURE, work / "probe.3mf")
    (work / "out").mkdir()
    # Vision OCR compiled once per ocr.swift revision (the interpreter costs seconds per call).
    binary = LOCAL_SHOTS / ("ocr-" + hashlib.sha256((WORK / "ocr.swift").read_bytes()).hexdigest()[:12])
    if not binary.is_file():
        built = work / "ocr"
        done = subprocess.run(["/usr/bin/xcrun", "swiftc", "-O", str(work / "ocr.swift"), "-o", str(built)],
                              capture_output=True, text=True, timeout=240)
        if done.returncode == 0:
            LOCAL_SHOTS.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built, binary)
    if binary.is_file():
        shutil.copy2(binary, work / "ocr")
        (work / "ocr").chmod(0o755)
    log(f"ocr binary: {binary.is_file()}")


def harvest(result, work, op):
    """Full frames stay local (artifacts/, not committed); panel crops go to the evidence dir."""
    stamp = time.strftime("%H%M%S")
    full_dir, crop_dir = LOCAL_SHOTS / f"{op}-{stamp}", EVIDENCE / "shots"
    shots = {}
    for name in sorted((work / "out").glob("*.png")):
        dest = crop_dir if name.name.endswith(".panel.png") else full_dir
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / f"{op}-{stamp}-{name.name}"
        shutil.copy2(name, target)
        shots[name.name] = str(target.relative_to(ROOT)) if dest is crop_dir else str(target)
    result["screenshots"] = shots
    return stamp


def record(result, stamp):
    path = EVIDENCE / "results.json"
    data = (json.loads(path.read_text()) if path.is_file() else
            {"task": "mac-param-ops-2026-11-23", "ops": {}, "attempts": []})
    data["ops"][result["op"]] = result
    data["attempts"].append({"op": result["op"], "stamp": stamp, "ok": result["ok"]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def supervise(ns):
    require(TRUSTED_PYTHON.is_file(), "Trusted Python.app not found")
    work = Path(tempfile.mkdtemp(prefix="orca-bb-param-ops.", dir=tempfile.gettempdir()))
    work.chmod(0o700)
    stage(work)
    label = "local.orcabb.param-ops." + uuid.uuid4().hex[:12]
    logfile = work / "worker.log"
    job = {"Label": label, "LimitLoadToSessionType": "Aqua", "RunAtLoad": True,
           "ProgramArguments": [str(TRUSTED_PYTHON), "-B", "-u", str(work / "param_ops.py"),
                                "--worker", json.dumps(vars(ns))],
           "WorkingDirectory": str(work), "StandardOutPath": str(logfile), "StandardErrorPath": str(logfile)}
    plist = work / "job.plist"
    plist.write_bytes(plistlib.dumps(job))
    result_file = work / "result.json"
    domain = f"gui/{os.getuid()}"
    result = {"op": ns.op, "ok": False}
    registered = False
    try:
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True, timeout=15)
        registered = True
        wait_for(result_file.is_file, "Mac worker timed out", ns.fuse)
        result = json.loads(result_file.read_text())
    except Exception:
        result["supervisor_error"] = traceback.format_exc()[-1200:]
    finally:
        if registered:
            subprocess.run(["launchctl", "bootout", domain + "/" + label], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
        try:
            close_owned(work / "datadir", work / "probe.3mf")
        except Exception as failure:
            result["cleanup_error"] = brief(failure, 300)
    result["ok"] = bool(result.get("ok")) and "supervisor_error" not in result and "cleanup_error" not in result
    stamp = harvest(result, work, ns.op)
    record(result, stamp)
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    return 0 if result["ok"] else 1


def parser():
    root = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="op", required=True)
    switch = sub.add_parser("switch_tab")
    switch.add_argument("--tabs", default=",".join(TABS))
    cases = {"find_row": ("Strength", "Walls", "Wall loops", ()),
             "set_float": ("Quality", "Layer height", "Layer height", (("--value", "0.2"),)),
             "set_checkbox": ("Strength", "Walls", "Detect thin walls", (("--key", "detect_thin_wall"),)),
             "pick_combo": ("Others", "Special mode", "Print sequence", (("--target", "By object"),))}
    for name, (tab, group, label, extra) in cases.items():
        case = sub.add_parser(name)
        case.add_argument("--tab", default=tab)
        case.add_argument("--group", default=group)
        case.add_argument("--label", default=label)
        for flag, default in extra:
            case.add_argument(flag, default=default)
    for case in sub.choices.values():
        case.add_argument("--fuse", type=int, default=240)
    root.add_argument("--worker", metavar="JSON", help=argparse.SUPPRESS)
    return root


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--worker"]:
        return worker_main(json.loads(argv[1]))
    return supervise(parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
