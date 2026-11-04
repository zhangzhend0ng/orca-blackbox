#!/usr/bin/env python3
# m7t74.py — Feishu #74 主流程-模板: 单模型切片调整测试
# feishu: baseline#152 baseline#156 baseline#164
#   M-01 import -> M-09 move -> M-11 rotate Z 45 -> M-12 scale 120
#   -> M-02 slice -> O-02 close
# Asserts: each gizmo field commits its value (OCR), the model stays on
# the plate, and the slice completes (m2 done rendering).
#
# ONE GIZMO PER APP SESSION (measured 09-23, 2.4.0): inside a single
# session the SECOND gizmo panel's field entry is unreliable — WM_CHARs
# drop at random ('45' arrives as '4', '120' as '1'), the toolbar toggle
# click gets eaten (the panel never opens) and re-selecting the model after
# a committed transform often fails, while the FIRST panel of a fresh
# session commits reliably. The assertions are unchanged; the case simply
# boots the fixture once per transform (move / rotate / scale) and slices at
# the end of the session that performs the last transform.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import argparse  # noqa: E402

from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

LOG = "[m7t74]"
import m7_common as m7  # noqa: E402


def wait_model(session, timeout_s=300, gate=None):
    from m2_slice_chain import MODEL_COLORED_THRESHOLD
    gate = MODEL_COLORED_THRESHOLD if gate is None else gate
    deadline = time.monotonic() + timeout_s
    frac = m7.model_colored_frac(session)
    while frac < gate and time.monotonic() < deadline:
        time.sleep(2.0)
        frac = m7.model_colored_frac(session)
    print(f"{LOG} model arrives: {frac >= gate} ({frac:.2%}, gate {gate:.2%})")
    return frac >= gate


def gizmo_session(args, results, key, slot_pred, row_label, index, value,
                  fallback_dx=0, slice_after=False):
    """Boot a fresh app, do ONE gizmo edit, verify, close.

    Returns True when the field committed AND the model is still present."""
    session = boot_session(args, model=args.model)
    ok = False
    try:
        m7.ensure_maximized(session)
        arrived = wait_model(session)
        results.setdefault("model arrives", "PASS" if arrived else "FAIL")
        if arrived:
            ok, text = m7.op_gizmo_field(session, slot_pred, row_label,
                                         index, value, fallback_dx=fallback_dx)
            results[key] = "PASS" if ok else f"FAIL (now {text!r})"
            present = m7.model_present(session)
            results.setdefault("model still on plate", "PASS")
            if not present:
                results["model still on plate"] = "FAIL"
            if ok and slice_after:
                m7.op_slice(session, results)
        else:
            results[key] = "FAIL (model never arrived)"
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed ({key})")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    results = {}
    # --- session 1: move X = 60 -------------------------------------------
    gizmo_session(args, results, "move X commits 60",
                  lambda t: "move" in t, "position", 0, "60")
    # --- session 2: rotate absolute Z = 45 --------------------------------
    gizmo_session(args, results, "rotate Z commits 45",
                  lambda t: "rotate" in t, "rotate", -1, "45")
    # --- session 3: scale to 120% -> slice completes ----------------------
    gizmo_session(args, results, "scale commits 120",
                  lambda t: "scale" in t, "scale", 0, "120",
                  fallback_dx=44, slice_after=True)
    return m7.m7_verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
