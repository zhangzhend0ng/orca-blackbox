#!/usr/bin/env python3
# m3e_preset_switch.py — P0-2: print-preset switch -> gcode header follows.
# feishu: baseline#159 baseline#166 baseline#182
#
# White-box ref: wx_gui_business_tests.cpp:304 — switching the print preset
# (combo path) and reslicing moves "; layer_height" with the new preset
# (0.40 Standard <-> 0.24 Standard @Snapmaker U1 (0.8 nozzle)).
#
# Black-box path: slice + export A -> click the print-preset selector (the
# '0.40 Standard @Snapmaker U1 (0.8 nozzle)' wxWindowNR, screen y~765) ->
# its SidePopup lists the U1 print presets -> click the '0.24 ...' row
# (popup rows are a SEPARATE top-level: click WITHOUT root piercing) ->
# reslice (button returns to idle on preset change, or the app auto-slices)
# -> export B -> assert "; layer_height" moved to 0.24.
#
# This is also the black-box cover for the "parameter change -> reslice ->
# different artifact" assertion family (P0-1's field-edit path needs real
# keyboard focus, which SendMessage injection cannot transfer).

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m1_minimal_loop import match, capture_bgr  # noqa: E402
from m3_common import (MIXED_3MF, RESOURCE, add_common_args,  # noqa: E402
                       boot_session, export_and_check, verdict)


def find_preset_combo(hwnd: int):
    """The print-preset selector: the child whose text carries a print-preset
    name ('0.40 Standard @Snapmaker U1 (0.8 nozzle)').

    Anchored to the neighbouring 'Process' label instead of an absolute screen
    band: the old test (text + screen y 740-810) was calibrated on the original
    rig's MAXIMIZED window; this rig's window is the app's default 1200x800 and
    the combo sits at y≈644, so the band rejected it and every preset switch
    failed (measured 09-21). Text + label proximity survives maximize/restore.
    """
    rows = list(export_util._children_texts(hwnd))
    anchor = next((r for t, r, _c in rows if t.strip() == "Process"), None)
    for text, rect, ch in rows:
        if "@Snapmaker U1" not in text:
            continue
        if anchor and not (anchor[1] - 10 <= rect[1] <= anchor[3] + 90):
            continue
        return rect, ch
    return None, None


def switch_preset(session, target: str) -> bool:
    """Switch the process preset by OCR-matching its popup ROW.

    Was a blind pitch walk (popup_top+14+i*28) plus a full-name readback.
    On 2.4.0 the rows read '0.24mm Standard @Snapmaker U1 (0.8 nozzle)' —
    the added 'mm' suffix breaks the name comparison and OCR splits rows
    into tokens — so both the click and the readback missed (measured
    09-22: m7t84/m7t109 'preset switches FAIL' with the popup listed in
    the log). Delegates to the OCR row matcher in harness.process_panel,
    which computes the rows from the popup's own pixels and normalises
    the 'mm' suffix."""
    from harness import process_panel as pp  # noqa: PLC0415
    return pp.switch_process_preset(session, target)


def gcode_layer_height(data: bytes):
    m = re.search(rb"; layer_height = ([0-9.]+)", data)
    return m.group(1).decode() if m else None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out_a = Path(args.datadir).parent / "m3e_a.gcode"
    out_b = Path(args.datadir).parent / "m3e_b.gcode"
    for p in (out_a, out_b):
        if p.exists():
            p.unlink()

    session = boot_session(args, model=args.model)
    try:
        # --- slice once, export baseline A ---
        from m3_common import slice_and_wait
        ok_slice = slice_and_wait(session, timeout_s=1500)
        ok_a, data_a = export_and_check(session, out_a)
        lh_a = gcode_layer_height(data_a)
        print(f"[m3e] slice={ok_slice} exportA={ok_a} layer_height={lh_a}")
        results["baseline slice + export"] = "PASS" if (ok_slice and ok_a) else "FAIL"

        # --- switch print preset 0.40 -> 0.24 ---
        target = ("0.24 Standard"
                  if lh_a and "0.24" not in lh_a
                  else "0.40 Standard")
        switched = switch_preset(session, target)
        print(f"[m3e] preset switch to '{target}': {switched}")
        results["preset combo switch"] = "PASS" if switched else "FAIL"
        time.sleep(2.0)

        # --- reslice (button returns idle on preset change / auto-slice) ---
        from m3_common import slice_and_wait
        ok_slice2 = slice_and_wait(session, timeout_s=1500)
        ok_b, data_b = export_and_check(session, out_b)
        lh_b = gcode_layer_height(data_b)
        print(f"[m3e] reslice={ok_slice2} exportB={ok_b} layer_height={lh_b}")
        results["reslice after preset switch"] = (
            "PASS" if ok_slice2 and ok_b else "FAIL")

        same = (data_a == data_b)
        print(f"[m3e] gcode identical: {same}")
        results["gcode differs after preset switch"] = (
            "PASS" if not same else "FAIL")
        target_short = target.split(" Standard")[0]  # e.g. '0.24'
        results["header follows new preset"] = (
            "PASS" if (lh_b and target_short in lh_b) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3e] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
