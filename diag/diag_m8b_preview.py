#!/usr/bin/env python3
"""diag_m8b_preview.py — find an observation surface for #46/#56 on 2.4.0.

Why: m8b's #46 ("确定生效") reads the SIDEBAR filament swatch, but 2.4.0's
sidebar slot has a fixed color-wheel icon (no live color bitmap) — the case
header itself documents the intended surface as "重开弹窗当前选中色变化
(swatch 像素)", i.e. DIALOG-internal. #56 ("模型渲染显示双拼/渐变耗材主色")
is currently a weak sidebar-pixel assertion, while the baseline sentence is
about the MODEL RENDER.

This probe answers, with pixels instead of guesses:
  phase dialog  — open the official Color dialog twice (before pick / after
                  pick+OK) and diff the dialog rect, so the current-color
                  indicator cell is located by EVIDENCE (it is the cell that
                  changes), not by a hardcoded offset.
  phase rainbow — set slot 2 to a 双拼/渐变 preset and measure the model's
                  rendered colors (hue clusters on the plate) as the surface
                  for #56.

    C:\\Python311\\python.exe diag\\diag_m8b_preview.py --phase dialog
    C:\\Python311\\python.exe diag\\diag_m8b_preview.py --phase rainbow
"""
import argparse
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
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d8b]"
OUT = HERE / "artifacts" / "m8b_probe"


def grab_screen():
    """Desktop pixels as BGR (screen coordinates, unambiguous).

    winutil.screen_grab returns (w, h, BGRA bytes) — decode it here; the
    window-capture path (PrintWindow) can time out while the app is busy.
    """
    sw, sh, buf = winutil.screen_grab()
    arr = np.frombuffer(buf, np.uint8).reshape(sh, sw, 4)
    return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)


def crop(img, rect):
    x0, y0, x1, y1 = rect
    x0 = max(0, x0); y0 = max(0, y0)
    return img[y0:y1, x0:x1]


def dump_children(dlg, tag):
    kids = export_util._children_texts(dlg[3])
    print(f"{LOG} {tag}: dialog={dlg[0]!r} rect={dlg[2]} children={len(kids)}")
    named = [(t.strip(), r) for t, r, _h in kids if t.strip()]
    for t, r in named[:25]:
        print(f"{LOG}   text={t[:44]!r} rect={r}")
    return kids


def diff_regions(before, after, rect, min_delta=12, top=8):
    """Screen rects inside `rect` whose pixels changed the most."""
    x0, y0, x1, y1 = rect
    b = crop(before, rect).astype(int)
    a = crop(after, rect).astype(int)
    if b.shape != a.shape or b.size == 0:
        return []
    d = np.abs(a - b).max(axis=2)
    mask = (d > min_delta).astype(np.uint8)
    n, lab, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 20:
            continue
        sub = d[y:y + h, x:x + w]
        out.append((int(sub.max()), int(area), w, h,
                    (x0 + x, y0 + y, x0 + x + w, y0 + y + h)))
    out.sort(key=lambda t: -t[1])
    return out[:top]


def phase_dialog(session):
    dlg = m8.click_color_picker(session, slot=2)
    if not dlg:
        print(f"{LOG} FAIL: color dialog did not open")
        return 1
    time.sleep(0.8)
    before = grab_screen()
    cv2.imwrite(str(OUT / "dialog_before.png"), crop(before, dlg[2]))
    kids = dump_children(dlg, "before")

    cards = [(t, r) for t, r, _h in kids
             if not t.strip() and (r[2] - r[0]) in range(24, 60)
             and (r[3] - r[1]) in range(24, 60)]
    print(f"{LOG} candidate cards (empty 24-60px cells): {len(cards)}")
    for r in [r for _t, r in cards[:12]]:
        print(f"{LOG}   card rect={r}")
    if not cards:
        print(f"{LOG} FAIL: no card cells found — layout differs")
        return 1

    # pick the most saturated card in the grid: a strong change is easiest to
    # see, and it is what '#46 更改颜色' means for a user
    best, best_sat = None, -1
    for _t, r in cards[:40]:
        c = crop(before, r)
        if c.size == 0:
            continue
        bgr = c.reshape(-1, c.shape[-1])[:, :3].astype(int)
        sat = int((bgr.max(axis=1) - bgr.min(axis=1)).mean())
        if sat > best_sat:
            best, best_sat = r, sat
    print(f"{LOG} picking card rect={best} saturation={best_sat}")
    if not best:
        return 1
    winutil.msg_click_screen((best[0] + best[2]) // 2, (best[1] + best[3]) // 2)
    time.sleep(0.8)
    picked = grab_screen()
    cv2.imwrite(str(OUT / "dialog_after_pick.png"), crop(picked, dlg[2]))

    if not m8.close_dialog_by_button(dlg, "OK"):
        print(f"{LOG} FAIL: no OK button")
        return 1
    time.sleep(1.2)
    print(f"{LOG} OK clicked; dialog visible now: "
          f"{bool(winutil.user32.IsWindowVisible(dlg[3]))}")

    dlg2 = m8.click_color_picker(session, slot=2)
    if not dlg2:
        print(f"{LOG} FAIL: reopen failed")
        return 1
    time.sleep(0.8)
    after = grab_screen()
    cv2.imwrite(str(OUT / "dialog_reopened_after_ok.png"), crop(after, dlg2[2]))
    dump_children(dlg2, "reopened")

    # the current-color indicator is the cell that DIFFERS between the
    # reopened dialog and the pre-pick one
    regions = diff_regions(before, after, dlg[2])
    print(f"{LOG} dialog-rect diff regions (max_delta, area, w, h, rect):")
    for r in regions:
        print(f"{LOG}   {r}")
    if not regions:
        print(f"{LOG} WARN: nothing in the dialog changed after pick+OK")

    # sidebar swatch: does 2.4.0's slot bitmap track the color at all? (this
    # decides whether #46/#56 can keep reading it, or must move to the dialog
    # indicator / the model render)
    slots = m8.filament_slots(session)
    hit = next((s for s in slots if s["slot"] == 2), None)
    print(f"{LOG} slot2 picker client-rect: {hit and hit.get('picker')}")
    if hit and hit.get("picker"):
        x0, y0, x1, y1 = hit["picker"]
        sx0, sy0 = winutil.client_to_screen(session.hwnd, x0, y0)
        sx1, sy1 = winutil.client_to_screen(session.hwnd, x1, y1)
        r = (sx0, sy0, sx1, sy1)
        c0, c1 = crop(before, r), crop(after, r)
        if c0.size and c1.size:
            m0 = c0.reshape(-1, c0.shape[-1])[:, :3].mean(axis=0)
            m1 = c1.reshape(-1, c1.shape[-1])[:, :3].mean(axis=0)
            print(f"{LOG} sidebar picker mean BGR {[int(v) for v in m0]} -> "
                  f"{[int(v) for v in m1]} "
                  f"(delta={int(abs(m1 - m0).max())})")
            cv2.imwrite(str(OUT / "slot2_picker_before.png"), c0)
            cv2.imwrite(str(OUT / "slot2_picker_after.png"), c1)

    m8.close_dialog_by_button(dlg2, "Cancel")
    time.sleep(0.5)
    return 0


HUE_NAMES = [(0, 15, "red"), (15, 40, "orange/yellow"), (40, 75, "green"),
             (75, 165, "cyan/blue"), (165, 180, "pink/red")]


def hue_clusters(img, rect):
    """(cluster name, pixel share) for saturated pixels inside a screen rect."""
    c = crop(img, rect)
    if c.size == 0:
        return []
    bgr = c[:, :, :3].astype(np.uint8)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(int)
    val = hsv[:, :, 2].astype(int)
    keep = (sat > 60) & (val > 60)
    if keep.sum() < 50:
        return []
    hues = hsv[:, :, 0][keep].astype(int)
    total = len(hues)
    out = []
    for lo, hi, name in HUE_NAMES:
        n = int(((hues >= lo) & (hues < hi)).sum())
        if n / total > 0.02:
            out.append((name, round(n / total, 3)))
    out.sort(key=lambda t: -t[1])
    return out


def phase_rainbow(session):
    ok, frac = m8.wait_arrival(session)
    print(f"{LOG} model arrives={ok} colored_frac={frac:.3%}")
    if not ok:
        return 1
    # a cube on the plate renders the slot color in the viewport
    final = m8.switch_filament_preset(session, slot=2, target_substr="Rainbow")
    print(f"{LOG} slot2 preset -> {final!r}")
    time.sleep(2.0)

    img = grab_screen()
    h, w = img.shape[:2]
    viewport = (m7.VIEWPORT_X0 + 10, 110, w - 10, h - 60)
    cv2.imwrite(str(OUT / "rainbow_viewport.png"), crop(img, viewport))
    clusters = hue_clusters(img, viewport)
    print(f"{LOG} viewport hue clusters: {clusters}")

    # where is the model? reuse the blob finder, then measure hues around
    # each click point (model_candidates returns centers, not rects)
    cands = m7.model_candidates(session)
    print(f"{LOG} model candidates (client pts): {cands}")
    for i, (cx, cy) in enumerate(cands[:4], start=1):
        sx, sy = m7.client(session, cx, cy)
        rect = (sx - 60, sy - 60, sx + 60, sy + 60)
        cl = hue_clusters(img, rect)
        print(f"{LOG}   candidate {i} client=({cx},{cy}) screen=({sx},{sy}) hues={cl}")
    return 0


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    ap.add_argument("--phase", choices=("dialog", "rainbow"), default="dialog")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    session = boot_session(args, model=args.model)
    try:
        if args.phase == "dialog":
            return phase_dialog(session)
        return phase_rainbow(session)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
