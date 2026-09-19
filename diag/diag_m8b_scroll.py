#!/usr/bin/env python3
"""diag_m8b_scroll.py — find a scroll primitive for the self-drawn preset
popup. 09-19 walk fact: click-probe covers the first ~10 rows and stalls at
the bottom-visible row; WM_MOUSEWHEEL to the popup TOP-LEVEL does nothing.
This diag enumerates the popup's inner children and tries wheel/keydown on
each, plus a row9-always walk, reading the combo text after each probe.

    C:\\Python311\\python.exe diag\\diag_m8b_scroll.py
"""
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import export_util, winutil  # noqa: E402

LOG = "[dscroll]"


def open_popup(session, cx, cy):
    winutil.user32.SetForegroundWindow(session.hwnd)
    time.sleep(0.4)
    winutil.msg_click_screen(cx, cy, session.hwnd)
    return export_util.wait_popup(session.pid, timeout_s=4.0)


def click_row(popup, row):
    pr = popup[2]
    winutil.msg_click_screen((pr[0] + pr[2]) // 2, pr[1] + 14 + row * 28)
    time.sleep(0.9)


def wheel_at(hwnd, x, y, notches=3):
    wp = ((-120 * notches) & 0xFFFF) << 16
    lp = (y << 16) | (x & 0xFFFF)
    winutil.user32.PostMessageW(hwnd, 0x020A, wp, lp)
    time.sleep(0.4)


def key_to(hwnd, vk, repeat=1):
    for _ in range(repeat):
        winutil.msg_key(hwnd, vk)
        time.sleep(0.25)


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        if not m8.wait_arrival(session)[0]:
            return 1
        m7.ensure_maximized(session)
        time.sleep(1.0)

        slots = m8.filament_slots(session)
        hit = next(s for s in slots if s["slot"] == 2)
        _text, rect, _ch = hit["combo"]
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        start = m8.combo_text(hit["combo"][2])
        print(f"{LOG} start: {start!r}")

        VK_DOWN, VK_NEXT, VK_END = 0x28, 0x22, 0x23

        # --- method A: wheel on popup + each inner child ----------------
        popup = open_popup(session, cx, cy)
        if not popup:
            print(f"{LOG} popup missing")
            return 1
        pr = popup[2]
        print(f"{LOG} popup rect: {pr}")
        kids = export_util._children_texts(popup[3])
        print(f"{LOG} popup children ({len(kids)}):")
        targets = [("popup", popup[3])]
        for t, r, ch in kids:
            cls = ctypes.create_unicode_buffer(64)
            winutil.user32.GetClassNameW(ch, cls, 64)
            print(f"{LOG}   hwnd=0x{ch:x} cls={cls.value!r} txt={t!r} rect={r}")
            targets.append((f"child0x{ch:x}", ch))
        m7.dismiss_menus(session)
        time.sleep(0.5)

        for name, hwnd in targets:
            popup = open_popup(session, cx, cy)
            if not popup:
                print(f"{LOG} A/{name}: popup missing")
                continue
            pr = popup[2]
            wx = (pr[0] + pr[2]) // 2
            wy = (pr[1] + pr[3]) // 2
            wheel_at(hwnd, wx, wy)
            click_row(popup, 8)
            now = m8.combo_text(hit["combo"][2])
            print(f"{LOG} A wheel({name}) -> row8: {now!r}")
            if now != start and "Silk" not in now:
                break

        # --- method B: VK keys on popup + each child ---------------------
        for name, hwnd in targets[:3]:
            popup = open_popup(session, cx, cy)
            if not popup:
                print(f"{LOG} B/{name}: popup missing")
                continue
            key_to(hwnd, VK_END)
            key_to(hwnd, 0x0D)  # VK_RETURN
            time.sleep(0.6)
            now = m8.combo_text(hit["combo"][2])
            print(f"{LOG} B VK_END+RET({name}) -> {now!r}")
            if "Rainbow" in now:
                break

        # --- method C: row9-always walk ----------------------------------
        for attempt in range(14):
            popup = open_popup(session, cx, cy)
            if not popup:
                print(f"{LOG} C a{attempt}: popup missing")
                continue
            click_row(popup, 9)
            now = m8.combo_text(hit["combo"][2])
            print(f"{LOG} C a{attempt} row9: {now!r}")
            if "Rainbow" in now:
                break
        print(f"{LOG} final: {m8.combo_text(hit['combo'][2])!r}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
