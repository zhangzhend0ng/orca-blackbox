#!/usr/bin/env python3
"""diag_137_probe_two_surfaces.py — #137 after the doc correction:

  耗材丝配置 and 工艺配置 carry the Standard / High Flow tabs (the PRINTER config
  does not). The one knob not yet tried is the NOZZLE DIAMETER (0.4mm) — the
  tester said 0.4 is required for high flow, and switching the diameter is a
  nozzle setting, not a machine-model change (机型始终用 U1).

Probe, read-only apart from the nozzle combo:
  1. set the sidebar nozzle Diameter to 0.4mm (verified by its own readback);
  2. open slot 2's filament editor ('Material settings' via the row menu → Edit)
     and dump its TAB strip — looking for Standard / High Flow;
  3. dump the process panel's tab strip as well;
  4. screenshots of both.

    C:\\Python311\\python.exe diag\\diag_137_probe_two_surfaces.py
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

LOG = "[d137two]"
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


def sidebar_rows(session, y0, y1):
    return sorted([(t.strip(), r) for t, r, _h in export_util._children_texts(session.hwnd)
                   if t.strip() and r[0] < 520 and y0 <= r[1] <= y1],
                  key=lambda x: (x[1][1], x[1][0]))


def set_diameter(session, target="0.4mm"):
    """Set the nozzle Diameter combo (sidebar nozzle section) to `target`."""
    reads = m8.nozzle_reads(session)
    print(f"{LOG} nozzles before: {reads}")
    # the diameter combo sits next to the 'Diameter' label in the nozzle section
    r = reads.get("diameter_rect")
    if not r:
        lab = next((rr for t, rr in sidebar_rows(session, 230, 330)
                    if t.lower().startswith("diameter")), None)
        if not lab:
            print(f"{LOG} 'Diameter' label not found")
            return ""
        r = (lab[2] + 4, lab[1] - 4, lab[2] + 120, lab[3] + 4)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
    for attempt in range(3):
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.25)
        winutil.real_click_screen(sx, sy)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            print(f"{LOG} diameter popup did not open (attempt {attempt + 1})")
            time.sleep(0.5)
            continue
        if m8.click_popup_row(session, popup[2], target, popup_hwnd=popup[3]):
            time.sleep(1.5)
            now = m8.nozzle_reads(session)
            print(f"{LOG} nozzles after: {now}")
            return now.get("diameter") or ""
    return ""


def editor_tabs(session):
    """Open slot 2's filament editor and dump: all texts + the tab-ish row."""
    slots = m8.wait_slots(session)
    hit = next((s for s in slots if s["slot"] == 2), None)
    if not hit or not hit.get("picker"):
        return None, [], []
    r = hit["picker"]
    sx, sy = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    time.sleep(1.2)
    menu = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32768", timeout_s=4.0)
    if not menu:
        return None, [], []
    mr = menu[2]
    winutil.user32.SetCursorPos(mr[0] + 20, mr[1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(mr[0] + 20, mr[1] + 12)
    time.sleep(1.6)
    dlg = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770", timeout_s=6.0)
    if not dlg:
        return None, [], []
    kids = export_util._children_texts(dlg[3])
    texts = [t.strip() for t, _r, _h in kids if t.strip()]
    # tab-like rows: several short texts sharing one y
    by_y = {}
    for t, r, _h in kids:
        tt = t.strip()
        if tt and (r[3] - r[1]) <= 40 and 12 <= (r[2] - r[0]) <= 160:
            by_y.setdefault(r[1] // 6, []).append((tt, r))
    tabrows = [v for v in by_y.values() if len(v) >= 3]
    return dlg, texts, tabrows


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
        shot("70_boot")

        d = set_diameter(session, "0.4mm")
        print(f"{LOG} diameter now: {d!r}")
        time.sleep(2.0)
        shot("71_nozzle_04")

        # --- 工艺配置 tab strip --------------------------------------------
        rows = sidebar_rows(session, 620, 1045)
        print(f"{LOG} process panel rows after the nozzle change:")
        for t, r in rows[:26]:
            print(f"{LOG}   {t[:38]!r:42s} rect={r}")
        tabs = [(t, r) for t, r in rows if t.lower() in ("standard", "high flow")]
        print(f"{LOG} PROCESS flow tabs: {tabs}")

        # --- 耗材丝配置 editor ---------------------------------------------
        dlg, texts, tabrows = editor_tabs(session)
        if dlg:
            print(f"{LOG} filament editor: {dlg[0]!r} {dlg[1]!r} rect={dlg[2]}")
            print(f"{LOG} editor texts ({len(texts)}): {texts[:40]}")
            for i, row in enumerate(tabrows[:4], start=1):
                print(f"{LOG} tab-ish row {i}: {[t for t, _r in sorted(row, key=lambda x: x[1][0])]}")
            shot("72_filament_editor", dlg[2])
            words = [w for w, *_ in mdu.ocr_words_img(
                screen_bgr()[dlg[2][1]:dlg[2][3], dlg[2][0]:dlg[2][2]], scale=2, psm=6)]
            print(f"{LOG} editor OCR: {' '.join(words)[:260]!r}")
            flowish = [(i, w) for i, w in enumerate(words)
                       if w.lower() in ("standard", "high", "flow")]
            print(f"{LOG} editor flow-ish words: {flowish}")
            for t, r, _h in export_util._children_texts(dlg[3]):
                if t.strip().lower() in ("cancel", "取消"):
                    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                    winutil.user32.SetCursorPos(cx, cy)
                    time.sleep(0.2)
                    winutil.real_click_screen(cx, cy)
                    break
        else:
            print(f"{LOG} filament editor did not open")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
