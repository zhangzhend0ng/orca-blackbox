# anchors.py — named UI-locator asset registry (STRUCTURING_PLAN 第二期 #1).
#
# Single home for the things a UI change can break: template images, tab
# color probes, viewport geometry, named dialog regions, and the shared
# match machinery. Case scripts import from here; they must not carry
# scattered coordinates/thresholds. The companion smoke case
# tests/m0_anchor_health.py boots the app and matches every idle-boot
# anchor, so a UI change surfaces as a 5-minute failure list instead of
# 35 red cases.
#
# Scope: anything DUPLICATED across cases or calibrated against the app UI
# (templates, colors, regions, reused thresholds) lives here. Single-use
# case-local numbers stay in the case (over-abstraction hurts review).
# Harness-internal calibrated bands (process_panel/topbar_util internals)
# are already the organized home and stay there.
#
# The ANCHORS table at the bottom is the machine-readable view (consumed by
# m0_anchor_health); the module-level names are the import-friendly
# projections. Keys are stable IDs — never rename (same rule as cases.py).

import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import winutil  # noqa: E402

RESOURCE = HERE / "resource" / "image"

# --- template images (OpenCV matchTemplate) ------------------------------
# All measured on the maximized window unless noted; cut rects live in
# TEMPLATE_CUTS below.
TAB_PREPARE_ACTIVE = "tab_prepare_active.png"
TAB_PREPARE_INACTIVE = "tab_prepare_inactive.png"
TAB_PREVIEW_ACTIVE = "tab_preview_active.png"
TAB_PREVIEW_INACTIVE = "tab_preview_inactive.png"
SLICE_PLATE_BUTTON = "slice_plate_button.png"
SLICE_BUTTON_DONE = "slice_button_done.png"

TEMPLATE_PATHS = {
    TAB_PREPARE_ACTIVE: RESOURCE / TAB_PREPARE_ACTIVE,
    TAB_PREPARE_INACTIVE: RESOURCE / TAB_PREPARE_INACTIVE,
    TAB_PREVIEW_ACTIVE: RESOURCE / TAB_PREVIEW_ACTIVE,
    TAB_PREVIEW_INACTIVE: RESOURCE / TAB_PREVIEW_INACTIVE,
    SLICE_PLATE_BUTTON: RESOURCE / SLICE_PLATE_BUTTON,
    SLICE_BUTTON_DONE: RESOURCE / SLICE_BUTTON_DONE,
}

# idle-boot state: the tab bar shows Prepare-active + Preview-inactive and
# the idle slice button; SLICE_BUTTON_DONE only exists mid/after a slice
# (context-gated — m0_anchor_health skips it).
IDLE_BOOT_TEMPLATES = (
    TAB_PREPARE_ACTIVE, TAB_PREPARE_INACTIVE,
    TAB_PREVIEW_ACTIVE, TAB_PREVIEW_INACTIVE,
    SLICE_PLATE_BUTTON,
)


def template_path(name: str) -> Path:
    """Resolve a template NAME (stable ID) or pass a Path through."""
    p = TEMPLATE_PATHS.get(name)
    return p if p is not None else Path(name)


# --- match thresholds -----------------------------------------------------
# TM_CCOEFF_NORMED gate for all tab/button templates (m1, since 08-2x).
MATCH_THRESHOLD = 0.80
# Button-state gates: idle-plate / done-badge must score >= this to count
# (m3a/m3d; false-positives on the empty-bed print-button area measured).
IDLE_DONE_SCORE = 0.9

# --- tab color probes (ButtonsListCtrl, Notebook.cpp) ----------------------
# Selected tab bg = teal #009688 -> BGR (136,150,0); unselected = BGR
# (70,68,59). Probe points are tab-bar centers at the 1200x800 boot frame
# and hold on the maximized window (tab chrome is left-anchored).
TAB_TEAL_BGR = (136, 150, 0)
TAB_UNSELECTED_BGR = (70, 68, 59)
COLOR_TOL = 60            # L1 distance budget (measured stable)
TAB_PREVIEW_PROBE = (244, 49)
TAB_PREPARE_PROBE = (108, 49)

# Template bootstrap cuts (client px, y0:y1, x0:x1 @ the 1200x800 boot
# frame): m1 cuts the switched-state templates from the VERIFIED teal state
# only — never blind.
TEMPLATE_CUTS = {
    TAB_PREVIEW_ACTIVE: (31, 67, 176, 312),
    TAB_PREPARE_INACTIVE: (31, 67, 40, 176),
}


def is_tab_teal(img, x: int, y: int) -> bool:
    px = img[y, x]
    return (abs(int(px[0]) - TAB_TEAL_BGR[0])
            + abs(int(px[1]) - TAB_TEAL_BGR[1])
            + abs(int(px[2]) - TAB_TEAL_BGR[2])) < COLOR_TOL


def is_tab_unselected(img, x: int, y: int) -> bool:
    px = img[y, x]
    return (abs(int(px[0]) - TAB_UNSELECTED_BGR[0])
            + abs(int(px[1]) - TAB_UNSELECTED_BGR[1])
            + abs(int(px[2]) - TAB_UNSELECTED_BGR[2])) < COLOR_TOL


# --- viewport geometry + content thresholds --------------------------------
# 3D viewport (client px): right of the fixed-width sidebar, below the
# topbar (m2, measured 08-28). Right/bottom edges follow the window;
# left/top origins are fixed (sidebar/tab chrome don't scale).
VIEWPORT_X0, VIEWPORT_Y0 = 430, 70


def viewport_crop(img):
    """Viewport crop calibrated for any window size (m2_slice_chain._vp)."""
    h, w = img.shape[:2]
    return img[VIEWPORT_Y0:max(VIEWPORT_Y0 + 1, h - 8),
               VIEWPORT_X0:max(VIEWPORT_X0 + 1, w - 8)]


def viewport_diff(a, b) -> float:
    """Mean abs pixel diff over the viewport region (m3i's view-change
    detector; measured 55 for a real camera switch)."""
    va = viewport_crop(a).astype(int)
    vb = viewport_crop(b).astype(int)
    return float(np.abs(va - vb).mean())


# channel-spread floor for "clearly chromatic" (bed/grid/UI chrome are
# near-gray; toolpath/filament colors clear it by 2-4x)
SPREAD_COLORED = 40

# Fraction of viewport pixels that must be chromatic for the model to count
# as loaded: empty bed ~0.15%, multicolor model ~2.1% — 1% sits with >5x
# margin both sides (measured 2026-08-28; maximized window enlarges the
# denominator).
MODEL_COLORED_THRESHOLD = 0.006
# Absolute floor for the toolpath assertion (pre-slice baseline 0.7-2.1%
# by model; the >=2x ratio gate does the real discrimination).
TOOLPATH_COLORED_FLOOR = 0.010

# Checkbox teal-fraction gate: checked reads ~0.21, unchecked ~0.00-0.06
# (measured 08-31 maximized; the windowed-era 0.25 misclassified every
# checked state). Shared by m4g and process_panel.checked_state.
CHECKED_FRACTION = 0.13

# View-switch mean-abs-diff gate (measured 55 for plate->Top; >5x margin).
VIEW_DIFF_THRESHOLD = 10.0


def has_colored_content(img) -> float:
    """Fraction of viewport pixels that are clearly CHROMATIC (the m2
    model/toolpath detector, now viewport-crop canonical)."""
    vp = viewport_crop(img).astype(int)
    spread = vp.max(axis=2) - vp.min(axis=2)
    return float((spread > SPREAD_COLORED).mean())


# --- named dialog/panel regions --------------------------------------------
# Color Mixing sidebar panel (client px x0,y0,x1,y1) — m3p persistence
# check; the panel sits left of the mixing-match bar (measured 09-02).
SIDEBAR_COLOR_MIXING_PANEL = (40, 320, 190, 400)
# Batch dialog view panels (screen px offsets from the dialog origin, same
# convention as mixing_util.map_region_colored) — m3q original/result.
MIX_VIEW_PANEL_ORIG = (738, 451, 918, 631)
MIX_VIEW_PANEL_RESULT = (938, 451, 1165, 678)

# --- Color Painting gizmo bands (m4e, recalibrated 08-31 maximized) --------
# The gizmo toolbar row is top-anchored but centered over the 3D view: on a
# window wider than 1200 it reaches past x=1160, so the hover-scan starts at
# the viewport left edge; palette/centroid bands are viewport-relative.
PAINT_BAR_Y = 88            # gizmo toolbar row (client y)
PAINT_PITCH = 35
PAINT_SCAN_X0_OFF = 60      # scan from viewport-left + offset
PAINT_PAL_Y0, PAINT_PAL_Y1 = 55, 470
PAINT_PAL_LEFT_OFF = 250

# --- match machinery (moved from m1_minimal_loop 09-03 — it was the only
# generic matcher and harness modules had to import it from a TEST file) ----


def capture_bgr(session):
    cap = winutil.capture_window(session.hwnd)
    return cv2.cvtColor(np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4),
                        cv2.COLOR_BGRA2BGR)


def match(screen_bgr: np.ndarray, template) -> tuple:
    """Best match of template (name or path) in a BGR capture; returns
    (score, x, y, w, h) top-left."""
    path = template_path(template) if isinstance(template, str) else Path(template)
    tpl = cv2.imread(str(path))
    if tpl is None:
        raise FileNotFoundError(path)
    res = cv2.matchTemplate(screen_bgr, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return score, loc[0], loc[1], tpl.shape[1], tpl.shape[0]


def wait_for(session, template, timeout_s: float = 30.0, poll_s: float = 0.5,
             threshold: float = None):
    """Poll until `template` matches the live capture (score >= threshold).

    Startup page selection is racy (the final select_tab runs in a CallAfter
    after GL init — see GUI_App.cpp load_gl_resources), so the driver must
    WAIT for the expected visual state, never assume a fixed delay.
    Returns (score, screen_x, screen_y) of the best match.
    """
    if threshold is None:
        threshold = MATCH_THRESHOLD
    path = template_path(template) if isinstance(template, str) else Path(template)
    tpl = cv2.imread(str(path))
    deadline = time.monotonic() + timeout_s
    best = (0.0, 0, 0)
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        cx, cy = loc[0] + tpl.shape[1] // 2, loc[1] + tpl.shape[0] // 2
        ox, oy = winutil.client_to_screen(session.hwnd, 0, 0)
        best = (float(score), cx + ox, cy + oy)
        if score >= threshold:
            return best
        time.sleep(poll_s)
    return best


def click_and_verify(session, click_tpl, expect_tpl, attempts: int = 4):
    """Click the control matching `click_tpl`, retry until `expect_tpl`
    shows AND STAYS for the bounce window.

    Retrying is essential for two reasons:
      - page switches posted early after boot can be undone by late startup
        events (EVT_GLVIEWTOOLBAR_3D / restore-project CallAfters bounce the
        selection back to Prepare — see GUI_App::load_gl_resources);
      - a click landing mid-repaint can be lost.
    A single positive sighting is not enough: the app may bounce back within
    ~1s, so the expected state must be RE-confirmed after a settle delay.
    Vision drivers retry; they never assume.
    Returns (ok, last_expect_score).
    """
    click_path = template_path(click_tpl) if isinstance(click_tpl, str) else Path(click_tpl)
    expect_path = template_path(expect_tpl) if isinstance(expect_tpl, str) else Path(expect_tpl)
    last = 0.0
    for i in range(attempts):
        score, sx, sy = wait_for(session, click_path, timeout_s=5.0)
        if score < MATCH_THRESHOLD:
            print(f"[anchors] attempt {i+1}: click target not found ({score:.3f})")
            continue
        hwnd = winutil.msg_click_screen(sx, sy, session.hwnd)
        print(f"[anchors] attempt {i+1}: clicked {click_path.name} at ({sx},{sy}) -> hwnd 0x{hwnd:x}")
        score2, _, _ = wait_for(session, expect_path, timeout_s=6.0)
        last = score2
        if score2 >= MATCH_THRESHOLD:
            time.sleep(1.0)  # bounce window
            img = capture_bgr(session)
            tpl = cv2.imread(str(expect_path))
            res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            _, score3, _, _ = cv2.minMaxLoc(res)
            last = float(score3)
            if score3 >= MATCH_THRESHOLD:
                print(f"[anchors] attempt {i+1}: state stable ({score3:.3f})")
                return True, score3
            print(f"[anchors] attempt {i+1}: state BOUNCED back ({score2:.3f} -> {score3:.3f}), retrying")
        else:
            print(f"[anchors] attempt {i+1}: expected state not reached ({score2:.3f}), retrying")
    return False, last


# --- machine-readable table (m0_anchor_health consumer) --------------------
# kind: template (matched against the idle-boot capture) | color (pixel
# probe) | region (bounded + content-checked) | threshold (reported only).
ANCHORS = {
    "tab_prepare_active": {"kind": "template", "when": "idle-boot",
                           "threshold": MATCH_THRESHOLD},
    "tab_prepare_inactive": {"kind": "template", "when": "idle-boot",
                             "threshold": MATCH_THRESHOLD},
    "tab_preview_active": {"kind": "template", "when": "idle-boot",
                           "threshold": MATCH_THRESHOLD},
    "tab_preview_inactive": {"kind": "template", "when": "idle-boot",
                             "threshold": MATCH_THRESHOLD},
    "slice_plate_button": {"kind": "template", "when": "idle-boot",
                           "threshold": IDLE_DONE_SCORE},
    "slice_button_done": {"kind": "template", "when": "context-gated",
                          "threshold": IDLE_DONE_SCORE},
    "tab_teal_probe": {"kind": "color", "when": "idle-boot",
                       "probe": TAB_PREPARE_PROBE, "bgr": TAB_TEAL_BGR},
    "tab_unselected_probe": {"kind": "color", "when": "idle-boot",
                             "probe": TAB_PREPARE_PROBE, "bgr": TAB_UNSELECTED_BGR},
    "viewport": {"kind": "region", "when": "always",
                 "expect": "chromatic fraction > MODEL_COLORED_THRESHOLD "
                           "with the standard fixture loaded"},
}
