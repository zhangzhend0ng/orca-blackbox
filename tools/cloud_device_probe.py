"""Read-only discovery of a signed-in Orca user's devices."""
from __future__ import annotations

import csv
import io
import re
import subprocess
import time


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


def device_labels(lines):
    fixed = re.compile(
        r"\b(?:my devices|add device|no devices?|no data|lan mode|cloud mode|"
        r"manual(?:ly)? connect|manual add|connect|device control|device discovery|"
        r"devices? nearby|nearby devices?|finding new devices|enter ip address|"
        r"offline|online|idle|working|printing|unavailable|disconnected|"
        r"snapmaker|u1|j1s?|artisan|a[23]50|a150)\b"
    )
    return [
        {"labels": fixed.findall(label), "x_band": x // 80, "y_band": y // 40}
        for label, x, y in lines
    ]


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

    add_targets = []
    page_seen_at = None

    def read_devices():
        nonlocal add_targets, page_seen_at
        width, lines = visible_lines(app.hwnd)
        content = [label for label, x, _ in lines if x > width // 4]
        add_targets = [(x, y) for label, x, y in lines if x > width // 4
                       and re.search(r"\badd\s+device\b", label)]

        def count(pattern):
            return sum(bool(re.search(pattern, label)) for label in content)

        result["device_page"] = {
            "heading": bool(count(r"\bmy\s+devices\b")),
            "add_device_visible": bool(count(r"\badd\s+device\b")),
            "idle_labels": count(r"\bidle\b"),
            "online_labels": count(r"\bonline\b"),
            "offline_labels": count(r"\boffline\b"),
            "working_labels": count(r"\b(?:working|printing|paused)\b"),
            "empty_message": bool(count(r"\b(?:no\s+(?:device|data)s?|add\s+your\s+first\s+device)\b")),
            "network_error": bool(count(r"\b(?:network\s+error|failed\s+to\s+load)\b")),
            "file_tab_visible": bool(count(r"\b(?:local\s+files|uploaded\s+files|u-disk\s+files)\b")),
            "upload_label_visible": bool(count(r"\bupload\b")),
            "content_text_lines": len(content),
        }
        result["device_layout"] = device_labels([
            (label, x, y) for label, x, y in lines if x > width // 4 and y > 90
        ])
        page = result["device_page"]
        if not page["heading"] or not page["add_device_visible"]:
            return False
        if page_seen_at is None:
            page_seen_at = time.monotonic()
        return time.monotonic() - page_seen_at >= 6

    poll(read_devices, 24)
    page = result.get("device_page", {})
    if page.get("heading") or page.get("add_device_visible"):
        result["device_stage"] = "device_page_observed"
        if not (page.get("idle_labels") or page.get("online_labels")) and len(add_targets) == 1:
            inspect_nearby(app, add_targets[0], result, poll)
        return True
    return False


def inspect_nearby(app, add_target, result, poll):
    from harness import winutil

    if not winutil.force_set_foreground(app.hwnd):
        return
    if winutil.real_click_screen(*winutil.client_to_screen(app.hwnd, *add_target)) != 2:
        return
    result["nearby_stage"] = "discovery_opened"
    ready_at = None

    def discovery():
        nonlocal ready_at
        for hwnd, pid in winutil.enum_windows():
            if pid != app.pid:
                continue
            _, lines = visible_lines(hwnd)
            words = "\n".join(label for label, _, _ in lines)
            nearby = bool(re.search(r"\b(?:nearby\s+devices?|devices?\s+nearby|discovery\s+device|device\s+discovery)\b", words))
            manual = bool(re.search(r"\bmanual(?:ly)?\s+(?:connect|add)\b|\benter\s+ip\s+address\b", words))
            title = winutil.window_title(hwnd).casefold()
            discovery_window = (
                hwnd != app.hwnd and title in {"add device", "device discovery", "discovery device"}
            )
            if not (nearby or manual or discovery_window):
                continue
            if ready_at is None:
                ready_at = time.monotonic()
            result["nearby_page"] = {
                "nearby_heading": nearby,
                "manual_connect_visible": manual,
                "searching": bool(re.search(r"\b(?:finding|searching\s+for)\s+(?:new\s+)?devices\b", words)),
                "empty_message": bool(re.search(r"\bno\s+(?:nearby\s+)?devices?\b", words)),
                "device_model_labels": len(re.findall(r"\b(?:snapmaker\s+)?(?:u1|j1s?|artisan|a[23]50|a150)\b", words)),
                "content_text_lines": len(lines),
            }
            result["nearby_layout"] = device_labels(lines)
            return time.monotonic() - ready_at >= 10
        return False

    poll(discovery, 25)
    if result.get("nearby_page"):
        result["nearby_stage"] = "discovery_observed"
