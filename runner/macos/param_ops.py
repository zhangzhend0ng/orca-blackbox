"""Parameter-page operations on macOS Orca 2.4.1 (Feishu param-case port).

Subcommands, each printing ONE JSON line (ok, readback, screenshot paths):
  switch_tab    [--tabs a,b,...]        click each page tab once and read the page back
  find_row      --tab T [--group G] --label L
                                       OCR a row label inside a group, return screen coords
  set_float     --tab T [--group G] --label L --value V
  set_checkbox  --tab T [--group G] --label L
  pick_combo    --tab T [--group G] --label L --target X
  scroll_page   --tab T --group G        how the page reaches a group below the fold (step 2)
  scenario      --name N                 one edit + Save Project + 3mf key check (step 2)

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
VIEW_TOP = 712     # options viewport starts here (window-relative px): tab band + gap
VIEW_RIGHT = 406   # viewport right edge (window-relative); the 15 px strip beyond is not page
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


def title_key(text):
    """A page title without the fold glyph OCR reads in front of it."""
    words = norm(text).split(" ")
    while words and len(words[0]) <= 2:
        words = words[1:]
    return " ".join(words)


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


def row_profiles(path):
    """Left-half and right-half mean luminance of each pixel row of a viewport crop."""
    width, height, channels, lines = png_pixels(path)
    half = width // 2
    profiles = []
    for line in lines:
        left = sum(line[i] for i in range(0, half * channels, channels)) // half
        right = sum(line[i] for i in range(half * channels, width * channels, channels)) // (width - half)
        profiles.append((left, right))
    return profiles


def pixel_shift(first, second):
    """Row offset d (px) for which after[y] matches before[y + d] best: d > 0 means the page
    scrolled down. Row profiles pick the candidates, the pixels decide. `ratio` is the share
    of the overlap pixels that still differ at d, `ratio_still` the same at d = 0."""
    before, after = row_profiles(first), row_profiles(second)
    require(len(before) == len(after), "Pixel crops differ in shape")
    height = len(before)

    def mismatch(d):
        total, count = 0, 0
        for y in range(max(0, -d), min(height, height - d)):
            total += abs(before[y + d][0] - after[y][0]) + abs(before[y + d][1] - after[y][1])
            count += 2
        return total / count if count >= 24 else None  # at least 12 overlapping rows
    ranked = [(mismatch(d), d) for d in range(-height + 12, height - 11) if abs(d) >= 3]
    candidates = [0] + [d for _, d in sorted(pair for pair in ranked if pair[0] is not None)[:4]]
    width, _, channels, a = png_pixels(first)
    _, _, _, b = png_pixels(second)
    scores = []
    for d in candidates:
        overlap, differing = height - abs(d), 0
        for y in range(max(0, -d), min(height, height - d)):
            ra, rb = a[y + d], b[y]
            for i in range(0, width * channels, channels):
                if max(abs(ra[i] - rb[i]), abs(ra[i + 1] - rb[i + 1]), abs(ra[i + 2] - rb[i + 2])) > 40:
                    differing += 1
        scores.append((differing / (overlap * width), d))
    still, best = scores[0][0], min(scores)
    return {"d": best[1], "ratio": round(best[0], 3), "ratio_still": round(still, 3),
            "pure_shift": best[0] < 0.3 and best[0] < 0.35 * still}


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
        self.trial, self.scroll_up_button = None, None  # the scroll probe's working state
        self.scroll_down_buttons = None  # page scrollbar buttons that page down, widest step first

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

    def _mouse(self, kind, gx, gy, wid):
        """Post one pointer event of NSEvent type `kind` at the global point."""
        point, size = self.geometry()
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

    def click(self, gx, gy, guard=True):
        """Targeted pointer click at a global point (screen px)."""
        point, size = self.geometry()
        if guard:
            modal = self.modal_open()
            require(modal is None, f"A modal dialog is covering the project: {modal}")
        wid = self.window_id(point, size)
        require(ax.post_allowed(), "Targeted input requires event posting permission")
        for attempt in range(3):  # a busy app can miss an AX read (run 014224: "Missing field position")
            posted = False
            try:
                for kind in (1, 2):
                    self._mouse(kind, gx, gy, wid)
                    posted = True
                break
            except RuntimeError as error:
                if posted or attempt == 2 or "Missing field" not in str(error):
                    raise  # never repeat a half-sent click
                time.sleep(0.6)

    def drag(self, gx, gy, tx, ty, steps=8):
        """Press at (gx, gy), drag in a straight line to (tx, ty), release."""
        point, size = self.geometry()
        modal = self.modal_open()
        require(modal is None, f"A modal dialog is covering the project: {modal}")
        wid = self.window_id(point, size)
        require(ax.post_allowed(), "Targeted input requires event posting permission")
        self._mouse(1, gx, gy, wid)
        for step in range(1, steps + 1):
            self._mouse(6, gx + (tx - gx) * step / steps, gy + (ty - gy) * step / steps, wid)
        self._mouse(2, tx, ty, wid)

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
        """Open `tab` and find the row; page the viewport down to a group below the fold; fall
        back to Advanced mode and a taller window. Returns (rows, row, notes, tag of the page shot)."""
        note = self.last_notes = []

        def attempt(tag):
            rows = self.read(f"{prefix}-{tag}-locate")
            note.append({"tab_click": self.click_tab(tab, rows)})
            rows = self.read(f"{prefix}-{tag}")
            try:
                return rows, self.find_row(rows, group, label), f"{prefix}-{tag}"
            except RuntimeError as error:
                if not group:
                    raise
                why = brief(error)
            note.append({"scrolled": self.scroll_to(group, label, f"{prefix}-{tag}-scroll", why)})
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
        try:
            rows, row, tag = attempt("page-tall")
            return rows, row, note, tag
        except RuntimeError as error:
            note.append({"tall_window": brief(error)})
        # The page does not scroll from injected input (A2): fold the group
        # headers that are on screen so the groups below them move up, stopping
        # as soon as the wanted group title is on screen.
        point = self.geometry()[0]
        done, folded = [], []
        for index in range(4):
            titles = [t for t in self.read(f"{prefix}-fold-{index}") if t["x"] - point.x < 26]
            if any(norm(group) in norm(t["text"]) for t in titles):
                break
            todo = [t for t in titles if t["text"] not in done]
            if not todo:
                break
            title = todo[0]
            done.append(title["text"])
            spot = (point.x + 10, title["y"] + title["h"] / 2)
            self.click(*spot)
            time.sleep(1.0)
            after = [t["text"] for t in self.read(f"{prefix}-fold-{index}-after") if t["x"] - point.x < 26]
            folded.append({"title": title["text"], "click": [round(spot[0]), round(spot[1])], "titles_after": after})
        note.append({"folded": folded})
        rows, row, tag = attempt("page-folded")
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

    # -- page viewport: where it is, how far it moved, folding a group --

    def viewport(self):
        """Screen rect (x, y, w, h) of the options viewport."""
        point, size = self.geometry()
        return (point.x + 2, point.y + VIEW_TOP, VIEW_RIGHT - 3, size.y - VIEW_TOP - 3)

    def page_titles(self, rows):
        """Group-title tokens of the Process page: fold icon at the column's left edge
        (x within 12 px of the window), below the tab band - never the sidebar above it."""
        point = self.geometry()[0]
        return sorted((r for r in self.page_rows(rows) if -2 <= r["x"] - point.x <= 12 and norm(r["text"])),
                      key=lambda r: r["y"])

    def title_of(self, rows, group):
        wanted = norm(group)
        return next((t for t in self.page_titles(rows) if wanted in norm(t["text"])), None)

    def page_lines(self, rows):
        """[text, y, x] of the page tokens inside the viewport, top to bottom."""
        try:
            page = self.page_rows(rows)
        except RuntimeError:  # no tab band in this capture
            return []
        x, y, w, h = self.viewport()
        return [[r["text"], round(r["y"]), round(r["x"])] for r in sorted(page, key=lambda r: r["y"])
                if y - 6 <= r["y"] <= y + h][:40]

    def ink_box(self, png, rect, dark=150):
        """[x0, y0, x1, y1] of the pixels darker than `dark` inside a screen rect, or None."""
        temp = OUT / f".ink-{time.time_ns()}.png"
        crop_png(png, temp, rect)
        width, height, channels, lines = png_pixels(temp)
        temp.unlink()
        x0, y0, x1, y1 = width, height, -1, -1
        for row in range(height):
            line = lines[row]
            for column in range(width):
                if line[column * channels] < dark:
                    x0, y0, x1, y1 = min(x0, column), min(y0, row), max(x1, column), max(y1, row)
        if x1 < 0:
            return None
        return [round(rect[0]) + x0, round(rect[1]) + y0, round(rect[0]) + x1, round(rect[1]) + y1]

    def ink_runs(self, png, rect, dark=225):
        """Screen row ranges [y0, y1] of a column strip holding a pixel darker than `dark`."""
        temp = OUT / f".ink-{time.time_ns()}.png"
        crop_png(png, temp, rect)
        width, height, channels, lines = png_pixels(temp)
        temp.unlink()
        marked = [any(line[column * channels] < dark for column in range(width)) for line in lines]
        runs, start = [], None
        for row, hit in enumerate(marked + [False]):
            if hit and start is None:
                start = row
            elif not hit and start is not None:
                runs.append([round(rect[1]) + start, round(rect[1]) + row - 1])
                start = None
        return runs

    def view_crop(self, png, tag):
        """The viewport part of shot `png`, saved as `tag`.view.png (metrics + review)."""
        target = OUT / f"{tag}.view.png"
        crop_png(png, target, self.viewport())
        return target

    def measure(self, tag, before_rows, before_view):
        """Capture `tag` and say how far the viewport content moved against the `before` shot."""
        after = self.read(tag)
        view = self.view_crop(OUT / f"{tag}.png", tag)
        x, y, w, h = self.viewport()

        def landmarks(rows):
            seen, count = {}, {}
            try:
                page = self.page_rows(rows)
            except RuntimeError:  # no tab band in this capture
                return {}
            for r in page:
                if y - 6 <= r["y"] <= y + h:
                    key = norm(r["text"])
                    count[key] = count.get(key, 0) + 1
                    seen[key] = r
            return {key: r for key, r in seen.items() if count[key] == 1 and key}

        old, new = landmarks(before_rows), landmarks(after)
        shifts = sorted(old[key]["y"] - new[key]["y"] for key in new if key in old)
        note = {"lines": self.page_lines(after), "ocr_matches": len(shifts),
                "scroll_px": round(shifts[len(shifts) // 2], 1) if shifts else None}  # + = page down
        before_tag = Path(before_view).name[:-len(".view.png")]
        try:
            note["pixels_changed"] = pixel_diff(before_view, view)
            note["column_changed"] = pixel_diff(OUT / f"{before_tag}.panel.png", OUT / f"{tag}.panel.png")
            note["pixel_shift"] = pixel_shift(before_view, view)
        except RuntimeError as error:  # the viewport itself was resized between the shots
            note["pixel_metrics"] = brief(error, 120)
        return after, view, note

    def click_title(self, rows, tag, title, how):
        """Click a page group title: its fold glyph (`icon`), the right end of its label (`text`),
        the label's centre, the row well right of the label, a 4 px drag or a double click on the
        glyph, or the glyph after a mouse-moved event onto it."""
        icon = self.ink_box(OUT / f"{tag}.png", (title["x"] - 5, title["y"] - 3, 22, title["h"] + 6))
        cy = title["y"] + title["h"] / 2
        glyph = ((icon[0] + icon[2]) / 2, (icon[1] + icon[3]) / 2) if icon else (title["x"] + 4, cy)
        spots = {"icon": glyph, "move-icon": glyph, "drag-icon": glyph, "double-icon": glyph,
                 "text": (title["x"] + title["w"] - 6, cy), "label": (title["x"] + title["w"] / 2, cy),
                 "row-right": (self.geometry()[0].x + 300, cy)}
        spot = spots[how]
        if how == "move-icon":
            post_move(self.pid, *spot)
            time.sleep(0.6)
        if how == "drag-icon":
            self.drag(spot[0], spot[1], spot[0] + 4, spot[1] + 1)
        elif how == "double-icon":
            self.click(*spot)
            self.click(*spot)
        else:
            self.click(*spot)
        time.sleep(1.0)
        return {"title": title["text"], "how": how, "click": [round(spot[0]), round(spot[1])],
                "icon_box": icon, "title_box": [round(title[k]) for k in ("x", "y", "w", "h")]}

    def scrollbar(self):
        """The options page's own scrollbar (the AXScrollBar inside the settings column):
        {element, box, value, knob, buttons} - buttons are the pressable children in AX order."""
        point = self.geometry()[0]
        for bar in self.scrollbars():
            x, y = bar["box"][:2]
            if point.x <= x <= point.x + PANEL_WIDTH and y >= point.y + VIEW_TOP - 30:
                knob = next((kid["box"] for kid in bar["kids"] if kid["role"] == "AXValueIndicator"), None)
                return {"element": bar["element"], "box": [round(v, 1) for v in bar["box"]],
                        "value": cf_scalar(self.desktop, self.desktop.attr(bar["element"], "AXValue")),
                        "knob": [round(v, 1) for v in knob] if knob else None,
                        "buttons": [kid for kid in bar["kids"]
                                    if "AXPress" in self.desktop.actions(kid["element"])]}
        return None

    def knob_at(self):
        """Knob top below the scrollbar top (px): the track inset while the page is at its top."""
        bar = self.scrollbar()
        require(bar and bar["knob"], "The options page exposes no scrollbar knob")
        return bar["knob"][1] - bar["box"][1]

    def press_scroll(self, index, times=1, pause=0.45):
        """AXPress scrollbar button `index` (AX order of the pressable children) `times` times."""
        bar = self.scrollbar()
        require(bar and len(bar["buttons"]) > index, f"The page scrollbar has no pressable button {index}")
        for _ in range(times):
            self.desktop.act(self.pid, bar["buttons"][index]["element"], "AXPress")
            time.sleep(pause)

    def scroll_top(self, button, limit=30):
        """AXPress scrollbar button `button` until the knob stops moving; returns the trail."""
        seen = [self.knob_at()]
        for _ in range(limit):
            self.press_scroll(button, 1)
            seen.append(self.knob_at())
            if seen[-1] == seen[-2]:
                break
        return {"button": button, "presses": len(seen) - 1, "knob_at": seen}

    def find_scroll_buttons(self):
        """Which of the page scrollbar's pressable buttons page down / up (their AX order is
        not fixed): press each once and read the knob, AX only. Two passes, since an up button
        moves nothing while the page is at its top."""
        if self.scroll_down_buttons and self.scroll_up_button is not None:
            return {"down": self.scroll_down_buttons, "up": self.scroll_up_button}
        downs, ups, marks = {}, set(), {}
        for _ in range(2):
            for index in range(len(self.scrollbar()["buttons"])):
                before = self.knob_at()
                self.press_scroll(index, 1)
                moved = self.knob_at() - before
                marks.setdefault(index, []).append(moved)
                if moved > 0:
                    downs[index] = max(moved, downs.get(index, 0))
                elif moved < 0:
                    ups.add(index)
        require(downs and ups, f"The page scrollbar shows no up/down button: knob marks {marks}")
        self.scroll_down_buttons = sorted(downs, key=downs.get, reverse=True)  # page step, then line step
        self.scroll_up_button = min(ups)
        return {"down": self.scroll_down_buttons, "up": self.scroll_up_button, "knob_dy": marks}

    def scroll_to(self, group, label, tag, why):
        """Page the options viewport down one scrollbar step at a time until the group title
        and the row are both inside it (step 2: AXPress on the page scrollbar reached the
        Others page's last group); stops where no down button moves the page any more."""
        trail = {"not_found": str(why)[:200], "buttons": self.find_scroll_buttons()}
        trail["to_top"] = self.scroll_top(self.scroll_up_button)
        trail["steps"] = []
        x, y, w, h = self.viewport()
        moved = 1
        for index in range(24):
            rows = self.read(f"{tag}-{index}")  # look first: one page step empties this small viewport
            title, row, missing, titles = None, None, None, []
            try:
                # The group title as find_row reads it (x < TITLE_X): the stricter fold-icon
                # test of title_of missed the Strength page's 'Walls' and paged it to the end.
                left = self.geometry()[0].x
                heads = [r for r in self.page_rows(rows) if r["x"] - left < TITLE_X and norm(r["text"])]
                wanted = norm(group)
                title = next((t for t in heads if wanted in norm(t["text"]) or norm(t["text"]) in wanted), None)
                titles = [t["text"] for t in heads]
                row = self.find_row(rows, group, label)
            except RuntimeError as error:  # no tab band, no group title, or no such row
                missing = error
            step = {"step": index, "knob_dy": moved, "titles": titles}
            trail["steps"].append(step)
            if row and row["y"] + row["h"] <= y + h - 2:
                step["row_y"] = round(row["y"], 1)
                return trail
            # The group is on screen with room for a row under its title: the row is not on
            # this page (an Advanced-only one in standard mode), so scrolling cannot find it.
            if title and (row or title["y"] + title["h"] <= y + h - 40) and (row is None or not moved):
                raise missing if row is None else RuntimeError(
                    f"Row {label!r} touches the viewport's lower edge in group {group!r}")
            if not moved:
                step["end_of_page"] = True
                break
            knob = self.knob_at()
            for button in self.scroll_down_buttons:
                before = self.knob_at()
                self.press_scroll(button, 1)
                if self.knob_at() != before:
                    break
            moved = self.knob_at() - knob
        raise RuntimeError(f"{group!r} / {label!r} not on the page after scrolling to its end: "
                           f"{json.dumps(trail)[-600:]}")

    def ax_named(self, wanted):
        """AX elements of this app - any of its windows, a popup list is its own - whose title,
        value or description reads `wanted`."""
        found = []
        for window in self.desktop.children(self.root, "AXWindows"):
            for element in self.desktop.descendants(window):
                if any(norm(self.desktop.text(element, key)) == norm(wanted)
                       for key in ("AXTitle", "AXValue", "AXDescription")):
                    found.append(element)
        return found

    def windows(self):
        """[subrole, title, box] of every window the app has on screen."""
        return [[self.desktop.text(window, "AXSubrole"), self.desktop.text(window, "AXTitle")[:40],
                 [round(v) for v in box] if (box := self.desktop.box(window)) else None]
                for window in self.desktop.children(self.root, "AXWindows")]

    def controls_in(self, rect):
        """AX elements positioned inside a screen rect: role, box, texts, actions."""
        x, y, w, h = rect
        found = []
        for element in self.desktop.descendants(self.window):
            box = self.desktop.box(element)
            if not box or not (x <= box[0] <= x + w and y <= box[1] <= y + h):
                continue
            found.append({"role": self.desktop.text(element, "AXRole"), "box": [round(v) for v in box],
                          "title": self.desktop.text(element, "AXTitle")[:40],
                          "help": (self.desktop.text(element, "AXHelp") or "")[:70],
                          "actions": self.desktop.actions(element)})
        return found

    def scrollbars(self):
        """AXScrollBar elements of the window: {element, box, kids: [{element, role, box}]}."""
        found = []
        for element in self.desktop.descendants(self.window):
            if self.desktop.text(element, "AXRole") != "AXScrollBar":
                continue
            box = self.desktop.box(element)
            if box is None:
                continue
            kids = [{"element": child, "role": self.desktop.text(child, "AXRole"), "box": self.desktop.box(child)}
                    for child in self.desktop.children(element)]
            found.append({"element": element, "box": box, "kids": kids})
        return found

    def focused(self):
        """The app's focused AX control, if any."""
        element = self.desktop.attr(self.root, "AXFocusedUIElement")
        if not element:
            return None
        return {"role": self.desktop.text(element, "AXRole"), "box": self.desktop.box(element),
                "help": (self.desktop.text(element, "AXHelp") or "")[:70]}

    def blank_spot(self, rows):
        """A point on a page row between the end of its label and its value cell."""
        x, y, w, h = self.viewport()
        for row in self.page_rows(rows):
            if row["x"] - self.geometry()[0].x < TITLE_X + 20 or not y + 10 < row["y"] < y + h - 20:
                continue
            values = self.line_values(rows, row)
            if values and values[0]["x"] - (row["x"] + row["w"]) > 60:
                return row["x"] + row["w"] + (values[0]["x"] - row["x"] - row["w"]) / 2, row["y"] + row["h"] / 2
        return x + w / 2, y + h / 2

    def set_frame(self, x, y, width, height):
        position = create_value(1, ct.byref(ax.Point(x, y)))
        error = ax.set_attr(self.window, self.desktop.string("AXPosition"), position)
        ax.release(position)
        require(error == 0, f"AXPosition set failed with AX error {error}")
        time.sleep(0.8)
        return self.resize(width, height)

    def maximize(self):
        """Move the window to the top of the usable screen area and give it the full height."""
        areas = ax.screen_areas()
        require(areas, "No screen in the worker session")
        point, size = self.geometry()
        return areas, self.set_frame(point.x, areas["visible"][1], size.x, areas["visible"][3])


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
    """Open the row's choice list and pick `target`; proven only when the row then paints
    exactly the target. The entry is taken by a pointer click on its text, failing that by its
    AX element, failing that by Down + Return keys while the list is open."""
    target = ns["target"]
    rows, row, note, tag = panel.locate_row(ns["tab"], ns.get("group"), ns["label"], "combo")
    tokens = panel.line_values(rows, row)
    require(tokens, f"No value token on the row: {row['text']}")
    token = tokens[0]
    painted_before = " ".join(t["text"] for t in tokens)
    cy = token["y"] + token["h"] / 2
    left = token["x"] + min(8, token["w"] / 2)
    plans = [("cell", left, cy, 1), ("cell-again", left, cy, 1), ("cell-double", left, cy, 2),
             ("right-edge", token["x"] + token["w"] + 16, cy, 1),
             ("cell-right", panel.geometry()[0].x + VIEW_RIGHT - 12, cy, 1)]
    off_row = lambda r: abs(r["y"] - row["y"]) > 12  # the row's own painted value is no list entry

    def painted_now(shot):
        """What the row paints in capture `shot` (a note when the row itself is lost)."""
        try:
            current = panel.read(shot)
            return " ".join(t["text"] for t in panel.line_values(
                current, panel.find_row(current, ns.get("group"), ns["label"])))
        except RuntimeError as error:
            return f"<row lost: {brief(error, 160)}>"

    attempts, chosen, plan = [], None, None
    for index, (how, gx, gy, clicks) in enumerate(plans):
        name = f"combo-{index}-{how}"
        for _ in range(clicks):
            panel.click(gx, gy, guard=False)
            time.sleep(0.12)
        time.sleep(0.9)
        popup_rows = panel.read(f"{name}-popup", full=True)
        entry = next((r for r in popup_rows if off_row(r) and norm(target) in norm(r["text"])), None)
        plan = {"how": how, "click": [round(gx), round(gy)], "focused": panel.focused(),
                "popup_entries_seen": sorted({r["text"] for r in popup_rows
                                              if off_row(r) and norm(r["text"]) in ("by layer", "by object")})}
        attempts.append(plan)
        if entry is None:  # no list on screen: a closed read-only combo may still take an arrow key
            takes = [("closed-down-key", lambda: post_keys(panel.pid, 125, 1))]
        else:
            spot = (entry["x"] + entry["w"] / 2, entry["y"] + entry["h"] / 2)
            plan["entry_box"] = {k: round(entry[k]) for k in ("x", "y", "w", "h")}
            plan["entry_click"] = [round(spot[0]), round(spot[1])]
            plan["windows"] = panel.windows()
            takes = [("pointer", lambda: panel.click(*spot, guard=False))]
            for order, element in enumerate(e for e in panel.ax_named(target)
                                             if (box := panel.desktop.box(e)) and off_row({"y": box[1]})):
                if "AXPress" in panel.desktop.actions(element):
                    takes.append((f"ax-press-{order}", lambda element=element:
                                  panel.desktop.act(panel.pid, element, "AXPress")))
            takes.append(("open-down-return-keys", lambda: [post_keys(panel.pid, code, 1)
                                                            for code in (125, 36)]))
        for take, act in takes:
            try:
                act()
            except Exception as error:
                plan[f"{take}_error"] = brief(error, 200)
            time.sleep(0.9)
            shot = f"{name}-{take}-after"
            attempt = {"how": take, "painted_after": painted_now(shot), "title": panel.title,
                       "screenshot_after": shot + ".png"}
            plan.setdefault("takes", []).append(attempt)
            # The judged value: the row's painted words, less the dropdown glyph OCR glues in
            # front of them ('~ By object', 'v By object').
            if title_key(attempt["painted_after"]) == norm(target):
                chosen = attempt
                break
        if chosen:
            break
    return {"ok": chosen is not None,
            "readback": {"tab": ns["tab"], "label": row["text"], "before": painted_before,
                         "after": chosen["painted_after"] if chosen else None, "expected": target,
                         "click": plan["click"], "entry_click": plan.get("entry_click"),
                         "taken_by": chosen["how"] if chosen else None},
            "evidence": {"notes": note, "attempts": attempts,
                         "screenshots": {"before": tag + ".png", "popup": f"combo-0-cell-popup.png",
                                         "after": chosen["screenshot_after"] if chosen else None}}}


# --- step 4: one edit, Save Project, the key read from the saved 3mf ---

SCENARIOS = {  # name: (operation, project_settings.config key, value expected there, its arguments)
    "layer-height": ("set_float", "layer_height", "0.2",
                     {"tab": "Quality", "group": "Layer height", "label": "Layer height", "value": "0.2"}),
    "thin-wall": ("set_checkbox", "detect_thin_wall", "1",
                  {"tab": "Strength", "group": "Walls", "label": "Detect thin walls", "key": "detect_thin_wall"}),
    "print-sequence": ("pick_combo", "print_sequence", "by object",
                       {"tab": "Others", "group": "Special mode", "label": "Print sequence",
                        "target": "By object"})}


def tick_checkbox(panel, ns):
    """The first turn of set_checkbox on its own: tick the row's cell, Save Project, and return
    (the saved key, what the click did)."""
    rows, row, note, tag = panel.locate_row(ns["tab"], ns["group"], ns["label"], "scen")
    base = checkbox_strip(panel, row, tag)
    gx, gy = panel.geometry()[0].x + VALUE_X, row["y"] + row["h"] / 2
    panel.click(gx, gy)
    time.sleep(0.9)
    panel.shot("scen-checked")
    changed = pixel_diff(checkbox_strip(panel, row, "scen-checked"), base)
    require(panel.dirty and changed > 8,
            f"The cell click did not tick the box: dirty={panel.dirty}, pixels changed={changed}")
    return save_settings(panel).get(ns["key"]), {"click": [round(gx), round(gy)],
                                                 "pixels_changed_vs_before": changed,
                                                 "screenshot": "scen-checked.png"}


def op_scenario(panel, ns):
    """One edit through its operation, Save Project, then the key read from the saved 3mf's
    Metadata/project_settings.config; proven only when the saved value is the expected one."""
    edit, key, want, case = SCENARIOS[ns["name"]]
    case = {**ns, **case}
    if edit == "set_checkbox":
        value, taken = tick_checkbox(panel, case)
        done = {"ok": value is not None, "readback": taken, "evidence": {}}
    else:
        done = OPS[edit](panel, case)
        require(done["ok"], f"{edit} did not take: {json.dumps(done['readback'])[:300]}")
        value = save_settings(panel).get(key)
    saved = {"key": key, "value": None if value is None else str(value), "expected": want}
    return {"ok": done["ok"] and saved["value"] == want,
            "readback": {"scenario": ns["name"], "edit": done["readback"], "saved": saved,
                         "title_after_save": panel.title},
            "evidence": {"notes": panel.last_notes, "edit": done["evidence"]}}


# --- step 2: how the page reaches a group below the fold ---

def post_move(pid, x, y):
    """Mouse-moved event from the HID source, posted to the app with its location inside the page."""
    source = ax.create_source(1)  # kCGEventSourceStateHIDSystemState
    try:
        event = ax.create_move(source, 5, ax.Point(x, y), 0)  # kCGEventMouseMoved, left button
        require(event, "Mouse-moved event is unavailable")
        ax.post_to_pid(pid, event)
        ax.release(event)
    finally:
        ax.release(source)


def post_wheel(pid, x, y, notches, unit, step, interval=0.45):
    """One scroll-wheel notch per event, each located at (x, y), `interval` seconds apart."""
    source = ax.create_source(1)
    try:
        for _ in range(notches):
            event = ax.create_scroll(source, unit, 1, step)
            require(event, "Scroll event is unavailable")
            ax.set_location(event, ax.Point(x, y))
            ax.post_to_pid(pid, event)
            ax.release(event)
            time.sleep(interval)
    finally:
        ax.release(source)


def post_keys(pid, code, presses, interval=0.45):
    """`presses` key presses (down + up) posted to the app."""
    for _ in range(presses):
        for pressed in (True, False):
            event = ax.create_key(None, code, pressed)
            require(event, "Keyboard event is unavailable")
            ax.post_to_pid(pid, event)
            ax.release(event)
            time.sleep(0.08)
        time.sleep(interval)


def cursor():
    point = ax.cursor_position()
    return [round(point.x, 1), round(point.y, 1)]


class Trial:
    """One scroll method: labelled actions, each measured against the shot taken before it."""

    def __init__(self, panel, out, prefix, group, label):
        self.panel, self.out, self.prefix, self.group, self.label = panel, out, prefix, group, label
        panel.trial = self
        self.tag = f"{prefix}-before"
        self.rows = panel.read(self.tag)
        self.view = panel.view_crop(OUT / f"{self.tag}.png", self.tag)
        self.knob = panel.knob_at() if panel.scrollbar() else None
        out["lines_before"] = panel.page_lines(self.rows)

    def run(self, label, action, keep=False):
        step = {"how": label, "lines_before": self.panel.page_lines(self.rows), "shot": None}
        if keep:
            self.out.setdefault("keep", set()).update((self.tag, f"{self.prefix}-{len(self.out['attempts'])}"))
        try:
            step.update(action() or {})
        except Exception as error:
            step["error"] = brief(error, 300)
        tag = f"{self.prefix}-{len(self.out['attempts'])}"
        self.rows, self.view, moved = self.panel.measure(tag, self.rows, self.view)
        step.update(moved)
        knob = self.panel.knob_at() if self.panel.scrollbar() else None
        if knob is not None and self.knob is not None:
            step["knob_dy"] = round(knob - self.knob, 1)
        self.knob, self.tag = knob, tag
        lines = self.panel.page_lines(self.rows)
        step["shot"] = f"{tag}.panel.png"
        step["reached"] = self.panel.title_of(self.rows, self.group) is not None
        step["row_seen"] = any(norm(self.label) in norm(line[0]) for line in lines)
        if step["row_seen"]:  # what the AX tree offers at the row once it is on screen
            x, y, w, h = self.panel.viewport()
            step["controls"] = self.panel.controls_in((x, y, w, h))
        self.out["attempts"].append(step)
        return step

    def seen(self, step):
        """Signed page scroll (px, down positive) of a finished step."""
        return step["scroll_px"] if step.get("scroll_px") is not None else step.get("knob_dy") or 0


FOLD_WAYS = ("icon", "text", "move-icon", "label", "row-right", "drag-icon", "double-icon")


def step_fold(panel, ns):
    """(a) click the title row of the page groups above the target group, then click again."""
    out = {"method": "a-fold-icon", "attempts": [], "folds": []}
    trial = Trial(panel, out, "a", ns["group"], ns["label"])
    done = []
    for index in range(4):
        if panel.title_of(trial.rows, ns["group"]):
            break
        todo = [t for t in panel.page_titles(trial.rows) if title_key(t["text"]) not in done]
        if not todo:
            out["blocker"] = f"No page group title left to fold; titles seen: {[t['text'] for t in panel.page_titles(trial.rows)]}"
            break
        title = todo[0]
        for how in FOLD_WAYS:
            found = {}

            def click(title=title, how=how, found=found):
                found.update(panel.click_title(trial.rows, trial.tag, title, how))
            step = trial.run(f"fold-0-{how}", click, keep=how in ("icon", "text"))
            step.update(found)
            if step.get("pixels_changed", 0) > 150 and step.get("lines") != step["lines_before"]:
                out["folds"].append(step)
                done.append(title_key(title["text"]))
                break
        else:
            out["blocker"] = (f"Clicking the title row of {title['text']!r} changed nothing "
                              f"(ways tried: {', '.join(FOLD_WAYS)})")
            break
    for index, step in enumerate(reversed(out["folds"])):
        found = {}

        def click(step=step, found=found):
            title = panel.title_of(trial.rows, title_key(step["title"]))
            require(title, f"Title {step['title']!r} is not on screen any more")
            found.update(panel.click_title(trial.rows, trial.tag, title, step["how"]))
        trial.run(f"unfold-{index}-{step['how']}", click)
    out["lines_restored"] = panel.page_lines(trial.rows)
    out["restored"] = out["lines_restored"] == out["lines_before"]
    out["reached"] = any(step["reached"] for step in out["attempts"])
    return out


def step_scrollbar(panel, ns):
    """(b) the page scrollbar: AXPress on each pressable button of the AXScrollBar, clicks on
    its track below the thumb, a drag of the thumb."""
    out = {"method": "b-scrollbar", "attempts": []}
    trial = Trial(panel, out, "b", ns["group"], ns["label"])
    bar = panel.scrollbar()
    require(bar, "No AXScrollBar inside the settings column")
    out["ax_scrollbar"] = {"box": bar["box"], "value": bar["value"], "knob": bar["knob"],
                           "buttons": [{"role": b["role"], "box": b["box"]} for b in bar["buttons"]]}
    point, size = panel.geometry()
    out["viewport_controls"] = panel.controls_in((point.x, point.y + VIEW_TOP, VIEW_RIGHT, size.y - VIEW_TOP))
    count = len(bar["buttons"])

    def press(index, times=1):
        panel.press_scroll(index, times)
        return {"presses": times, "box": panel.scrollbar()["buttons"][index]["box"]}

    def click_at(spot):
        panel.click(*spot)
        time.sleep(0.8)
        return {"click": [round(spot[0]), round(spot[1])]}

    def drag_thumb(px):
        knob = panel.scrollbar()["knob"]
        start = (knob[0] + knob[2] / 2, knob[1] + knob[3] / 2)
        panel.drag(start[0], start[1], start[0], start[1] + px)
        time.sleep(0.6)
        return {"knob": knob, "press": [round(start[0]), round(start[1])],
                "release": [round(start[0]), round(start[1] + px)]}

    def to_top():
        if panel.scroll_up_button is None:
            return None
        note = panel.scroll_top(panel.scroll_up_button)
        trial.run("back-to-top", lambda: {"presses": note["presses"]})
        return note

    for index in range(count):
        trial.run(f"ax-press-{index}", lambda index=index: press(index), keep=True)
    marks = [trial.seen(step) for step in out["attempts"]]
    downs, ups = [i for i, mark in enumerate(marks) if mark > 0], [i for i, mark in enumerate(marks) if mark < 0]
    out["button_direction"] = {"down": downs, "up": ups, "marks": marks}
    if ups:
        panel.scroll_up_button = ups[-1]
    out["resets"] = []
    if ups:
        out["resets"].append(to_top())
    for index in downs or range(count):
        for extra in (1, 2):
            trial.run(f"ax-press-{index}-x{extra}", lambda index=index, extra=extra: press(index, extra), keep=True)
        if ups:
            out["resets"].append(to_top())
    point, size = panel.geometry()
    bx, by, bw, bh = panel.scrollbar()["box"]
    bottom = point.y + size.y - 8  # clear of the window's resize border
    for label, depth in (("track-click-mid", 0.6), ("track-click-low", 0.95)):
        trial.run(label, lambda spot=(bx + bw / 2, min(by + bh * depth, bottom)): click_at(spot), keep=True)
    if ups:
        out["resets"].append(to_top())
    trial.run("drag-thumb-20px", lambda: drag_thumb(20), keep=True)
    if ups:
        out["resets"].append(to_top())
    out["reached"] = any(step["reached"] for step in out["attempts"])
    return out


def step_wheel(panel, ns):
    """(c) wheel notches located inside the viewport after a HID-source cursor move, then
    Page Down / Down with the page focused."""
    out = {"method": "c-wheel-cursor", "attempts": []}
    trial = Trial(panel, out, "c", ns["group"], ns["label"])
    vx, vy, vw, vh = panel.viewport()
    inside = (vx + vw * 0.45, vy + vh * 0.6)
    on_strip = (panel.geometry()[0].x + VIEW_RIGHT + 7, vy + vh * 0.6)
    out["cursor_before"] = cursor()
    for label, where, unit, notch in (("line-notches", inside, 1, -1), ("pixel-60", inside, 0, -60),
                                      ("line-notches-on-strip", on_strip, 1, -1)):
        def roll(where=where, unit=unit, notch=notch):
            post_move(panel.pid, *where)
            time.sleep(0.4)
            post_wheel(panel.pid, where[0], where[1], 6, unit, notch)
            return {"point": [round(where[0]), round(where[1])], "unit": unit, "notch": notch, "notches": 6,
                    "cursor_after": cursor()}
        trial.run(label, roll, keep=label == "line-notches")

    def warped():
        code = ax.warp_cursor(ax.Point(*inside))  # this session's cursor; the worker never runs on console
        time.sleep(0.4)
        post_wheel(panel.pid, inside[0], inside[1], 6, 1, -1)
        return {"warp_result": code, "cursor_after": cursor()}
    trial.run("warp-cursor-then-line-notches", warped)
    spot = panel.blank_spot(trial.rows)
    out["focus_click"] = [round(spot[0]), round(spot[1])]
    panel.click(*spot)
    time.sleep(0.6)
    out["focused_after_click"] = panel.focused()
    trial.run("blank-click", lambda: None, keep=True)
    for code, label, presses in ((121, "page-down", 2), (125, "down-arrow", 4)):
        trial.run(label, lambda code=code, presses=presses: post_keys(panel.pid, code, presses) or {"keycode": code},
                  keep=True)
    if panel.scroll_up_button is not None:  # leave the page where the next method expects it
        panel.scroll_top(panel.scroll_up_button)
        trial.run("back-to-top", lambda: None)
    out["reached"] = any(step["reached"] for step in out["attempts"])
    return out


def step_maximize(panel, ns):
    """(d) move the window to the top of the usable screen area and give it the full height,
    read the page, then put the window back."""
    out = {"method": "d-maximize", "attempts": []}
    trial = Trial(panel, out, "d", ns["group"], ns["label"])
    point, size = panel.geometry()

    def grow():
        areas, grown = panel.maximize()
        return {"screen": {key: [round(v) for v in areas[key]] for key in areas},
                "geometry_after": {"origin": [grown[0].x, grown[0].y], "size": [grown[1].x, grown[1].y]}}
    try:
        trial.run("maximized", grow, keep=True)
    finally:
        back = panel.set_frame(point.x, point.y, size.x, size.y)
    trial.run("restored", lambda: {"geometry": [back[0].x, back[0].y, back[1].x, back[1].y]})
    out["reached"] = any(step["reached"] for step in out["attempts"] if step["how"] == "maximized")
    return out


def op_scroll_page(panel, ns):
    """Try the four ways of reaching a page group below the fold, cheapest first; every method
    starts from the top of the page in the standard window and reports what it did to the viewport."""
    ns.setdefault("label", "Print sequence")
    report = {"tab": ns["tab"], "group": ns["group"], "label": ns["label"]}
    rows = panel.read("scroll-entry")
    report["click_tab"] = panel.click_tab(ns["tab"], rows)
    point, size = panel.geometry()
    report["geometry"] = {"origin": [point.x, point.y], "size": [size.x, size.y]}
    report["viewport"] = [round(v) for v in panel.viewport()]
    try:
        report["screen"] = {key: [round(v) for v in areas] for key, areas in (ax.screen_areas() or {}).items()}
    except Exception as error:  # the screen read is context for method (d), not a precondition
        report["screen"] = {"error": brief(error, 300)}
    report["methods"], report["between"] = [], []
    for index, step in enumerate((step_fold, step_scrollbar, step_wheel, step_maximize)):
        try:
            report["methods"].append(step(panel, ns))
        except Exception as error:
            trial = getattr(panel, "trial", None)
            report["methods"].append({"method": step.__name__.replace("step_", "", 1), "error": brief(error, 700),
                                      "attempts": getattr(trial, "out", {}).get("attempts"),
                                      "keep": sorted(getattr(trial, "out", {}).get("keep", ()))})
        # between methods: top of the page (read back), standard window frame
        between = {}
        if panel.scroll_up_button is not None:
            between["top"] = panel.scroll_top(panel.scroll_up_button)
            between["lines"] = panel.page_lines(panel.read(f"scroll-top-{index}"))
        at = panel.geometry()
        if (at[0].x, at[0].y, at[1].x, at[1].y) != (point.x, point.y, size.x, size.y):
            back = panel.set_frame(point.x, point.y, size.x, size.y)
            between["frame_restored"] = [back[0].x, back[0].y, back[1].x, back[1].y]
        report["between"].append(between)
    reached = [method["method"] for method in report["methods"] if method.get("reached")]
    # The same page in Advanced mode (the set_float / set_checkbox path switches it on).
    try:
        # On the active Others page OCR glues the other tab names into one token, which hides
        # the Speed tab: read the band from the Quality page before judging Advanced mode.
        panel.click_tab("Quality", panel.read("scroll-advanced-quality-locate"))
        advanced = panel.ensure_advanced("scroll-advanced")
        panel.click_tab(ns["tab"], panel.read("scroll-advanced-others-locate"))
        report["advanced"] = {"switch": advanced, "lines": panel.page_lines(panel.read("scroll-advanced-others"))}
    except Exception as error:
        report["advanced"] = {"error": brief(error, 500)}
    kept = {"entry", "scroll-entry", "scroll-advanced-others"}
    for method in report["methods"]:
        kept.update(method.get("keep", ()))
        method["keep"] = sorted(method.get("keep", ()))  # JSON carries lists, not sets
    return {"ok": bool(reached), "keep_shots": sorted(kept),
            "readback": {"tab": ns["tab"], "group": ns["group"], "label": ns["label"], "reached_by": reached,
                         "methods": [{"method": method["method"], "reached": method.get("reached", False)}
                                     for method in report["methods"]]},
            "evidence": report}


OPS = {"switch_tab": op_switch_tab, "find_row": op_find_row, "set_float": op_set_float,
       "set_checkbox": op_set_checkbox, "pick_combo": op_pick_combo, "scroll_page": op_scroll_page,
       "scenario": op_scenario}


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
                    "at": [round(panel.desktop.position(element).x), round(panel.desktop.position(element).y)]}
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
    result = {"op": ns["op"], "name": ns.get("name"), "ok": True, "sut": {"version": info.get("CFBundleShortVersionString")},
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
    shots, keep = {}, result.get("keep_shots")
    for name in sorted((work / "out").glob("*.png")):
        crop = name.name.endswith(".panel.png")
        if crop and keep is not None and name.name[:-len(".panel.png")] not in keep:
            continue  # a probe's working shots stay out of the evidence directory
        dest = crop_dir if crop else full_dir
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
    key = ":".join(filter(None, (result["op"], result.get("name"))))  # scenarios stay apart
    data["ops"][key] = result
    data["attempts"].append({"op": key, "stamp": stamp, "ok": result["ok"]})
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
    scroll = sub.add_parser("scroll_page")
    scroll.add_argument("--tab", default="Others")
    scroll.add_argument("--group", default="Special mode")
    scroll.add_argument("--label", default="Print sequence")
    sub.add_parser("scenario").add_argument("--name", required=True, choices=sorted(SCENARIOS))
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
