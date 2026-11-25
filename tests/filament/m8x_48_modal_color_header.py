#!/usr/bin/env python3
# m8x_48_modal_color_header.py — 飞书基线 #48：验证官方色盘的模态和头部布局
# feishu: baseline#48

import argparse
import time

import numpy as np

from m8b_official_color import MIXED_3MF, add_common_args, boot_session, click_cancel, m7, m8
from harness import export_util, winutil

LOG = "[m8x48]"
NAME = "Mint Lemonade"
SKU = "sku 34205"
# The fixture's official PLA Silk color carries these two catalog colors.
CARD_BGR = ((23, 237, 236), (229, 173, 68))


def center(rect):
    x0, y0, x1, y1 = rect
    return (x0 + x1) // 2, (y0 + y1) // 2


def contains(rect, point):
    x0, y0, x1, y1 = rect
    x, y = point
    return x0 <= x < x1 and y0 <= y < y1


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
    print(f"{LOG} visible dialog labels={children!r}")
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
    image = m8._screen_crop(*card_rect)
    if image.size == 0:
        return f"FAIL (preview area outside the desktop: {card_rect})"
    pixels = image.astype(np.int16)
    shares = tuple(float((np.abs(pixels - color).max(axis=2) <= 16).mean())
                   for color in CARD_BGR)
    detail = (f"name={NAME!r} at {name}, {SKU!r} at {sku}, preview={card_rect}, "
              f"catalog pixel shares={tuple(round(v, 3) for v in shares)}")
    return f"{'PASS' if min(shares) >= 0.08 else 'FAIL'} ({detail})"


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

        winutil.force_set_foreground(session.hwnd)
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
        outside = not contains(dialog[2], probe)
        sent = winutil.real_click_screen(*probe) if outside else 0
        time.sleep(0.8)
        after = {window[3] for window in m8._visible_toplevels(session.pid)}
        remained = dlg_hwnd in after
        still_blocked = not wu.IsWindowEnabled(session.hwnd)
        restored = wu.GetForegroundWindow() == dlg_hwnd
        detail = (f"outside={outside}, real mouse events={sent}, foreground before={foreground}, "
                  f"dialog foreground after={restored}, same dialog visible={remained}, "
                  f"owner disabled before/after={owner_blocked}/{still_blocked}, "
                  f"new Orca windows={len(after - before)}")
        passed = (outside and sent == 2 and foreground and restored and remained
                  and owner_blocked and still_blocked and not (after - before))
        results["#48 modal dialog blocks background chip"] = (
            f"{'PASS' if passed else 'FAIL'} ({detail})")
        results["#48 header has color card, name and SKU"] = (
            verify_header(dialog) if remained else "FAIL (dialog closed before header read)")
        if remained:
            click_cancel(dialog)
            print(f"{LOG} cleanup: dialog visible={bool(wu.IsWindowVisible(dlg_hwnd))}, "
                  f"owner enabled={bool(wu.IsWindowEnabled(session.hwnd))}")
        return m7.m7_verdict(results)
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
