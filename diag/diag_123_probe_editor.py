#!/usr/bin/env python3
"""diag_123_probe_editor.py — recon for baseline #123 (修改耗材预设的软化温度 →
温类归类 → GCode 更新). READ-ONLY: it opens the filament editor, dumps every
child control (text + rect + class) and screenshots it, then cancels. Nothing
is written.

What it must answer:
  * which UI entry opens the filament preset editor (the slot row's #32768 menu
    'Edit' → 'Material settings'? the sidebar gear? a topbar dialog?)
  * the control that carries temperature_vitrification (the gcode echoes
    `; temperature_vitrification = 70,45,45,45,45`, and the topcap class rule is
    <=50 → 强冷 MODE=1, >50 → 保温 MODE=3) — its label, rect, class and whether
    it is an Edit/ComboBox
  * how a change is committed (OK / 保存 / a "save preset" prompt)

    C:\\Python311\\python.exe diag\\diag_123_probe_editor.py
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

LOG = "[d123]"
OUT = HERE / "artifacts" / "m8x_123"


def screen_bgr():
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def dump(hwnd, tag):
    kids = export_util._children_texts(hwnd)
    print(f"{LOG} {tag}: {len(kids)} children")
    for t, r, h in kids:
        cls = winutil.window_class(h)
        w, hh = r[2] - r[0], r[3] - r[1]
        if t.strip() or cls in ("Edit", "ComboBox", "Button", "Static"):
            print(f"{LOG}   {cls!r:16s} {t.strip()[:48]!r:52s} rect={r} size={w}x{hh}")


def shot(name, rect=None):
    img = screen_bgr()
    if rect:
        img = img[max(0, rect[1] - 10):rect[3] + 10, max(0, rect[0] - 10):rect[2] + 10]
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / name), img)
    print(f"{LOG} shot -> {name} {img.shape[1]}x{img.shape[0]}")


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives={ok} colored_frac={frac:.3%}")
        m7.ensure_maximized(session)
        m8.wait_slots(session)          # sidebar readiness (see m8_common)
        time.sleep(1.0)

        slots = m8.filament_slots(session)
        print(f"{LOG} slots: {[(s['slot'], (s['combo'] or [None])[0]) for s in slots]}")
        hit = next((s for s in slots if s["slot"] == 2), None)
        if not hit or not hit.get("picker"):
            print(f"{LOG} FAIL: slot 2 has no row button")
            return 1

        # --- path A: the slot row's small button -> #32768 menu -----------------
        r = hit["picker"]
        sx, sy = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2,
                                          (r[1] + r[3]) // 2)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.25)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        menu = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32768",
                                         timeout_s=4.0)
        if not menu:
            print(f"{LOG} row-button click opened no menu")
        else:
            shot("01_slot_menu.png", menu[2])
            rows = m7.list_menu(menu[3])
            print(f"{LOG} menu rows via HMENU: {[(i, l) for i, l in rows]}")
            mrect = menu[2]
            # This menu is a wx popup whose HMENU enumeration comes back EMPTY,
            # so rows are addressed geometrically. Measured 09-28 (screenshot
            # 01_slot_menu.png + the Delete-confirm it produced): 3 rows Edit /
            # Delete / Merge with, ~24px each — the middle of the menu is
            # DELETE. The first row sits at menu.top + 12, and its left edge is
            # clicked because a 'Click to edit preset' TOOLTIP is drawn over the
            # row's text area.
            cx, cy = mrect[0] + 20, mrect[1] + 12
            print(f"{LOG} menu rect={mrect}; clicking row 0 (Edit) at ({cx},{cy})")
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            winutil.real_click_screen(cx, cy)
            time.sleep(1.5)

        # --- whatever dialog came up: dump everything --------------------------
        dlg = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770",
                                       timeout_s=6.0)
        if not dlg:
            print(f"{LOG} no #32770 after the menu row")
            return 1
        print(f"{LOG} dialog class={dlg[0]!r} title={dlg[1]!r} rect={dlg[2]}")
        kids_all = export_util._children_texts(dlg[3])
        warning = any("deleting this filament" in t.lower() for t, _r, _h in kids_all)
        if warning:
            print(f"{LOG} WRONG ROW: this is the DELETE confirmation — cancelling")
        dump(dlg[3], "dialog")
        shot("02_dialog.png", dlg[2])
        # look for the vitrification field by label
        kids = export_util._children_texts(dlg[3])
        hits = [(t, r2, h) for t, r2, h in kids
                if any(k in t.lower() for k in ("vitrif", "glass", "soften", "软化",
                                                "温度", "temperature"))]
        print(f"{LOG} temperature-ish labels: "
              f"{[(t.strip(), r2, winutil.window_class(h)) for t, r2, h in hits][:12]}")
        # cancel (read-only recon)
        for t, r2, h in kids:
            if t.strip().lower() in ("cancel", "取消"):
                winutil.msg_click_screen((r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2, h)
                print(f"{LOG} cancelled the dialog")
                break
        time.sleep(0.8)
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
