#!/usr/bin/env python3
"""diag_m8c_fila.py — drive the object list's native 'Fila.' column
(wxDataViewCtrl editable BitmapChoice cell, GUI_ObjectList.cpp:443-460) to
assign a cube to extruder 2, then slice+export and read the job's used
filaments. If used==[2] (or any slot != 1), m8c #111 becomes reachable:
switch another used slot to ABS and the temp-mix gate must grey the Slice
button.

    C:\\Python311\\python.exe diag\\diag_m8c_fila.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

import cv2  # noqa: E402

from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from harness import export_util, winutil  # noqa: E402

LOG = "[dfila]"
OUT = HERE / "artifacts" / "m8c_diag"

CLS_HINTS = ("wxDataView", "dataview", "DataView")


def find_dataview(session):
    """Any descendant window whose class looks like the object list."""
    out = []
    for text, rect, ch in export_util._children_texts(session.hwnd):
        cls = ctypes_wire_class(ch)
        if any(h.lower() in cls.lower() for h in CLS_HINTS):
            out.append((cls, text, rect, ch))
    return out


def ctypes_wire_class(hwnd):
    import ctypes
    buf = ctypes.create_unicode_buffer(64)
    winutil.user32.GetClassNameW(hwnd, buf, 64)
    return buf.value


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=args.model)
    try:
        if not m8.wait_arrival(session)[0]:
            print(f"{LOG} arrival FAIL")
            return 1
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        if not m7.step_delete_all(session, {}):
            print(f"{LOG} delete-all FAIL")
            return 1
        if not m7.op_add_primitive(session, "cube"):
            print(f"{LOG} cube add FAIL")
            return 1
        time.sleep(1.0)

        views = find_dataview(session)
        print(f"{LOG} dataview-ish windows: {[(c, t[:20], r) for c, t, r, _h in views]}")
        if not views:
            return 1
        cls, text, rect, ch = views[0]
        print(f"{LOG} using hwnd=0x{ch:x} cls={cls} rect={rect}")
        img = cap(session)
        crop = img[rect[1]:rect[3], rect[0]:rect[2]]
        cv2.imwrite(str(OUT / "objectlist.png"), crop)
        kids = export_util._children_texts(ch)
        print(f"{LOG} dataview children ({len(kids)}):")
        for t, r, k in kids[:25]:
            print(f"{LOG}   txt={t[:30]!r} rect={r}")
        # the Fila. column: header row is the first ~24px; the column order
        # per source: Name | (print icon) | Fila. | (support/color/...).
        # Click near the right end of the header band to locate columns.
        print(f"{LOG} done (geometry dump only)")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
