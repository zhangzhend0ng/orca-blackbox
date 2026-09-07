#!/usr/bin/env python3
# Adaptive gizmo-toolbar slot discovery: locate the icon row by dark-pixel
# profile, then hover-scan it and OCR the in-canvas tooltip per slot.
import sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
import numpy as np  # noqa: E402
from harness import mix_dialog_util as mdu, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)

def tooltip_at(session, img, cx, cy):
    sx, sy = client(session, cx, cy)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    deadline = time.monotonic() + 1.3
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        crop = img[cy + 12:cy + 100, max(0, cx - 120):cx + 140]
        if crop.size:
            words = mdu.ocr_words_img(crop, scale=3)
            text = " ".join(w for w, *_ in words)
            if len(text) >= 6:
                return text
        time.sleep(0.3)
    return ""

def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=args.model or MIXED_3MF)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=240)
        print(f"[slots] model loaded: {ok}", flush=True)
        time.sleep(1.5)
        img = capture_bgr(session)
        h, w = img.shape[:2]
        gray = img.mean(axis=2)
        # icon row = upper-band rows with many dark pixels right of sidebar
        bands = []
        for y in range(40, 140, 4):
            dark = int((gray[y:y+4, 440:w-100] < 120).sum())
            bands.append((y, dark))
            print(f"[slots] y{y}: dark={dark}", flush=True)
        ys = [y for y, d in bands if d > 1500]
        if not ys:
            print("[slots] NO icon band found"); return 1
        y0 = min(ys)
        cy = y0 + 14
        print(f"[slots] icon band starts y{y0}, hover cy={cy}", flush=True)
        slots = []
        prev = ""
        for x in range(450, w - 120, 22):
            text = tooltip_at(session, img, x, cy)
            if text and text != prev:
                print(f"[slots] @x{x}: {text!r}", flush=True)
            if text:
                slots.append((x, text))
            prev = text if text else prev
        print(f"[slots] total={len(slots)}", flush=True)
        return 0
    finally:
        session.close()
        print("[slots] app closed", flush=True)

if __name__ == "__main__":
    raise SystemExit(main())
