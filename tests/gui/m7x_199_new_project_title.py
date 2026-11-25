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
from harness import export_util, topbar_util, winutil
from m2_slice_chain import wait_model_loaded
from m3_common import MIXED_3MF, add_common_args, boot_session


def project_title(hwnd):
    title = winutil.window_title(hwnd).strip()
    return title, title.partition(" - ")[0].strip()


def visible_project_title(session):
    topbar = topbar_util._topbar(session.hwnd)
    if not topbar:
        return ""
    _, (_, top, _, bottom), _ = topbar
    image = m7.capture_bgr(session)
    width = image.shape[1]
    title_band = image[:bottom - top, width // 4:3 * width // 4]
    return " ".join(word[0] for word in m7.mdu.ocr_words_img(title_band, scale=3, psm=7))


def save_prompt_text(hwnd):
    width, height, pixels = winutil.capture_window(hwnd)
    frame = np.frombuffer(pixels, np.uint8).reshape(height, width, 4)
    image = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return " ".join(word[0] for word in m7.mdu.ocr_words_img(image, scale=3, psm=6))


def is_save_prompt(text):
    return bool(re.search(r"\bsave\b", text, re.I)
                and re.search(r"\b(?:unsaved|changes)\b", text, re.I)
                and re.search(r"\bcancel\b", text, re.I))


def import_unsaved_model(session):
    model = HERE / "fixtures" / "Prusa.stl"
    before = m7.model_colored_frac(session)
    initial_blobs = m7.model_blob_count(session)
    dispatched, dialog = m7.file_menu_dispatch(session, "stl", via="Import", expect_dialog=True)
    if not (dispatched and dialog):
        print("[m7x199] Import STL file chooser did not open")
        return False
    edit = export_util.find_edit(dialog[3])
    if not edit:
        print(f"[m7x199] no filename control in {dialog[1]!r}")
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(model))
    entered = winutil.edit_text(edit, size=260)
    if entered != str(model):
        print(f"[m7x199] import filename control read {entered!r}, expected {str(model)!r}")
        return False
    winutil._send_msg(dialog[3], m7.WM_COMMAND_MSG, 1, 0)  # IDOK
    deadline = time.monotonic() + 20
    while session.alive() and time.monotonic() < deadline:
        if not winutil.user32.IsWindowVisible(dialog[3]):
            current = m7.model_colored_frac(session)
            blobs = m7.model_blob_count(session)
            if blobs > initial_blobs and current > before:
                print(f"[m7x199] Imported {model.name}: colored fraction {before:.3%} -> "
                      f"{current:.3%}; object-shaped blobs {initial_blobs} -> {blobs}")
                return True
        time.sleep(0.8)
    print(f"[m7x199] could not confirm additional {model.name} geometry")
    return False


def main():
    args = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF).parse_args()
    session = boot_session(args, model=args.model)
    try:
        arrived, fraction = wait_model_loaded(session, timeout_s=240)
        if not arrived:
            return m7.m7_verdict({"original model loaded": f"FAIL ({fraction:.3%})"})
        m7.ensure_maximized(session)
        original_title, original_project = project_title(session.hwnd)
        original_label = visible_project_title(session)
        print(f"[m7x199] before edit: title={original_title!r}, topbar={original_label!r}, "
              f"model fraction={fraction:.3%}")
        if args.model.stem != original_project or original_label.lstrip("*") != original_project:
            return m7.m7_verdict({"named project loaded": f"FAIL ({original_title!r})"})

        if not import_unsaved_model(session):
            return m7.m7_verdict({"edit model": "FAIL (could not verify unsaved STL import)"})

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
        current_label = original_label
        after = fraction
        while session.alive() and time.monotonic() < deadline:
            closed = not winutil.user32.IsWindowVisible(dialog_hwnd)
            current_title, current_project = project_title(session.hwnd)
            if closed:
                after = m7.model_colored_frac(session)
                if current_project == "Untitled" and after < m7.EMPTY_BED_FLOOR:
                    current_label = visible_project_title(session)
                    if current_label == current_project:
                        break
            time.sleep(0.5)
        print(f"[m7x199] after confirmation: title={current_title!r}, topbar={current_label!r}, "
              f"model fraction={after:.3%}, empty threshold={m7.EMPTY_BED_FLOOR:.3%}, "
              f"prompt_closed={closed}")
        return m7.m7_verdict({
            "unsaved changes prompt": "PASS",
            "discard closes prompt": "PASS" if clicked and closed else "FAIL",
            "empty new project": "PASS" if closed and after < m7.EMPTY_BED_FLOOR else "FAIL",
            "default project title": (
                "PASS" if current_project == current_label == "Untitled" else "FAIL"),
            "app alive": "PASS" if session.alive() else "FAIL",
        })
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
