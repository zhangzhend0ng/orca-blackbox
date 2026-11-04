#!/usr/bin/env python3
"""diag_m8b_swatch_probe.py — which control in a slot row opens the OFFICIAL
filament colour dialog?

Why: m8b's click chain (slot clr_picker -> #32768 menu 'Edit' -> 'Material
settings' -> its 'colourpicker' child) lands on the NATIVE Windows color picker
on 2.4.0, while the user clicking the slot's colour swatch BY HAND gets the
official FilamentColorDialog (色卡库). So the automated path is probably hitting
the wrong control: m8_common.filament_slots() picks the 'picker' by SIZE among
the row's children (12-30 px, leftmost), which is a heuristic, not an identity.

Method: enumerate every child in the slot-2 row (rect + window class), then
click each candidate in turn and report what appears — a #32768 context menu
(with its rows), or a #32770 dialog (title + a native/official signature). One
click per candidate, everything closed between attempts.

    C:\\Python311\\python.exe diag\\diag_m8b_swatch_probe.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m8_common as m8  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[d8sw]"
OUT = HERE / "artifacts" / "m8b_swatch"


def save_screen(name: str):
    """Full desktop crop around the app - screen coords, so a rect taken from
    GetWindowRect can be cropped directly (the earlier stills mixed client and
    screen coordinates and landed on the viewport, measured 09-24)."""
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = np.frombuffer(buf, np.uint8).reshape(sh, sw, 4)
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / name), cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))
    print(f"{LOG}     shot -> {name}")


def dismiss_everything(session):
    """Close any menu/dialog left over from the previous click."""
    for _ in range(4):
        tops = m8._visible_toplevels(session.pid)
        menu = [t for t in tops if t[0] == "#32768"]
        dlg = [t for t in tops if t[0] == "#32770"]
        if not menu and not dlg:
            break
        for cls, title, rect, hwnd in menu:
            winutil.user32.PostMessageW(hwnd, 0x0011, 0, 0)   # WM_CANCELMODE
            time.sleep(0.3)
        for cls, title, rect, hwnd in dlg:
            print(f"{LOG}   closing dialog {title!r}")
            m8.close_dialog_by_button((cls, title, rect, hwnd), "Cancel")
            time.sleep(0.6)


def signature(hwnd):
    """'NATIVE picker' / 'other' from the dialog's child texts."""
    texts = [t.strip().lower() for t, _r, _h in export_util._children_texts(hwnd)]
    if any("basic colors" in t for t in texts):
        return "NATIVE Windows picker"
    sku_like = [t for t in texts if t and len(t) > 3 and not t.startswith("&")]
    return "OTHER (children: " + ", ".join(sku_like[:5]) + ")"


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives={ok} colored_frac={frac:.3%}")
        time.sleep(1.5)

        rows = list(export_util._children_texts(session.hwnd))
        anchor = next((r for t, r, _c in rows if t.strip() == "Filaments"), None)
        print(f"{LOG} 'Filaments' label rect: {anchor}")
        lo, hi = (anchor[1] - 20, anchor[1] + 260) if anchor else (395, 540)
        band = [(t.strip(), r, winutil.window_class(h), h)
                for t, r, h in rows if lo <= r[1] <= hi and r[0] < 500]
        print(f"{LOG} children in the filament band: {len(band)}")
        for t, r, cls, h in band:
            w, hh = r[2] - r[0], r[3] - r[1]
            print(f"{LOG}   {cls!r:22s} rect={r} size={w}x{hh} text={t[:28]!r}")

        chip = next(((t, r) for t, r, _c, _h in band
                     if t.strip() == "2" and (r[2] - r[0]) < 26), None)
        if not chip:
            print(f"{LOG} FAIL: no '2' chip found — cannot isolate the row")
            return 1
        cy = (chip[1][1] + chip[1][3]) / 2
        print(f"{LOG} slot-2 row centre y={cy:.0f}")

        cands = [(t, r, cls, h) for t, r, cls, h in band
                 if abs(((r[1] + r[3]) / 2) - cy) < 14          # same row
                 and (r[2] - r[0]) <= 40 and (r[3] - r[1]) <= 40]  # small widget
        print(f"{LOG} candidates in the slot-2 row: {len(cands)}")
        for i, (t, r, cls, h) in enumerate(cands, start=1):
            cx, cyy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            sx, sy = winutil.client_to_screen(session.hwnd, cx, cyy)
            print(f"{LOG} [{i}] click {cls!r} rect={r} at screen ({sx},{sy}) text={t!r}")
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.6)
            tops = m8._visible_toplevels(session.pid)
            menu = [x for x in tops if x[0] == "#32768"]
            dlg = [x for x in tops if x[0] == "#32770"]
            if menu or dlg:
                save_screen(f"cand{i}_{'menu' if menu else 'dialog'}.png")
            if menu:
                for cls2, title2, rect2, hwnd2 in menu:
                    items = m7.list_menu(hwnd2)
                    print(f"{LOG}     -> MENU {rect2} rows={[(i2, l2) for i2, l2 in items][:6]}")
            if dlg:
                for cls2, title2, rect2, hwnd2 in dlg:
                    print(f"{LOG}     -> DIALOG title={title2!r} rect={rect2} "
                          f"sig={signature(hwnd2)}")
            if not menu and not dlg:
                print(f"{LOG}     -> nothing appeared")
            dismiss_everything(session)
            time.sleep(0.8)
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
