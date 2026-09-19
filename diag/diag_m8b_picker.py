#!/usr/bin/env python3
"""diag_m8b_picker.py — identify the TRUE clr_picker in the sidebar slot row.

09-19 evidence: the rect filament_slots() returned as 'picker' is the "…"
row button (opens the Edit/Delete/Merge-with menu → preset settings editor,
NOT FilamentColorDialog). Source says the clr_picker (20x20 wxBitmapButton,
tooltip 'Click to select filament color') opens FilamentColorDialog DIRECTLY
(PresetComboBoxes.cpp:912->1086). Hypothesis: the colored chip left of the
combo IS that button. This diag real-clicks the chip and dumps whatever
toplevel + child tree appears.

    C:\\Python311\\python.exe diag\\diag_m8b_picker.py
"""
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

import cv2  # noqa: E402

from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import export_util, mixing_util, winutil  # noqa: E402

LOG = "[dpick]"
OUT = HERE / "artifacts" / "m8b_diag"
WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def descendants(parent):
    """[(class, text, rect, ctrl_id, hwnd)] for every descendant of parent."""
    out = []
    user32 = winutil.user32

    def cb(hwnd, _lp):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(hwnd, txt, 128)
        rc = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        cid = user32.GetDlgCtrlID(hwnd)
        out.append((cls.value, txt.value,
                    (rc.left, rc.top, rc.right, rc.bottom), cid, hwnd))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), WNDENUM(cb), 0)
    return out


def toplevels(pid):
    return [(c, t, r, h) for c, t, r, h in mixing_util.toplevel(pid)]


def main() -> int:
    ap = __import__("argparse").ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=MIXED_3MF)
    try:
        ok, frac = m8.wait_arrival(session)
        if not ok:
            print(f"{LOG} arrival FAIL ({frac:.2%})")
            return 1
        m7 = __import__("m7_common", fromlist=["ensure_maximized"])
        m7.ensure_maximized(session)
        time.sleep(1.0)

        # 1) dump every descendant in the filament-rows band, with classes
        print(f"{LOG} --- slot-band children (y 395-545, x<440) ---")
        for cls, txt, rect, _cid, ch in descendants(session.hwnd):
            if not (395 <= rect[1] <= 545 and rect[0] < 440):
                continue
            print(f"{LOG} hwnd=0x{ch:x} cls={cls!r} txt={txt!r} rect={rect} id={_cid}")

        # cluster rows by y-center within 14px, identify chips vs combos
        slots = m8.filament_slots(session)
        print(f"{LOG} parsed slots: {[(s['slot'], s['combo'][0][:28] if s['combo'] else None, s['picker']) for s in slots]}")
        hit = next((s for s in slots if s["slot"] == 2), None)
        if not hit:
            print(f"{LOG} slot2 missing")
            return 1

        # candidate points: chip = left of combo; parsed 'picker'; right of combo
        combo_rect = hit["combo"][1]
        cy = (combo_rect[1] + combo_rect[3]) // 2
        candidates = {
            "chip(left-of-combo-20px)": (combo_rect[0] - 22, cy),
            "parsed_picker": hit["picker"] and
                             ((hit["picker"][0] + hit["picker"][2]) // 2, cy),
        }
        for name, (px, py) in candidates.items():
            if px is None:
                continue
            before = {h for _c, _t, _r, h in toplevels(session.pid)}
            sx, sy = winutil.client_to_screen(session.hwnd, px, py)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
            print(f"{LOG} clicked {name} client({px},{py}) screen({sx},{sy})")
            new = None
            deadline = time.time() + 5.0
            while time.time() < deadline and not new:
                time.sleep(0.4)
                for c, t, r, h in toplevels(session.pid):
                    if h in before or h == session.hwnd:
                        continue
                    if not winutil.user32.IsWindowVisible(h):
                        continue
                    new = (c, t, r, h)
                    break
            if not new:
                print(f"{LOG} {name}: NO new toplevel")
                continue
            c, t, r, h = new
            print(f"{LOG} {name}: NEW toplevel cls={c!r} title={t!r} rect={r}")
            img = __import__("m1_minimal_loop",
                             fromlist=["capture_bgr"]).capture_bgr(session)
            cv2.imwrite(str(OUT / f"picker_{name.split('(')[0]}.png"), img)
            kids = descendants(h)
            print(f"{LOG} dialog descendants ({len(kids)}):")
            for k in kids[:40]:
                print(f"{LOG}   cls={k[0]!r} txt={k[1]!r} rect={k[2]} id={k[3]}")
            # try pressing OK by descendant ctrl-id 5100
            ok_btn = next((k for k in kids if k[3] == 5100), None)
            cancel_btn = next((k for k in kids if k[3] == 5101), None)
            print(f"{LOG} id5100={ok_btn and (ok_btn[0], ok_btn[1], ok_btn[2])}")
            print(f"{LOG} id5101={cancel_btn and (cancel_btn[0], cancel_btn[1], cancel_btn[2])}")
            if ok_btn:
                r2 = ok_btn[2]
                winutil.msg_click_screen((r2[0] + r2[2]) // 2,
                                         (r2[1] + r2[3]) // 2)
                time.sleep(1.2)
                gone = not winutil.user32.IsWindowVisible(h)
                print(f"{LOG} msg_click id5100 -> dialog gone: {gone}")
                if not gone:
                    winutil.user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
                    time.sleep(0.8)
            else:
                winutil.user32.PostMessageW(h, 0x0010, 0, 0)
                time.sleep(0.8)
        print(f"{LOG} done")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
