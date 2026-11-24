"""Measure Feishu #18 on a single coloured cube, fixed wait vs observed readiness.

Explicit profiling case. The silhouette is a colour proxy. This script reports
the four margins but cannot certify the product owner's approximate tolerance.
"""
# feishu: baseline#18
import argparse
import hashlib
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import cv2
import win32gui

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from m8a_fit_view import cap, m7, m8, winutil
from m3_common import add_common_args, boot_session

FIXTURE = ROOT / "fixtures/feishu_std_cube.3mf"


@contextmanager
def measure(row, stage):
    start = time.perf_counter()
    try:
        yield
    finally:
        row["seconds"][stage] = round(time.perf_counter() - start, 3)


def viewport(session):
    handles = []
    def collect(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "wxGLCanvas":
            handles.append(hwnd)
        return True
    win32gui.EnumChildWindows(session.hwnd, collect, None)
    def rect(hwnd):
        return [win32gui.ScreenToClient(session.hwnd, win32gui.ClientToScreen(hwnd, xy))
                for xy in [(0, 0), win32gui.GetClientRect(hwnd)[2:]]]
    rects = [rect(h) for h in handles]
    if not rects:
        raise ValueError("no visible wxGLCanvas")
    return max(rects, key=lambda r: (r[1][0] - r[0][0]) * (r[1][1] - r[0][1]))


def cube(frame, bounds):
    (l, t), (r, b) = bounds
    if not (0 <= l < r <= frame.shape[1] and 0 <= t < b <= frame.shape[0]):
        raise ValueError("canvas outside capture")
    # The one-object fixture binds slot 1, #D9A63A (OpenCV hue ~20).
    hsv = cv2.cvtColor(frame[t:b, l:r], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (10, 55, 40), (30, 255, 255))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if len(stats) < 2:
        return None
    x, y, w, h, area = map(int, max(stats[1:], key=lambda s: s[4]))
    if min(w, h) < 12 or area < 300:
        return None
    margins = (x/(r-l), (r-l-x-w)/(r-l), y/(b-t), (b-t-y-h)/(b-t))
    return {"bbox": [x, y, w, h], "area": area, "margins": [round(v, 4) for v in margins],
            "touches_edge": min(margins) == 0,
            "within_proposed_8_12_percent": all(.08 <= v <= .12 for v in margins)}


def select_cube(session, row):
    # This client coordinate is a hint from the fixed pass. Require the
    # disabled-to-enabled Rotate tooltip transition before trusting it.
    rotate_x = 1108
    m7.ensure_maximized(session)
    bounds = viewport(session)
    target = cube(cap(session), bounds)
    if target:
        old = m7.tooltip_text(session, rotate_x, m7.BAR_Y).lower()
        if "rotate" in old and "select" in old:
            x, y, w, h = target["bbox"]
            (left, top), _ = bounds
            xy = m7.client(session, left + x + w//2, top + y + 3*h//4)
            winutil.user32.SetCursorPos(*xy)
            winutil.real_click_screen(*xy)
            new = m7.tooltip_text(session, rotate_x, m7.BAR_Y).lower()
            row["selection_tooltips"] = [old, new]
            if "rotate" in new and "[r" in new and "select" not in new:
                row["selection_path"] = "confirmed_hint"
                return True
    row["selection_path"] = "toolbar_scan"
    return m7.select_model(session)


def observe(session, mode, row):
    with measure(row, "arrival"):
        arrived, _ = m8.wait_arrival(session, timeout_s=35)
        if not arrived:
            raise ValueError("fixture arrival unconfirmed")
    with measure(row, "select"):
        selected = select_cube(session, row) if mode == "guided_select" else m7.select_model(session)
        if not selected:
            raise ValueError("object selection unconfirmed")
    with measure(row, "pre_fit"):
        bounds = viewport(session)
        frame = cap(session)
        initial = cube(frame, bounds)
        row.update(canvas=bounds, before=initial)
        if initial is None:
            raise ValueError("fixture colour missing before Fit")
    with measure(row, "click"):
        xy = m7.client(session, m7.VIEWPORT_X0 + m8.FIT_X_OFF, frame.shape[0] - m8.FIT_Y_FROM_BOTTOM)
        winutil.user32.SetCursorPos(*xy)
        time.sleep(.3)
        winutil.msg_click_screen(*xy, session.hwnd)
    with measure(row, "fit_observe"):
        start = time.perf_counter()
        samples = row["samples"] = []
        stable = 0
        last_box = None
        while time.perf_counter() - start < 5:
            state = cube(cap(session), bounds)
            elapsed = time.perf_counter() - start
            samples.append({"s": round(elapsed, 3), "state": state})
            if state and state["area"] >= 1.5 * initial["area"]:
                box = state["bbox"]
                same = last_box and max(abs(a-b) for a, b in zip(last_box, box)) <= 2
                stable = stable + 1 if same else 1
                last_box = box
                if stable >= 3 and (mode != "fixed" or elapsed >= 1.5):
                    row["after"] = state
                    return
            else:
                stable, last_box = 0, None
            time.sleep(.10)
        raise ValueError("enlarged stable fixture silhouette unconfirmed")


def main(modes=("fixed", "ready"), output_name="fit18_profile.json"):
    args = add_common_args(argparse.ArgumentParser(), default_model=FIXTURE).parse_args()
    if args.model.resolve() != FIXTURE.resolve():
        raise ValueError("profiling contract requires the one-cube fixture")
    report = {"case": 18, "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), "runs": []}
    for mode in modes:
        row = {"mode": mode, "seconds": {}}
        report["runs"].append(row)
        start = time.perf_counter()
        try:
            with measure(row, "fresh_boot"):
                session = boot_session(args, model=FIXTURE)
            try:
                observe(session, mode, row)
            finally:
                with measure(row, "close"):
                    session.close()
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["wall_s"] = round(time.perf_counter() - start, 3)
        (ROOT / "artifacts" / output_name).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[fit18] {mode} {row['seconds']} {row.get('error', 'observed')}", flush=True)
    # This is a timing experiment. Keep row #18 outside the release verdict.
    return int(any("after" not in r or "error" in r for r in report["runs"]))


if __name__ == "__main__":
    raise SystemExit(main())
