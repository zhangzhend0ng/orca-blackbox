#!/usr/bin/env python3
# m7c_import_stl.py — Feishu #11 (GUI业务, P0):
#   【正向】导入本地STL模型文件并正确显示
#
# Source facts: the File menu carries an Import STL entry (MainFrame file
# menu; exact label enumerated at runtime) -> native OPEN dialog (#32770,
# filename Edit + IDOK) -> GUI_Plater::load_project/load_files path. The
# seeded fixture Prusa.stl is the vendored import target.
#
# Black-box path: empty boot -> File menu (labels enumerated as evidence)
# -> dispatch Import -> type the stl path into the open dialog -> IDOK ->
# the model must arrive on the plate (viewport chromatic fraction over the
# m2 loaded threshold).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from m3_common import HERE as ROOT  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7c]"
STL = ROOT / "fixtures" / "Prusa.stl"


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=None)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=None)
    try:
        frac0 = m7.model_colored_frac(session)
        print(f"{LOG} empty-bed fraction: {frac0:.3%}")
        results["empty bed at boot"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")

        # --- File > Import STL -> native open dialog ---
        dispatched, dlg = m7.file_menu_dispatch(session, "stl",
                                                expect_dialog=True,
                                                via="Import")
        print(f"{LOG} import dispatch: {dispatched}, dialog: {dlg and dlg[1]!r}")
        results["import entry dispatches"] = (
            "PASS" if dispatched else "FAIL")
        if not dispatched:
            return m7.m7_verdict(results)
        if not dlg:
            results["open dialog appears"] = "FAIL"
            return m7.m7_verdict(results)
        results["open dialog appears"] = "PASS"

        edit = export_util.find_edit(dlg[3])
        if edit is None:
            results["filename edit located"] = "FAIL"
            return m7.m7_verdict(results)
        winutil.select_all(edit)
        winutil.msg_text(edit, str(STL))
        import ctypes
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK

        # --- model must arrive: Prusa.stl is a SMALL single-color model
        # (measured 0.35% colored vs 0.06% empty — the fixture-calibrated
        # 0.6% gate would miss it), so the gate is 0.25% + a chromatic blob
        deadline = time.monotonic() + 90
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(1.0)
            frac = m7.model_colored_frac(session)
        print(f"{LOG} colored fraction after import: {frac:.3%} "
              f"(threshold 0.25%)")
        results["stl imports and displays"] = (
            "PASS" if (frac >= 0.0025 and m7.blob_count(session) >= 1) else
            f"FAIL ({frac:.3%})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
