#!/usr/bin/env python3
# m8x_46_color_confirm.py — 飞书基线 #46：选另一色、确定、重开读回新色
# feishu: baseline#46

import argparse
import time

from m8b_official_color import (MIXED_3MF, add_common_args, boot_session,
                                click_cancel, is_native_picker, m7, m8, read_rgb,
                                select_native_color)
from harness import export_util, winutil


def open_slot_picker(session, stage):
    slot = next((row for row in m8.wait_slots(session) if row["slot"] == 1), None)
    if not slot or not slot["combo"] or "Generic PETG" not in slot["combo"][0]:
        print(f"[m8x46] {stage}: expected Generic PETG in slot 1, found {slot!r}")
        return None

    x0, y0, x1, y1 = slot["swatch"]
    x, y = (x0 + x1) // 2, (y0 + y1) // 2
    target = winutil.deepest_child_at(session.hwnd, x, y)
    if winutil.window_title(target).strip() != "1":
        print(f"[m8x46] {stage}: chip {slot['swatch']} did not resolve to button 1")
        return None

    existing = {dialog[3] for dialog in m8._visible_toplevels(session.pid)}
    winutil.msg_click_screen(x, y, session.hwnd)
    print(f"[m8x46] {stage}: slot=1 preset={slot['combo'][0]!r} chip={slot['swatch']}")
    deadline = time.monotonic() + 8.0
    observed = set()
    while time.monotonic() < deadline:
        for dialog in m8._visible_toplevels(session.pid):
            if dialog[3] not in existing and dialog[0] == "#32770" and is_native_picker(dialog):
                print(f"[m8x46] {stage}: picker={dialog[1]!r} hwnd={dialog[3]:#x}")
                return dialog
            observed.add(dialog[:2])
        time.sleep(0.25)
    print(f"[m8x46] {stage}: no new native picker, windows={sorted(observed)}")
    return None


def current_rgb(session, dialog):
    rgb = read_rgb(session, dialog)
    if rgb is None or any(not (field.isascii() and field.isdecimal()) for field in rgb):
        return None
    channels = tuple(int(field) for field in rgb)
    return channels if all(0 <= value <= 255 for value in channels) else None


def click_ok(dialog):
    for text, rect, hwnd in export_util._children_texts(dialog[3]):
        if (text.replace("&", "").strip().casefold() == "ok"
                and winutil.window_class(hwnd).casefold() == "button"
                and winutil.user32.IsWindowVisible(hwnd)
                and winutil.user32.IsWindowEnabled(hwnd)):
            x0, y0, x1, y1 = rect
            winutil.msg_click_screen((x0 + x1) // 2, (y0 + y1) // 2, dialog[3])
            return True
    return False


def check_confirm_applies_color(session, results):
    dialog = open_slot_picker(session, "before confirm")
    before = current_rgb(session, dialog) if dialog else None
    if before is None:
        results["#46 color selection updates"] = "FAIL (slot 1 picker RGB missing)"
        return

    hsl_changed = select_native_color(dialog, tuple(map(str, before)))
    selected = current_rgb(session, dialog)
    changed = hsl_changed and selected is not None and selected != before
    results["#46 color selection updates"] = (
        f"{'PASS' if changed else 'FAIL'} (before={before}, selected={selected}, "
        f"hsl_changed={hsl_changed})")
    if not changed:
        return

    ok_clicked = click_ok(dialog)
    deadline = time.monotonic() + 6.0
    while ok_clicked and winutil.user32.IsWindowVisible(dialog[3]) and time.monotonic() < deadline:
        time.sleep(0.15)
    closed = not winutil.user32.IsWindowVisible(dialog[3])
    results["#46 OK closes the picker"] = (
        f"{'PASS' if ok_clicked and closed else 'FAIL'} "
        f"(ok_clicked={ok_clicked}, old_hwnd={dialog[3]:#x}, closed={closed})")
    if not (ok_clicked and closed):
        return

    reopened = open_slot_picker(session, "after confirm")
    fresh_picker = reopened is not None and reopened[3] != dialog[3]
    after = current_rgb(session, reopened) if fresh_picker else None
    results["#46 filament keeps the selected color"] = (
        f"{'PASS' if fresh_picker and after == selected else 'FAIL'} "
        f"(slot=1, fresh_picker={fresh_picker}, selected={selected}, reopened={after})")
    if reopened:
        click_cancel(reopened)


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF).parse_args()
    session = boot_session(args, model=args.model)
    results = {}
    try:
        arrived, _ = m8.wait_arrival(session)
        if not arrived:
            return m7.m7_verdict({"#46 fixture load": "FAIL"})
        m7.ensure_maximized(session)
        check_confirm_applies_color(session, results)
        return m7.m7_verdict(results)
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
