#!/usr/bin/env python3
"""diag_137_probe_tabs.py — verify the tester's pointer for #137: the Standard /
High Flow TABS live in the 0.2mm Standard PROCESS preset (not the nozzle Flow
combo I had been poking at).

Steps (read-only apart from switching the process preset):
  1. switch the process preset to a 0.2mm Standard one (harness.process_panel);
  2. dump every sidebar text around the panel's tab strip;
  3. screenshot, so the tabs (and any per-row flow marker) are visible.

    C:\Python311\python.exe diag\diag_137_probe_tabs.py
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

from harness import export_util, process_panel as pp, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d137tab]"
OUT = HERE / "artifacts" / "m8x_137"


def shot(name):
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / (name if name.endswith(".png") else name + ".png")), img)
    print(f"{LOG} shot -> {name}")


def sidebar_texts(session, y0=630, y1=1040):
    out = []
    for t, r, h in export_util._children_texts(session.hwnd):
        if t.strip() and r[0] < 520 and y0 <= r[1] <= y1:
            out.append((t.strip(), r, winutil.window_class(h)))
    return sorted(out, key=lambda x: (x[1][1], x[1][0]))


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
        r, ch, txt = pp.find_process_preset_combo(session)
        print(f"{LOG} process preset before: {txt!r}")
        shot("40_before_switch")
        for target in ("0.2 Standard", "0.2mm Standard", "0.24 Standard"):
            ok2 = pp.switch_process_preset(session, target)
            r, ch, now = pp.find_process_preset_combo(session)
            print(f"{LOG} switch to {target!r} -> {ok2} (combo now {now!r})")
            if ok2 and "0.2" in (now or ""):
                shot(f"41_after_{target.replace(' ', '_').replace('.', '')}")
                break
        time.sleep(1.0)
        rows = sidebar_texts(session)
        print(f"{LOG} sidebar rows after switch ({len(rows)}):")
        for t, rr, c in rows[:40]:
            print(f"{LOG}   {c!r:12s} {t[:38]!r:42s} rect={rr}")
        flowish = [(t, rr) for t, rr, _c in rows
                   if "flow" in t.lower() or "standard" in t.lower()]
        print(f"{LOG} flow/standard rows: {flowish}")
        shot("42_after_switch")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
