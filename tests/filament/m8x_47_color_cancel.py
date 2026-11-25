#!/usr/bin/env python3
# m8x_47_color_cancel.py — 飞书基线 #47：选另一色、取消、重开读回原色
# feishu: baseline#47

import argparse
import time

from m8b_official_color import (MIXED_3MF, add_common_args, boot_session,
                                check_cancel_keeps_color, is_native_picker, m7, m8)
from harness import winutil


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF).parse_args()
    session = boot_session(args, model=args.model)
    try:
        arrived, _ = m8.wait_arrival(session)
        if not arrived:
            return m7.m7_verdict({"#47 cancel keeps color": "FAIL (fixture did not load)"})
        m7.ensure_maximized(session)

        def open_slot_color(tag):
            # The fixture carries Generic PETG in slot 1. The numbered chip's
            # GetWindowRect is already in screen coordinates.
            hit = next((row for row in m8.wait_slots(session) if row["slot"] == 1), None)
            if not hit or not hit["combo"] or "Generic PETG" not in hit["combo"][0]:
                return None
            x0, y0, x1, y1 = hit["swatch"]
            x, y = (x0 + x1) // 2, (y0 + y1) // 2
            winutil.real_click_screen(x, y)
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                for dialog in m8._visible_toplevels(session.pid):
                    if dialog[0] == "#32770" and is_native_picker(dialog):
                        print(f"[m8x47] {tag}: slot=1 preset={hit['combo'][0]!r} "
                              f"chip={hit['swatch']} picker={dialog[1]!r}")
                        return dialog
                time.sleep(0.25)
            return None

        result = check_cancel_keeps_color(session, open_slot_color)
        return m7.m7_verdict({"#47 cancel keeps color": result})
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
