#!/usr/bin/env python3
"""diag_123_probe_save2.py — #123 rounds 2: locate the field by OCR and learn the
commit path.

Round 1 (diag_123_probe_save.py) established:
  * the editor is the 'Material settings' dialog (585,216)-(1335,816),
  * its field LABELS are painted, not child controls (the 175 children expose only
    section headers, unit suffixes and a 'colourpicker'), so a label lookup can
    never find 'Softening temperature' — locate it by OCR of the screenshot,
  * some child rects do not even live in the dialog's screen space, so clicks are
    derived from OCR/screen coordinates and verified by re-OCR.

This probe: OCR -> click the value box -> type 80 -> verify by OCR -> try the two
top-right icon buttons (a bookmark icon = save preset) -> report any prompt ->
restore 45 -> close. Nothing destructive is confirmed.

    C:\\Python311\\python.exe diag\\diag_123_probe_save2.py
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

LOG = "[d123s2]"
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
    return img


def ocr_words(img):
    """[(text, (x0,y0,x1,y1))] in the image's own coordinates."""
    out = []
    for w, x, y, ww, hh in mdu.ocr_words_img(img, scale=2):   # (text,x,y,w,h)
        out.append((w, (int(x), int(y), int(x + ww), int(y + hh))))
    return out


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
    mrect = menu[2]
    winutil.user32.SetCursorPos(mrect[0] + 20, mrect[1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(mrect[0] + 20, mrect[1] + 12)
    time.sleep(1.5)
    return export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770", timeout_s=6.0)


def find_softening_box(dlg_rect):
    """(label rect, value-box click point) from OCR of the dialog, SCREEN coords."""
    img = screen_bgr()
    x0, y0, x1, y1 = dlg_rect
    crop = img[y0:y1, x0:x1]
    words = ocr_words(crop)
    lab = None
    for t, r in words:
        if "soften" in t.lower():
            lab = r
            break
    if not lab:
        print(f"{LOG} 'Softening' not found; OCR saw: {[t for t, _r in words][:30]}")
        return None, None
    lab_screen = (x0 + lab[0], y0 + lab[1], x0 + lab[2], y0 + lab[3])
    # the value box sits to the right of the label on the same line: the dump put
    # the °C unit around x+240..x+360 from the label's left edge
    cy = (lab_screen[1] + lab_screen[3]) // 2
    cx = lab_screen[2] + 70
    print(f"{LOG} 'Softening temperature' label={lab_screen} -> value box click ({cx},{cy})")
    return lab_screen, (cx, cy)


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
        print(f"{LOG} dialog title={dlg[1]!r} rect={dlg[2]}")
        shot("10_editor.png", dlg[2])
        lab, box = find_softening_box(dlg[2])
        if not box:
            return 1
        # click the box, select-all, type 80
        winutil.user32.SetCursorPos(*box)
        time.sleep(0.3)
        winutil.real_click_screen(*box)
        time.sleep(0.5)
        # message keyboard to the deepest child under the click point
        ch = winutil.deepest_child_at(session.hwnd, *box) or session.hwnd
        print(f"{LOG} deepest child under the box: 0x{ch:x} ({winutil.window_class(ch)!r})")
        winutil.select_all(ch)
        time.sleep(0.2)
        winutil.msg_text(ch, "80")
        time.sleep(0.4)
        winutil.press_enter(ch)
        time.sleep(0.8)
        img = shot("11_after_set80.png", dlg[2])
        words = ocr_words(img)
        row = [t for t, r in words if abs(r[1] - lab[1]) < 26]
        print(f"{LOG} OCR on the softening row after typing: {row[:12]}")
        # try the two top-right icon buttons (bookmark = save preset?)
        for i, (ix, iy) in enumerate(((1184, 272), (1210, 272)), start=1):
            print(f"{LOG} clicking top-right icon #{i} at ({ix},{iy})")
            winutil.user32.SetCursorPos(ix, iy)
            time.sleep(0.2)
            winutil.msg_click_screen(ix, iy)
            time.sleep(1.4)
            shot(f"12_after_icon{i}.png")
            prompt = export_util.wait_toplevel(
                session.pid, lambda c, t, r2: c == "#32770" and r2 != dlg[2], timeout_s=2.5)
            if prompt:
                ptxt = [t.strip() for t, _r, _h in export_util._children_texts(prompt[3]) if t.strip()]
                print(f"{LOG} icon #{i} -> prompt title={prompt[1]!r} texts={ptxt[:10]}")
                shot(f"13_prompt{i}.png", prompt[2])
                for t, r2, h in export_util._children_texts(prompt[3]):
                    if t.strip().lower() in ("cancel", "取消"):
                        winutil.msg_click_screen((r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2, h)
                        print(f"{LOG} prompt cancelled (no destructive confirm)")
                        break
                break
            print(f"{LOG} icon #{i}: nothing popped up")
        # restore
        winutil.user32.SetCursorPos(*box)
        time.sleep(0.3)
        winutil.real_click_screen(*box)
        time.sleep(0.5)
        winutil.select_all(ch)
        time.sleep(0.2)
        winutil.msg_text(ch, "45")
        time.sleep(0.3)
        winutil.press_enter(ch)
        time.sleep(0.6)
        shot("14_restored.png", dlg[2])
        print(f"{LOG} restored the field to 45")
        # close with the dialog's X (top-right of the title bar)
        x, y = dlg[2][2] - 14, dlg[2][1] + 12
        winutil.msg_click_screen(x, y)
        time.sleep(1.0)
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
