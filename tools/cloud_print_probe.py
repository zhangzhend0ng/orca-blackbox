"""Start one verified print from a newly created Orca project."""
from __future__ import annotations

import re

from tools.cloud_device_probe import visible_lines
from tools.cloud_upload_probe import click_client, one, opens_preprint_page


def observe_u1_task(app, result):
    from harness import winutil

    width, height, _ = winutil.capture_window(app.hwnd)
    _, full = visible_lines(app.hwnd)
    headers = [(x, y) for label, x, y in full
               if re.search(r"\bprinting\s+task\b", label) and x < width * 0.65]
    lines = full
    if len(headers) == 1:
        x, y = headers[0]
        if y + 15 < height:
            _, lines = visible_lines(
                app.hwnd, crop=(max(0, x - 130), y + 7, min(width, x + 510), height - 3), psm=6,
            )
    text = "\n".join(label for label, _, _ in lines)
    percentages = [int(value) for value in re.findall(r"(?<!\d)([0-9]{1,3})\s*%", text)]
    working = bool(re.search(
        r"\b(?:paused|resume\s+print|pause\s+print|printing\s+in\s+progress|heating|calibrating)\b", text
    )) or any(0 < n < 100 for n in percentages)
    idle = bool(re.search(r"\b(?:idle|no\s+(?:current\s+|printing\s+|print\s+)?(?:task|job))\b", text))
    state = {"printing_task_area": len(headers) == 1, "idle_label": idle,
             "active_job": working, "progress_percent": percentages[:6]}
    result["print_device_before"] = state
    return idle and not working


def start_print(app, filename, result, poll):
    from harness import winutil

    result["print_stage"] = "find_preprint_dialog"

    def identify():
        dialogs = [hwnd for hwnd, pid in winutil.enum_windows()
                   if pid == app.pid and winutil.window_title(hwnd) == "Print Preprocessing"]
        candidate = one(dialogs)
        return candidate if candidate is not None and opens_preprint_page(candidate, 4) else None

    dialog = poll(identify, 20)
    if dialog is None:
        return False
    result["print_page_verified"] = True
    result["print_stage"] = "verify_target_and_readiness"

    def button():
        width, height, raw = winutil.capture_window(dialog)
        _, lines = visible_lines(dialog)
        heading = one([(x, y) for label, x, y in lines if label.strip() == "select printer"])
        selected = False
        if heading is not None:
            _, labels = visible_lines(
                dialog, crop=(width // 4 + 164, heading[1], width // 4 + 240, heading[1] + 34), psm=7,
            )
            selected = any(label.strip() == "u1" for label, _, _ in labels)
        words = "\n".join(label for label, _, _ in lines)
        warning = bool(re.search(
            r"\b(?:offline|mismatch(?:es)?|not\s+(?:ready|available|connected)"
            r"|failed|different\s+material|nozzle\s+does\s+not\s+match|printer\s+is\s+printing)\b", words,
        ))
        _, footer = visible_lines(
            dialog, crop=(width - 140, height - 60, width - 35, height - 16), psm=7,
        )
        target = one([(x, y) for label, x, y in footer if label.strip() in {"print", "start print"}])
        enabled = False
        if target is not None:
            x, y = target
            offset = (y * width + x - 38) * 4
            blue, green, red = raw[offset:offset + 3]
            enabled = blue >= 190 and green >= 95 and red < 100
        result["preprint"] = {"u1_selected": selected, "filename_visible": filename in words,
                              "warning": warning, "print_button_enabled": enabled}
        return target if selected and filename in words and not warning and enabled else None

    point = poll(button, 22)
    if point is None:
        return False
    if not result.get("print_device_idle_before") or not opens_preprint_page(dialog, 4):
        result["print_stage"] = "await_confirmed_idle_device"
        return False
    if not click_client(dialog, point):
        return False
    result["print_submitted"] = True
    result["print_stage"] = "verify_print_started"

    def receipt():
        for current, pid in winutil.enum_windows():
            if pid != app.pid:
                continue
            _, lines = visible_lines(current)
            words = "\n".join(label for label, _, _ in lines)
            if re.search(r"\bprint\s+started\b", words):
                result["print_receipt"] = "orca_print_started"
                return True
            if filename in words and re.search(r"\b(?:heating|printing\s+in\s+progress|printing)\b", words):
                result["print_receipt"] = "matching_job_on_device"
                return True
        return False

    if poll(receipt, 75):
        result["print_stage"] = "print_started"
        return True
    return False
