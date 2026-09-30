#!/usr/bin/env python3
"""diag_137_probe_marker.py — recon for baseline #137 (三类配置里“有流量喷嘴标志”
的参数：带标志的两模式独立、不带标志的同步变更).

Questions this probe answers, READ-ONLY (nothing is written):
  * where the PROCESS settings are edited (same slot-row menu route as the
    filament editor?), and what the dialog/dump looks like;
  * whether the "flow nozzle" marker is visible in the UI at all — a per-row icon
    would show up as a small child control or a painted glyph, so the screenshot
    is the evidence;
  * which settings keys look flow-marked (the app's profile JSONs).

    C:\Python311\python.exe diag\diag_137_probe_marker.py
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

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d137]"
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


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives={ok} ({frac:.3%})")
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        # the sidebar rows: filaments (1..5) + Process + others; list the small
        # row buttons so the process editor entry can be identified
        kids = export_util._children_texts(session.hwnd)
        rows = [(t.strip(), r, winutil.window_class(h)) for t, r, h in kids
                if t.strip() and r[0] < 520]
        print(f"{LOG} sidebar texts (x<520): {[(t, r) for t, r, _c in rows][:24]}")
        shot("01_sidebar")
        # process row button: a 16x26 button on the Process row (the sidebar shows
        # a preset name like '0.40mm Standard @Snapmaker U1 (0.8 n...')
        proc = next((t for t, _r, _c in rows if "0.40mm" in t or "Standard @" in t), None)
        print(f"{LOG} process preset text: {proc!r}")
        flow = next((t for t, _r, _c in rows if "flow" in t.lower()), None)
        print(f"{LOG} flow-ish text: {flow!r}")

        # --- process parameter rows (the sidebar's settings section) ---------
        band = [(t, r, winutil.window_class(h)) for t, r, h in kids
                if t.strip() and 640 <= r[1] <= 1032 and r[0] < 520]
        print(f"{LOG} process band controls ({len(band)}):")
        for t, r, c in band[:40]:
            print(f"{LOG}   {c!r:14s} {t.strip()[:34]!r:38s} rect={r}")
        shot("02_process_panel")

        # --- the Process row's own button -> menu -> Edit ---------------------
        btns = [(t.strip(), r, h) for t, r, h in kids
                if winutil.window_class(h) == "Button"
                and (r[2] - r[0]) in range(14, 20) and (r[3] - r[1]) in range(24, 30)]
        print(f"{LOG} row buttons: {[(t, r) for t, r, _h in btns]}")
        # the Process row sits above the settings section: pick the button whose
        # y is in 595..640 (measured 09-28: Process row buttons at y 604..630)
        pr = next((r for _t, r, _h in btns if 595 <= r[1] <= 641), None)
        if pr:
            cx, cy = (pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.25)
            winutil.real_click_screen(cx, cy)
            time.sleep(1.2)
            menu = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32768",
                                            timeout_s=4.0)
            if menu:
                shot("03_process_menu", menu[2])
                mrect = menu[2]
                print(f"{LOG} process menu rect={mrect}")
                winutil.user32.SetCursorPos(mrect[0] + 20, mrect[1] + 12)
                time.sleep(0.2)
                winutil.real_click_screen(mrect[0] + 20, mrect[1] + 12)
                time.sleep(1.5)
                dlg = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770",
                                               timeout_s=6.0)
                if dlg:
                    print(f"{LOG} editor dialog: {dlg[0]!r} {dlg[1]!r} rect={dlg[2]}")
                    dtxt = [t.strip() for t, _r, _h in export_util._children_texts(dlg[3]) if t.strip()]
                    print(f"{LOG} editor texts ({len(dtxt)}): {dtxt[:36]}")
                    shot("04_process_editor", dlg[2])
                    from harness import mix_dialog_util as mdu
                    x0, y0, x1, y1 = dlg[2]
                    crop = screen_bgr()[y0:y1, x0:x1]
                    words = [w for w, *_ in mdu.ocr_words_img(crop, scale=2)]
                    print(f"{LOG} editor OCR ({len(words)}): {' '.join(words)[:280]!r}")
                else:
                    print(f"{LOG} no #32770 after the process menu row")
            else:
                print(f"{LOG} process row button opened no menu")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
