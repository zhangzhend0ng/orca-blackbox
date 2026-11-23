"""Offline check of the shot file names param_case cuts its checkbox strips from - no Orca, no
screen, no GUI session.

  .venv/bin/python -B runner/macos/param_case_check.py

op_case stores every shot of an op under its prefix (op1-check-checked.png); locate_row hands
back the bare tag (check-page). Run 034725 cut from the bare names, found no file and stopped
right after the cell click. Here tick() runs the way op_case runs it - the same per_op_shots
wrapper, the real Panel.shot / read, the real sips crop and pixel_diff - over a page whose
shots are PNG files written to a temporary out/.

  1  negative control: the bare names in that out/ are refused (the run 034725 error)
  2  tick(): both strips cut from the op1- files, the click posted once, ok
  3  a page shot that is not on disk: tick() refuses before any click

Prints one JSON line; exit 0 only when all three hold.
"""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import param_case as pc
import param_ops as po

ORIGIN, SIZE = types.SimpleNamespace(x=100, y=100), types.SimpleNamespace(x=700, y=700)
ROW = {"x": 120, "y": 392, "w": 90, "h": 16, "text": "Detect thin walls"}
PAGE = [{"x": 110, "y": 150, "w": 60, "h": 16, "text": "Strength"}, ROW]
MID = ROW["y"] + ROW["h"] / 2
OP = {"label": "Detect", "value": True}
CURRENT = None  # the page whose frame param_ops.capture copies


def frame(path, marked):
    """An 800x800 RGB PNG: a light page and, when `marked`, a dark square in the row's value cell."""
    blank = b"\x00" + b"\xf0\xf0\xf0" * 800
    lines = []
    for y in range(800):
        if marked and MID - 8 <= y < MID + 8:
            line = bytearray(b"\xf0\xf0\xf0" * 800)
            for x in range(ORIGIN.x + po.VALUE_X - 8, ORIGIN.x + po.VALUE_X + 8):
                line[x * 3:x * 3 + 3] = b"\x20\x20\x20"
            lines.append(b"\x00" + bytes(line))
        else:
            lines.append(blank)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 800, 800, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(b"".join(lines))) + chunk(b"IEND", b""))


def capture(tag):
    """param_ops.capture over a file: the page's current frame, stored as out/<tag>.png."""
    target = po.OUT / f"{tag}.png"
    shutil.copy2(CURRENT.frames / ("after.png" if CURRENT.clicks else "before.png"), target)
    return target


class FakePage(po.Panel):
    """A Panel over files: a click marks the frame (the box is ticked); locate_row is its first
    attempt and hands back the bare tag, as the real one does."""

    def __init__(self, out):
        po.Panel.__init__(self, None, 0, None, None)
        self.out, self.frames, self.clicks = out, out / "frames", 0
        self.frames.mkdir()
        frame(self.frames / "before.png", False)
        frame(self.frames / "after.png", True)

    def geometry(self):
        return ORIGIN, SIZE

    @property
    def dirty(self):
        return self.clicks > 0

    def click(self, gx, gy, guard=True):
        self.clicks += 1

    def locate_row(self, tab, group, label, prefix):
        self.read(f"{prefix}-page-locate")
        self.read(f"{prefix}-page")
        return PAGE, ROW, [{"tab_click": "faked"}], f"{prefix}-page"


def main():
    global CURRENT
    po.capture, po.ocr_rows = capture, lambda png, crop=None: PAGE
    top = Path(tempfile.mkdtemp(prefix="orca-bb-param-case-check."))
    parts, held = {}, {}
    try:
        # 1 - the bare names, looked up the way tick() did before the fix
        po.OUT = top / "control"
        po.OUT.mkdir()
        page = CURRENT = FakePage(po.OUT)
        pc.per_op_shots(page, 1)
        page.read("check-page")
        page.shot("check-checked")
        base = po.checkbox_strip(page, ROW, "check-page")
        try:
            po.pixel_diff(po.checkbox_strip(page, ROW, "check-checked"), base)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            parts["1_bare_names_refused"] = po.brief(error).replace(str(top), "<tmp>")
        else:
            parts["1_bare_names_refused"] = "NOT REFUSED: the bare names are usable in this out/"
        # 2 - tick() under op_case's wrapper
        po.OUT = top / "tick"
        po.OUT.mkdir()
        page = CURRENT = FakePage(po.OUT)
        pc.per_op_shots(page, 1)
        try:
            done = pc.tick(page, OP, "Strength", "Detect")
            parts["2_tick"] = {"ok": done["ok"], "clicks": page.clicks, "dirty": page.dirty,
                               "pixels_changed_vs_before": done["readback"]["pixels_changed_vs_before"],
                               "strips": sorted(p.name for p in po.OUT.glob("*.cell.png")),
                               "shots": dict(page.shots)}
        except Exception as error:
            parts["2_tick"] = {"ok": False, "clicks": page.clicks, "error": po.brief(error).replace(str(top), "<tmp>")}
        # 3 - the page shot is not a file: refused before any click
        po.OUT = top / "missing"
        po.OUT.mkdir()
        page = CURRENT = FakePage(po.OUT)
        page.locate_row = lambda tab, group, label, prefix: (PAGE, ROW, [], f"{prefix}-page-gone")
        pc.per_op_shots(page, 1)
        try:
            pc.tick(page, OP, "Strength", "Detect")
        except RuntimeError as error:
            parts["3_missing_page_shot"] = {"clicks": page.clicks, "error": po.brief(error, 200).replace(str(top), "<tmp>")}
        else:
            parts["3_missing_page_shot"] = {"clicks": page.clicks, "error": "NOT REFUSED"}
    finally:
        shutil.rmtree(top, ignore_errors=True)
    one, two, three = (parts.get(k, {}) for k in ("1_bare_names_refused", "2_tick", "3_missing_page_shot"))
    held["1"] = isinstance(one, str) and not one.startswith("NOT REFUSED")
    held["2"] = (two.get("ok") is True and two.get("clicks") == 1
                 and two.get("strips") == ["op1-check-checked.cell.png", "op1-check-page.cell.png"])
    held["3"] = three.get("clicks") == 0 and three.get("error", "NOT REFUSED") != "NOT REFUSED"
    print(json.dumps({"check": "param_case shot file names (offline, no GUI)", "held": held,
                      "ok": all(held.values()), "parts": parts}, separators=(",", ":")))
    return 0 if all(held.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
