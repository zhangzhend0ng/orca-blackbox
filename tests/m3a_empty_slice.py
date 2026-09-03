#!/usr/bin/env python3
# m3a_empty_slice.py — P3-13: an empty scene rejects slicing.
#
# White-box ref: wx_gui_business_tests.cpp:638. Source gate:
# MainFrame::get_enable_slice_status() (MainFrame.cpp:1989) — an empty
# plate fails can_slice(), so clicking Slice starts nothing.
#
# Black-box assertion: click Slice on an empty scene and the slice NEVER
# leaves the idle rendering (no background process starts, no done badge,
# Preview stays empty). click_slice_start already encodes exactly this:
# it only reports "started" when the button leaves its idle rendering.
# Additionally verify Preview shows no toolpath after a grace window.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import anchors  # noqa: E402
from harness.anchors import IDLE_DONE_SCORE  # noqa: E402
from m1_minimal_loop import capture_bgr, click_and_verify, match  # noqa: E402
from m2_slice_chain import (TOOLPATH_COLORED_FLOOR, click_slice_start,  # noqa: E402
                            has_colored_content)
from m3_common import add_common_args, boot_session, verdict  # noqa: E402


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)  # no model = empty scene
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=None)
    try:
        # 1) Slice click must NOT start anything on the empty scene
        started = click_slice_start(session)
        print(f"[m3a] slice click started a job: {started}")
        results["empty scene rejects slice"] = (
            "PASS" if not started else "FAIL")

        # 2) grace window: the idle rendering must be PRESERVED (the done
        #    template alone false-positives on the print-button area of an
        #    empty scene — see wait_slicing_done's idle gate)
        time.sleep(6.0)
        idle_score, _, _, _, _ = match(capture_bgr(session),
                                       anchors.SLICE_PLATE_BUTTON)
        print(f"[m3a] idle button preserved after grace: {idle_score:.3f}")
        results["button stays idle on empty scene"] = (
            "PASS" if idle_score >= IDLE_DONE_SCORE else "FAIL")

        # 3) Preview tab: no toolpath
        ok_pv, _ = click_and_verify(session, anchors.TAB_PREVIEW_INACTIVE,
                                    anchors.TAB_PREVIEW_ACTIVE)
        time.sleep(2.0)
        colored = has_colored_content(capture_bgr(session))
        print(f"[m3a] Preview colored fraction: {colored:.3%} "
              f"(floor {TOOLPATH_COLORED_FLOOR:.3%})")
        results["preview stays empty"] = (
            "PASS" if ok_pv and colored < TOOLPATH_COLORED_FLOOR else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3a] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
