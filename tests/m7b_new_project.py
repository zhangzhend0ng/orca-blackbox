#!/usr/bin/env python3
# m7b_new_project.py — Feishu #9 (GUI业务, P0):
#   【正向】新建项目清空当前模型数据
#
# Source facts: File > New Project (MainFrame.cpp:2548, Ctrl+N). With a
# DIRTY project the frame pops a save prompt (wxMessageDialog: Save /
# Don't save / Cancel — native #32770, buttons are real HWNDs so
# message clicks reach them, m3c precedent); choosing not to save clears
# the plater (Plater::new_project).
#
# Black-box path: load the mixed fixture -> dirty the project with a real
# Add-Primitive (bed menu > Add Primitive > Cube) -> File > New Project ->
# the save prompt must appear -> click 'Don't save'/'No' -> the viewport
# falls back to the empty-bed chromatic floor.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7b]"


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
        time.sleep(1.0)

        # dirty the project: Add Primitive > Cube (bed context menu)
        added = m7.context_click_row(
            session, "bed", "cube", via="Add Primitive",
            success_fn=lambda: m7.blob_count(session) >= 2
            or m7.model_colored_frac(session) > 0.02,
            label="add-cube")
        print(f"{LOG} cube added (dirty): {added}")
        results["project dirtied (add cube)"] = "PASS" if added else "FAIL"

        # --- File > New Project -> save prompt -> Don't save ---
        dispatched, dlg = m7.file_menu_dispatch(session, "New Project",
                                                expect_dialog=True)
        results["new project dispatches"] = "PASS" if dispatched else "FAIL"
        if not dispatched:
            return m7.m7_verdict(results)

        clicked = None
        if dlg:
            print(f"{LOG} save prompt: '{dlg[1]}'")
            clicked = m7.click_dialog_button(dlg[3], "no")  # Don't save / No
        results["save prompt handled (don't save)"] = (
            "PASS" if clicked else "FAIL")
        time.sleep(2.5)

        # --- viewport must fall back to the empty-bed floor ---
        deadline = time.monotonic() + 12
        frac_after = m7.model_colored_frac(session)
        while frac_after >= m7.EMPTY_BED_FLOOR and time.monotonic() < deadline:
            time.sleep(1.0)
            frac_after = m7.model_colored_frac(session)
        print(f"{LOG} colored fraction after new project: {frac_after:.3%}")
        results["viewport empty (model cleared)"] = (
            "PASS" if frac_after < m7.EMPTY_BED_FLOOR else
            f"FAIL ({frac_after:.3%})")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
