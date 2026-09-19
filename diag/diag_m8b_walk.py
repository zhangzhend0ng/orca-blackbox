#!/usr/bin/env python3
"""diag_m8b_walk.py — ground-truth the preset-popup walk + wheel assist.

Walks slot2's combo popup attempting 'Rainbow' (deep row, needs scrolling)
and slot1's popup hunting a PC row (for m8d #127). Logs every probed row
text and saves popup screenshots so the scroll behavior is visible.

    C:\\Python311\\python.exe diag\\diag_m8b_walk.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

import cv2  # noqa: E402

from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import export_util  # noqa: E402

LOG = "[dwalk]"
OUT = HERE / "artifacts" / "m8b_diag"


def walk_log(session, slot, target, excludes=(), attempts=26, tag=""):
    """switch_filament_preset with verbose logging + popup screenshots."""
    slots = m8.filament_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["combo"]:
        print(f"{LOG} slot{slot} combo missing")
        return ""
    text, rect, ch = hit["combo"]
    print(f"{LOG} slot{slot} start: {m8.combo_text(ch)!r}")
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    seen = []
    import harness.winutil as winutil
    for attempt in range(attempts):
        try:
            winutil.user32.SetForegroundWindow(session.hwnd)
            time.sleep(0.4)
        except Exception:  # noqa: BLE001
            pass
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            print(f"{LOG} a{attempt}: popup missing")
            time.sleep(0.5)
            continue
        if attempt >= 8:
            m8._wheel(popup)
        if attempt in (0, 9, 17):
            img = cap(session)
            cv2.imwrite(str(OUT / f"walk_{tag}_a{attempt}.png"), img)
        pr = popup[2]
        px = (pr[0] + pr[2]) // 2
        py = pr[1] + 14 + min(attempt, 8) * 28
        winutil.msg_click_screen(px, py)
        time.sleep(0.9)
        now = m8.combo_text(ch)
        seen.append(now)
        print(f"{LOG} slot{slot} a{attempt} row{min(attempt, 8)}: {now!r}")
        if target in now and not any(e in now for e in excludes):
            print(f"{LOG} slot{slot} REACHED {target!r} at attempt {attempt}")
            return now
        time.sleep(0.3)
    print(f"{LOG} slot{slot} walk done, distinct={len(set(seen))}")
    return m8.combo_text(ch)


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=args.model)
    try:
        ok, _f = m8.wait_arrival(session)
        if not ok:
            print(f"{LOG} arrival FAIL")
            return 1
        m7.ensure_maximized(session)
        time.sleep(1.0)

        print(f"{LOG} === slot2 walk -> Rainbow ===")
        walk_log(session, 2, "Rainbow", tag="s2rainbow")

        print(f"{LOG} === slot1 walk -> PC (excl PCTG) ===")
        final = walk_log(session, 1, "PC", excludes=("PCTG",), tag="s1pc")
        if "PC" not in final or "PCTG" in final:
            print(f"{LOG} no PC row — full slot1 inventory above; "
                  f"falling back to ABS-GF")
            walk_log(session, 1, "ABS-GF", tag="s1absgf")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
