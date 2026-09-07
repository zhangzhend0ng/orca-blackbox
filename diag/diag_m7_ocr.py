#!/usr/bin/env python3
# OCR the full window frame + pixel-scan toolbar bands (text-only diag).
import sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
from harness import mix_dialog_util as mdu, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import numpy as np  # noqa: E402

def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser())
    args = ap.parse_args()
    session = boot_session(args, model=args.model or MIXED_3MF)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=240)
        print(f"[ocr] model loaded: {ok} ({frac:.2%})", flush=True)
        time.sleep(1.5)
        img = capture_bgr(session)
        h, w = img.shape[:2]
        print(f"[ocr] frame {w}x{h}", flush=True)
        # dark-pixel column profile of the upper band (toolbar icons are dark)
        gray = img.mean(axis=2)
        for y0 in range(60, 140, 10):
            band = gray[y0:y0+10, 430:w-20]
            dark = (band < 120).sum()
            print(f"[ocr] band y{y0}-{y0+10}: darkpx={dark}", flush=True)
        words = mdu.ocr_words_img(img, scale=2)
        print(f"[ocr] words={len(words)}", flush=True)
        line = " | ".join(f"{t}@({x},{y})" for t, x, y, *_ in words)
        for i in range(0, len(line), 200):
            print(f"[ocr] {line[i:i+200]}", flush=True)
        return 0
    finally:
        session.close()
        print("[ocr] app closed", flush=True)

if __name__ == "__main__":
    raise SystemExit(main())
