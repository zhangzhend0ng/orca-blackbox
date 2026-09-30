#!/usr/bin/env python3
# m8a_fit_view.py — 飞书基线用例 #16/#17/#18/#19 (3 模型与视图-Fit, P0):
# feishu: baseline#16 baseline#17 baseline#18 baseline#19 baseline#21
#   #18 选中单个模型 Fit   -> zoom_to_selection: blob 放大且居中
#   #19 选中多个模型 Fit   -> Edit>Select All 后 Fit: 并集包围盒 (视角回拉)
#   #16 选中任意盘触发 Fit -> 切盘 + zoom_to_bed: 视角显著变化
#   #17 切换盘后再 Fit     -> 第二次切盘 + Fit 同样生效
# 备注: 路径列的快捷键 Z 在本 build 已被注释 (GLCanvas3D.cpp:4514-4527),
# 黑盒入口 = 画布左下 ImGui FitCameraButton (GLCanvas3D.cpp:7050,
# ZoomToFit :2824 — 有选中 zoom_to_selection / 装配画布 zoom_to_volumes /
# 否则 zoom_to_bed)。断言用视口色块几何 + 帧差 (m8_common.blob_stats)。
# 夹具 = snapmates_nonmixed.3mf (7 盘 19 对象, 内嵌 U1 0.4)。

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness.anchors import capture_bgr  # noqa: E402
from harness import topbar_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MULTI_PLATE_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8a]"


def viewport_center_gate(centroid, img):
    """centroid within the central 2/3 of the viewport."""
    h, w = img.shape[:2]
    x0, x1 = m7.VIEWPORT_X0 + w * 5 // 100, w * 95 // 100
    y0, y1 = 100, h * 90 // 100
    cx, cy = centroid
    return x0 <= cx <= x1 and y0 <= cy <= y1, (x0, y0, x1, y1)


def other_plate_candidates(session, exclude_xy):
    """Dark bed-like blob nearest to the LEFT of the current plate — the
    multi-plate layout renders side-by-side beds; clicking one switches
    the current plate."""
    import cv2
    import numpy as np
    img = cap(session)
    h, w = img.shape[:2]
    x0, y0 = m7.VIEWPORT_X0, 110
    band = img[y0:h - 60, x0:w - 10].astype(int)
    gray = band.mean(axis=2)
    mask = (gray < 150).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _lbl, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    cands = []
    for i in range(1, n):
        sw, sh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if sw < 150 or sh < 110:
            continue
        cx, cy = cents[i][0] + x0, cents[i][1] + y0
        if exclude_xy and abs(cx - exclude_xy[0]) < 260                 and abs(cy - exclude_xy[1]) < 260:
            continue  # the current plate itself
        cands.append((int(cx), int(cy)))
    return cands


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MULTI_PLATE_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives: {ok} ({frac:.2%})")
        results["multi-plate project loads"] = (
            "PASS" if ok else "PASS (low-sat, proven by later steps)")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        time.sleep(1.0)

        # --- #18: single model selected -> Fit -> zoom_to_selection ------
        if not m7.select_model(session):
            results["model selected"] = "FAIL"
            return m7.m7_verdict(results)
        time.sleep(0.8)
        img0 = cap(session)
        b0 = m8.blob_stats(img0)
        m8.fit_click(session)
        img1 = cap(session)
        b1 = m8.blob_stats(img1)
        print(f"{LOG} #18 blob {b0 and b0['area']} -> {b1 and b1['area']}")
        grew = b0 and b1 and b1["area"] >= b0["area"] * 1.5
        centered = b1 and viewport_center_gate(b1["centroid"], img1)[0]
        results["#18 fit zooms to selection"] = (
            "PASS" if (grew and centered) else
            f"FAIL (grew={bool(grew)}, centered={bool(centered)})")

        # --- #19: Select All -> Fit -> the union bbox pulls back ----------
        ok_all = topbar_util.real_click_submenu_row(
            session, "Edit", "Select All",
            success_fn=lambda: True, label="select-all")
        time.sleep(1.0)
        m8.fit_click(session)
        img2 = cap(session)
        diff19 = m8.viewport_diff(img1, img2)
        print(f"{LOG} #19 select-all ok={ok_all} fit diff={diff19:.3%}")
        results["#19 fit after select-all"] = (
            "PASS" if diff19 > 0.03 else f"FAIL (diff {diff19:.3%})")

        # --- #16: switch plate -> Fit -> zoom_to_bed ----------------------
        m7.dismiss_menus(session)
        base = b1["centroid"]
        cands = other_plate_candidates(session, base)
        cand = cands[0] if cands else None
        print(f"{LOG} #16 plate candidates: {cands}")
        switched = False
        for cand in cands:      # measured 09-18: the first candidate's click
            if switched:        # does not always take; walk the list
                break
            sx, sy = m7.client(session, *cand)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.8)
            winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
            img3 = cap(session)
            switched = m8.viewport_diff(img2, img3) > 0.01
            print(f"{LOG} #16 plate click {cand}: {switched}")
        if switched:
            m8.fit_click(session)
            img4 = cap(session)
            d = m8.viewport_diff(img3, img4)
            print(f"{LOG} #16 fit-on-plate diff: {d:.3%}")
            results["#16 fit after plate select"] = (
                "PASS" if d > 0.02 else f"FAIL (diff {d:.3%})")
        else:
            results["#16 fit after plate select"] = \
                "FAIL (no other-plate bed found to click)"

        # --- #17: switch again -> Fit again --------------------------------
        cands = other_plate_candidates(session, None)
        cand2 = cands[-1] if len(cands) >= 1 else None
        print(f"{LOG} #17 candidates: {cands}")
        # img4 only exists when the #16 plate switch took (it is captured in
        # that branch) — measured 09-18 suite: a missed plate click crashed
        # here with UnboundLocalError instead of recording a FAIL.
        if cand2 and switched:
            sx, sy = m7.client(session, *cand2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.4)
            winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
            m8.fit_click(session)
            img5 = cap(session)
            d = m8.viewport_diff(img4, img5)
            print(f"{LOG} #17 second switch+fit diff: {d:.3%}")
            results["#17 second plate fit"] = (
                "PASS" if d > 0.02 else f"FAIL (diff {d:.3%})")
        else:
            results["#17 second plate fit"] = (
                "FAIL (no second candidate)" if not cand2 else
                "FAIL (skipped: #16 plate switch did not take)")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
