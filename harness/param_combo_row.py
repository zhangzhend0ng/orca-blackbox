"""Row-anchored combo picking for painted parameter pages.

pp.set_combo_by_popup locates the combo by its painted VALUE, which is
ambiguous when sibling rows share a value (run 6d6fef17: two 'Monotonic'
pattern rows). This helper locates the combo by its painted ROW LABEL
(phrase OCR) and reuses the same popup capture/OCR/click mechanics."""
import time

from .agent_protocol import ProtocolError
from .param_case_lib import _find_phrase_row


def pick_combo_at_label(ui, label, target, group_substr=None):
    """Open the combo on the row labeled `label` and click the popup row
    containing `target`; verify via the combo's real window text."""
    from . import process_panel as pp
    from harness import export_util, mix_dialog_util as mdu, winutil
    import numpy as np
    from win32gui import EnumChildWindows, IsWindowVisible

    wu, app = ui.wu, ui.app
    ui.main_input()
    if group_substr and not pp.scroll_group_into_view(app, group_substr):
        # a wrong group name must not degrade into a whole-page search for
        # the label (fa706g3 review D2, 2026-11-23)
        raise ProtocolError("param_combo_group:" + group_substr)

    def locate_combo():
        """((cx, cy), bounds) of the combo on the row labeled `label`, or None."""
        y_row = _find_phrase_row(app, label, group_substr=None)  # already scrolled
        if y_row is None:
            return None
        canvas_left = wu.window_rect(_canvas(ui))[0]
        origin_x, origin_y = wu.client_to_screen(app.hwnd, 0, 0)
        combo = []

        def collect(handle, _):
            if (wu.window_class(handle) != "ComboBox" or not IsWindowVisible(handle)
                    or wu._window_pid(handle) != app.pid):
                return True
            b = wu.window_rect(handle)
            cy = (b[1] + b[3]) // 2 - origin_y
            # On the matched line, or ~15px off it: a label that wraps to
            # two lines has its control centred on the ROW (fa706g3 review;
            # find_option_checkbox does the same for boxes).
            if (abs(cy - y_row) <= 14 or abs(abs(cy - y_row) - 15) <= 8) \
                    and 0 <= (b[0] + b[2]) // 2 < canvas_left:
                combo.append((handle, list(b)))
            return True

        EnumChildWindows(app.hwnd, collect, None)
        if len(combo) == 1:
            bounds = combo[0][1]
        elif len(combo) == 0:
            # Painted-value combos carry no ComboBox HWND (runs 5e095f2c/
            # 79ca1e8c): the value zone at the row's right opens the popup.
            # The value is its own small window (census f1c5433b: 120x26
            # 'Auto'): take that window's centre when the point resolves to
            # one. WindowFromPoint hands back the big row container for a
            # DISABLED value - that is left to the open attempt to report.
            best = None
            for dy in (0, 15, -15):
                target = winutil.window_from_screen_point(canvas_left - 90, y_row + dy + origin_y)
                rect = winutil.window_rect(target) if target else None
                if rect and (rect[2] - rect[0]) <= 250 and (rect[3] - rect[1]) <= 60:
                    best = rect
                    break
            bounds = best or (canvas_left - 150, y_row + origin_y - 13,
                              canvas_left - 30, y_row + origin_y + 13)
        else:
            raise ProtocolError("param_combo_field:" + label + ":" + str(len(combo)))
        return ((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2), bounds

    found = locate_combo()
    if not found:
        raise ProtocolError("param_combo_row:" + label)
    (cx, cy), _bounds = found
    # Park the row before the popup is opened: its list opens straight down
    # and a row that lands under the taskbar cannot be clicked (brim run
    # f323be97 OCR'd an empty popup, by_object clicked Shell_TrayWnd).
    if pp.park_for_popup(app, _bounds):
        found = locate_combo()  # the row moved up with the page
        if not found:
            raise ProtocolError("param_combo_row_after_park:" + label)
        (cx, cy), _bounds = found

    def _click_target(words_, pr, ph):
        """True = clicked, 'offscreen' = the row is under the taskbar,
        False = no such row in these words. Line-level match: a two-word
        target is never inside one OCR word."""
        for cx_, cy_, _line in pp.popup_line_hits(words_, target):
            x, y = pr[0] + cx_, pr[1] + cy_
            if not pp.popup_hit_clickable(ph, x, y):
                print("[popup] row %r at (%d,%d) is off-screen (popup %r, "
                      "work area %r)" % (target, x, y, pr, pp.work_area()), flush=True)
                return "offscreen"
            winutil.msg_click_screen(x, y)
            return True
        return False

    def _popup_words(ph):
        # psm 6 (uniform block): the default psm 3 dropped whole rows of
        # list-like popups - '1 PETG' and '5 PLA' of the extruder list were
        # missing while '2) PLA' / '4 PLA' came through (census c814315c).
        time.sleep(0.8)
        words_ = []
        for _attempt in range(3):
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words_ = mdu.ocr_words_img(img, scale=3, psm=6)
            if words_:
                break
            time.sleep(0.6)
        return words_

    clicked = False
    offscreen = False
    words = []
    for attempt in (1, 2):
        popup = None
        for click in (1, 2):   # a just-dismissed popup can swallow a click
            winutil.msg_click_screen(cx, cy, app.hwnd)
            for _ in range(12 if click == 1 else 20):
                popup = export_util.wait_popup(app.pid, timeout_s=0.5)
                if popup:
                    break
            if popup:
                break
            time.sleep(0.6)
        if not popup:
            raise ProtocolError("param_combo_popup:" + label)
        pr, ph = popup[2], popup[3]
        words = _popup_words(ph)
        first = _click_target(words, pr, ph)
        if first is True:
            clicked = True
            break
        if first == "offscreen":
            offscreen = True
            if attempt == 2:
                break
            # close it, move the page further up, open it again - once
            pp.close_popup(app, ph, (cx, cy))
            vp = pp.options_viewport(app)
            if vp:
                pp.wheel_viewport(app, vp, 3, delta=-120)
            found = locate_combo()
            if not found:
                raise ProtocolError("param_combo_row_after_park:" + label)
            (cx, cy), _bounds = found
            continue
        break
    if offscreen and not clicked:
        # wheeling a popup whose rows are under the taskbar cannot help
        raise ProtocolError("param_combo_popup_offscreen:" + target + ":" + repr(pr))
    for page in range(8):
        if clicked:
            break
        # 2026-11-22 fa706g3 hands-on diagnosis (fa706g3-gui-diag-2026-11-22):
        # the popup is a childless self-drawn list. WM_CHAR typeahead never
        # renders, and ANY key (VK_NEXT / VK_DOWN, real or posted) CLOSES it.
        # The proven deep-item recipe is a REAL wheel, ONE notch per step
        # with >=0.4s settle (Gyroid fully visible after 2 notches, list
        # freezes after ~4), with the touch-style painted bar as fallback
        # (drag UP = content follows finger deeper) where the wheel does
        # not accumulate at all (VM 2.4.0 rebound records).
        from win32gui import EnumChildWindows
        if page == 0:
            kids = []

            def census(handle, _):
                kids.append((handle, wu.window_class(handle)))
                return True

            EnumChildWindows(ph, census, None)
            print("[popup] children: " + repr(kids)[:300], flush=True)
        pcx, pcy = (pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2
        winutil.real_wheel_screen(pcx, pcy, -1)
        time.sleep(0.45)
        w, hgt, bgra = winutil.capture_window(ph)
        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
        words = mdu.ocr_words_img(img, scale=3, psm=6)
        if _click_target(words, pr, ph) is True:
            clicked = True
        if clicked:
            break
        if page == 1:
            # Wheel not accumulating on this build: pull the touch-style
            # bar (right edge, drag UP drags deep items into view).
            winutil.real_drag_screen(pr[2] - 6, pcy + (pr[3] - pr[1]) // 4,
                                     pr[2] - 6, pcy - (pr[3] - pr[1]) // 4)
            time.sleep(0.6)
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3, psm=6)
    if not clicked:
        raise ProtocolError("param_combo_target:" + target + ":" +
                            "|".join(t for t, *_ in words)[:80])
    time.sleep(2.5)  # a combo commit rebuilds the page
    ui.main_input()


def _canvas(ui):
    from .param_case_lib import _canvas_hwnd
    return _canvas_hwnd(ui)
