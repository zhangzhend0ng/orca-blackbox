#!/usr/bin/env python3
# m1_minimal_loop.py — M1: the minimal closed loop, raw-Python version.
#
#   launch -> capture -> template-match the Preview tab -> message-click it ->
#   assert the view switched (tab state + left panel content changed) ->
#   switch back -> assert.
#
# Decisive experiments recorded (see README hazard/conclusion matrix):
#   (a) can a message-level click drive the CUSTOM-DRAWN topbar tabs?
#   (b) can message-level input reach NATIVE child controls (Edit fields)?
#   (c) PrintWindow(PW_RENDERFULLCONTENT) GL capture — proven in m0.
#
# 09-03: the match machinery (capture_bgr / match / wait_for /
# click_and_verify / is_tab_teal) and every locator constant moved to
# harness/anchors.py (STRUCTURING_PLAN 第二期 #1). This module re-exports
# them so the ~20 `from m1_minimal_loop import capture_bgr` importers keep
# working unchanged.
#
# Exit code 0 = loop green.

import argparse
import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent.parent  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import anchors, env_check, launcher, profile, winutil  # noqa: E402
from harness.anchors import (  # noqa: E402  — re-export shim (see header)
    MATCH_THRESHOLD, TAB_PREPARE_PROBE, TAB_PREVIEW_PROBE, TEMPLATE_CUTS,
    TEMPLATE_PATHS, capture_bgr, click_and_verify, is_tab_teal,
    is_tab_unselected, match, wait_for)

user32 = ctypes.WinDLL("user32")


def get_edit_text(hwnd) -> str:
    n = user32.SendMessageW(hwnd, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(hwnd, 0x000D, n + 1, buf)  # WM_GETTEXT
    return buf.value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    verdict = {}

    profile.seed_profile(args.datadir)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    try:
        report = env_check.print_preflight(session.hwnd)

        # Boot page selection is racy (deferred CallAfter after GL init):
        # WAIT for the Prepare tab's active state instead of a fixed sleep.
        score, px, py = wait_for(session, anchors.TAB_PREPARE_ACTIVE, timeout_s=45.0)
        print(f"[m1] boot settled on Prepare: score={score:.3f} tab center=({px},{py})")
        if score < MATCH_THRESHOLD:
            cv2.imwrite(str(HERE / "artifacts" / "m1_debug_timeout.png"), capture_bgr(session))
            print("[m1] FAIL: app never reached the Prepare page"); return 2
        # Late, non-interfering presentation: no taskbar button, bottom of
        # the z-order (rendering/hit-testing untouched).
        winutil.demote_window(session.hwnd)
        time.sleep(1.0)  # let the settings panel finish laying out

        # ---------- click Preview (custom-drawn tab), with retry ----------
        (HERE / "artifacts").mkdir(exist_ok=True)
        cv2.imwrite(str(HERE / "artifacts" / "m1_debug_cap0.png"), capture_bgr(session))
        print(f"[m1] client origin screen: {winutil.client_to_screen(session.hwnd, 0, 0)}")

        active_tpl = anchors.template_path(anchors.TAB_PREVIEW_ACTIVE)
        bootstrap = not active_tpl.exists()
        if bootstrap:
            # First run: no active-state template yet. Click, settle, verify by
            # the teal pixel (ButtonsListCtrl selected color) STABLY, then cut.
            score, sx, sy = wait_for(session, anchors.TAB_PREVIEW_INACTIVE, timeout_s=5.0)
            if score < MATCH_THRESHOLD:
                print("[m1] FAIL: preview tab not found"); return 2
            img1 = None
            for i in range(4):
                winutil.msg_click_screen(sx, sy, session.hwnd)
                time.sleep(1.0)
                probe = capture_bgr(session)
                if is_tab_teal(probe, *TAB_PREVIEW_PROBE):
                    time.sleep(1.0)  # bounce window
                    probe2 = capture_bgr(session)
                    if is_tab_teal(probe2, *TAB_PREVIEW_PROBE):
                        img1 = probe2
                        break
            if img1 is None:
                print("[m1] FAIL: Preview never became stably selected (teal)"); return 2
        else:
            ok, score2 = click_and_verify(session, anchors.TAB_PREVIEW_INACTIVE,
                                          anchors.TAB_PREVIEW_ACTIVE)
            if not ok:
                img1 = capture_bgr(session)
                print("[m1] FAIL: switch to Preview not verifiable "
                      f"(score {score2:.3f})"); return 2
            img1 = capture_bgr(session)

        # ---------- assert switched ----------
        # Dark theme evidence, per ButtonsListCtrl source (Notebook.cpp):
        # selected tab bg = teal (0,150,136); unselected = (59,68,70).
        # (Template matching alone is a weak state discriminator here — the
        # glyphs are identical between states and TM_CCOEFF_NORMED normalizes
        # the uniform background away — so assert on the button COLORS.)
        px_, py_ = TAB_PREVIEW_PROBE
        tab_px = img1[py_, px_]  # Preview tab center (capture coords)
        preview_now_selected = is_tab_teal(img1, px_, py_)
        qx_, qy_ = TAB_PREPARE_PROBE
        prep_px = img1[qy_, qx_]
        prep_now_unselected = is_tab_unselected(img1, qx_, qy_)
        print(f"[m1] after click: Preview tab BGR={tab_px} selected={preview_now_selected}; "
              f"Prepare tab BGR={prep_px} unselected={prep_now_unselected}")
        verdict["(a) custom tab click"] = "PASS" if (preview_now_selected and prep_now_unselected) else "FAIL"

        # cut templates from the VERIFIED switched state only (never blind)
        y0, y1, x0, x1 = TEMPLATE_CUTS[anchors.TAB_PREVIEW_ACTIVE]
        cv2.imwrite(str(anchors.TEMPLATE_PATHS[anchors.TAB_PREVIEW_ACTIVE]),
                    img1[y0:y1, x0:x1])
        y0, y1, x0, x1 = TEMPLATE_CUTS[anchors.TAB_PREPARE_INACTIVE]
        cv2.imwrite(str(anchors.TEMPLATE_PATHS[anchors.TAB_PREPARE_INACTIVE]),
                    img1[y0:y1, x0:x1])

        # ---------- click back to Prepare ----------
        ok_back, score_back = click_and_verify(session, anchors.TAB_PREPARE_INACTIVE,
                                               anchors.TAB_PREPARE_ACTIVE)
        img2 = capture_bgr(session)
        print(f"[m1] back on Prepare: template score={score_back:.3f}, "
              f"tab BGR={img2[qy_, qx_]} teal={is_tab_teal(img2, qx_, qy_)}")
        verdict["(a2) switch back to Prepare"] = (
            "PASS" if (ok_back and is_tab_teal(img2, qx_, qy_)) else "FAIL")

        # ---------- (b) native Edit control reachable? ----------
        # 'Layer height' Edit was at screen (258,708)-ish; re-discover children
        edit = None
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, _):
            nonlocal edit
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cls, 64)
            if cls.value == "Edit" and edit is None:
                edit = h
            return True
        user32.EnumChildWindows(ctypes.c_void_p(session.hwnd), WNDENUMPROC(cb), 0)
        if edit is not None:
            before = get_edit_text(edit)
            winutil.msg_text(edit, "0.16")
            time.sleep(0.5)
            after = get_edit_text(edit)
            print(f"[m1] native Edit text: {before!r} -> {after!r}")
            verdict["(b) native Edit WM_CHAR"] = "PASS" if "0.16" in after else "FAIL"
        else:
            verdict["(b) native Edit WM_CHAR"] = "SKIP (no Edit found)"

        print("\n[m1] === verdict ===")
        for k, v in verdict.items():
            print(f"  {k}: {v}")
        ok = all(v == "PASS" for v in verdict.values())
        print("[m1] " + ("GREEN" if ok else "RED"))
        return 0 if ok else 1
    finally:
        session.close()
        print("[m1] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
