#!/usr/bin/env python3
# diag_fa706g3_mixing_panel.py — why is the right-side 'Color Mixing Match'
# panel missing on the fa706g3 physical Win10 host (Task C env baseline)?
#
# Mirrors m3j's boot exactly (seed -> launch MIXED_3MF -> hands-off ->
# maximize -> gl ready), then dumps EVERY titled child of the main window,
# the seeded datadir/system vendor set, and a screenshot — no guessing.
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import env_check, mixing_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        from m2_slice_chain import wait_model_loaded
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[diag] model arrived: {ok_model} (colored {frac:.2%})")

        rows = mixing_util.children(session.hwnd)
        titled = [{"text": t, "class": c, "rect": list(r), "hwnd": h}
                  for (t, c, r, h) in rows if t.strip()]
        print("[diag] titled children (%d/%d):" % (len(titled), len(rows)))
        for row in titled:
            print("   %-28r %s %s" % (row["text"][:28], row["class"],
                                      row["rect"]))

        vendors = sorted(p.name for p in
                         (Path(args.datadir) / "system").iterdir()
                         if p.is_dir()) if (Path(args.datadir) / "system").exists() else []
        print("[diag] datadir/system vendors: %s" % vendors)

        w, h, bgra = winutil.capture_window(session.hwnd)
        out = HERE / "artifacts" / "diag_fa706g3_mixing_panel"
        out.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        import numpy as np
        img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
        Image.fromarray(img[:, :, ::-1].copy(), "RGB").save(out / "panel_state.png")
        (out / "children.json").write_text(
            json.dumps({"titled": titled, "vendors": vendors,
                        "model_arrived": ok_model, "colored": frac},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print("[diag] artifacts -> %s" % out)
    finally:
        winutil.close_window(session.hwnd)
        time.sleep(2)
        session.popen.wait(timeout=20)
    return 0


if __name__ == "__main__":
    sys.exit(main())
