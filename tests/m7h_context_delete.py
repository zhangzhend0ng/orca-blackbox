#!/usr/bin/env python3
# m7h_context_delete.py — Feishu #18 (GUI业务, P0):
#   【正向】右键删除模型后恢复空白打印板
#
# Source facts: the Plater context menu (Plater.cpp on_right_click -> the
# object menu, GUI_Factories.cpp append_menu_item_delete:528) carries
# 'Delete  Del' -> plater()->remove_selected(). The menu is a NATIVE popup
# (#32768): message clicks are eaten by its modal loop — both opening
# (real right-click) and row selection (real click on the GetMenuItemRect
# row) go through real input (m3b precedent for the topbar dropdown).
#
# Black-box path: load the mixed fixture -> select the model (gizmo
# toolbar tooltip gate) -> real right-click the model centroid -> enumerate
# the popup (evidence) -> real-click the 'Delete' row -> the viewport must
# fall back to the empty-bed chromatic floor AND a Slice click must start
# nothing (m3b's second signal that the scene is really empty).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import click_slice_start  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7h]"


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model arrived: {ok} ({frac:.2%})")
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.5)

        selected = m7.select_model(session)
        results["model selectable (gizmo gate)"] = (
            "PASS" if selected else "FAIL")
        if not selected:
            return m7.m7_verdict(results)

        # --- right-click the model -> the object context menu ---
        menu = m7.open_context_menu(session, where="model")
        if not menu:
            results["context menu opens"] = "FAIL (no popup)"
            return m7.m7_verdict(results)
        hwnd, hmenu = menu
        rows = m7.list_menu(hmenu)
        labels = [lbl for _i, lbl in rows]
        print(f"{LOG} object menu rows: {labels}")
        results["context menu opens"] = (
            "PASS" if any("delete" in l.lower() for l in labels)
            else "FAIL (no Delete row)")
        del_idx = m7.click_menu_row(session, hwnd, hmenu, "delete")
        results["delete row clicks"] = "PASS" if del_idx is not None else "FAIL"
        time.sleep(2.0)

        # --- viewport must fall back to the empty-bed floor ---
        deadline = time.monotonic() + 10
        frac_after = m7.model_colored_frac(session)
        while frac_after >= m7.EMPTY_BED_FLOOR and time.monotonic() < deadline:
            time.sleep(1.0)
            frac_after = m7.model_colored_frac(session)
        print(f"{LOG} colored fraction after delete: {frac_after:.3%}")
        results["viewport empty after delete"] = (
            "PASS" if frac_after < m7.EMPTY_BED_FLOOR else
            f"FAIL ({frac_after:.3%})")

        # --- second signal: an emptied scene rejects slicing ---
        if frac_after < m7.EMPTY_BED_FLOOR:
            started = click_slice_start(session)
            print(f"{LOG} slice on empty scene started: {started}")
            results["empty scene rejects slice"] = (
                "PASS" if not started else "FAIL")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
