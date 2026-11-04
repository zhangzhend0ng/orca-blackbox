#!/usr/bin/env python3
"""diag_137_probe_editor_flow.py — #137: the FILAMENT editor's flow control.

The two-surface probe found a child text `[Standard flow]` inside slot 2's
'Material settings' editor — the tester's "编辑耗材有标准和高流量的tab". This
probe pins down that control: screenshot, its rect and neighbours, and what
clicking it does (does it switch to a High Flow variant? open a list?).

    C:\\Python311\\python.exe diag\\diag_137_probe_editor_flow.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d137ef]"
OUT = HERE / "artifacts" / "m8x_137"


def screen_bgr():
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def shot(name, rect=None):
    img = screen_bgr()
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / (name if name.endswith(".png") else name + ".png")), img)
    print(f"{LOG} shot -> {name}")


def open_editor(session):
    slots = m8.wait_slots(session)
    hit = next((s for s in slots if s["slot"] == 2), None)
    r = hit["picker"]
    sx, sy = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    time.sleep(1.2)
    menu = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32768", timeout_s=4.0)
    if not menu:
        return None
    mr = menu[2]
    winutil.user32.SetCursorPos(mr[0] + 20, mr[1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(mr[0] + 20, mr[1] + 12)
    time.sleep(1.6)
    return export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770", timeout_s=6.0)


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrives={ok} ({frac:.3%})")
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        dlg = open_editor(session)
        if not dlg:
            print(f"{LOG} FAIL: editor did not open")
            return 1
        print(f"{LOG} editor {dlg[0]!r} {dlg[1]!r} rect={dlg[2]}")
        kids = export_util._children_texts(dlg[3])
        print(f"{LOG} children: {len(kids)}")
        for t, r, h in kids:
            tt = t.strip()
            if tt and (("flow" in tt.lower()) or (r[3] - r[1]) > 0 and tt in
                       ("Filament", "Cooling", "Setting Overrides")):
                print(f"{LOG}   {winutil.window_class(h)!r:12s} {tt!r:24s} rect={r}")
        flow = [(t.strip(), r, h) for t, r, h in kids if "flow" in t.strip().lower()]
        shot("80_editor")
        if flow:
            t, r, h = flow[0]
            print(f"{LOG} flow control: {t!r} rect={r} class={winutil.window_class(h)!r}")
            shot("81_flow_control", (r[0] - 40, r[1] - 20, r[2] + 260, r[3] + 20))
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.25)
            winutil.real_click_screen(cx, cy)
            time.sleep(1.5)
            shot("82_after_click")
            tips = [(c, tt, rr) for c, tt, rr, _h in m8._visible_toplevels(session.pid)
                    if c != "wxWindowNR" or tt]
            print(f"{LOG} toplevels after the click: {tips[:6]}")
            after = [t.strip() for t, _r, _h in export_util._children_texts(dlg[3])
                     if t.strip() and "flow" in t.strip().lower()]
            print(f"{LOG} flow-ish texts after the click: {after}")
            words = [w for w, *_ in mdu.ocr_words_img(
                screen_bgr()[dlg[2][1]:dlg[2][3], dlg[2][0]:dlg[2][2]], scale=2, psm=6)]
            print(f"{LOG} editor OCR: {' '.join(words)[:240]!r}")
        for t, r, _h in kids:
            if t.strip().lower() in ("cancel", "取消"):
                cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                winutil.user32.SetCursorPos(cx, cy)
                time.sleep(0.2)
                winutil.real_click_screen(cx, cy)
                break
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
