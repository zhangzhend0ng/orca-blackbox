"""China region sign-in probe, on win11-test through hv_go only."""
from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def poll(read, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = read()
        if result:
            return result
        time.sleep(0.4)
    return None


def scan(hwnd=None, *, root=None):
    from pywinauto.uia_defines import IUIA

    uia = IUIA().iuia
    walker = uia.RawViewWalker
    stack = [root if root is not None else uia.ElementFromHandle(hwnd)]
    nodes = []
    visited = 0
    while stack and visited < 700:
        node = stack.pop()
        visited += 1
        try:
            kind = node.CurrentControlType
            if not node.CurrentIsOffscreen:
                nodes.append((kind, node.CurrentName or "", node))
            child = walker.GetFirstChildElement(node)
            children = []
            while child and len(children) < 230:
                children.append(child)
                child = walker.GetNextSiblingElement(child)
            stack.extend(reversed(children))
        except Exception:
            continue
    return nodes


def invoke(node):
    from pywinauto import uia_defines

    for pattern, method in (("Invoke", "Invoke"),
                            ("LegacyIAccessible", "DoDefaultAction")):
        try:
            action = uia_defines.get_elem_interface(node, pattern)
        except uia_defines.NoPatternInterfaceError:
            continue
        getattr(action, method)()
        return True
    return False


def cn_document(nodes):
    from pywinauto import uia_defines

    for kind, _, node in nodes:
        if kind != 50030:
            continue
        try:
            url = urlsplit(uia_defines.get_elem_interface(node, "Value").CurrentValue)
        except (ValueError, uia_defines.NoPatternInterfaceError):
            continue
        if url.scheme == "https" and url.netloc == "id.snapmaker.cn":
            return node
    return None


class Credential(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32), ("kind", ctypes.c_uint32),
        ("target", ctypes.c_void_p), ("comment", ctypes.c_void_p),
        ("written", ctypes.c_uint32 * 2), ("size", ctypes.c_uint32),
        ("blob", ctypes.c_void_p), ("persist", ctypes.c_uint32),
        ("attribute_count", ctypes.c_uint32), ("attributes", ctypes.c_void_p),
        ("alias", ctypes.c_void_p), ("user", ctypes.c_void_p),
    ]


def read_login():
    vault = ctypes.WinDLL("Advapi32", use_last_error=True)
    pointer = ctypes.POINTER(Credential)()
    vault.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                ctypes.POINTER(type(pointer))]
    vault.CredFree.argtypes = [ctypes.c_void_p]
    vault.CredFree.restype = None
    if not vault.CredReadW("snapmaker-login", 1, 0, ctypes.byref(pointer)):
        raise RuntimeError("credential_unavailable")
    try:
        entry = pointer.contents
        if not entry.user or not entry.blob or not entry.size or entry.size % 2:
            raise RuntimeError("credential_invalid")
        account = ctypes.wstring_at(entry.user)
        password = ctypes.string_at(entry.blob, entry.size).decode("utf-16-le").removesuffix("\0")
        return account, password
    finally:
        vault.CredFree(pointer)


def unique(nodes, kind, label, *, password=False):
    matches = [node for node_kind, name, node in nodes
               if node_kind == kind and name == label
               and bool(node.CurrentIsPassword) == password]
    return matches[0] if len(matches) == 1 else None


def enter_secret(hwnd, node, value):
    from pywinauto.uia_defines import IUIA

    from harness import winutil
    from harness.mix_dialog_util import _send_chars

    if not winutil.force_set_foreground(hwnd):
        return False
    rect = node.CurrentBoundingRectangle
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return False
    if winutil.real_click_screen((rect.left + rect.right) // 2,
                                 (rect.top + rect.bottom) // 2) != 2:
        return False
    uia = IUIA().iuia
    if not poll(lambda: uia.CompareElements(uia.GetFocusedElement(), node), 2):
        return False
    if winutil.user32.GetForegroundWindow() != hwnd:
        return False
    # Windows SendInput expects UTF-16 code units.
    units = value.encode("utf-16-le")
    _send_chars("".join(chr(units[i] + 256 * units[i + 1]) for i in range(0, len(units), 2)))
    return True


def observe_home_sidebar(hwnd):
    """Record only the known sidebar labels from an in-memory observation."""
    from PIL import Image

    from harness import ocr_util, winutil

    width, height, pixels = winutil.capture_window(hwnd)
    picture = Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX").crop(
        (0, 0, width // 3, height // 2))
    payload = io.BytesIO()
    picture.resize((picture.width * 2, picture.height * 2)).save(payload, format="PNG")
    text = subprocess.run([ocr_util.TESSERACT_EXE, "stdin", "stdout", "-l", "eng", "--psm", "11"],
                          input=payload.getvalue(), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=True, timeout=8).stdout.decode("utf-8")
    return {
        "home_login_button_visible": bool(re.search(r"\blogin[ \t]*/[ \t]*register\b", text, re.I)),
        "home_devices_entry_visible": bool(re.search(r"\bmy[ \t]+devices\b", text, re.I)),
        "home_library_entry_visible": bool(re.search(r"\bmodel[ \t]+library\b", text, re.I)),
    }


def confirm_home_entry(hwnd, result, *, visible):
    evidence_key = "home_before" if visible else "home_after"
    expected_samples = 1 if visible else 2
    matches = 0

    def read():
        nonlocal matches
        sample = observe_home_sidebar(hwnd)
        result[evidence_key] = sample
        ready = sample["home_devices_entry_visible"] and sample["home_library_entry_visible"]
        if ready and sample["home_login_button_visible"] == visible:
            matches += 1
        else:
            matches = 0
        result[evidence_key + "_matching_samples"] = matches
        return matches >= expected_samples

    return bool(poll(read, 10))


def authenticate(app, hwnd, result):
    from pywinauto import uia_defines

    from harness import winutil

    def form():
        root = cn_document(scan(hwnd))
        return scan(root=root) if root is not None else []

    nodes = form()
    user = unique(nodes, 50004, "请输入手机号")
    password = unique(nodes, 50004, "请输入密码", password=True)
    terms = unique(nodes, 50002, "")
    if any(node is None for node in (user, password, terms)):
        result["stage"] = "password_form_controls_unconfirmed"
        return

    result["stage"] = "read_guest_credential"
    username, secret = read_login()
    phone = re.fullmatch(r"(?:\+86[ -]?)?(1[0-9]{10})", username.strip())
    if phone is None:
        result["stage"] = "china_form_requires_mobile_number"
        return

    result["stage"] = "confirm_login_terms"
    toggle = uia_defines.get_elem_interface(terms, "Toggle")
    if toggle.CurrentToggleState == 0:
        toggle.Toggle()
    if not poll(lambda: toggle.CurrentToggleState == 1, 3):
        return

    result["stage"] = "enter_account"
    value = uia_defines.get_elem_interface(user, "Value")
    if value.CurrentValue or not enter_secret(hwnd, user, phone[1]):
        return
    if not poll(lambda: value.CurrentValue == phone[1], 3):
        if value.CurrentValue or not enter_secret(hwnd, user, phone[1]):
            result["stage"] = "account_readback_failed"
            return
        if not poll(lambda: value.CurrentValue == phone[1], 3):
            result["stage"] = "account_readback_failed"
            return
    result["stage"] = "enter_masked_password"
    password = unique(form(), 50004, "请输入密码", password=True)
    if password is None or not enter_secret(hwnd, password, secret):
        return
    del secret, username, phone

    def enabled_submit():
        control = unique(form(), 50000, "登录")
        return control if control is not None and control.CurrentIsEnabled else None

    result["stage"] = "submit_disabled"
    submit = poll(enabled_submit, 4)
    if submit is None:
        return
    result["stage"] = "submit_password_login"
    if not invoke(submit):
        return
    result["submitted"] = True
    result["stage"] = "wait_for_orca_callback"
    if not poll(lambda: not any(h == hwnd for h, _ in winutil.enum_windows()), 24):
        result["challenge_or_rejection_visible"] = True
        return

    result["stage"] = "verify_home_account_state"
    result["login_dialog_closed"] = True
    if confirm_home_entry(app.hwnd, result, visible=False):
        result["home_proof"] = "login_entry_removed_on_ready_home"
        result["home_signed_in"] = True
        result["stage"] = "home_signed_in"


def home_login_point(hwnd):
    import numpy as np

    from harness import winutil
    from harness.mix_dialog_util import ocr_words_img

    width, height, pixels = winutil.capture_window(hwnd)
    bgr = np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 4)
    sidebar = bgr[:height // 3, :width // 4, :3].copy()
    matches = [(x + w // 2, y + h // 2)
               for label, x, y, w, h in ocr_words_img(sidebar, scale=3, psm=11)
               if label.casefold() == "login/register"]
    return matches[0] if len(matches) == 1 else None


def inspect(app, result, run_dir, authenticate_login, hide_sign_in=None):
    from harness import winutil

    login_names = {"login/register", "登录/注册"}
    result["stage"] = "find_entry"
    names = []
    semantics_enabled = False

    def entry():
        nonlocal names, semantics_enabled
        nodes = scan(app.hwnd)
        names = list(dict.fromkeys(name[:80] for kind, name, _ in nodes
                                   if name and kind in (50000, 50002, 50005, 50019, 50020, 50030)))[:85]
        entries = [node for _, name, node in nodes if name.strip().casefold() in login_names]
        if len(entries) == 1:
            return entries[0]
        if not semantics_enabled:
            for _, name, node in nodes:
                if name == "Enable accessibility":
                    semantics_enabled = invoke(node)
                    result["flutter_semantics_enabled"] = semantics_enabled
                    break
        return None

    button = poll(entry, 5)
    if not confirm_home_entry(app.hwnd, result, visible=True) and authenticate_login:
        result["stage"] = "signed_out_home_unconfirmed"
        return
    point = None
    if button is not None and invoke(button):
        result["home_entry"] = "uia"
    else:
        point = poll(lambda: home_login_point(app.hwnd), 25)
        if point is None:
            if authenticate_login:
                return
            result["signed_out_controls"] = names
            # Discovery only. No credential is read or entered in this probe.
            from PIL import Image

            width, height, pixels = winutil.capture_window(app.hwnd)
            Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX").save(
                run_dir / "signed_out.png")
            return
        if not winutil.force_set_foreground(app.hwnd):
            result["stage"] = "home_foreground_unavailable"
            return
        x, y = winutil.client_to_screen(app.hwnd, *point)
        if winutil.real_click_screen(x, y) != 2:
            result["stage"] = "home_click_incomplete"
            return
        result["home_entry"] = "signed_out_ocr"

    result["stage"] = "find_form"
    form = []
    dialog_hwnd = None
    wizard_dismissed = set()

    def form_ready():
        nonlocal form, dialog_hwnd
        for hwnd, pid in winutil.enum_windows():
            if pid != app.pid or hwnd == app.hwnd:
                continue
            if winutil.window_title(hwnd).casefold() == "setup wizard":
                if hwnd not in wizard_dismissed:
                    wizard_dismissed.add(hwnd)
                    winutil.close_window(hwnd)
                    if poll(lambda: not winutil.user32.IsWindowVisible(hwnd), 3):
                        retry = home_login_point(app.hwnd)
                        if retry and winutil.force_set_foreground(app.hwnd):
                            winutil.real_click_screen(*winutil.client_to_screen(app.hwnd, *retry))
                            result["late_setup_wizard_dismissed"] = True
                return False
            nodes = scan(hwnd)
            if any(kind == 50030 for kind, _, _ in nodes):
                dialog_hwnd = hwnd
                form = nodes
                if cn_document(nodes) is not None and any(kind == 50004 for kind, _, _ in nodes):
                    return True
            elif nodes and not authenticate_login:
                result["pre_auth_dialog_controls"] = list(dict.fromkeys(
                    name[:80] for _, name, _ in nodes if name))[:25]
        return False

    poll(form_ready, 32)
    if dialog_hwnd is None:
        result["stage"] = "login_dialog_unavailable"
        return
    document = cn_document(form)
    result["cn_document"] = document is not None
    if not result["cn_document"]:
        result["stage"] = "login_origin_unconfirmed"
        return

    password_tabs = [node for kind, name, node in scan(root=document)
                     if kind == 50000 and name == "密码登录"]
    if len(password_tabs) == 1 and invoke(password_tabs[0]):
        def password_form():
            nodes = scan(dialog_hwnd)
            if cn_document(nodes) is not None and any(kind == 50004 and node.CurrentIsPassword
                                                      for kind, _, node in nodes):
                return nodes
            return None

        form = poll(password_form, 8) or form
    if authenticate_login:
        if hide_sign_in is not None:
            hide_sign_in()
        authenticate(app, dialog_hwnd, result)
        return
    result["signed_out_controls"] = [
        {"kind": kind, "name": name[:80], "password": bool(node.CurrentIsPassword),
         "enabled": bool(node.CurrentIsEnabled)}
        for kind, name, node in form
        if kind in (50000, 50002, 50004, 50005, 50020, 50030) and (name or kind in (50002, 50004))
    ][:85]
    result["stage"] = "form_inspected"


def run(run_id, authenticate_login, discover_devices=False, upload_gcode=False,
        video_review=False, video_live=False, print_new_project=False):
    from harness import host_guard, launcher, profile

    host_guard.assert_guest_or_allow()
    if os.environ.get("USERNAME", "").casefold() != "test":
        raise RuntimeError("wrong_interactive_user")

    started = time.monotonic()
    run_dir = ROOT / "artifacts" / "cloud_login_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    private = run_dir / "private"
    datadir = private / "orca"
    result = {
        "run_id": run_id, "region": "CN", "verdict": "NON_GREEN",
        "stage": "seed_profile", "private_removed": False,
        "mode": ("print_live_video" if print_new_project else "upload_live_video" if video_live
                 else "upload_review" if video_review
                 else "upload" if upload_gcode else "devices" if discover_devices
                 else "authenticate" if authenticate_login else "inspect"),
    }
    session = None
    video = None
    live = None
    try:
        settings = {"app": {"region": "China", "language": "en_US", "default_page": "0"}}
        if print_new_project:
            settings["models"] = [{"vendor": "Snapmaker", "model": "SM_U1", "nozzle_diameter": "0.4"}]
            settings["presets"] = {"machine": "Snapmaker U1 (0.4 nozzle)"}
            settings["filaments"] = {"Snapmaker PLA Basic @U1": "true"}
        profile.seed_profile(datadir, conf_extra=settings)
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(private / "webview")
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--force-renderer-accessibility"
        result["stage"] = "launch"
        session = launcher.launch(datadir=datadir, wait_window_s=55, boot_demote_s=0,
                                  blocker_sweep_s=8 if print_new_project else 3, dismiss_wizard=True)
        if video_live:
            from ctypes.wintypes import HWND

            from harness import winutil
            from harness.native_desktop_video import DesktopVideo
            from tools.cloud_upload_video import LiveDesktopCapture

            console_window = ctypes.windll.kernel32.GetConsoleWindow
            console_window.restype = HWND
            console = console_window()
            if console:
                winutil.user32.ShowWindow(console, 0)
            winutil.user32.ShowWindow(session.hwnd, 3)
            if not winutil.force_set_foreground(session.hwnd):
                raise RuntimeError("upload_video_foreground")
            live = LiveDesktopCapture(session, result)
            video = DesktopVideo(run_dir, capture=live.frame, fps=10, size=live.size)
            video.start()
        inspect(session, result, run_dir, authenticate_login,
                hide_sign_in=live.hide_sign_in if live is not None and not print_new_project else None)
        if discover_devices and result.get("home_signed_in"):
            from tools.cloud_device_probe import inspect_devices

            if video_review:
                from harness.native_desktop_video import DesktopVideo
                from tools.cloud_upload_video import capture

                video = DesktopVideo(run_dir, capture=lambda: capture(session, result))
                video.start()
            if live is not None:
                live.show_signed_in()
                result["signed_in_at_ns"] = time.time_ns()
            if print_new_project:
                from tools.cloud_print_probe import select_idle_device

                select_idle_device(session, result, poll)
            else:
                result["device_page_observed"] = inspect_devices(session, result, poll)
            if upload_gcode and print_new_project:
                from tools.cloud_upload_probe import run_upload

                outcome = run_upload(session, None, run_dir, result, poll, print_project=True)
                result["print_started"] = outcome
                if outcome:
                    time.sleep(4)
            elif upload_gcode:
                result["upload_stage"] = "await_u1_device_panel"
                panel_observed = result.get("device_stage") in {
                    "u1_device_panel_observed", "device_files_opened", "u1_device_files_observed"
                }
                control = result.get("device_control", {})
                recorded_panel = (
                    (video_review or video_live) and result.get("device_stage") == "device_control_opened"
                    and control.get("temperature") and not control.get("still_on_home") and not control.get("offline")
                )
                if panel_observed or recorded_panel:
                    from tools.cloud_upload_probe import run_upload

                    outcome = run_upload(
                        session, ROOT / "fixtures" / "agent_layer_cube.3mf", run_dir, result, poll,
                        review_only=video_review,
                    )
                    outcome_key = "review_ready" if video_review else "device_upload_confirmed"
                    result[outcome_key] = outcome
                    if video_live and outcome:
                        time.sleep(3)
    except Exception as exc:
        result["error"] = type(exc).__name__
    finally:
        if video is not None:
            try:
                result["video"] = video.finish()
                if live is not None:
                    result["video"]["privacy_frames"] = live.privacy_frames
                    result["video"]["foreground_console_frames"] = live.foreground_console_frames
            except Exception as exc:
                result["video_error"] = type(exc).__name__
        try:
            if session is not None:
                session.close(timeout_s=4)
                session.popen.wait(timeout=8)
            def remove_private():
                try:
                    shutil.rmtree(private)
                except FileNotFoundError:
                    pass
                except PermissionError:
                    return False
                return True

            result["private_removed"] = bool(poll(remove_private, 12))
        except Exception as exc:
            result["cleanup_error"] = type(exc).__name__
        goal_observed = result.get("device_page_observed") if discover_devices else result.get("home_signed_in")
        if upload_gcode:
            goal_observed = (result.get("review_ready") and result.get("video") if video_review
                             else result.get("device_upload_confirmed"))
        if video_live:
            goal_observed = goal_observed and result.get("video")
        if print_new_project:
            goal_observed = result.get("print_started") and result.get("video")
        if goal_observed and result["private_removed"]:
            result["verdict"] = "SHADOW"
        result["duration_s"] = round(time.monotonic() - started, 2)
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0 if result["verdict"] == "SHADOW" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--authenticate", action="store_true")
    parser.add_argument("--discover-devices", action="store_true")
    parser.add_argument("--upload-gcode", action="store_true")
    video_args = parser.add_mutually_exclusive_group()
    video_args.add_argument("--record-upload-review", action="store_true")
    video_args.add_argument("--record-upload-live", action="store_true")
    parser.add_argument("--print-new-project", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{32}", args.run_id):
        parser.error("invalid run ID")
    if args.discover_devices and not args.authenticate:
        parser.error("--discover-devices requires --authenticate")
    if args.upload_gcode and not args.discover_devices:
        parser.error("--upload-gcode requires --discover-devices")
    if (args.record_upload_review or args.record_upload_live) and not args.upload_gcode:
        parser.error("upload video options require --upload-gcode")
    if args.print_new_project and not args.record_upload_live:
        parser.error("--print-new-project requires --record-upload-live")
    return run(args.run_id, args.authenticate, args.discover_devices, args.upload_gcode,
               args.record_upload_review, args.record_upload_live, args.print_new_project)


if __name__ == "__main__":
    raise SystemExit(main())

