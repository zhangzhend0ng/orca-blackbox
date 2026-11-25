"""Open the selected model's native context menu in the guest desktop."""

import time

import m7_common as m7
from harness import topbar_util, winutil
from m8x_48_modal_color_header import bring_main_to_mouse


def _label(text):
    return text.partition('\t')[0].replace('&', '').rstrip('. …').strip().casefold()


def open_model_menu(session, exact_label, *, candidates=None):
    """Return the visible menu and exact enabled item, using a model hit point."""
    if not bring_main_to_mouse(session.hwnd):
        print('[model context] Orca could not own the guest foreground')
        return None
    if candidates is None:
        center = m7.find_centroid(session)
        if center is None:
            print('[model context] fixture model centroid missing')
            return None
        candidates = [center]
    points = ((x, y + shift) for x, y in candidates for shift in (14, 0, 26))
    for point in points:
        sx, sy = m7.client(session, *point)
        canvas = winutil.deepest_child_at(session.hwnd, sx, sy)
        if winutil.window_class(canvas) != 'wxGLCanvas' or winutil._window_pid(canvas) != session.pid:
            continue
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.4)
        winutil.msg_click_screen(sx, sy, session.hwnd)
        time.sleep(0.4)
        known = {row[4] for row in topbar_util._enum_menu_windows(session.pid)}
        if winutil.window_from_screen_point(sx, sy) == canvas:
            sent = winutil.real_right_click_screen(sx, sy)
            print(f'[model context] real right-click @({sx},{sy}) on {canvas:#x}: sent={sent}')
            popup = topbar_util.wait_submenu(session.pid, known, timeout_s=2.0)
        else:
            print(f'[model context] desktop hit-test did not resolve to canvas at ({sx},{sy})')
            popup = None
        if popup is None:
            lp = winutil._lparam_from_screen(canvas, sx, sy)
            winutil._send_msg(canvas, 0x0204, 0x0002, lp)  # WM_RBUTTONDOWN.
            winutil._send_msg(canvas, 0x0205, 0, lp)       # WM_RBUTTONUP.
            print(f'[model context] message right-click @({sx},{sy}) on {canvas:#x}')
            popup = topbar_util.wait_submenu(session.pid, known, timeout_s=3.0)
        if not popup:
            continue
        _, hwnd, menu = popup
        rows = topbar_util.menu_items(menu)
        print(f'[model context] menu hwnd={hwnd:#x}: {rows!r}')
        matches = [index for index, text, flags in rows
                   if _label(text) == _label(exact_label) and not flags & 3]
        if len(matches) == 1:
            return hwnd, menu, matches[0]
        topbar_util.close_menu_windows(session.pid)
    return None
