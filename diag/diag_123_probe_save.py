#!/usr/bin/env python3
"""diag_123_probe_save.py — #123's last unknown: how a preset edit is committed.

The editor is 'Material settings' (opened from the slot row's #32768 menu, first
row). Its first section carries 'Softening temperature 45 °C' — the UI name of
`temperature_vitrification` (the gcode echoes `; temperature_vitrification =
70,45,45,45,45` and the topcap rule is <=50 → 强冷 MODE=1, >50 → 保温 MODE=3).

This probe answers, with the value restored at the end:
  * the edit control for that field and whether typing 80 lands
  * what the top-right icon buttons are (a bookmark icon suggests 'save preset')
    and whether saving raises a prompt (overwrite / save-as)
  * the dialog's commit/cancel buttons

Notes: each case boot re-seeds the datadir (`boot_session(fresh=True)`), so a
preset touched here cannot leak into other cases — but the value is restored
anyway.

    C:\\Python311\\python.exe diag\\diag_123_probe_save.py
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

LOG = "[d123s]"
OUT = HERE / "artifacts" / "m8x_123"


def screen_bgr():
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def shot(name, rect=None):
    img = screen_bgr()
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / name), img)
    print(f"{LOG} shot -> {name}")


def set_field(edit_hwnd, rect, text):
    """Type into a dialog control addressed in SCREEN coordinates.

    m7.type_into_field takes CLIENT coordinates (it converts via client()), so
    it cannot address a dialog; the sequence here is the same idea: real click
    for focus, select-all + WM_CHAR through the control itself, then Enter.
    """
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.25)
    winutil.real_click_screen(cx, cy)
    time.sleep(0.4)
    winutil.select_all(edit_hwnd)
    time.sleep(0.2)
    winutil.msg_text(edit_hwnd, text)
    time.sleep(0.3)
    winutil.press_enter(edit_hwnd)
    time.sleep(0.6)


def open_editor(session):
    """Slot row button -> #32768 menu -> first row (Edit) -> 'Material settings'."""
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
    mrect = menu[2]
    # first row (Edit): wx popup, HMENU enumeration empty -> geometry
    winutil.user32.SetCursorPos(mrect[0] + 20, mrect[1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(mrect[0] + 20, mrect[1] + 12)
    time.sleep(1.5)
    return export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770", timeout_s=6.0)


def find_label_edit(dlg, label_text):
    """(label rect, edit hwnd, edit rect) for a labelled row inside the dialog."""
    kids = export_util._children_texts(dlg[3])
    lab = next((r for t, r, _h in kids
                if label_text.lower() in t.strip().lower()), None)
    if not lab:
        return None, None, None
    lcy = (lab[1] + lab[3]) // 2
    cands = [(h, r) for t, r, h in kids
             if not t.strip() and winutil.window_class(h) == "Edit"
             and abs(((r[1] + r[3]) // 2) - lcy) < 8 and r[0] > lab[2]]
    if not cands:
        return lab, None, None
    h, r = sorted(cands, key=lambda c: c[1][0])[0]
    return lab, h, r


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives={ok} ({frac:.3%})")
        m7.ensure_maximized(session)
        time.sleep(1.0)
        dlg = open_editor(session)
        if not dlg:
            print(f"{LOG} FAIL: editor did not open")
            return 1
        kids = export_util._children_texts(dlg[3])
        texts = [t.strip() for t, _r, _h in kids if t.strip()]
        print(f"{LOG} dialog title={dlg[1]!r} rect={dlg[2]} children={len(kids)}")
        print(f"{LOG} all texts: {texts[:40]}")
        # buttons / bottom area
        btns = [(t.strip(), r, winutil.window_class(h)) for t, r, h in kids
                if winutil.window_class(h) in ("Button", "wxWindowNR")
                and (r[3] - r[1]) >= 22 and r[2] - r[0] >= 40]
        print(f"{LOG} button-ish controls: {[(t, r) for t, r, c in btns][:14]}")

        lab, eh, er = find_label_edit(dlg, "softening temperature") or (None, None, None)
        if not lab:
            lab, eh, er = find_label_edit(dlg, "Softening")
        print(f"{LOG} softening row: label={lab} edit_hwnd={eh} edit={er}")
        if eh:
            print(f"{LOG} current value = {winutil.edit_text(eh)!r}")
        shot("03_editor.png", dlg[2])

        # --- set 80 and look at the commit path -----------------------------
        if eh:
            set_field(eh, er, "80")
            print(f"{LOG} after typing 80 -> {winutil.edit_text(eh)!r}")
            shot("04_after_set80.png", dlg[2])
            # the two 16x26 icons at the dialog's top right
            icons = [(t.strip(), r, h) for t, r, h in kids
                     if winutil.window_class(h) == "Button"
                     and (r[2] - r[0]) in range(14, 20) and (r[3] - r[1]) in range(24, 30)]
            print(f"{LOG} small icon buttons: {[r for _t, r, _h in icons]}")
            if icons:
                r = icons[0][1]
                cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                print(f"{LOG} clicking the first icon button at ({cx},{cy})")
                winutil.msg_click_screen(cx, cy)
                time.sleep(1.5)
                shot("05_after_icon_click.png")
                prompt = export_util.wait_toplevel(
                    session.pid, lambda c, t, r2: c == "#32770" and r2 != dlg[2],
                    timeout_s=3.0)
                if prompt:
                    print(f"{LOG} prompt appeared: title={prompt[1]!r} rect={prompt[2]}")
                    print(f"{LOG} prompt texts: "
                          f"{[t.strip() for t, _r, _h in export_util._children_texts(prompt[3]) if t.strip()]}")
                    shot("06_prompt.png", prompt[2])
                    # do NOT confirm anything destructive: cancel it
                    for t, r2, h in export_util._children_texts(prompt[3]):
                        if t.strip().lower() in ("cancel", "取消"):
                            winutil.msg_click_screen((r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2, h)
                            print(f"{LOG} prompt cancelled")
                            break
                else:
                    print(f"{LOG} no prompt — the icon click did not raise a dialog")
            # restore 45 (best effort; the datadir is re-seeded per case anyway)
            if eh:
                set_field(eh, er, "45")
                print(f"{LOG} restored -> {winutil.edit_text(eh)!r}")
        # close without committing further
        for t, r2, h in export_util._children_texts(dlg[3]):
            if t.strip().lower() in ("cancel", "取消"):
                winutil.msg_click_screen((r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2, h)
                print(f"{LOG} dialog cancelled")
                break
        time.sleep(0.8)
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
