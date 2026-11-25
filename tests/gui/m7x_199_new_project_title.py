#!/usr/bin/env python3
# m7x_199_new_project_title.py — Feishu #199: discard changes and verify Untitled.
# feishu: baseline#199

import argparse
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7
from harness import winutil
from m2_slice_chain import wait_model_loaded
from m3_common import MIXED_3MF, add_common_args, boot_session


def project_title(hwnd):
    title = winutil.window_title(hwnd).strip()
    return title, title.partition(" - ")[0].strip()


def save_prompt_text(hwnd):
    width, height, pixels = winutil.capture_window(hwnd)
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    image = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return " ".join(word[0] for word in m7.mdu.ocr_words_img(image, scale=3, psm=6))


def is_save_prompt(text):
    return bool(re.search(r"\bsave\b", text, re.I)
                and re.search(r"\b(?:unsaved|changes)\b", text, re.I)
                and re.search(r"\bcancel\b", text, re.I))


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF).parse_args()
    session = boot_session(args, model=args.model)
    try:
        arrived, fraction = wait_model_loaded(session, timeout_s=240)
        if not arrived:
            return m7.m7_verdict({"original model loaded": f"FAIL ({fraction:.3%})"})
        m7.ensure_maximized(session)
        original_title, original_project = project_title(session.hwnd)
        print(f"[m7x199] before edit: title={original_title!r}, model fraction={fraction:.3%}")
        if args.model.stem != original_project:
            return m7.m7_verdict({"named project loaded": f"FAIL ({original_title!r})"})

        original_blobs = m7.model_blob_count(session)
        added = m7.context_click_row(
            session, "bed", "cube", via="Add Primitive",
            success_fn=lambda: m7.model_blob_count(session) > original_blobs,
            label="add-cube",
        )
        print(f"[m7x199] Add Primitive > Cube invoked: {added}")
        if not added:
            return m7.m7_verdict({"edit model": "FAIL (could not invoke Add Cube)"})

        dispatched, dialog = m7.file_menu_dispatch(session, "New Project", expect_dialog=True)
        if not dispatched or not dialog:
            return m7.m7_verdict({"unsaved changes prompt": "FAIL (dialog did not open)"})
        _, dialog_title, _, dialog_hwnd = dialog
        text = save_prompt_text(dialog_hwnd)
        print(f"[m7x199] dialog={dialog_title!r} body={text!r}")
        if not is_save_prompt(text):
            return m7.m7_verdict({"unsaved changes prompt": "FAIL (prompt body did not match)"})

        clicked = m7.click_dialog_button(dialog_hwnd, "no", fallback_first=False)
        print(f"[m7x199] discard choice: {clicked!r}")
        deadline = time.monotonic() + 15
        closed = False
        current_title, current_project = original_title, original_project
        after = fraction
        while session.alive() and time.monotonic() < deadline:
            closed = not winutil.user32.IsWindowVisible(dialog_hwnd)
            current_title, current_project = project_title(session.hwnd)
            if closed:
                after = m7.model_colored_frac(session)
                if current_project == "Untitled" and after < m7.EMPTY_BED_FLOOR:
                    break
            time.sleep(0.5)
        print(f"[m7x199] after confirmation: title={current_title!r}, "
              f"model fraction={after:.3%}, empty threshold={m7.EMPTY_BED_FLOOR:.3%}, "
              f"prompt_closed={closed}")
        return m7.m7_verdict({
            "unsaved changes prompt": "PASS",
            "discard closes prompt": "PASS" if clicked and closed else "FAIL",
            "empty new project": "PASS" if closed and after < m7.EMPTY_BED_FLOOR else "FAIL",
            "default project title": "PASS" if current_project == "Untitled" else "FAIL",
            "app alive": "PASS" if session.alive() else "FAIL",
        })
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
