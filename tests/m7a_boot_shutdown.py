#!/usr/bin/env python3
# m7a_boot_shutdown.py — Feishu #7 + #8 (GUI业务, P0):
#   #7 【正向】首次启动Orca软件进入准备页面 — boot reaches the ready page
#   #8 【正向】正常关闭Orca软件无残留进程 — graceful close, zero leftovers
#
# Source facts: the seeded profile conf marks firstguide.finish=true, so the
# first-run Setup Wizard is skipped deterministically (its "complete the
# wizard" step is a seed invariant, not a black-box walk — noted PARTIAL);
# the app must still reach the Prepare page with an empty plate. Closing is
# WM_CLOSE (launcher.AppSession.close) — MainFrame handles it like the X
# button; no snapmaker-orca.exe process may survive it.
#
# Black-box path: seed + launch (no model) -> Prepare tab template active +
# viewport paints + idle Slice button rendering (empty plate) -> WM_CLOSE ->
# process gone (tasklist poll for 10s).

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import launcher, profile  # noqa: E402
from harness.anchors import (IDLE_DONE_SCORE, SLICE_PLATE_BUTTON,  # noqa: E402
                             TAB_PREPARE_ACTIVE, match, wait_for)
from m1_minimal_loop import capture_bgr  # noqa: E402
from m3_common import add_common_args, ensure_gl_ready  # noqa: E402

LOG = "[m7a]"


def leftover_processes() -> list:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq snapmaker-orca.exe"],
                         capture_output=True, text=True).stdout or ""
    return [ln for ln in out.splitlines() if "snapmaker-orca" in ln.lower()]


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=None)
    args = ap.parse_args()

    results = {}
    datadir = Path(args.datadir)
    profile.seed_profile(datadir, fresh=True)
    session = launcher.launch(exe=args.exe, datadir=datadir, dismiss_wizard=True)
    try:
        # --- #7: reaches the Prepare page, canvas paints ---
        score, _sx, _sy = wait_for(session, TAB_PREPARE_ACTIVE, timeout_s=60)
        results["prepare tab active"] = (
            f"PASS ({score:.2f})" if score >= 0.80 else f"FAIL ({score:.2f})")
        results["canvas paints"] = (
            "PASS" if ensure_gl_ready(session) else "FAIL")

        idle_score, *_ = match(capture_bgr(session), SLICE_PLATE_BUTTON)
        results["empty plate (slice idle)"] = (
            f"PASS ({idle_score:.2f})" if idle_score >= IDLE_DONE_SCORE
            else f"FAIL ({idle_score:.2f})")

        # --- #8: graceful close leaves no process ---
        session.close(timeout_s=15)
        time.sleep(2.0)
        leftover = leftover_processes()
        for _ in range(5):
            if not leftover:
                break
            time.sleep(2.0)
            leftover = leftover_processes()
        results["no leftover process"] = (
            "PASS" if not leftover else f"FAIL ({leftover})")
        return m7_verdict(results)
    finally:
        try:
            session.close()
        except Exception:
            pass


def m7_verdict(results: dict) -> int:
    print("\n[m7] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    ok = all(str(v).startswith("PASS") for v in results.values())
    print("[m7] " + ("GREEN" if ok else "RED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
