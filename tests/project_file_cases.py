"""File menu and on-disk write observations shared by the project cases."""

import hashlib
import time
from zipfile import BadZipFile, ZipFile

from harness import export_util, topbar_util, winutil


def project_title(session):
    title = winutil.window_title(session.hwnd).strip()
    return title.partition(" - ")[0].removeprefix("*").strip()


def digest_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _command_label(label):
    return label.partition("\t")[0].replace("&", "").rstrip(". …").casefold()


def dispatch_file_command(session, exact_label):
    menu = topbar_util.open_file_menu(session)
    if not menu:
        print("[project file] File menu did not open")
        return False
    _, _, hmenu = menu
    try:
        rows = topbar_util.menu_items(hmenu)
        matches = [(i, name) for i, name, flags in rows
                   if _command_label(name) == _command_label(exact_label) and not flags & 0x0003]
        if len(matches) != 1:
            print(f"[project file] expected one enabled {exact_label!r}, got {matches!r} in {rows!r}")
            return False
        index, name = matches[0]
        print(f"[project file] File > {name!r}")
        return topbar_util.activate_menu_item(session, hmenu, index)
    finally:
        topbar_util.close_menu_windows(session.pid)


def wait_project_write(session, path, previous_digest, timeout_s=18):
    """Observe a different, valid archive at the exact existing project path."""
    deadline = time.monotonic() + timeout_s
    while session.alive() and time.monotonic() < deadline:
        dialog = export_util.wait_toplevel(
            session.pid, lambda cls, _title, _rect: cls == "#32770", timeout_s=0.1)
        if dialog or not winutil.user32.IsWindowEnabled(session.hwnd):
            print(f"[project file] save blocked by an unexpected dialog: {dialog!r}")
            return None
        try:
            current = digest_file(path)
            if current != previous_digest:
                with ZipFile(path) as archive:
                    if "3D/3dmodel.model" in archive.namelist() and archive.testzip() is None:
                        if digest_file(path) == current:
                            print(f"[project file] {path} sha256 {previous_digest} -> {current}")
                            return current
        except (OSError, BadZipFile):
            pass  # Saving can still be replacing the archive.
        time.sleep(0.3)
    print(f"[project file] no valid rewritten archive at {path}")
    return None
