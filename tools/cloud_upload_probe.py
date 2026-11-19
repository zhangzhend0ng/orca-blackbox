"""Upload a fresh U1 slice via Orca's separate send-only page."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlsplit

from tools.cloud_device_probe import visible_lines


def one(values):
    return values[0] if len(values) == 1 else None


def button_point(hwnd, label, *, ymax=None):
    _, lines = visible_lines(hwnd)
    return one([(x, y) for text, x, y in lines if text.strip() == label
                and (ymax is None or y < ymax)])


def click_client(hwnd, point):
    from harness import winutil

    return (point is not None and winutil.force_set_foreground(hwnd)
            and winutil.real_click_screen(*winutil.client_to_screen(hwnd, *point)) == 2)


def open_test_project(app, fixture, poll):
    from harness import export_util, winutil
    from harness.mix_dialog_util import _send_keys

    if not click_client(app.hwnd, button_point(app.hwnd, "prepare", ymax=85)):
        return False
    if winutil.user32.GetForegroundWindow() != app.hwnd:
        return False
    _send_keys([(0x11, False), (ord("O"), False), (ord("O"), True), (0x11, True)])

    def chooser():
        return one([hwnd for hwnd, pid in winutil.enum_windows()
                    if pid == app.pid and winutil.window_class(hwnd) == "#32770"
                    and winutil.window_title(hwnd).rstrip(":") == "Choose one file (3mf)"])

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


def run_upload(app, fixture, output_dir, result, poll):
    from harness import export_util, launcher, winutil

    result["upload_stage"] = "check_fixed_sut"
    with launcher.default_exe().open("rb") as binary:
        if hashlib.file_digest(binary, "sha256").hexdigest() != (
            "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf"
        ):
            return False

    result["upload_stage"] = "open_u1_project"
    if not fixture.is_file() or not open_test_project(app, fixture, poll):
        return False
    result["upload_stage"] = "slice_u1_project"
    if not export_util.switch_to_export_mode(app):
        return False
    _, slice_button = export_util.find_slice_buttons(app.hwnd)
    if slice_button is None or not winutil.user32.IsWindowEnabled(slice_button[2]):
        return False
    if not click_rect(slice_button[1]):
        return False

    def sliced():
        _, action = export_util.find_print_buttons(app.hwnd)
        return action and action[0] == "Export G-code file" and winutil.user32.IsWindowEnabled(action[2])

    if not poll(sliced, 95):
        return False
    filename = "orcabb" + result["run_id"][:10] + ".gcode"
    gcode = output_dir / filename
    if not export_util.export_gcode(app, gcode, timeout_s=25):
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

    def send_candidate():
        _, lines = visible_lines(only)
        choices = [text for text, _, _ in lines if re.search(r"\bu1\b", text)]
        filename_visible = any(filename in text for text, _, _ in lines)
        send = one([(x, y) for text, x, y in lines if text.strip() == "send"])
        result["send_view"] = {"recognized_u1_labels": len(choices), "standalone_send_visible": send is not None,
                               "filename_visible": filename_visible}
        return send if len(choices) == 1 and filename_visible and send is not None else None

    send = poll(send_candidate, 12)
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
