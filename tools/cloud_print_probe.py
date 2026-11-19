"""Start one verified print from a newly created Orca project."""
from __future__ import annotations

import re

from tools.cloud_device_probe import visible_lines
from tools.cloud_upload_probe import click_client, one, opens_preprint_page


def find_device_name(hwnd, name, bounds, surface):
    x0, y0, x1, y1 = bounds
    if name == "U1":
        _, lines = visible_lines(hwnd, crop=bounds, psm=11)
        return one([(x, y) for label, x, y in lines if label == "u1"])

    import cv2
    import numpy as np

    from harness import anchors, winutil

    width, height, raw = winutil.capture_window(hwnd)
    frame = cv2.cvtColor(np.frombuffer(raw, np.uint8).reshape(height, width, 4)[y0:y1, x0:x1],
                         cv2.COLOR_BGRA2BGR)
    variants = (surface, "card") if surface != "card" else ("card",)
    for variant in variants:
        template = anchors.RESOURCE / f"cloud_client_test_{variant}.png"
        score, x, y, width, height = anchors.match(frame, template)
        if score >= .86:
            return x0 + x + width // 2, y0 + y + height // 2
    return None


def observe_device_task(app, name):
    from harness import winutil

    width, height, raw = winutil.capture_window(app.hwnd)
    selected = False
    idle_badge = False
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
            label = find_device_name(app.hwnd, name, (x - 52, y + 30, x + 190, y + 66), "panel")
            if label:
                selected = True
                # Verified green idle badge immediately to the left of the device name.
                label_width = 80 if name == "客户端测试" else 20
                badge_start = label[0] - label_width // 2 - 36
                green_pixels = 0
                for row in range(label[1] - 6, label[1] + 7):
                    for column in range(badge_start, badge_start + 30):
                        offset = (row * width + column) * 4
                        blue, green, red = raw[offset:offset + 3]
                        green_pixels += green >= 140 and green >= red + 80 and green >= blue + 80
                idle_badge = green_pixels >= 130
    text = "\n".join(label for label, _, _ in lines)
    percentages = [int(value) for value in re.findall(r"(?<!\d)([0-9]{1,3})\s*%", text)]
    working = bool(re.search(
        r"\b(?:working|paused|resume\s+print|pause\s+print|printing\s+in\s+progress|heating|calibrating)\b", text
    )) or any(0 < n < 100 for n in percentages)
    idle = bool(re.search(r"\b(?:idle|no\s+(?:current\s+|printing\s+|print\s+)?(?:task|job))\b", text))
    return {"selected": selected, "printing_task_area": len(headers) == 1, "idle_label": idle or idle_badge,
            "active_job": working, "progress_percent": percentages[:6]}


def select_idle_device(app, result, poll):
    from tools.cloud_device_probe import inspect_devices

    checks = {}
    result["print_device_checks"] = checks
    for index, name in enumerate(("客户端测试", "U1")):
        if index and not click_client(app.hwnd, (20, 50)):
            break
        observation = {}
        inspect_devices(app, observation, poll, print_target=name)
        if observation.get("device_stage") in {"device_control_opened", "device_tab_opened"}:
            state = {}

            def ready():
                state.update(observe_device_task(app, name))
                return state["selected"] and state["printing_task_area"] and (
                    state["idle_label"] or state["active_job"])

            observed = poll(ready, 8)
            state["stage"] = observation["device_stage"]
            checks[name] = state
            if observed and state["idle_label"] and not state["active_job"]:
                result["print_target"] = name
                result["print_device_idle_before"] = True
                return
        else:
            checks[name] = {"stage": observation.get("device_stage")}
    result["print_device_idle_before"] = False


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
    name = result.get("print_target")
    if name is None:
        result["print_stage"] = "await_confirmed_idle_device"
        return False

    picker = None

    def button():
        nonlocal picker
        width, height, raw = winutil.capture_window(dialog)
        _, lines = visible_lines(dialog)
        heading = one([(x, y) for label, x, y in lines if label.strip() == "select printer"])
        selected = None
        if heading is not None:
            picker = (width * 57 // 100, heading[1] + 16)
            selected = find_device_name(dialog, name, (width // 4 + 150, heading[1],
                                                       width // 4 + 283, heading[1] + 38), "picker")
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
        filename_visible = filename in words or filename.removesuffix(".gcode") in words
        result["preprint"] = {"target_selected": selected is not None, "filename_visible": filename_visible,
                              "warning": warning, "print_button_enabled": enabled}
        return target if selected and filename_visible and not warning and enabled else None

    point = poll(button, 8)
    if point is None and picker and not result["preprint"]["target_selected"]:
        if not opens_preprint_page(dialog, 4) or not click_client(dialog, picker):
            return False
        width, height, _ = winutil.capture_window(dialog)
        choice = poll(lambda: find_device_name(dialog, name, (width // 4 + 110, picker[1] + 24,
                                                              width // 4 + 374, min(height, picker[1] + 180)),
                                               "picker"), 12)
        if choice is not None and click_client(dialog, choice):
            point = poll(button, 15)
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
            if (filename.removesuffix(".gcode") in words and
                    re.search(r"\b(?:heating|printing\s+in\s+progress|working|preparing)\b", words)):
                result["print_receipt"] = "matching_job_on_device"
                return True
        return False

    if poll(receipt, 75):
        result["print_stage"] = "print_started"
        return True
    return False
