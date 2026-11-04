#!/usr/bin/env python3
"""diag_137_probe_targets.py — click-target matrix for #137 (one question: which
control actually opens what).

Candidates, each clicked with a REAL click and observed:
  flow combo:   left third / centre / right edge (arrow)
  process row:  the two 16x26 buttons right of the preset name, and the name itself
Everything opened is reported (menu rows / popup shape / dialog), and closed again.

    C:\Python311\python.exe diag\diag_137_probe_targets.py
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

LOG = "[d137t]"
OUT = HERE / "artifacts" / "m8x_137"


def shot(name):
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / (name if name.endswith(".png") else name + ".png")), img)


def tops(session):
    return {(c, t, r) for c, t, r, _h in m8._visible_toplevels(session.pid)}


def click_and_report(session, client_pt, tag):
    before = tops(session)
    sx, sy = winutil.client_to_screen(session.hwnd, *client_pt)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    time.sleep(1.5)
    after = tops(session)
    new = [x for x in after if x not in before]
    print(f"{LOG} {tag}: client={client_pt} screen=({sx},{sy}) -> "
          f"{len(new)} new toplevel(s)")
    for cls, title, rect in new:
        if cls == "#32768":
            print(f"{LOG}   MENU {title!r} rect={rect}")
        else:
            print(f"{LOG}   {cls!r} {title!r} rect={rect}")
    shot(f"30_{tag}")
    # dismiss whatever opened
    for cls, title, rect, hwnd in m8._visible_toplevels(session.pid):
        if (cls, title, rect) in new:
            if cls == "#32768":
                winutil.user32.PostMessageW(hwnd, 0x0011, 0, 0)
            else:
                for t, r, h in export_util._children_texts(hwnd):
                    if t.strip().lower() in ("cancel", "取消", "close", "关闭"):
                        winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, h)
                        break
            time.sleep(0.8)
    return new


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
        reads = m8.nozzle_reads(session)
        fr = reads.get("flow_rect")
        print(f"{LOG} nozzle reads: {reads}")
        if fr:
            x0, y0, x1, y1 = fr
            cy = (y0 + y1) // 2
            click_and_report(session, (x0 + 15, cy), "flow_left")
            click_and_report(session, ((x0 + x1) // 2, cy), "flow_center")
            click_and_report(session, (x1 - 6, cy), "flow_arrow")
        # process row controls
        kids = export_util._children_texts(session.hwnd)
        cands = [(r, h) for t, r, h in kids
                 if winutil.window_class(h) == "Button"
                 and (r[2] - r[0]) in range(14, 20) and (r[3] - r[1]) in range(24, 30)
                 and 636 <= r[1] <= 652]
        for i, (r, _h) in enumerate(cands, start=1):
            click_and_report(session, ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2),
                             f"proc_btn{i}")
        name = next(((t, r) for t, r, _h in kids
                     if "0.40mm" in t and 636 <= r[1] <= 652), None)
        if name:
            click_and_report(session, ((name[1][0] + name[1][2]) // 2, 657), "proc_name")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
