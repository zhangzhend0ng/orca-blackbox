"""China region sign-in probe, on win11-test through hv_go only."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json


def poll(read, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = read()
        if result:
            return result
        time.sleep(0.4)
    return None


def scan(hwnd):
    from pywinauto.uia_defines import IUIA

    uia = IUIA().iuia
    walker = uia.RawViewWalker
    stack = [uia.ElementFromHandle(hwnd)]
    nodes = []
    while stack and len(nodes) < 700:
        node = stack.pop()
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


def is_cn_document(nodes):
    from pywinauto import uia_defines

    for kind, _, node in nodes:
        if kind != 50030:
            continue
        try:
            url = urlsplit(uia_defines.get_elem_interface(node, "Value").CurrentValue)
        except (ValueError, uia_defines.NoPatternInterfaceError):
            continue
        if url.scheme == "https" and url.netloc == "id.snapmaker.cn":
            return True
    return False


def inspect(app, result):
    from harness import winutil

    login_names = {"login", "log in", "sign in", "登录", "登陆"}
    result["stage"] = "find_entry"
    names = []

    def entry():
        nonlocal names
        nodes = scan(app.hwnd)
        names = list(dict.fromkeys(name[:80] for kind, name, _ in nodes
                                   if name and kind in (50000, 50002, 50005, 50019, 50020, 50030)))[:85]
        entries = [node for _, name, node in nodes if name.strip().casefold() in login_names]
        return entries[-1] if entries else None

    button = poll(entry, 20)
    if button is None:
        result["signed_out_controls"] = names
        return
    if not invoke(button):
        result["stage"] = "entry_not_invokable"
        return

    result["stage"] = "find_form"
    form = []
    dialog_hwnd = None

    def form_ready():
        nonlocal form, dialog_hwnd
        for hwnd, pid in winutil.enum_windows():
            if pid != app.pid or hwnd == app.hwnd:
                continue
            nodes = scan(hwnd)
            if any(kind == 50030 for kind, _, _ in nodes):
                dialog_hwnd = hwnd
                form = nodes
                if any(kind == 50004 for kind, _, _ in nodes):
                    return True
        return False

    poll(form_ready, 24)
    if dialog_hwnd is None:
        result["stage"] = "login_dialog_unavailable"
        return
    result["cn_document"] = is_cn_document(form)
    result["signed_out_controls"] = [
        {"kind": kind, "name": name[:80], "password": bool(node.CurrentIsPassword)}
        for kind, name, node in form
        if kind in (50000, 50004, 50005, 50020, 50030) and (name or kind == 50004)
    ][:85]
    result["stage"] = "form_inspected"


def run(run_id):
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
    }
    session = None
    try:
        profile.seed_profile(datadir, conf_extra={"app": {"region": "China", "language": "en_US", "default_page": "0"}})
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(private / "webview")
        result["stage"] = "launch"
        session = launcher.launch(datadir=datadir, wait_window_s=55, boot_demote_s=0,
                                  blocker_sweep_s=3, dismiss_wizard=True)
        inspect(session, result)
    except Exception as exc:
        result["error"] = type(exc).__name__
    finally:
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
        result["duration_s"] = round(time.monotonic() - started, 2)
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{32}", args.run_id):
        parser.error("invalid run ID")
    return run(args.run_id)


if __name__ == "__main__":
    raise SystemExit(main())

