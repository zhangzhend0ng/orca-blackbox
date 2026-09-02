#!/usr/bin/env python3
# diag_m6_move.py — P1-5 prerequisite diag: locate the Move gizmo and its
# ImGui input window (Position X/Y/Z), to design the transform case.
#
# Steps: boot mixed fixture -> select model (m4e.select_model reuse) ->
# hover-scan the gizmo bar for 'Move' -> click it -> screenshots at each
# step + OCR of the canvas right side (window per do_render_move_window,
# GizmoObjectManipulation.cpp:800).
# Artifacts: artifacts/diag_m6_step*.png

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
from m4e_mixing_paint import (BAR_Y, client, find_slot, select_model,  # noqa: E402
                              viewport_img)
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import winutil  # noqa: E402

import cv2  # noqa: E402

LOG = "[diag-m6]"
ART = HERE / "artifacts"
ART.mkdir(exist_ok=True)


def save(session, tag):
    p = ART / f"diag_m6_{tag}.png"
    cv2.imwrite(str(p), viewport_img(session))
    print(f"{LOG} shot -> {p.name}")
    return p


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        ok, _ = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok}")
        if not ok:
            return 1
        time.sleep(2.0)
        save(session, "01_loaded")

        if not select_model(session):
            print(f"{LOG} select_model FAILED")
            return 2
        save(session, "02_selected")

        move_x, tip = find_slot(session, lambda t: "move" in t)
        print(f"{LOG} move slot: x={move_x} tip={tip!r}")
        if move_x is None:
            save(session, "03_nomoveslot")
            return 3
        save(session, "03_move_found")

        # activate the Move gizmo (real click, same as m4e)
        sx, sy = client(session, move_x, BAR_Y)
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        winutil.real_click_screen(sx, sy)
        time.sleep(2.5)
        p = save(session, "04_move_active")

        # OCR the full canvas for the Position/Size window location
        img = viewport_img(session)
        words = mdu.ocr_words_img(img, scale=3)
        hits = [(w, x, y) for w, x, y, *_ in words
                if w.lower() in ("position", "size", "rotation", "world",
                                 "object", "coordinates", "x", "y", "z")]
        print(f"{LOG} OCR hits: {hits}")
        with open(ART / "diag_m6_ocr.txt", "w", encoding="utf-8") as f:
            f.write(repr(words))
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
