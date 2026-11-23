"""Probe 14 (task A5 step 1): is Screen Capture TCC granted to the probe channel.

A2 left both OCR unlock channels TCC-blocked (screencapture -x timed out at
6 s, System Events -1743). Before any walls work, re-test the grant with the
user possibly having enabled it since: launch Orca so the screen carries the
distinctive slicer UI, then run `screencapture -x` twice at most (red line:
no more than 2 attempts). A valid PNG alone can be a wallpaper-only capture,
so also grab the Orca window region with -R and decode it in pure Python
(IHDR + zlib + unfilter): the verdict reports dimensions, byte size and the
unique-color count of the decoded region. Read-only for the project; Orca is
killed and verified gone in main(). 240 s fuse.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import struct
import subprocess
import sys
import time
import zlib

import accessibility as ax

WORK = Path(__file__).resolve().parent
APP = Path("/Applications/Snapmaker Orca.app")
EXE = str(APP / "Contents/MacOS/Snapmaker_Orca")
PROJECT = WORK / "probe.3mf"
PROFILE = WORK / "datadir"
OUT = WORK / "out"
RESULT = {"ok": False}


def note(key, value):
    RESULT[key] = value
    print(f"[probe14] {key}: {json.dumps(value)[:700]}", flush=True)


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


def png_ihdr(raw):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    offset = 8
    while offset + 8 <= len(raw):
        length, kind = struct.unpack(">I4s", raw[offset:offset + 8])
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", raw[offset + 8:offset + 18])
            return {"width": width, "height": height, "bit_depth": depth, "color_type": color}
        offset += 12 + length
    return None


def decode_png(raw, cap_width=700):
    """Decode an 8-bit RGB/RGBA PNG with stdlib only; returns stats + a sample."""
    header = png_ihdr(raw)
    if not header or header["bit_depth"] != 8 or header["color_type"] not in (2, 6):
        return {"error": "unsupported png", "ihdr": header}
    width, height, color = header["width"], header["height"], header["color_type"]
    if width > cap_width:
        return {"error": "region too large to decode", "ihdr": header}
    channels = 4 if color == 6 else 3
    offset, idat = 8, []
    while offset + 8 <= len(raw):
        length, kind = struct.unpack(">I4s", raw[offset:offset + 8])
        body = raw[offset + 8:offset + 8 + length]
        if kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        offset += 12 + length
    try:
        stream = zlib.decompress(b"".join(idat))
    except zlib.error as error:
        return {"error": f"zlib: {error}", "ihdr": header}
    stride = width * channels
    colors = set()
    first_row = None
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        if pos + 1 + stride > len(stream):
            return {"error": "truncated scanline data", "ihdr": header, "rows_done": y}
        filter_type = stream[pos]
        row = bytearray(stream[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if filter_type == 1:  # Sub
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = prev[i]
                corner = prev[i - channels] if i >= channels else 0
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                predictor = left if (pa <= pb and pa <= pc) else (up if pb <= pc else corner)
                row[i] = (row[i] + predictor) & 0xFF
        if y == 0:
            first_row = bytes(row[:min(stride, 96)])
        if y % 3 == 0:  # sample every third row; enough for a diversity verdict
            for x in range(0, stride - channels + 1, channels):
                colors.add(bytes(row[x:x + 3]))
        prev = row
    return {"ihdr": header, "rows": height, "sampled_unique_colors": len(colors),
            "first_row_hex": first_row.hex() if first_row else None}


def try_capture(tag, args, timeout=10):
    target = OUT / (tag + ".png")
    attempt = {"tag": tag, "args": args}
    try:
        done = subprocess.run(["/usr/sbin/screencapture", *args, str(target)],
                              capture_output=True, text=True, timeout=timeout)
        attempt.update(rc=done.returncode, err=done.stderr[-300:],
                       bytes=target.stat().st_size if target.exists() else 0)
    except subprocess.TimeoutExpired:
        attempt.update(error=f"screencapture timed out ({timeout} s)")
        if target.exists():
            target.unlink()
    if target.exists() and attempt.get("bytes"):
        attempt["ihdr"] = png_ihdr(target.read_bytes()[:64])
    return attempt


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
        note("entry", {"pid": pid, "version": version, "origin": [origin.x, origin.y]})

        # Full-screen capture, at most 2 attempts (red line).
        full = try_capture("full", ["-x"])
        if not full.get("bytes"):
            time.sleep(1.5)
            full = try_capture("full_retry", ["-x"])
        note("full_capture", full)
        granted = bool(full.get("bytes"))

        region_stats = None
        if granted:
            # 600x400 of the Orca window: distinctive UI vs wallpaper-only proof.
            region = try_capture("orca_region", ["-x", "-R360,85,600,400"])
            note("region_capture", region)
            if region.get("bytes"):
                region_stats = decode_png((OUT / "orca_region.png").read_bytes())
                note("region_decode", region_stats)

        note("screen_tcc", {
            "granted": granted,
            "verdict_hint": ("valid_png" if granted else "no_png")
            + (f"; region_unique_colors={region_stats['sampled_unique_colors']}"
               if region_stats and "sampled_unique_colors" in region_stats else ""),
        })


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
    print("[probe14] result:", json.dumps(RESULT)[:900], flush=True)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
