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
    if group_substr:
        pp.scroll_group_into_view(app, group_substr)
    y_row = _find_phrase_row(app, label, group_substr=None)  # already scrolled
    if y_row is None:
        raise ProtocolError("param_combo_row:" + label)
    canvas_left = wu.window_rect(_canvas(ui))[0]
    origin_x, origin_y = wu.client_to_screen(app.hwnd, 0, 0)
    combo = []

    def collect(handle, _):
        if (wu.window_class(handle) != "ComboBox" or not IsWindowVisible(handle)
                or wu._window_pid(handle) != app.pid):
            return True
        b = wu.window_rect(handle)
        cy = (b[1] + b[3]) // 2 - origin_y
        if abs(cy - y_row) <= 14 and 0 <= (b[0] + b[2]) // 2 < canvas_left:
            combo.append((handle, list(b)))
        return True

    EnumChildWindows(app.hwnd, collect, None)
    if len(combo) == 1:
        _handle, bounds = combo[0]
        cx, cy = (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
    elif len(combo) == 0:
        # Painted-value combos carry no ComboBox HWND (runs 5e095f2c/
        # 79ca1e8c): the value zone at the row's right opens the popup.
        cx, cy = canvas_left - 90, y_row + origin_y
    else:
        raise ProtocolError("param_combo_field:" + label + ":" + str(len(combo)))
    winutil.msg_click_screen(cx, cy, app.hwnd)
    popup = None
    for _ in range(20):
        popup = export_util.wait_popup(app.pid, timeout_s=0.5)
        if popup:
            break
    if not popup:
        raise ProtocolError("param_combo_popup:" + label)
    pr, ph = popup[2], popup[3]
    time.sleep(0.8)
    words = []
    for _attempt in range(3):
        w, hgt, bgra = winutil.capture_window(ph)
        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
        words = mdu.ocr_words_img(img, scale=3)
        if words:
            break
        time.sleep(0.6)
    clicked = False
    for page in range(4):
        for t, x, y, ww, hh in words:
            if target.lower() in t.lower():
                winutil.msg_click_screen(pr[0] + x + ww // 2, pr[1] + y + hh // 2)
                clicked = True
                break
        if clicked:
            break
        # Long lists (Gyroid sits pages down, run 9866d291): wheel the
        # popup itself via WM_MOUSEWHEEL (mouse_event misses when the
        # cursor is not over the popup).
        import ctypes
        u32 = ctypes.windll.user32
        lparam = ((pr[1] + 10) << 16) | ((pr[0] + pr[2]) // 2 & 0xFFFF)
        u32.PostMessageW(ph, 0x020A, (0xFFFFFFFF << 16) & 0xFFFFFFFF, lparam)
        time.sleep(0.7)
        w, hgt, bgra = winutil.capture_window(ph)
        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
        words = mdu.ocr_words_img(img, scale=3)
    if not clicked:
        raise ProtocolError("param_combo_target:" + target + ":" +
                            "|".join(t for t, *_ in words)[:80])
    time.sleep(2.5)  # a combo commit rebuilds the page
    ui.main_input()


def _canvas(ui):
    from .param_case_lib import _canvas_hwnd
    return _canvas_hwnd(ui)
