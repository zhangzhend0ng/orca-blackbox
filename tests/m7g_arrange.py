#!/usr/bin/env python3
# m7g_arrange.py — Feishu #17 (GUI业务, P1):
#   【正向】多模型重叠后自动整理分离
#
# Source facts: the toolbar 'Arrange all objects' [A] item (GLCanvas3D:7740,
# ArrangerJob/arrange wrapper) runs Plater::arrange; the mixed fixture model
# plus an Add-Primitive cube (which lands at the plate CENTER, i.e.
# overlapping) give the overlapping multi-model state the record's
# precondition asks for. Per-plate/global arrange split is out of a
# single-plate black-box reach (noted in the mapping).
#
# Black-box path: boot mixed fixture -> bed menu > Add Primitive > Cube
# (overlap) -> click the Arrange slot -> the viewport must show >= 2
# distinct chromatic blobs whose centroids are far apart (separation).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from harness.anchors import VIEWPORT_X0, capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7g]"


def top2_centroids(session):
    """The two largest chromatic blob centroids of the viewport."""
    img = capture_bgr(session)
    h, w = img.shape[:2]
    band = img[110:h - 60, VIEWPORT_X0 + 10:w - 10].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _l, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    out = [cents[i] for i in order[:2] if stats[i, cv2.CC_STAT_AREA] >= 400]
    return out



def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.0)

        # overlapping second model: a primitive lands at the plate center
        before = m7.model_colored_frac(session)
        added = m7.context_click_row(
            session, "bed", "cube", via="Add Primitive",
            success_fn=lambda: m7.model_colored_frac(session) > before + 0.001,
            label="add-cube")
        print(f"{LOG} cube added over the model: {added}")
        results["second model added (overlap)"] = (
            "PASS" if added else "FAIL")

        arr_x, tip = m7.find_slot(session, lambda t: "arrange" in t)
        results["arrange slot located"] = (
            f"PASS ({tip!r})" if arr_x else "FAIL")
        if arr_x is None:
            return m7.m7_verdict(results)
        m7.click_slot(session, arr_x)
        time.sleep(6.0)  # the arranger runs async (job + refresh)

        cents = top2_centroids(session)
        print(f"{LOG} top-2 blob centroids: {cents}")
        results["two models present"] = "PASS" if len(cents) >= 2 else "FAIL"
        if len(cents) >= 2:
            dist = float(np.hypot(cents[0][0] - cents[1][0],
                                  cents[0][1] - cents[1][1]))
            print(f"{LOG} centroid distance: {dist:.0f}px")
            results["models separated after arrange"] = (
                f"PASS ({dist:.0f}px)" if dist > 120 else
                f"FAIL ({dist:.0f}px)")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
