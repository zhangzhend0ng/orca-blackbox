"""Upload a fresh U1 slice via Orca's separate send-only page."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlsplit

from tools.cloud_device_probe import visible_lines


def one(values):
    return values[0] if len(values) == 1 else None


def click_client(hwnd, point):
    from harness import winutil

    return (point is not None and winutil.force_set_foreground(hwnd)
            and winutil.real_click_screen(*winutil.client_to_screen(hwnd, *point)) == 2)


def open_test_project(app, fixture, result, poll):
    from harness import export_util, topbar_util, winutil

    result["upload_stage"] = "open_fixture_file_menu"
    if not winutil.force_set_foreground(app.hwnd):
        return False
    toolbar = topbar_util._topbar(app.hwnd)
    if toolbar is None or winutil._window_pid(toolbar[2]) != app.pid:
        return False
    rect = toolbar[1]
    x, y = rect[0] + 20, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    winutil.msg_click_screen(x, y, app.hwnd)
    menu = poll(lambda: one(topbar_util._enum_menu_windows(app.pid)), 5)
    if menu is None or winutil._window_pid(menu[4]) != app.pid:
        return False
    try:
        hmenu = topbar_util.menu_hmenu(menu[4])
        row = one([item for item in topbar_util.menu_items(hmenu)
                   if item[1].replace("&", "").split("\t", 1)[0].strip().rstrip(".\u2026").lower()
                   == "open project" and not item[2] & 3])
        if row is None:
            return False
        item_id, _ = topbar_util.item_info(hmenu, row[0])
        if not item_id:
            return False
        winutil._send_msg(app.hwnd, 0x0111, item_id, 0)
    finally:
        if winutil.user32.IsWindow(menu[4]):
            winutil._send_msg(menu[4], 0x001F, 0, 0)

    def chooser():
        return one([hwnd for hwnd, pid in winutil.enum_windows()
                    if pid == app.pid and winutil.window_class(hwnd) == "#32770"
                    and winutil.window_title(hwnd).rstrip(":") == "Choose one file (3mf)"])

    result["upload_stage"] = "open_fixture_chooser"
    hwnd = poll(chooser, 12)
    if hwnd is None:
        return False
    edit = export_util.find_edit(hwnd)
    if edit is None or not winutil.user32.IsChild(hwnd, edit):
        return False
    winutil._send_msg(edit, 0x00B1, 0, -1)
    winutil.msg_text(edit, str(fixture))
    if winutil.edit_text(edit, len(str(fixture)) + 1) != str(fixture):
        return False
    winutil._send_msg(hwnd, 0x0111, 1, 0)

    def loaded():
        for owned, pid in winutil.enum_windows():
            if pid == app.pid and winutil.window_title(owned).casefold() == "customized preset":
                winutil.close_window(owned)
        return not winutil.user32.IsWindow(hwnd) and fixture.stem in winutil.window_title(app.hwnd)

    result["upload_stage"] = "load_fixture_project"
    return bool(poll(loaded, 18))


def owned_button(app, hwnd, label):
    from harness import export_util, winutil

    return one([row for row in export_util._children_texts(hwnd)
                if row[0].strip() == label and winutil._window_pid(row[2]) == app.pid
                and winutil.user32.IsWindowVisible(row[2])
                and winutil.user32.IsWindowEnabled(row[2])])


def click_rect(rect):
    from harness import winutil

    x0, y0, x1, y1 = rect
    return winutil.real_click_screen((x0+x1)//2, (y0+y1)//2) == 2


def export_native(app, path, result):
    from harness import export_util, winutil

    result["upload_stage"] = "find_export_button"
    _, button = export_util.find_print_buttons(app.hwnd)
    if (button is None or button[0] != "Export G-code file"
            or not winutil.user32.IsWindowVisible(button[2])
            or not winutil.user32.IsWindowEnabled(button[2])
            or not winutil.force_set_foreground(app.hwnd) or not click_rect(button[1])):
        return False
    result["upload_stage"] = "find_export_dialog"
    dialog = export_util.wait_toplevel(
        app.pid, lambda cls, title, rect: cls == "#32770" and title.startswith("Save G-code file as"),
        timeout_s=12,
    )
    if dialog is None:
        return False
    hwnd = dialog[3]
    edit = export_util.find_edit(hwnd)
    if edit is None or not winutil.user32.IsChild(hwnd, edit) or path.exists():
        return False
    winutil._send_msg(edit, 0x00B1, 0, -1)
    winutil.msg_text(edit, str(path))
    if winutil.edit_text(edit, len(str(path)) + 1) != str(path):
        result["upload_stage"] = "export_path_readback_failed"
        return False
    winutil._send_msg(hwnd, 0x0111, 1, 0)
    result["upload_stage"] = "await_exported_gcode"
    return export_util.wait_file(path, timeout_s=25)


def opens_send_only(hwnd):
    from pywinauto import uia_defines

    from tools.cloud_login_probe import scan

    for kind, _, node in scan(hwnd):
        if kind != 50030:
            continue
        try:
            url = urlsplit(uia_defines.get_elem_interface(node, "Value").CurrentValue)
        except (ValueError, uia_defines.NoPatternInterfaceError):
            continue
        if (url.scheme == "http" and url.netloc == "127.0.0.1:13619"
                and url.path == "/web/flutter_web/index.html"
                and parse_qs(url.query).get("path") == ["5"]):
            return True
    return False


def record_picker_sample(hwnd, row_y, path):
    """Capture the device dropdown inside the verified upload-only dialog."""
    from PIL import Image

    from harness import winutil

    if not opens_send_only(hwnd):
        return
    width, height, pixels = winutil.capture_window(hwnd)
    box = (width // 4, max(0, row_y - 42), width - 12, min(height, row_y + 260))
    image = Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX")
    image.crop(box).save(path)


def record_send_footer(hwnd, row_y, path):
    """Record the controls below the picker for diagnosing a missing Send button."""
    from PIL import Image

    from harness import winutil

    if opens_send_only(hwnd):
        width, height, pixels = winutil.capture_window(hwnd)
        image = Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX")
        image.crop((0, min(row_y + 48, height - 1), width, height)).save(path)


def run_upload(app, fixture, output_dir, result, poll):
    from harness import export_util, launcher, winutil

    result["upload_stage"] = "check_fixed_sut"
    with launcher.default_exe().open("rb") as binary:
        if hashlib.file_digest(binary, "sha256").hexdigest() != (
            "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf"
        ):
            return False

    result["upload_stage"] = "open_u1_project"
    if not fixture.is_file() or not open_test_project(app, fixture, result, poll):
        return False
    result["upload_stage"] = "prepare_slice_toolbar"
    winutil.user32.ShowWindow(app.hwnd, 3)
    if not winutil.force_set_foreground(app.hwnd):
        return False

    def ready_to_slice():
        _, button = export_util.find_slice_buttons(app.hwnd)
        return button if button and winutil.user32.IsWindowVisible(button[2]) and winutil.user32.IsWindowEnabled(button[2]) else None

    if not poll(ready_to_slice, 4):
        _, lines = visible_lines(app.hwnd)
        prepare = one([(x, y) for text, x, y in lines if y < 85 and x < 230
                       and re.search(r"\bprepare\b", text)])
        if not click_client(app.hwnd, prepare) or not poll(ready_to_slice, 8):
            return False
    result["upload_stage"] = "select_export_mode"
    if not export_util.switch_to_export_mode(app):
        return False
    result["upload_stage"] = "activate_slice"
    slice_button = poll(ready_to_slice, 6)
    if slice_button is None:
        return False
    if not click_rect(slice_button[1]):
        return False

    def sliced():
        _, action = export_util.find_print_buttons(app.hwnd)
        return action and action[0] == "Export G-code file" and winutil.user32.IsWindowEnabled(action[2])

    result["upload_stage"] = "wait_for_slice_result"
    if not poll(sliced, 95):
        return False
    filename = "orcabb" + result["run_id"][:10] + ".gcode"
    gcode = output_dir / filename
    result["upload_stage"] = "export_gcode"
    if not export_native(app, gcode, result):
        return False
    data = gcode.read_bytes()
    if b"; printer_model = Snapmaker U1" not in data or b"G1 " not in data:
        result["upload_stage"] = "u1_gcode_not_verified"
        return False
    result["gcode"] = {"name": filename, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    result["upload_stage"] = "open_native_send_dialog"
    option, _ = export_util.find_print_buttons(app.hwnd)
    if option is None or not click_rect(option[1]):
        return False
    popup = export_util.wait_popup(app.pid, timeout_s=5)
    if popup is None:
        return False
    rows = [row for row in export_util._children_texts(popup[3]) if row[0].strip() == "Print"]
    if len(rows) != 1 or not click_rect(rows[0][1]):
        return False

    def print_choice():
        _, button = export_util.find_print_buttons(app.hwnd)
        return button if button and button[0] == "Print" and winutil.user32.IsWindowEnabled(button[2]) else None

    action = poll(print_choice, 6)
    if action is None or not click_rect(action[1]):
        return False
    dialog = export_util.wait_toplevel(
        app.pid, lambda cls, title, rect: title == "Send G-code to printer host", timeout_s=12)
    if dialog is None:
        return False
    hwnd = dialog[3]
    field = export_util.find_edit(hwnd)
    upload = owned_button(app, hwnd, "Upload")
    if field is None or not winutil.user32.IsChild(hwnd, field) or upload is None:
        return False
    winutil._send_msg(field, 0x00B1, 0, -1)
    winutil.msg_text(field, filename)
    if winutil.edit_text(field, len(filename) + 1) != filename:
        return False
    if not winutil.force_set_foreground(hwnd) or not click_rect(upload[1]):
        return False
    result["upload_stage"] = "check_send_only_page"

    def only_page():
        candidates = [wid for wid, pid in winutil.enum_windows()
                      if pid == app.pid and winutil.window_title(wid) == "Pretreat the uploaded content"]
        candidate = one(candidates)
        return candidate if candidate is not None and opens_send_only(candidate) else None

    only = poll(only_page, 20)
    if only is None:
        return False
    result["send_only_page_verified"] = True
    result["upload_stage"] = "select_u1_in_send_page"
    open_picker = None
    picker_heading = None

    def send_candidate():
        nonlocal open_picker, picker_heading
        width, lines = visible_lines(only)
        choices = [(x, y) for text, x, y in lines if re.search(r"\bu1\b", text)]
        filename_visible = any(filename in text for text, _, _ in lines)
        send = one([(x, y) for text, x, y in lines if re.fullmatch(r"[\W_]*send[\W_]*", text)])
        # The shipped send page renders a static title, then a thumbnail,
        # then the 300 px dropdown on the same horizontal row.
        heading = one([(x, y) for text, x, y in lines if text.strip() == "select printer"])
        placeholder = one([(x, y) for text, x, y in lines if "click to select printer" in text])
        open_picker = placeholder
        if open_picker is None and heading is not None and heading[0] < width // 4:
            open_picker = (width * 57 // 100, heading[1])
        picked = False
        if heading is not None:
            picker_heading = heading[1]
            label_crop = (width // 4 + 164, picker_heading, width // 4 + 240, picker_heading + 34)
            _, label_lines = visible_lines(only, crop=label_crop, psm=7)
            picked = any(text.strip() == "u1" for text, _, _ in label_lines)
        labels = re.compile(r"\b(?:select|choose|refresh|loading|device|printer|send|upload|connect|"
                            r"offline|online|available|unavailable|no|cannot|lan|wan|working|"
                            r"print|u1|cancel|file|network|error|model)\b")
        result["send_view"] = {"recognized_u1_labels": len(choices), "standalone_send_visible": send is not None,
                               "filename_visible": filename_visible, "device_picker_visible": open_picker is not None,
                               "printer_placeholder_visible": placeholder is not None,
                               "u1_selected": picked}
        result["send_view_labels"] = [
            {"labels": labels.findall(text), "x_band": x // 60, "y_band": y // 35}
            for text, x, y in lines if labels.search(text)
        ]
        return send if picked and filename_visible and send is not None and placeholder is None else None

    send = poll(send_candidate, 8)
    if (send is None and not result["send_view"]["u1_selected"] and open_picker is not None
            and opens_send_only(only) and click_client(only, open_picker)):
        picker_y = open_picker[1]

        def list_devices():
            width, _ = visible_lines(only)
            _, lines = visible_lines(
                only, crop=(width // 4 + 154, picker_y + 49, width // 4 + 239, picker_y + 99), psm=6,
            )
            result["u1_picker_labels"] = [
                {"labels": re.findall(r"\bu1\b|\blan mode\b|\badd device\b", text),
                 "x_band": x // 60, "y_band": y // 35}
                for text, x, y in lines if re.search(r"\bu1\b|\blan mode\b|\badd device\b", text)
            ]
            u1 = one([(x, y) for text, x, y in lines if re.search(r"\bu1\b", text)])
            return u1

        choice = poll(list_devices, 18)
        record_picker_sample(only, picker_y, output_dir / "upload-picker.png")
        if choice is not None and click_client(only, choice):
            result["u1_picker_selection_clicked"] = True
            send = poll(send_candidate, 8)
        elif opens_send_only(only) and click_client(only, open_picker):
            # Closing the expanded list lets us observe the selected value.
            send = poll(send_candidate, 5)
    if send is None and picker_heading is not None:
        record_send_footer(only, picker_heading, output_dir / "upload-footer.png")
    if send is None or not opens_send_only(only) or not click_client(only, send):
        return False
    result["upload_submitted"] = True
    result["upload_stage"] = "verify_device_receipt"

    def receipt():
        for current, pid in winutil.enum_windows():
            if pid != app.pid:
                continue
            _, lines = visible_lines(current)
            words = "\n".join(text for text, _, _ in lines)
            if filename in words and re.search(r"\bsent\s+successfully\s+to\s+the\s+device\b", words):
                result["device_upload_receipt"] = "send_success_named_device_file"
                return True
            if re.search(r"\bupload\s+(?:completed|successful)\b", words):
                result["device_upload_receipt"] = "upload_completed_in_send_page"
                return True
            if filename in words and re.search(r"\blocal\s+files\b", words):
                result["device_upload_receipt"] = "unique_filename_in_device_files"
                return True
        return False

    if poll(receipt, 35):
        result["upload_stage"] = "device_upload_confirmed"
        return True
    return False
