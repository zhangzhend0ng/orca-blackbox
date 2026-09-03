#!/usr/bin/env python3
# m0_anchor_health.py — UI-change smoke (STRUCTURING_PLAN 第二期 #1): boot
# the app and match EVERY idle-boot anchor from harness/anchors.py, printing
# the invalid list. A UI upgrade surfaces here in ~2 minutes as a precise
# "which anchors died" report instead of 35 red regression cases.
#
# Covered: the 5 idle-boot templates (Prepare active/inactive, Preview
# active/inactive, idle slice button), the tab color probes (teal selected /
# gray unselected), and the viewport region gate (standard fixture must
# render chromatic content). SLICE_BUTTON_DONE is context-gated (only
# exists mid/after a slice) — reported SKIP, never failed here.
# OCR needle corpora live at their harness call-sites and are not
# independently matchable without driving flows — out of health scope.
#
# Black-box path: boot standard fixture -> wait Prepare settles -> one
# steady capture -> match all templates + probe tab colors + viewport gate
# -> print the invalid list -> verdict (RED if anything idle-boot failed).

import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent.parent  # repo root
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import anchors, winutil  # noqa: E402
from m2_slice_chain import has_colored_content, wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

LOG = "[health]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    invalid = []
    out_dir = HERE / "artifacts" / "m0_anchor_health"
    out_dir.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=args.model)
    try:
        # steady state: Prepare tab settled (same boot race m1 waits through)
        score, px, py = anchors.wait_for(session, anchors.TAB_PREPARE_ACTIVE,
                                         timeout_s=45.0)
        print(f"{LOG} boot settled on Prepare: score={score:.3f} "
              f"tab center=({px},{py})")
        if score < anchors.MATCH_THRESHOLD:
            print(f"{LOG} FAIL: app never reached the Prepare page")
            return 2
        winutil.demote_window(session.hwnd)
        time.sleep(1.0)  # settings panel layout settle
        img = anchors.capture_bgr(session)
        cv2.imwrite(str(out_dir / "steady.png"), img)

        # 1) template anchors (idle-boot set)
        for name in anchors.IDLE_BOOT_TEMPLATES:
            s, *_ = anchors.match(img, name)
            th = anchors.ANCHORS[name]["threshold"]
            ok = s >= th
            print(f"{LOG} template {name}: {s:.3f} (gate {th}) "
                  f"{'PASS' if ok else 'FAIL'}")
            results[f"template {name}"] = "PASS" if ok else "FAIL"
            if not ok:
                invalid.append(name)
                cv2.imwrite(str(out_dir / f"fail_{name}.png"), img)

        # 2) tab color probes
        px_, py_ = anchors.TAB_PREPARE_PROBE
        ok_teal = anchors.is_tab_teal(img, px_, py_)
        print(f"{LOG} tab teal probe {anchors.TAB_PREPARE_PROBE}: "
              f"BGR={img[py_, px_]} -> {'PASS' if ok_teal else 'FAIL'}")
        results["tab teal probe (Prepare selected)"] = (
            "PASS" if ok_teal else "FAIL")
        qx_, qy_ = anchors.TAB_PREVIEW_PROBE
        ok_gray = anchors.is_tab_unselected(img, qx_, qy_)
        print(f"{LOG} tab unselected probe {anchors.TAB_PREVIEW_PROBE}: "
              f"BGR={img[qy_, qx_]} -> {'PASS' if ok_gray else 'FAIL'}")
        results["tab unselected probe (Preview)"] = (
            "PASS" if ok_gray else "FAIL")
        if not ok_teal:
            invalid.append("tab_teal_probe")
        if not ok_gray:
            invalid.append("tab_unselected_probe")

        # 3) viewport region: the standard fixture must render chromatic
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        frac2 = has_colored_content(anchors.capture_bgr(session))
        ok_vp = ok_model and frac2 > anchors.MODEL_COLORED_THRESHOLD
        print(f"{LOG} viewport chromatic: {frac2:.2%} "
              f"(gate {anchors.MODEL_COLORED_THRESHOLD:.2%}) "
              f"model={ok_model} -> {'PASS' if ok_vp else 'FAIL'}")
        results["viewport region content"] = "PASS" if ok_vp else "FAIL"
        if not ok_vp:
            invalid.append("viewport")

        # 4) context-gated anchors: reported, never failed by a smoke
        print(f"{LOG} context-gated (SKIP): slice_button_done — exists only "
              f"mid/after a slice")

        print(f"\n{LOG} === invalid anchors: {len(invalid)} ===")
        for n in invalid:
            print(f"  INVALID: {n}")
        results["invalid anchors"] = "PASS" if not invalid else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
