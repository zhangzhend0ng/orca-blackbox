#!/usr/bin/env python3
"""diag_137_probe_tabs2.py — verify the tester's pointer for #137 the right way
round: the Standard / High Flow TABS are said to live in the 0.20mm Standard
process preset, which belongs to the 0.4-nozzle machine.

So: switch the PRINTER preset to '0.4 nozzle', switch the PROCESS preset to
'0.20mm Standard', then dump the panel's tab strip and screenshot. If a
'High Flow' tab exists, click it and read the same parameter in both tabs — that
is the experiment #137 needs.

    C:\Python311\python.exe diag\diag_137_probe_tabs2.py
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
from m7t84 import switch_printer_preset  # noqa: E402

LOG = "[d137t2]"
OUT = HERE / "artifacts" / "m8x_137"


def shot(name):
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / (name if name.endswith(".png") else name + ".png")), img)
    print(f"{LOG} shot -> {name}")


def band_texts(session, y0=620, y1=1040):
    return sorted([(t.strip(), r) for t, r, _h in export_util._children_texts(session.hwnd)
                   if t.strip() and r[0] < 520 and y0 <= r[1] <= y1],
                  key=lambda x: (x[1][1], x[1][0]))


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
        shot("50_before")

        t = switch_printer_preset(session, "0.4 nozzle")
        print(f"{LOG} printer preset -> {t!r}")
        time.sleep(2.0)
        shot("51_printer_04")

        for target in ("0.20mm Standard", "0.20 Standard", "0.16mm Standard"):
            got = pp.switch_process_preset(session, target)
            r, ch, now = pp.find_process_preset_combo(session)
            print(f"{LOG} process preset {target!r} -> {got} (combo {now!r})")
            if got and "0.2" in (now or ""):
                break
        time.sleep(1.5)
        shot("52_process_020")

        rows = band_texts(session)
        print(f"{LOG} panel band after the switch ({len(rows)}):")
        for t, r in rows[:34]:
            print(f"{LOG}   {t[:40]!r:44s} rect={r}")
        tabs = [(t, r) for t, r in rows if t.strip().lower() in ("standard", "high flow")]
        print(f"{LOG} FLOW TABS found: {tabs}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
