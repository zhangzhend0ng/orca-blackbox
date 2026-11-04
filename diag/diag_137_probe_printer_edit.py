#!/usr/bin/env python3
"""diag_137_probe_printer_edit.py — #137's surface, per the tester's correction:
NOT a machine switch — the machine stays Snapmaker U1 — but the **edit control to
the right of the printer name** (the pencil icon). The Standard / High Flow tabs
live in there (high flow is a nozzle attribute, so the printer/nozzle editor is
where its per-mode parameters are edited).

Read-only: click the pencil, dump every child text + the tab strip, screenshot,
then close.

    C:\\Python311\\python.exe diag\\diag_137_probe_printer_edit.py
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

from harness import export_util, mixing_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d137pe]"
OUT = HERE / "artifacts" / "m8x_137"


def screen_bgr():
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def shot(name):
    img = screen_bgr()
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / (name if name.endswith(".png") else name + ".png")), img)
    print(f"{LOG} shot -> {name}")


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
        shot("60_sidebar")

        # the pencil/edit control right of the printer name (measured: (374,145)-(387,159)
        # on the maximized layout; locate it structurally as the small button on the
        # Printer row instead of hardcoding)
        kids = export_util._children_texts(session.hwnd)
        row = next(((t.strip(), r) for t, r, _h in kids
                    if "Snapmaker U1" in t and r[1] < 200), None)
        print(f"{LOG} printer row: {row}")
        cands = [(r, h) for t, r, h in kids
                 if winutil.window_class(h) in ("Button", "wxWindowNR")
                 and (r[2] - r[0]) in range(10, 30) and (r[3] - r[1]) in range(10, 30)
                 and 130 <= r[1] <= 175 and r[0] > 300]
        print(f"{LOG} small controls on the printer row: {[r for r, _h in cands]}")
        target = sorted(cands, key=lambda c: -c[0][0])[0][0] if cands else None
        if not target and row:
            target = (row[1][2] + 6, row[1][1] + 4, row[1][2] + 24, row[1][3] - 4)
        print(f"{LOG} clicking the printer edit control at {target}")
        if target:
            cx, cy = (target[0] + target[2]) // 2, (target[1] + target[3]) // 2
            sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.8)
            shot("61_after_click")
            tops = [(c, t, r2) for c, t, r2, _h in mixing_util.toplevel(session.pid) if t]
            print(f"{LOG} new toplevels: {[x for x in tops if x[0] != 'wxWindowNR'][:6]}")
            dlg = export_util.wait_toplevel(
                session.pid, lambda c, t, r2: c == "#32770", timeout_s=4.0)
            if dlg:
                print(f"{LOG} dialog {dlg[0]!r} {dlg[1]!r} rect={dlg[2]}")
                dtxt = [t.strip() for t, _r, _h in export_util._children_texts(dlg[3]) if t.strip()]
                print(f"{LOG} dialog texts ({len(dtxt)}): {dtxt[:40]}")
                shot("62_dialog", dlg[2])
                from harness import mix_dialog_util as mdu
                x0, y0, x1, y1 = dlg[2]
                words = [w for w, *_ in mdu.ocr_words_img(screen_bgr()[y0:y1, x0:x1],
                                                         scale=2, psm=6)]
                print(f"{LOG} dialog OCR: {' '.join(words)[:300]!r}")
                flows = [(i, w) for i, w in enumerate(words)
                         if w.lower() in ("standard", "high", "flow")]
                print(f"{LOG} flow-ish words: {flows}")
            else:
                print(f"{LOG} no #32770 dialog appeared")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
