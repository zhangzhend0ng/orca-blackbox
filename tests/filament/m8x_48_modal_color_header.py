#!/usr/bin/env python3
# m8x_48_modal_color_header.py — 飞书基线 #48：验证官方色盘的模态和头部布局
# feishu: baseline#48

import argparse
import time
from ctypes import byref, sizeof
from ctypes.wintypes import HWND, POINT

import numpy as np

from m8b_official_color import (MIXED_3MF, add_common_args, boot_session, click_cancel,
                                is_native_picker, m7, m8, read_rgb)
from harness import export_util, winutil
from harness.mix_dialog_util import GUITHREADINFO

LOG = "[m8x48]"
NAME = "Mint Lemonade"
SKU = "sku 34205"
# The fixture's official PLA Silk color carries these two catalog colors.
CARD_BGR = ((23, 237, 236), (229, 173, 68))
HWND_TOPMOST = HWND(-1)


def center(rect):
    x0, y0, x1, y1 = rect
    return (x0 + x1) // 2, (y0 + y1) // 2


def contains(rect, point):
    x0, y0, x1, y1 = rect
    x, y = point
    return x0 <= x < x1 and y0 <= y < y1


def bring_main_to_mouse(hwnd):
    """Temporarily expose the boot-demoted window on the dedicated VM desktop."""
    wu = winutil.user32
    style = wu.GetWindowLongW(hwnd, winutil.GWL_EXSTYLE)
    wu.SetWindowLongW(hwnd, winutil.GWL_EXSTYLE, style & ~winutil.WS_EX_NOACTIVATE)
    raised = wu.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0, winutil.SWP_NOMOVE | winutil.SWP_NOSIZE
    )
    foreground = winutil.force_set_foreground(hwnd)
    return bool(raised and foreground)


def request_background_focus(main, chip):
    """Request keyboard focus through Win32 and read the target input queue."""
    wu = winutil.user32
    ours = winutil.kernel32.GetCurrentThreadId()
    gui_thread = wu.GetWindowThreadProcessId(main, None)
    if not gui_thread or not wu.AttachThreadInput(ours, gui_thread, True):
        return None
    try:
        wu.SetActiveWindow(HWND(main))
        wu.SetFocus(HWND(chip))
        info = GUITHREADINFO(cbSize=sizeof(GUITHREADINFO))
        if not wu.GetGUIThreadInfo(gui_thread, byref(info)):
            return None
        return info.hwndActive or 0, info.hwndFocus or 0
    finally:
        wu.AttachThreadInput(ours, gui_thread, False)


def preview_pixels(hwnd, rect):
    """Capture the dialog client independently of desktop foreground changes."""
    x0, y0, x1, y1 = rect
    try:
        width, height, raw = winutil.capture_window(hwnd)
    except winutil.CaptureError as exc:
        print(f"{LOG} dialog client capture failed: {exc}")
    else:
        ox, oy = winutil.client_to_screen(hwnd, 0, 0)
        pixels = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
        yield "dialog client", pixels[max(0, y0 - oy):y1 - oy, max(0, x0 - ox):x1 - ox, :3]

    # After an outside click the VM may activate another process. Only use
    # the desktop surface after the same dialog has visibly regained focus.
    if winutil.force_set_foreground(hwnd):
        time.sleep(0.2)
        yield "foreground desktop", m8._screen_crop(*rect)


def verify_header(dialog):
    """Read the visible labels and the preview colors above the swatch list."""
    children = [
        (text.strip().casefold(), rect)
        for text, rect, hwnd in export_util._children_texts(dialog[3])
        if text.strip() and winutil.user32.IsWindowVisible(hwnd)
    ]
    rows = dict(children)
    name = rows.get(NAME.casefold())
    sku = rows.get(SKU)
    marker = rows.get("official filaments")
    print(f"{LOG} visible dialog labels={[(text, rect) for text, rect in children if text != 'panel']!r}")
    if not (name and sku and marker):
        return "FAIL (the official color name, SKU or swatch-list label is missing)"

    bounds = dialog[2]
    if not all(contains(bounds, center(rect)) and rect[3] <= marker[1]
               for rect in (name, sku)):
        return f"FAIL (name={name}, sku={sku}, swatch list={marker})"

    # wx draws the preview at the left of the name and SKU. Crop only the
    # header, so matching colors in the selectable grid cannot pass this step.
    dpi = winutil.get_dpi_for_window(dialog[3]) or 96
    pad = max(3, round(4 * dpi / 96))
    card_rect = (
        max(bounds[0] + pad, min(name[0], sku[0]) - round(82 * dpi / 96)),
        max(bounds[1], min(name[1], sku[1]) - pad),
        min(name[0], sku[0]) - pad,
        min(marker[1], min(name[1], sku[1]) + round(66 * dpi / 96)),
    )
    x0, y0, x1, y1 = card_rect
    if x1 <= x0 or y1 <= y0:
        return f"FAIL (invalid preview area {card_rect})"
    detail = f"name={NAME!r} at {name}, {SKU!r} at {sku}, preview={card_rect}"
    for surface, image in preview_pixels(dialog[3], card_rect):
        if not image.size:
            continue
        pixels = image.astype(np.int16)
        shares = tuple(float((np.abs(pixels - color).max(axis=2) <= 16).mean())
                       for color in CARD_BGR)
        evidence = f"surface={surface}, catalog pixel shares={tuple(round(v, 3) for v in shares)}"
        print(f"{LOG} {evidence}")
        if min(shares) >= 0.08:
            return f"PASS ({detail}, {evidence})"
    return f"FAIL ({detail}, official card colors not found)"


def verify_background_reenabled(session, official_dialog, chip, chip_hwnd):
    """After Cancel the same background chip can open its own color picker."""
    wu = winutil.user32
    clicked = click_cancel(official_dialog)
    closed = not wu.IsWindowVisible(official_dialog[3])
    enabled = bool(wu.IsWindowEnabled(session.hwnd))
    same_chip = (winutil.deepest_child_at(session.hwnd, *chip) == chip_hwnd
                 and winutil.window_title(chip_hwnd).strip() == "1")
    print(f"{LOG} after Cancel: clicked={clicked}, closed={closed}, owner enabled={enabled}, "
          f"same chip={same_chip}")
    if not (clicked and closed and enabled and same_chip):
        return "FAIL (official dialog did not return control to the same background chip)"

    main_foreground = bring_main_to_mouse(session.hwnd)
    hit = winutil.window_from_screen_point(*chip)
    keys = request_background_focus(session.hwnd, chip_hwnd)
    detail = (f"same background chip={chip_hwnd:#x}, desktop hit={hit:#x}, "
              f"main foreground={main_foreground}, active/focus={keys!r}")
    if not main_foreground or keys != (session.hwnd, chip_hwnd):
        return f"FAIL ({detail})"
    if hit == chip_hwnd:
        route = f"real mouse events={winutil.real_click_screen(*chip)}"
    else:
        winutil.msg_click_screen(*chip, session.hwnd)
        route = "Orca window tree"

    picker = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32770", timeout_s=6.0)
    native = picker and is_native_picker(picker)
    rgb = read_rgb(session, picker) if native else None
    if native:
        click_cancel(picker)
    detail += f", click={route}, native picker RGB={rgb!r}"
    passed = rgb == ("217", "166", "58")
    return f"{'PASS' if passed else 'FAIL'} ({detail})"


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF).parse_args()
    session = boot_session(args, model=args.model)
    wu = winutil.user32
    try:
        arrived, _ = m8.wait_arrival(session)
        if not arrived:
            return m7.m7_verdict({"#48 fixture loaded": "FAIL"})
        m7.ensure_maximized(session)
        rows = {row["slot"]: row for row in m8.wait_slots(session)}
        official, background = rows.get(2), rows.get(1)
        if not (official and official["combo"] and "Snapmaker PLA Silk" in official["combo"][0]
                and background and background["combo"] and "Generic PETG" in background["combo"][0]):
            print(f"{LOG} fixture slots={rows!r}")
            return m7.m7_verdict({"#48 official filament precondition": "FAIL"})

        opener = center(official["swatch"])
        probe = center(background["swatch"])
        opener_hwnd = winutil.deepest_child_at(session.hwnd, *opener)
        probe_hwnd = winutil.deepest_child_at(session.hwnd, *probe)
        main_was_enabled = bool(wu.IsWindowEnabled(session.hwnd))
        print(f"{LOG} official preset={official['combo'][0]!r}, opener={opener}, "
              f"background={probe}, owner initially enabled={main_was_enabled}")
        if not (winutil.window_title(opener_hwnd).strip() == "2"
                and winutil.window_title(probe_hwnd).strip() == "1"
                and wu.IsWindowEnabled(probe_hwnd) and main_was_enabled):
            return m7.m7_verdict({"#48 fixture controls available": "FAIL"})

        main_foreground = bring_main_to_mouse(session.hwnd)
        enabled_hit = winutil.window_from_screen_point(*probe)
        print(f"{LOG} enabled background desktop hit={enabled_hit:#x} "
              f"class={winutil.window_class(enabled_hit)!r} pid={winutil._window_pid(enabled_hit)}, "
              f"Orca chip={probe_hwnd:#x}, main foreground={main_foreground}")
        winutil.msg_click_screen(*opener, session.hwnd)
        dialog = m8.official_color_popup(session, timeout_s=8.0)
        if dialog is None:
            print(f"{LOG} visible Orca windows={m8._visible_toplevels(session.pid)!r}")
            return m7.m7_verdict({"#48 official color dialog opens": "FAIL"})

        results = {"#48 official color dialog opens": f"PASS ({dialog[:3]!r})"}
        dlg_hwnd = dialog[3]
        foreground = winutil.force_set_foreground(dlg_hwnd)
        before = {window[3] for window in m8._visible_toplevels(session.pid)}
        owner_blocked = not wu.IsWindowEnabled(session.hwnd)
        outside = (contains(winutil.window_rect(session.hwnd), probe)
                   and not contains(dialog[2], probe) and bool(wu.IsChild(session.hwnd, probe_hwnd)))
        hit = winutil.window_from_screen_point(*probe)
        sent = winutil.real_click_screen(*probe) if outside else 0
        time.sleep(0.8)
        after = {window[3] for window in m8._visible_toplevels(session.pid)}
        remained = dlg_hwnd in after
        still_blocked = not wu.IsWindowEnabled(session.hwnd)
        active = wu.GetForegroundWindow()
        active_pid = winutil._window_pid(active) if active else None
        cursor = POINT()
        cursor_on_chip = (wu.GetCursorPos(byref(cursor))
                          and contains(background["swatch"], (cursor.x, cursor.y)))
        same_preset = winutil.window_title(background["combo"][2]).strip() == background["combo"][0]
        other_orca_foreground = active_pid == session.pid and active != dlg_hwnd
        focus_ready = winutil.force_set_foreground(dlg_hwnd)
        keys = request_background_focus(session.hwnd, probe_hwnd) if focus_ready else None
        modal_keys = (keys is not None and keys[0] == dlg_hwnd
                      and (keys[1] == dlg_hwnd or bool(wu.IsChild(dlg_hwnd, keys[1]))))
        detail = (f"outside={outside}, real mouse events={sent}, foreground before={foreground}, "
                  f"cursor={(cursor.x, cursor.y)}, desktop hit={hit:#x}, foreground after={active:#x} "
                  f"(pid={active_pid}, dialog={dlg_hwnd:#x}), same dialog visible={remained}, "
                  f"owner disabled before/after={owner_blocked}/{still_blocked}, "
                  f"same background preset={same_preset}, new Orca windows={len(after - before)}, "
                  f"background active/focus request={keys!r}, modal retains focus={modal_keys}")
        passed = (outside and sent == 2 and foreground and cursor_on_chip and remained
                  and owner_blocked and still_blocked and same_preset
                  and not other_orca_foreground and not (after - before) and modal_keys)
        results["#48 modal dialog blocks background chip"] = (
            f"{'PASS' if passed else 'FAIL'} ({detail})")
        results["#48 header has color card, name and SKU"] = (
            verify_header(dialog) if remained else "FAIL (dialog closed before header read)")
        results["#48 same background chip works after Cancel"] = (
            verify_background_reenabled(session, dialog, probe, probe_hwnd)
            if remained else "FAIL (dialog closed during the outside click)")
        return m7.m7_verdict(results)
    finally:
        winutil.demote_window(session.hwnd)
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
