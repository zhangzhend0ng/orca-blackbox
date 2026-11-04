#!/usr/bin/env python3
"""diag_m8b_system_preset.py — which dialog opens when the slot runs on the
SYSTEM preset instead of the project-carried one?

Context (user instruction 09-24): the test must drive SYSTEM filament presets,
not the project's embedded preset values. mixed_filament_test.3mf carries 50
filament_* overrides, so slot 2 reads 'Snapmaker PLA Silk @U1 0.8 nozzle*' (name
+ Orca's profile-modified marker) and the case used to keep those values.

Hypothesis to test: the case header's rule — "only Snapmaker-named presets open
the official FilamentColorDialog (色卡库/178 colours), everything else falls back
to the legacy wx picker" — may only hold once the slot is in a CLEAN preset
state, the project override being what forced the native Windows picker.

    C:\\Python311\\python.exe diag\\diag_m8b_system_preset.py
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

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d8sys]"
OUT = HERE / "artifacts" / "m8b_syspreset"


def screen_bgr():
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives={ok} colored_frac={frac:.3%}")
        time.sleep(1.0)

        slots = m8.filament_slots(session)
        hit = next((s for s in slots if s["slot"] == 2), None)
        before = m8.combo_text(hit["combo"][2]) if hit and hit.get("combo") else ""
        print(f"{LOG} slot2 combo before: {before!r} (asterisk={'*' in before})")

        applied = m8.switch_filament_preset(session, slot=2,
                                            target_substr="Snapmaker PLA Silk",
                                            force=True)
        after = m8.combo_text(hit["combo"][2]) if hit and hit.get("combo") else ""
        print(f"{LOG} slot2 combo after re-apply: {after!r} (returned {applied!r}) "
              f"(asterisk={'*' in after})")

        dlg = m8.click_color_picker(session, slot=2)
        if not dlg:
            print(f"{LOG} FAIL: no dialog")
            return 1
        cls, title, rect, hwnd = dlg
        kids = export_util._children_texts(hwnd)
        named = [(t.strip(), r) for t, r, _h in kids if t.strip()]
        print(f"{LOG} dialog class={cls!r} title={title!r} rect={rect} "
              f"children={len(kids)}")
        for t, r in named[:22]:
            print(f"{LOG}   {t[:40]!r} {r}")
        img = screen_bgr()
        crop = img[max(0, rect[1] - 20):rect[3] + 20, max(0, rect[0] - 20):rect[2] + 20]
        cv2.imwrite(str(OUT / "dialog_after_system_preset.png"), crop)
        print(f"{LOG} saved dialog_after_system_preset.png {crop.shape[1]}x{crop.shape[0]}")
        # the official 色卡库 would show SKU/colour names as child texts; the
        # native picker shows the Basic/Custom/HSL/RGB set measured 09-24
        native = any("basic colors" in t.lower() for t, _r in named)
        print(f"{LOG} verdict: dialog is {'NATIVE picker' if native else 'not the native picker'}"
              f" (official library would list SKU/colour rows instead)")
        m8.close_dialog_by_button(dlg, "Cancel")
        time.sleep(0.5)
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
