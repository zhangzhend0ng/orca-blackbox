"""Read-only discovery of a signed-in Orca user's devices."""
from __future__ import annotations

import csv
import io
import re
import subprocess


def visible_lines(hwnd, *, sidebar=False):
    """Read label positions in memory. Device identities are never retained."""
    from PIL import Image

    from harness import ocr_util, winutil

    width, height, pixels = winutil.capture_window(hwnd)
    picture = Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX")
    if sidebar:
        picture = picture.crop((0, 0, width // 4, height // 2))
    payload = io.BytesIO()
    scale = 2
    picture.resize((picture.width * scale, picture.height * scale)).save(payload, format="PNG")
    data = subprocess.run(
        [ocr_util.TESSERACT_EXE, "stdin", "stdout", "-l", "eng", "--psm", "11", "tsv"],
        input=payload.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=10,
    ).stdout.decode("utf-8")
    groups = {}
    for word in csv.DictReader(io.StringIO(data), delimiter="\t", quoting=csv.QUOTE_NONE):
        if not word["text"].strip() or float(word["conf"]) < 35:
            continue
        line = tuple(word[key] for key in ("block_num", "par_num", "line_num"))
        groups.setdefault(line, []).append(word)
    lines = []
    for group in groups.values():
        words = " ".join(word["text"] for word in group).strip().casefold()
        left = min(int(word["left"]) for word in group)
        right = max(int(word["left"]) + int(word["width"]) for word in group)
        top = min(int(word["top"]) for word in group)
        bottom = max(int(word["top"]) + int(word["height"]) for word in group)
        lines.append((words, (left + right) // (2 * scale), (top + bottom) // (2 * scale)))
    return width, lines


def inspect_devices(app, result, poll):
    from harness import winutil

    result["device_stage"] = "find_my_devices"

    def find_entry():
        _, lines = visible_lines(app.hwnd, sidebar=True)
        matches = [(x, y) for label, x, y in lines if re.search(r"\bmy\s+devices\b", label)]
        return matches[0] if len(matches) == 1 else None

    target = poll(find_entry, 7)
    if target is None or not winutil.force_set_foreground(app.hwnd):
        return False
    if winutil.real_click_screen(*winutil.client_to_screen(app.hwnd, *target)) != 2:
        return False
    result["device_stage"] = "read_my_devices"

    def read_devices():
        width, lines = visible_lines(app.hwnd)
        content = [label for label, x, _ in lines if x > width // 4]

        def count(pattern):
            return sum(bool(re.search(pattern, label)) for label in content)

        result["device_page"] = {
            "heading": bool(count(r"\bmy\s+devices\b")),
            "add_device_visible": bool(count(r"\badd\s+device\b")),
            "idle_labels": count(r"\bidle\b"),
            "offline_labels": count(r"\boffline\b"),
            "working_labels": count(r"\b(?:working|printing|paused)\b"),
            "empty_message": bool(count(r"\b(?:no\s+(?:device|data)s?|add\s+your\s+first\s+device)\b")),
            "network_error": bool(count(r"\b(?:network\s+error|failed\s+to\s+load)\b")),
            "file_tab_visible": bool(count(r"\b(?:local\s+files|uploaded\s+files|u-disk\s+files)\b")),
            "upload_label_visible": bool(count(r"\bupload\b")),
        }
        return result["device_page"]["heading"] and any(
            result["device_page"][key]
            for key in ("idle_labels", "offline_labels", "working_labels", "empty_message", "network_error")
        )

    poll(read_devices, 24)
    page = result.get("device_page", {})
    if page.get("heading") or page.get("add_device_visible"):
        result["device_stage"] = "device_page_observed"
        return True
    return False
