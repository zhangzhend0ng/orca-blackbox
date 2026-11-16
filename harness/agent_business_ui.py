"""Fixed GUI operations for the layer-height shadow case; no model or OCR."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sys
import time

from .agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256, ProtocolError, write_json_once

GW_OWNER = 4  # winuser.h: 2 is GW_HWNDNEXT (Z order), not window ownership.


def _discard_choice(caption, children, *, close_requested=False):
    labels = [text.replace("&", "").strip() for text, _rect, _child in children if text.strip()]
    # Plater::close_with_confirm uses this exact HTML-backed query. Its
    # message body is not exposed by GetWindowText, so require the observed
    # structure as well as the owner's shutdown state instead of any "No".
    html_save = (close_requested and caption.strip() == "Snapmaker Orca - Save"
        and all(labels.count(label) == 1 for label in ("Yes", "No", "Cancel", "htmlWindow"))
        and set(labels) <= {"Yes", "No", "Cancel", "htmlWindow", "Remember my choice."})
    save_question = (re.fullmatch(r"Snapmaker Orca(?: [0-9][0-9A-Za-z.+_-]{0,40})?", caption.strip()) is not None and
                     any("save changes" in text.lower() for text, _rect, _child in children)) or html_save
    choices = [child for child in children if child[0].replace("&", "").strip() in
               {"Don't save", "Don't Save", "Discard"} or
               (save_question and child[0].replace("&", "").strip() == "No")]
    return choices[0] if len(choices) == 1 else None


class BusinessUI:
    def __init__(self, artifacts: Path, guard):
        # GUI imports are deliberately lazy: importing this module is harmless.
        from .agent_guest import REPO, _WindowsUI, _bytes_once
        from . import export_util
        self.artifacts, self.guard, self.eu = artifacts, guard, export_util
        self.exports, self.base = 0, None
        raw = (REPO / LAYER_FIXTURE).read_bytes()
        if hashlib.sha256(raw).hexdigest() != LAYER_FIXTURE_SHA256:
            raise ProtocolError("fixture_digest")
        (artifacts / "input").mkdir()
        fixture = artifacts / "input/fixture.3mf"
        _bytes_once(fixture, raw)
        try:
            self.base = _WindowsUI(artifacts, model=fixture)
            self.wu, self.app = self.base.winutil, self.base.app
            import ctypes
            self.wu.user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            self.wu.user32.GetWindow.restype = ctypes.c_void_p
            self.wu.user32.GetParent.argtypes = [ctypes.c_void_p]
            self.wu.user32.GetParent.restype = ctypes.c_void_p
            self.wu.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            self.wu.user32.GetAncestor.restype = ctypes.c_void_p
            self.wu.user32.IsChild.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.wu.user32.IsChild.restype = ctypes.c_int
            self.pause(12)  # CLI fixture load must remain hands-off.
            self.wu.user32.ShowWindow(self.app.hwnd, 3)
            self.pause(1)
            # Trusted setup exposes the Quality page; the model chooses its Edit.
            quality = self.wait(lambda: self.named_child("Quality"), 60)
            self.click_rect(quality[1])
            self.pause(3)
            self.boot_details = {"fixture_path": "input/fixture.3mf",
                "fixture_sha256": LAYER_FIXTURE_SHA256, "datadir": "profile", "driver_pid": os.getpid()}
        except BaseException:
            if self.base is not None:
                try:
                    self.close()
                except Exception as cleanup_error:
                    print(f"[business_ui] setup cleanup: {type(cleanup_error).__name__}", file=sys.stderr)
            raise

    def pause(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.guard()
            time.sleep(max(0, min(0.1, end - time.monotonic())))
        self.guard()

    def wait(self, predicate, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.guard()
            value = predicate()
            if value:
                return value
            self.pause(0.1)
        raise ProtocolError("gui_wait_timeout")

    def identity(self):
        return self.base.identity()

    def click(self, x, y):
        self.main_input()
        self.base.click(x, y)

    def main_input(self):
        self.guard()
        result = self.identity()
        if not self.wu.user32.IsWindowEnabled(self.app.hwnd):
            raise ProtocolError("main_window_modal_blocked")
        return result

    def owned(self, hwnd):
        return (self.wu.user32.IsWindow(hwnd) and self.wu.user32.IsWindowVisible(hwnd)
                and self.wu._window_pid(hwnd) == self.app.pid)

    def named_child(self, name):
        found = [child for child in self.eu._children_texts(self.app.hwnd)
                 if child[0].strip() == name and self.owned(child[2])]
        if len(found) > 1:
            raise ProtocolError("ambiguous_control")
        return found[0] if found else None

    def click_rect(self, rect, *, root=True, owner=None):
        self.guard()
        self.main_input() if root else self.identity()
        target_root = self.app.hwnd if root else owner
        if not target_root or not self.owned(target_root):
            raise ProtocolError("click_target_not_owned")
        self.wu.msg_click_screen((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2,
                                 target_root)

    def edit(self, x, y, text):
        window, _ = self.main_input()
        if not 0 <= x < window["width"] or not 0 <= y < window["height"]:
            raise ProtocolError("edit_outside_client")
        sx, sy = self.wu.client_to_screen(self.app.hwnd, x, y)
        target = self.wu.deepest_child_at(self.app.hwnd, sx, sy)
        if (not self.owned(target) or self.wu.window_class(target) != "Edit"
                or not self.wu.user32.IsChild(self.app.hwnd, target)
                or not self.wu.user32.IsWindowEnabled(target)):
            raise ProtocolError("edit_target_not_owned_edit")
        before = self.wu.edit_text(target)
        self.guard()
        self.wu.msg_click_screen(sx, sy, self.app.hwnd)
        self.guard()
        self.wu._send_msg(target, 0x00B1, 0, -1)  # native Edit EM_SETSEL, not config mutation
        self.guard()
        self.wu.msg_text(target, text)
        self.guard()
        self.wu.msg_text(target, "\r")  # real wx text-enter path, not WM_SETTEXT
        self.guard()
        # Leaving focus commits the GUI field. Never patch slicer configuration.
        self.wu._send_msg(target, 0x0008, 0, 0)
        self.pause(6)  # parameter rebuild is asynchronous (PITFALLS m5b).
        if not self.owned(target):
            raise ProtocolError("edit_target_disappeared")
        return {"target_hwnd": target, "control_class": "Edit", "before_text": before,
                "after_text": self.wu.edit_text(target)}

    def export_mode(self):
        option, main = self.eu.find_print_buttons(self.app.hwnd)
        if main and "Export G-code file" in main[0]:
            return main
        if not option or not self.owned(option[2]):
            raise ProtocolError("export_dropdown_missing")
        self.click_rect(option[1])
        def popup():
            # Zero-duration legacy waits do not poll; bounded 0.2s still
            # allows our cancellation/deadline checks between polls.
            return self.eu.wait_popup(self.app.pid, timeout_s=0.2)
        panel = self.wait(popup, 5)
        rows = [r for r in self.eu._children_texts(panel[3])
                if r[0].strip() == "Export G-code file" and self.owned(r[2])]
        if len(rows) != 1:
            raise ProtocolError("export_row_missing")
        self.click_rect(rows[0][1], root=False, owner=panel[3])
        def selected():
            _, main = self.eu.find_print_buttons(self.app.hwnd)
            return main if main and "Export G-code file" in main[0] else None
        return self.wait(selected, 5)

    def slice(self):
        self.main_input()
        self.export_mode()
        _, button = self.eu.find_slice_buttons(self.app.hwnd)
        if not button or not self.owned(button[2]) or not self.wu.user32.IsWindowEnabled(button[2]):
            raise ProtocolError("slice_button_unavailable")
        self.click_rect(button[1])  # One click only: re-clicking can cancel slicing.
        self.pause(0.5)
        def done():
            _, main = self.eu.find_print_buttons(self.app.hwnd)
            return bool(main and "Export G-code file" in main[0] and self.owned(main[2])
                        and self.wu.user32.IsWindowEnabled(main[2]))
        self.wait(done, 180)
        return {"button_hwnd": button[2], "done_observed": True}

    def export_gcode(self):
        self.main_input()
        main = self.export_mode()
        if not self.owned(main[2]) or not self.wu.user32.IsWindowEnabled(main[2]):
            raise ProtocolError("export_not_ready")
        relative = f"exports/{self.exports + 1:04d}.gcode"
        output = self.artifacts / relative
        output.parent.mkdir(exist_ok=True)
        if output.exists():
            raise ProtocolError("export_exists")
        self.click_rect(main[1])  # no fallback/re-click and no coordinate re-conversion
        dialog = self.wait(lambda: self.eu.wait_save_dialog(self.app.pid, timeout_s=0.2), 15)
        if not self.owned(dialog[3]) or not dialog[1].startswith("Save G-code file as"):
            raise ProtocolError("save_dialog_not_owned")
        edit = self.eu.find_edit(dialog[3])
        if not edit or not self.owned(edit) or not self.wu.user32.IsChild(dialog[3], edit):
            raise ProtocolError("save_edit_not_owned")
        self.guard()
        self.wu._send_msg(edit, 0x00B1, 0, -1)
        self.guard()
        self.wu.msg_text(edit, str(output))
        self.guard()
        if output.exists():
            raise ProtocolError("export_exists")
        self.wu._send_msg(dialog[3], 0x0111, 1, 0)  # owned save-dialog IDOK
        last, same_since = [None], [None]
        def stable():
            if not output.is_file():
                return False
            stat = output.stat()
            if not 0 < stat.st_size <= 64 * 1024 * 1024:
                raise ProtocolError("export_size")
            value = stat.st_size, stat.st_mtime_ns
            if value != last[0]:
                same_since[0] = time.monotonic()
            settled = (value == last[0] and same_since[0] is not None
                       and time.monotonic() - same_since[0] >= 1)
            last[0] = value
            return settled
        self.wait(stable, 60)
        raw = output.read_bytes()
        self.exports += 1
        return {"dialog_hwnd": dialog[3], "edit_hwnd": edit, "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}

    def perform(self, method, arguments):
        self.guard()
        if method == "edit":
            return self.edit(**arguments)
        if method == "slice":
            return self.slice()
        if method == "export_gcode":
            return self.export_gcode()
        raise ProtocolError("unknown_business_tool")

    def owned_dialog(self, hwnd):
        if not self.owned(hwnd) or self.wu.window_class(hwnd) != "#32770":
            return False
        seen = set()
        owner = self.wu.user32.GetWindow(hwnd, GW_OWNER)
        for _ in range(8):
            if owner == self.app.hwnd:
                return True
            if not owner or owner in seen or self.wu._window_pid(owner) != self.app.pid:
                return False
            # Plater::close_with_confirm parents its query to Plater, a
            # MainFrame descendant. A child HWND is a direct, verifiable
            # association; sharing a hidden owner with MainFrame is not.
            if self.wu.user32.IsChild(self.app.hwnd, owner):
                return True
            seen.add(owner)
            owner = self.wu.user32.GetWindow(owner, GW_OWNER)
        return False

    def diagnose_close(self):
        """Bounded first-failure census. This is diagnostic data, never an oracle."""
        windows = []
        for hwnd, pid in self.wu.enum_windows():
            if pid != self.app.pid or not self.owned(hwnd):
                continue
            children = [{"hwnd": child, "text": text[:160]}
                for text, _rect, child in self.eu._children_texts(hwnd)[:32]]
            windows.append({"hwnd": hwnd, "class": self.wu.window_class(hwnd)[:128],
                "title": self.wu.window_title(hwnd)[:128],
                "owner_hwnd": self.wu.user32.GetWindow(hwnd, GW_OWNER), "children": children})
            if len(windows) == 16:
                break
        pending = [window["hwnd"] for window in windows]
        relations, seen = [], set()
        while pending and len(relations) < 32:
            hwnd = pending.pop(0)
            if not hwnd or hwnd in seen or self.wu._window_pid(hwnd) != self.app.pid:
                continue
            seen.add(hwnd)
            owner = self.wu.user32.GetWindow(hwnd, GW_OWNER)
            parent = self.wu.user32.GetParent(hwnd)
            relations.append({"hwnd": hwnd, "pid": self.app.pid,
                "class": self.wu.window_class(hwnd)[:128], "title": self.wu.window_title(hwnd)[:128],
                "visible": bool(self.wu.user32.IsWindowVisible(hwnd)),
                "enabled": bool(self.wu.user32.IsWindowEnabled(hwnd)),
                "owner_hwnd": owner, "parent_hwnd": parent,
                "root_hwnd": self.wu.user32.GetAncestor(hwnd, 2),
                "root_owner_hwnd": self.wu.user32.GetAncestor(hwnd, 3),
                "is_main_descendant": bool(self.wu.user32.IsChild(self.app.hwnd, hwnd))})
            pending.extend((owner, parent))
        write_json_once(self.artifacts / "close_windows.json", {"schema_version": 1,
            "diagnostic_only": True, "oracle_evidence": False, "app_pid": self.app.pid,
            "main_hwnd": self.app.hwnd, "captured_at_ns": time.time_ns(),
            "reason": "graceful_close_unconfirmed", "windows": windows, "relations": relations,
            "close_attempts": getattr(self, "_close_attempts", [])[:16]})

    def close(self):
        if self.base is None or not self.app.alive():
            return
        if self.wu._window_pid(self.app.hwnd) != self.app.pid:
            raise ProtocolError("window_identity_changed")
        if not getattr(self, "_close_requested", False):
            self.wu.close_window(self.app.hwnd)
            self._close_requested = True
        # This profile and loaded fixture are run-owned; discard only named
        # buttons in this PID. An unknown prompt remains a truthful failure.
        end = time.monotonic() + 10
        handled = set()
        while self.app.alive() and time.monotonic() < end:
            for hwnd, pid in self.wu.enum_windows():
                if pid != self.app.pid or not self.owned_dialog(hwnd):
                    continue
                children = self.eu._children_texts(hwnd)
                chosen = _discard_choice(self.wu.window_title(hwnd), children,
                                         close_requested=getattr(self, "_close_requested", False))
                if chosen is not None and hwnd not in handled and self.owned(chosen[2]):
                    handled.add(hwnd)
                    rect = chosen[1]
                    target = self.wu.msg_click_screen((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2, hwnd)
                    if not hasattr(self, "_close_attempts"):
                        self._close_attempts = []
                    if len(self._close_attempts) < 16:
                        self._close_attempts.append({"dialog_hwnd": hwnd, "button_hwnd": chosen[2],
                            "target_hwnd": target, "at_ns": time.time_ns()})
            time.sleep(0.1)
        if self.app.alive():
            try:
                self.diagnose_close()
            except FileExistsError:
                pass  # Retain the first census; finally cleanup must never replace it.
            except Exception as diagnostic_error:
                print(f"[business_ui] close diagnosis: {type(diagnostic_error).__name__}", file=sys.stderr)
            raise ProtocolError("graceful_close_unconfirmed")
