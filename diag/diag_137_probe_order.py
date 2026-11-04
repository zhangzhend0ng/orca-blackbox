#!/usr/bin/env python3
"""diag_137_probe_order.py — two decisive checks for #137.

A) Does the Flow combo open in a PRISTINE state? m8f/m8g switch it successfully
   today, while the #137 probe failed four times in a row right after touching a
   process field — so either the control needs nothing special (and my earlier
   interactions broke it) or the probe's own clicks are at fault.
B) Does the PROCESS editor dialog accept typed input? The #123 filament dialog
   took WM_CHAR fine; if the process dialog does too, #137 can edit there instead
   of struggling with the inline sidebar spin.

    C:\Python311\python.exe diag\diag_137_probe_order.py
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

LOG = "[d137o]"
OUT = HERE / "artifacts" / "m8x_137"


def shot(name):
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
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
        shot("20_pristine")

        # --- A) flow switch FIRST, before touching anything else -------------
        reads = m8.nozzle_reads(session)
        print(f"{LOG} nozzles: {reads}")
        now = m8.switch_flow_combo(session, "High Flow")
        print(f"{LOG} A: switch_flow_combo(High Flow) -> {now!r}")
        m8.confirm_flow_dialog(session)
        time.sleep(1.5)
        shot("21_high_flow_first")
        print(f"{LOG} A: reads after switch: {m8.nozzle_reads(session)}")
        back = m8.switch_flow_combo(session, "Standard")
        print(f"{LOG} A: back -> {back!r}")
        m8.confirm_flow_dialog(session)
        time.sleep(1.0)

        # --- B) process editor dialog ----------------------------------------
        kids = export_util._children_texts(session.hwnd)
        btns = [(r, h) for t, r, h in kids
                if winutil.window_class(h) == "Button"
                and (r[2] - r[0]) in range(14, 20) and (r[3] - r[1]) in range(24, 30)]
        pr = next((r for r, _h in btns if 638 <= r[1] <= 650), None)
        print(f"{LOG} B: process row button = {pr}")
        if pr:
            cx, cy = (pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2
            sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.2)
            menu = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32768",
                                            timeout_s=4.0)
            if menu:
                shot("22_process_menu", menu[2])
                mr = menu[2]
                print(f"{LOG} B: menu rect={mr}, rows={m7.list_menu(menu[3])}")
                winutil.user32.SetCursorPos(mr[0] + 20, mr[1] + 12)
                time.sleep(0.2)
                winutil.real_click_screen(mr[0] + 20, mr[1] + 12)
                time.sleep(1.5)
                dlg = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32770",
                                               timeout_s=6.0)
                if dlg:
                    print(f"{LOG} B: editor {dlg[0]!r} {dlg[1]!r} rect={dlg[2]}")
                    texts = [t.strip() for t, _r, _h in export_util._children_texts(dlg[3]) if t.strip()]
                    print(f"{LOG} B: texts ({len(texts)}): {texts[:30]}")
                    shot("23_process_editor", dlg[2])
                    # try typing into a numeric Edit child of the dialog
                    edits = [(h, r) for t, r, h in export_util._children_texts(dlg[3])
                             if winutil.window_class(h) == "Edit"]
                    print(f"{LOG} B: dialog edits: {[(h, r) for h, r in edits[:6]]}")
                    if edits:
                        h, r = edits[0]
                        before = winutil.edit_text(h)
                        m7.type_into_field(session, ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2),
                                           "0.3", old_len=4)
                        after = winutil.edit_text(h)
                        print(f"{LOG} B: type into dialog edit: {before!r} -> {after!r}")
                        shot("24_after_type")
                else:
                    print(f"{LOG} B: no dialog after the process menu row")
            else:
                print(f"{LOG} B: process row button opened no menu")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
