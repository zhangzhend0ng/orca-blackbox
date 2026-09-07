#!/usr/bin/env python3
# m7d_import_corrupt.py — Feishu #12 (GUI业务, P1):
#   【异常】导入不合法模型文件提示错误
#
# Source facts: the import path surfaces load failures through an error
# dialog (show_error -> #32770) and the plater must survive (m3c proved the
# boot-load variant: error dialog + app alive + a good project still
# loads). This case drives the IMPORT-menu variant: a garbage .stl (written
# to artifacts at runtime — not a repo fixture) must produce the error
# dialog, no crash, and an intact empty plate.
#
# Black-box path: empty boot -> File > Import -> type the garbage path ->
# IDOK -> error #32770 appears (title/labels enumerated as evidence) ->
# dismiss -> app alive + plate still empty (no phantom geometry).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7d]"


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=None)
    args = ap.parse_args()

    results = {}
    bad = Path(args.datadir).parent / "m7d_garbage.stl"
    bad.write_bytes(b"solid garbage\nthis is not a mesh\nendsolid garbage\n")

    session = boot_session(args, model=None)
    try:
        frac0 = m7.model_colored_frac(session)
        results["empty bed at boot"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")

        dispatched, dlg = m7.file_menu_dispatch(session, "stl",
                                                expect_dialog=True,
                                                via="Import")
        results["import entry dispatches"] = (
            "PASS" if dispatched else "FAIL")
        if not (dispatched and dlg):
            results["open dialog appears"] = "FAIL"
            return m7.m7_verdict(results)
        edit = export_util.find_edit(dlg[3])
        if edit is None:
            results["filename edit located"] = "FAIL"
            return m7.m7_verdict(results)
        winutil.select_all(edit)
        winutil.msg_text(edit, str(bad))
        import ctypes
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK

        # --- the error dialog must appear ---
        err = m7.wait_dialog(session.pid, timeout_s=20.0)
        print(f"{LOG} error dialog: {err and err[1]!r}")
        results["error dialog appears"] = "PASS" if err else "FAIL"
        if err:
            m7.click_dialog_button(err[3], "ok")
        time.sleep(1.5)

        results["app alive after error"] = "PASS" if session.alive() else "FAIL"
        frac1 = m7.model_colored_frac(session)
        print(f"{LOG} colored fraction after failed import: {frac1:.3%}")
        results["plate unchanged (no phantom model)"] = (
            "PASS" if frac1 < m7.EMPTY_BED_FLOOR + 0.002 else
            f"FAIL ({frac1:.3%})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
