"""Deterministic preset-editor actions for the FDMT and STD02 comparisons."""
from decimal import Decimal, InvalidOperation
import re
from types import SimpleNamespace

from .agent_protocol import ProtocolError


def _center(rect):
    left, top, right, bottom = rect
    return (left + right) // 2, (top + bottom) // 2


def _unique(items, name):
    if len(items) > 1:
        raise ProtocolError("script_preset_ambiguous:" + name)
    return items[0] if items else None


def _normalize(text):
    return " ".join(text.casefold().split()).rstrip(":")


class PresetUI:
    def __init__(self, ui):
        from . import mix_dialog_util, mixing_util, process_panel, topbar_util

        self.ui, self.wu = ui, ui.wu
        self.mix, self.ocr = mixing_util, mix_dialog_util
        self.pp, self.menu = process_panel, topbar_util
        self.hwnd = ui.app.hwnd

    def _children(self):
        return [c for c in self.mix.children(self.hwnd) if self.ui.owned(c[3])]

    def _wait(self, predicate, seconds, stage):
        try:
            return self.ui.wait(predicate, seconds)
        except ProtocolError as error:
            if str(error) != "gui_wait_timeout":
                raise
            raise ProtocolError("script_preset_timeout:" + stage) from error

    def _trace(self, stage, candidates=()):
        print("[native-script] preset %s hwnd=%#x class=%s rect=%r candidates=%r" % (
            stage, self.hwnd, self.wu.window_class(self.hwnd),
            self.wu.window_rect(self.hwnd), list(candidates)[:8]), flush=True)

    def _onscreen(self, hwnd, point):
        hit = self.wu.window_from_screen_point(*point)
        return bool(hit and (hit == hwnd or self.wu.user32.IsChild(hwnd, hit)))

    def _click(self, point, scope, *, exact=None):
        self.ui.guard()
        self.ui.identity()
        if (not self.ui.owned(scope) or not self._onscreen(scope, point)
                or (exact is not None and self.wu.window_from_screen_point(*point) != exact)):
            raise ProtocolError("script_preset_click_target")
        self.wu.real_click_screen(*point)
        self.ui.pause(0.7)

    def _words(self, rect=None):
        self.ui.guard()
        dialog = SimpleNamespace(hwnd=self.hwnd, pid=self.ui.app.pid)
        image = self.pp.capture_bgr(dialog)
        ox, oy = self.pp.client_origin(dialog)
        if rect is not None:
            l, t, r, b = rect
            if not (0 <= l-ox < r-ox <= image.shape[1] and 0 <= t-oy < b-oy <= image.shape[0]):
                return []
            image = image[t-oy:b-oy, l-ox:r-ox]
            ox, oy = l, t
        return [(text, x+ox, y+oy, w, h)
                for text, x, y, w, h in self.ocr.ocr_words_img(image, psm=6)]

    def _preset_combo(self, identity, *, slot_one=False, trace=False):
        crops = self._children()
        main = self.hwnd == self.ui.app.hwnd
        sidebar_right = self.wu.window_rect(self.hwnd)[0] + 435
        candidates = [
            (text, rect, hwnd) for text, cls, rect, hwnd in crops
            if cls.startswith("wxWindow") and 85 <= rect[2] - rect[0] <= 420
            and 19 <= rect[3] - rect[1] <= 46 and self._onscreen(hwnd, _center(rect))
            and (not main or rect[2] <= sidebar_right)
            and (not slot_one or any(
                label.strip() == "1" and 0 <= rect[0] - badge[2] <= 18
                and abs(_center(badge)[1] - _center(rect)[1]) <= 6
                and self.wu.user32.GetParent(badge_hwnd) == self.wu.user32.GetParent(hwnd)
                for label, _cls, badge, badge_hwnd in crops))
        ]
        found = []
        observed = []
        # A preset may gain the app's embedded-project suffix.
        allowed = {identity, identity + "(fixture.3mf)", identity + " (fixture.3mf)"}
        for text, rect, hwnd in candidates:
            seen = text.strip()
            if not seen:
                seen = " ".join(word[0] for word in self._words(rect)).lstrip("vV⌄˅ ")
            matched = seen in allowed or (slot_one and re.fullmatch(r"Generic PLA @U1(?:\.{2,}|…)", seen))
            if matched:
                found.append((rect, hwnd))
            # Only fixture preset candidates are named. Other controls
            # contribute class and geometry, without exposing their text.
            display = seen if matched else "expected prefix" if seen.startswith(identity.split(" @")[0]) else "other"
            observed.append((self.wu.window_class(hwnd), rect, display))
        if trace:
            self._trace("slot1" if slot_one else "preset", observed)
        return _unique(found, identity)

    def _advanced(self):
        if self.ui.named_child("Speed"):
            return
        session = SimpleNamespace(hwnd=self.hwnd, pid=self.ui.app.pid)
        ox, oy = self.pp.client_origin(session)
        labels = [r for t, c, r, _h in self._children()
                  if c == "Static" and t.strip() == "Process" and 0 <= r[0] - ox <= 50]
        process = _unique(labels, "process_title")
        if process is None:
            raise ProtocolError("script_preset_process_title_missing")
        y = _center(process)[1]
        words = self._words((ox + 215, y - 14, ox + 355, y + 14))
        label = _unique([(x, t, w, h) for word, x, t, w, h in words
                         if word.casefold() == "advanced"], "advanced_label")
        if label is None:
            self._trace("advanced_label_missing", [process])
            raise ProtocolError("script_preset_advanced_label_missing")
        x, top, width, height = label
        # The Script run's Process header renders the 24x16 switch
        # immediately to the right of the Advanced label.
        controls = [
            (r, h) for text, _cls, r, h in self._children()
            if not text.strip() and 0 <= r[0] - (x + width) <= 18
            and 16 <= r[2] - r[0] <= 33 and 10 <= r[3] - r[1] <= 23
            and abs(_center(r)[1] - (top + height // 2)) <= 6
            and self._onscreen(h, _center(r))
        ]
        self._trace("advanced_switch", [(self.wu.window_class(h), r) for r, h in controls])
        switch = _unique(controls, "advanced_switch")
        if switch is None:
            raise ProtocolError("script_preset_advanced_switch_missing")
        bounds, hwnd = switch
        self._click(_center(bounds), hwnd, exact=hwnd)
        self._wait(lambda: self.ui.named_child("Speed"), 8, "advanced_speed_tab")

    def open(self, *, filament):
        self.ui.main_input()
        self._advanced()
        title, preset = (("Material settings", "Generic PLA @U1 0.4 nozzle") if filament
                         else ("Printer settings", "Snapmaker U1 (0.4 nozzle)"))
        combo_candidate = self._preset_combo(preset, slot_one=filament, trace=True)
        rect, combo = combo_candidate or self._wait(lambda: self._preset_combo(preset, slot_one=filament),
                                                    12, "slot1_combo" if filament else "printer_combo")
        before = {h for _c, _t, _r, h in self.mix.toplevel(self.ui.app.pid)}
        if filament:
            parent = self.wu.user32.GetParent(combo)
            action = _unique([
                (bounds, hwnd) for text, cls, bounds, hwnd in self._children()
                if not text.strip() and cls.startswith(("wxWindow", "Button"))
                and self.wu.user32.GetParent(hwnd) == parent
                and 0 <= bounds[0] - rect[2] <= 20
                and 14 <= bounds[2]-bounds[0] <= 40 and 14 <= bounds[3]-bounds[1] <= 40
                and abs(_center(bounds)[1] - _center(rect)[1]) <= 5
                and self._onscreen(hwnd, _center(bounds))
            ], "slot1_action")
            if action is None:
                raise ProtocolError("script_preset_slot1_action_missing")
            bounds, button = action
            self._trace("slot1_action", [(self.wu.window_class(button), bounds)])
            prior_menus = {m[4] for m in self.menu._enum_menu_windows(self.ui.app.pid)}
            self._click(_center(bounds), button)
            self._edit_menu(prior_menus, bounds)
        else:
            # The disconnected U1 card has an in-window 16 DIP edit glyph,
            # centered 8 raw pixels plus half its scaled size from the right.
            dpi = self.wu.get_dpi_for_window(combo)
            self._click((rect[2] - 8 - round(8*dpi/96), _center(rect)[1]), combo, exact=combo)

        def dialog():
            return _unique([h for c, t, _r, h in self.mix.toplevel(self.ui.app.pid)
                            if h not in before and c == "#32770" and t == title
                            and self.wu.user32.GetWindow(h, 4) == self.ui.app.hwnd], title)

        self.hwnd = self._wait(dialog, 10, title)
        # Recheck the editing preset displayed by the dialog before changing it.
        if self._preset_combo(preset, trace=True) is None:
            self._wait(lambda: self._preset_combo(preset), 10, "dialog_preset")

    def _edit_menu(self, before, bounds):
        def menu():
            return _unique([m for m in self.menu._enum_menu_windows(self.ui.app.pid)
                            if m[4] not in before and abs(m[0]-bounds[0]) <= 32
                            and abs(m[1]-bounds[3]) <= 48], "slot1_menu")

        popup = self._wait(menu, 5, "slot1_menu")
        popup_hwnd = popup[4]
        hmenu = self.menu.menu_hmenu(popup_hwnd)
        items = self.menu.menu_items(hmenu)
        if (len(items) < 2 or items[0][1].replace("&", "") != "Edit"
                or items[1][1].replace("&", "") != "Delete" or items[0][2] & 3):
            raise ProtocolError("script_preset_wrong_slot_menu")
        import ctypes
        from ctypes import wintypes

        item = wintypes.RECT()
        if not self.wu.user32.GetMenuItemRect(popup_hwnd, ctypes.c_void_p(hmenu), 0,
                                             ctypes.byref(item)):
            raise ProtocolError("script_preset_edit_menu_rect")
        self._click(_center((item.left, item.top, item.right, item.bottom)), popup_hwnd)

    def _line(self, name, *, rect=None, prefix=False):
        hits = self.pp.popup_line_hits(self._words(rect), name)
        target = _normalize(name)
        return _unique([
            (x, y) for x, y, text in hits
            if _normalize(text) == target or (prefix and _normalize(text).startswith(target))
        ], name)

    def page(self, name):
        # The page selector occupies the dialog's left column; same-named
        # text elsewhere in the pane cannot qualify as navigation.
        session = SimpleNamespace(hwnd=self.hwnd, pid=self.ui.app.pid)
        ox, oy = self.pp.client_origin(session)
        height, width = self.pp.capture_bgr(session).shape[:2]
        pane = (ox, oy, ox + width // 3, oy + height)
        point = self._wait(lambda: self._line(name, rect=pane), 12, "page:" + name)
        self._trace("page:" + name, [point])
        self._click(point, self.hwnd)
        self.ui.pause(0.8)

    def _row(self, name, match, *, paired=False):
        session = SimpleNamespace(hwnd=self.hwnd, pid=self.ui.app.pid)
        ox, oy = self.pp.client_origin(session)
        height, width = self.pp.capture_bgr(session).shape[:2]
        # The label is painted and some labels wrap. Use its unique leading
        # phrase in the content pane, and insist on a visible same-row field.
        pane = (ox + width // 4, oy + height // 8, ox + 2*width // 3, oy + height)
        for _ in range(16):
            label = self._line(name, rect=pane, prefix=True)
            if label is not None:
                x, y = label
                keys = [(r, h) for t, c, r, h in self._children()
                        if r[0] > x and abs(_center(r)[1] - y) <= 12
                        and self._onscreen(h, _center(r)) and match(t, c, r)]
                if paired and len(keys) in (1, 2):
                    # TabPrinter appends Normal before Silent. If both
                    # are present, select the leftmost field only.
                    ordered = sorted(keys, key=lambda entry: entry[0][0])
                    if len(ordered) == 2 and ordered[0][0][2] >= ordered[1][0][0]:
                        raise ProtocolError("script_preset_overlapping_machine_fields")
                    return ordered[0]
                field = _unique(keys, name)
                if field is not None:
                    return field
            self.ui.guard()
            scroll = (ox + 3*width//4, oy + 2*height//3)
            if not self._onscreen(self.hwnd, scroll):
                raise ProtocolError("script_preset_scroll_scope")
            self.wu.real_wheel_screen(*scroll, -2)
            self.ui.pause(0.4)
        raise ProtocolError("script_preset_row_missing:" + name)

    def number(self, name, start, wanted, *, paired=False):
        bounds, field = self._row(name, lambda t, c, r: c == "Edit", paired=paired)

        def read():
            try:
                return Decimal(self.wu.edit_text(field).strip())
            except InvalidOperation:
                raise ProtocolError("script_preset_numeric_unreadable:" + name) from None

        before = read()
        if before != Decimal(start):
            raise ProtocolError("script_preset_wrong_start:" + name)
        if before != Decimal(wanted):
            if not self.wu.user32.IsWindowEnabled(field):
                raise ProtocolError("script_preset_edit_disabled:" + name)
            self._click(_center(bounds), self.hwnd, exact=field)
            session = SimpleNamespace(hwnd=self.hwnd, pid=self.ui.app.pid)
            if (not self.ui.owned(field) or self.pp.focus_info(session)[0] != field
                    or read() != before):
                raise ProtocolError("script_preset_edit_focus:" + name)
            self.ui.guard()
            self.wu._send_msg(field, 0x00B1, 0, -1)  # EM_SETSEL
            self.ui.guard()
            self.wu.msg_text(field, wanted)
            self.ui.guard()
            self.wu.msg_text(field, "\r")
            self.ui.guard()
            self.wu._send_msg(field, 0x0008, 0, 0)
            self.ui.pause(1.2)
        if not self.ui.owned(field) or read() != Decimal(wanted):
            raise ProtocolError("script_preset_numeric_readback:" + name)
        print("[native-script] preset %s: %s -> %s" % (name, before, wanted), flush=True)

    def forced_cooling(self):
        bounds, _field = self._row("Force cooling for overhangs",
                                   lambda t, c, r: c == "Button" and not t.strip()
                                   and 12 <= r[2]-r[0] <= 26 and 12 <= r[3]-r[1] <= 26)
        session = SimpleNamespace(hwnd=self.hwnd, pid=self.ui.app.pid)
        if self.pp.checked_state(session, bounds) <= self.pp.CHECKED_FRACTION:
            raise ProtocolError("script_preset_force_cooling_not_checked")
        print("[native-script] preset force cooling already checked", flush=True)

    def threshold(self):
        name = "Overhang cooling activation"
        bounds, field = self._row(name, lambda t, c, r: t.strip() == "50%" and
                                  (c.startswith("wxWindow") or c == "ComboBox"))
        before = {h for _c, _t, _r, h in self.mix.toplevel(self.ui.app.pid)}
        self._click(_center(bounds), field)
        popup = self._wait(lambda: _unique([
            h for c, _t, rect, h in self.mix.toplevel(self.ui.app.pid)
            if h not in before and c.startswith(("wxWindow", "ComboLBox"))
            and abs(rect[0] - bounds[0]) <= 12
            and min(abs(rect[1]-bounds[3]), abs(rect[3]-bounds[1])) <= 12
        ], "threshold_popup"), 6, "threshold_popup")
        popup_rect = self.wu.window_rect(popup)
        hit = _unique([(x, y) for x, y, text in
                       self.pp.popup_line_hits(self.ocr.ocr_words(popup), "10%")
                       if text.strip() == "10%"], "10%")
        if hit is None:
            raise ProtocolError("script_preset_threshold_popup_value")
        self._click((popup_rect[0]+hit[0], popup_rect[1]+hit[1]), popup)
        if self.wu.window_title(field).strip() != "10%":
            raise ProtocolError("script_preset_threshold_readback")
        print("[native-script] preset overhang cooling threshold: 50% -> 10%", flush=True)

    def close(self):
        self.ui.guard()
        self.ui.identity()
        self.wu.close_window(self.hwnd)
        self.ui.wait(lambda: not self.ui.owned(self.hwnd), 8)
        self.ui.main_input()
        self.hwnd = self.ui.app.hwnd


def edit_cooling(ui):
    preset = PresetUI(ui)
    preset.open(filament=True)
    preset.page("Cooling")
    preset.forced_cooling()
    preset.threshold()
    preset.number("Overhangs and external", "100", "80")
    preset.close()


def edit_speed_limits(ui):
    preset = PresetUI(ui)
    preset.open(filament=False)
    preset.page("Motion ability")
    preset.number("Maximum speed X", "500", "500", paired=True)
    preset.close()
    preset.open(filament=True)
    preset.page("Filament")
    preset.number("Max volumetric speed", "12", "15")
    preset.close()
