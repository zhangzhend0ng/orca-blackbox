"""Read-only discovery of a signed-in Orca user's devices."""
from __future__ import annotations

import csv
import io
import re
import subprocess
import time


def visible_lines(hwnd, *, sidebar=False, crop=None, psm=11):
    """Read label positions in memory. Device identities are never retained."""
    from PIL import Image

    from harness import ocr_util, winutil

    width, height, pixels = winutil.capture_window(hwnd)
    picture = Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX")
    if sidebar:
        crop = (0, 0, width // 4, height // 2)
    x0, y0 = 0, 0
    if crop:
        x0, y0, x1, y1 = crop
        picture = picture.crop((max(x0, 0), max(y0, 0), min(x1, width), min(y1, height)))
    payload = io.BytesIO()
    scale = 4 if crop and not sidebar else 2
    picture.resize((picture.width * scale, picture.height * scale)).save(payload, format="PNG")
    data = subprocess.run(
        [ocr_util.TESSERACT_EXE, "stdin", "stdout", "-l", "eng", "--psm", str(psm), "tsv"],
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
        lines.append((words, x0 + (left + right) // (2 * scale), y0 + (top + bottom) // (2 * scale)))
    return width, lines


def home_sidebar_edge(hwnd, width):
    from harness import winutil

    return min(width // 4, round(262 * winutil.get_dpi_for_window(hwnd) / 96))


def device_labels(lines):
    fixed = re.compile(
        r"\b(?:my devices|add device|no devices?|no data|lan mode|cloud mode|"
        r"manual(?:ly)? connect|manual add|connect|device control|device discovery|"
        r"devices? nearby|nearby devices?|finding new devices|enter ip address|"
        r"offline|online|idle|working|printing|unavailable|disconnected|connecting|"
        r"lan|wan|ready|local files|u-disk files|temperature|nozzle|heated bed|files|"
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
    u1_cards = []
    page_seen_at = None

    def read_devices():
        nonlocal add_targets, u1_cards, page_seen_at
        width, lines = visible_lines(app.hwnd)
        edge = home_sidebar_edge(app.hwnd, width)
        content = [label for label, x, _ in lines if x > edge]
        add_targets = [(x, y) for label, x, y in lines if x > edge
                       and re.search(r"\badd\s+device\b", label)]
        u1_cards = [(x, y) for label, x, y in lines if x > edge and y > 230
                    and re.search(r"\bu1\b", label)]

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
            "u1_card_labels": len(u1_cards),
        }
        result["device_layout"] = device_labels([
            (label, x, y) for label, x, y in lines if x > edge and y > 90
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
        if u1_cards:
            connect_u1(app, u1_cards[0], result, poll)
        elif not (page.get("idle_labels") or page.get("online_labels")) and len(add_targets) == 1:
            inspect_nearby(app, add_targets[0], result, poll)
        return True
    return False


def connect_u1(app, card, result, poll):
    from harness import winutil

    result["device_stage"] = "find_u1_device_control"
    if not winutil.force_set_foreground(app.hwnd):
        return
    x, y = card

    def control():
        _, lines = visible_lines(app.hwnd, crop=(max(0, x - 96), max(0, y - 190), x + 124, y + 8))
        result["selected_card_layout"] = device_labels(lines)
        choices = [(cx, cy) for label, cx, cy in lines if cy < y - 9 and
                   (re.search(r"\bdevice\s+control\b", label) or label.strip() == "control")]
        return choices[0] if len(choices) == 1 else None

    point = None
    for y_offset in (82, 121, 47):
        if not winutil.user32.SetCursorPos(*winutil.client_to_screen(app.hwnd, x, y - y_offset)):
            return
        point = poll(control, 3)
        if point is not None:
            break
    if point is None or winutil.user32.GetForegroundWindow() != app.hwnd:
        return
    if winutil.real_click_screen(*winutil.client_to_screen(app.hwnd, *point)) != 2:
        return
    result["device_stage"] = "device_control_opened"
    seen = set()

    def check_connection():
        lines = []
        for hwnd, pid in winutil.enum_windows():
            if pid == app.pid:
                lines.extend(visible_lines(hwnd)[1])
        words = "\n".join(label for label, _, _ in lines)
        seen.update(label for row in device_labels(lines) for label in row["labels"])
        result["device_control_labels_seen"] = sorted(seen)
        state = {
            "idle": bool(re.search(r"\b(?:idle|ready)\b", words)),
            "offline": bool(re.search(r"\b(?:offline|not\s+available|disconnected|failed\s+to\s+connect|connection\s+failed)\b", words)),
            "local_files": bool(re.search(r"\b(?:local files|u-disk files)\b", words)),
            "temperature": bool(re.search(r"\b(?:temperature|heated bed|nozzle)\b", words)),
            "files_tab": any(label.strip() == "files" for label, _, _ in lines),
            "still_on_home": bool(re.search(r"\b(?:my devices|model library|add device)\b", words)),
        }
        result["device_control"] = state
        return state["offline"] or (
            not state["still_on_home"] and state["files_tab"] and state["temperature"]
        )

    if poll(check_connection, 14):
        if result["device_control"]["offline"]:
            result["device_stage"] = "device_reported_offline"
        else:
            inspect_files(app, result, poll)
        return
    _, lines = visible_lines(app.hwnd)
    tabs = [(tx, ty) for label, tx, ty in lines if ty < 95 and re.fullmatch(r"device", label)]
    if len(tabs) != 1 or not winutil.force_set_foreground(app.hwnd):
        return
    if winutil.real_click_screen(*winutil.client_to_screen(app.hwnd, *tabs[0])) != 2:
        return
    result["device_stage"] = "device_tab_opened"
    if poll(check_connection, 14) and not result["device_control"]["offline"]:
        inspect_files(app, result, poll)


def inspect_files(app, result, poll):
    from harness import winutil

    result["device_stage"] = "u1_device_panel_observed"

    def find_tab():
        tabs = []
        for hwnd, pid in winutil.enum_windows():
            if pid == app.pid:
                _, lines = visible_lines(hwnd)
                tabs.extend((hwnd, x, y) for label, x, y in lines if label.strip() == "files")
        return tabs[0] if len(tabs) == 1 else None

    found = poll(find_tab, 5)
    if found is None:
        return
    hwnd, x, y = found
    if not winutil.force_set_foreground(hwnd):
        return
    if winutil.real_click_screen(*winutil.client_to_screen(hwnd, x, y)) != 2:
        return
    result["device_stage"] = "device_files_opened"

    def files():
        _, lines = visible_lines(hwnd)
        words = "\n".join(label for label, _, _ in lines)
        result["device_file_labels"] = device_labels(lines)
        state = {
            "local_files": bool(re.search(r"\blocal\s+files\b", words)),
            "usb_files": bool(re.search(r"\b(?:u-disk|usb)\s+files\b", words)),
            "upload_button_label": any(label.strip() in {"upload", "upload file"} for label, _, _ in lines),
            "stored_gcode_labels": len(re.findall(r"\.gcode(?:\b|$)", words)),
            "network_error": bool(re.search(r"\b(?:failed\s+to\s+(?:fetch|load)|network\s+error)\b", words)),
        }
        result["device_files"] = state
        return state["local_files"] and (state["usb_files"] or state["stored_gcode_labels"])

    if poll(files, 14):
        result["device_stage"] = "u1_device_files_observed"


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
