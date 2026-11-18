"""Fixed GUI save/reopen operations inside the existing worker and owned Job."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import sys
import time

from .agent_business_ui import BusinessUI, GW_OWNER
from .agent_protocol import ProtocolError, write_json_once

PROJECT_PATH = "projects/0001.3mf"
MAX_PROJECT_BYTES = 16 * 1024 * 1024


class ProjectUI(BusinessUI):
    def __init__(self, artifacts: Path, guard):
        super().__init__(artifacts, guard)
        from . import topbar_util
        self.tb = topbar_util
        self.saved = None
        self.reopened = False

    def _project_path(self):
        path = self.artifacts / PROJECT_PATH
        base = self.artifacts.resolve(strict=True)
        if not path.resolve().is_relative_to(base):
            raise ProtocolError("project_path_escape")
        for candidate in (path, path.parent, self.artifacts):
            if candidate.is_symlink() or (candidate.exists() and
                    getattr(candidate.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ProtocolError("project_path_link")
        return path

    def _snapshot(self):
        path = self._project_path()
        if not path.is_file() or not 8 <= path.stat().st_size <= MAX_PROJECT_BYTES:
            raise ProtocolError("project_file_size")
        with path.open("rb") as stream:
            raw = stream.read(MAX_PROJECT_BYTES + 1)
        if not 8 <= len(raw) <= MAX_PROJECT_BYTES:
            raise ProtocolError("project_file_size")
        if not raw.startswith(b"PK\x03\x04"):
            raise ProtocolError("project_not_3mf")
        return {"path": PROJECT_PATH, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}

    def _save_command(self):
        toolbar = self.tb._topbar(self.app.hwnd)
        if not toolbar or not self.owned(toolbar[2]):
            raise ProtocolError("file_toolbar_missing")
        rect = toolbar[1]
        x, y = rect[0] + 20, (rect[1] + rect[3]) // 2
        self.guard()
        self.wu.user32.SetCursorPos(x, y)  # BBLTopbar checks the real cursor.
        self.wu.msg_click_screen(x, y, self.app.hwnd)  # One menu-opening click.
        menus = self.wait(lambda: self.tb._enum_menu_windows(self.app.pid), 5)
        if len(menus) != 1 or not self.owned(menus[0][4]):
            raise ProtocolError("file_menu_identity")
        menu_hwnd = menus[0][4]
        try:
            hmenu = self.tb.menu_hmenu(menu_hwnd)
            rows = [row for row in self.tb.menu_items(hmenu) if
                row[1].replace("&", "").split("\t", 1)[0].strip().rstrip(".\u2026").lower() == "save project as"]
            if len(rows) != 1 or rows[0][2] & 3:  # MF_GRAYED | MF_DISABLED
                raise ProtocolError("save_project_command_unavailable")
            item_id, _submenu = self.tb.item_info(hmenu, rows[0][0])
            if not item_id:
                raise ProtocolError("save_project_command_unavailable")
            self.guard()
            self.wu._send_msg(self.app.hwnd, 0x0111, item_id, 0)  # bounded WM_COMMAND
        finally:
            # Native popup loops need explicit dismissal, with a timeout.
            if self.owned(menu_hwnd):
                self.wu._send_msg(menu_hwnd, 0x001F, 0, 0)

    def _save_dialog_diagnostic(self, dialog, owned_dialog):
        """First rejected save-dialog census; SUT metadata only, not an oracle."""
        hwnd=dialog[3]
        pid=self.wu._window_pid(hwnd)
        candidate={"hwnd":hwnd,"pid":pid}
        if pid==self.app.pid:
            candidate.update(caption=self.wu.window_title(hwnd)[:128],wait_caption=dialog[1][:128],
                window_class=self.wu.window_class(hwnd)[:128],
                owner_hwnd=self.wu.user32.GetWindow(hwnd,GW_OWNER),
                parent_hwnd=self.wu.user32.GetParent(hwnd),
                root_owner_hwnd=self.wu.user32.GetAncestor(hwnd,3))
        write_json_once(self.artifacts/"project_save_dialog.json",{"schema_version":1,
            "diagnostic_only":True,"oracle_evidence":False,"reason":"project_save_dialog_identity",
            "captured_at_ns":time.time_ns(),"main_hwnd":self.app.hwnd,"app_pid":self.app.pid,
            "owned_dialog":bool(owned_dialog),"candidate":candidate})

    def save_project(self, *, prepared_dialog=None):
        if prepared_dialog is None:
            self.main_input()
        if self.saved is not None:
            raise ProtocolError("project_already_saved")
        path = self._project_path()
        if path.exists():
            raise ProtocolError("project_exists")
        path.parent.mkdir(exist_ok=True)
        self._project_path()
        if prepared_dialog is None:
            self._save_command()
        dialog = self.wait(lambda: self.eu.wait_save_dialog(self.app.pid, timeout_s=.2), 10)
        owned_dialog=self.owned_dialog(dialog[3])
        if (not owned_dialog or dialog[1] not in {"Save file as:", "Save file as"}
                or (prepared_dialog is not None and dialog[3] != prepared_dialog)):
            try:
                self._save_dialog_diagnostic(dialog,owned_dialog)
            except FileExistsError:
                pass  # Preserve the first rejected window instead of replacing evidence.
            except Exception as diagnostic_error:
                print(f"[project_ui] save diagnosis: {type(diagnostic_error).__name__}",file=sys.stderr)
            raise ProtocolError("project_save_dialog_identity")
        edit = self.eu.find_edit(dialog[3])
        if (not edit or not self.owned(edit) or self.wu.window_class(edit) != "Edit"
                or not self.wu.user32.IsChild(dialog[3], edit)):
            raise ProtocolError("project_save_edit_identity")
        self.guard()
        self.wu._send_msg(edit, 0x00B1, 0, -1)
        self.guard()
        self.wu.msg_text(edit, str(path))
        self.guard()
        if path.exists():
            raise ProtocolError("project_exists")
        self.wu._send_msg(dialog[3], 0x0111, 1, 0)
        last, since = [None], [None]
        def stable():
            self._project_path()
            if not path.is_file() or self.wu.user32.IsWindow(dialog[3]):
                return False
            info = path.stat()
            if not 8 <= info.st_size <= MAX_PROJECT_BYTES:
                raise ProtocolError("project_file_size")
            value = info.st_size, info.st_mtime_ns
            if value != last[0]:
                since[0] = time.monotonic()
            settled = value == last[0] and time.monotonic() - since[0] >= 1
            last[0] = value
            return settled
        self.wait(stable, 60)
        self.saved = self._snapshot()
        return {"dialog_hwnd": dialog[3], "edit_hwnd": edit, **self.saved}

    def reopen_project(self):
        self.main_input()
        if self.saved is None or self.reopened:
            raise ProtocolError("project_reopen_state")
        profile = self.artifacts / "profile_reopen"
        if profile.exists() or profile.is_symlink():
            raise ProtocolError("reopen_profile_exists")
        if self._snapshot() != self.saved:
            raise ProtocolError("saved_project_changed")
        old = self.app
        self.close()  # Graceful WM_CLOSE; never kills an app or the Job.
        code = old.popen.poll()
        if type(code) is not int or code != 0:
            raise ProtocolError("old_process_not_naturally_closed")
        closed_ns = time.time_ns()
        self.guard()
        if self._snapshot() != self.saved:
            raise ProtocolError("saved_project_changed")
        from .agent_guest import _WindowsUI
        started_ns = time.time_ns()
        # The worker remains in its owned no-breakaway Job. launcher.Popen
        # inherits that Job; no second runtime or deadline is introduced.
        base = _WindowsUI(self.artifacts, model=self._project_path(), profile_name="profile_reopen")
        self.base, self.app, self.wu = base, base.app, base.winutil
        self._close_requested = False
        self.pause(12)
        self.wu.user32.ShowWindow(self.app.hwnd, 3)
        self.pause(1)
        quality = self.wait(lambda: self.named_child("Quality"), 60)
        self.click_rect(quality[1])
        self.pause(3)
        window, _capture = self.identity()
        self.reopened = True
        return {**self.saved, "datadir": "profile_reopen", "old_pid": old.pid, "old_hwnd": old.hwnd,
            "old_exit_code": code, "old_closed_at_ns": closed_ns, "new_pid": window["pid"],
            "new_hwnd": window["hwnd"], "new_started_at_ns": started_ns, "driver_pid": os.getpid()}

    def perform(self, method, arguments):
        self.guard()
        if method in {"save_project", "reopen_project"}:
            if arguments:
                raise ProtocolError("project_tools_take_no_arguments")
            return self.save_project() if method == "save_project" else self.reopen_project()
        return super().perform(method, arguments)
