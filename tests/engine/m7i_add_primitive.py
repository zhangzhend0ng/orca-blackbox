#!/usr/bin/env python3
# m7i_add_primitive.py — Feishu #19 (GUI业务, P1):
# feishu: none  (无基线表映射)
#   【正向】通过右键菜单创建新模型
#
# Source facts: right-clicking EMPTY bed opens the default menu
# (Plater.cpp on_right_click 'empty space' branch -> MenuFactory::
# create_default_menu) whose 'Add Primitive' submenu loads shapes via
# obj_list()->load_generic_subobject("Cube", ...) (GUI_Factories.cpp:510).
#
# Black-box path: EMPTY boot -> real right-click the empty bed -> the
# default menu must show Add Primitive (rows enumerated as evidence) ->
# nested 'Add Primitive' -> 'Cube' -> a model must appear on the plate
# (chromatic fraction rises) and a Slice click must START a job (the
# non-empty scene accepts slicing — m3a's gate inverted).

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

from m2_slice_chain import click_slice_start  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7i]"


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=None)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=None)
    try:
        frac0 = m7.model_colored_frac(session)
        results["empty bed at boot"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")

        menu = m7.open_context_menu(session, where="bed")
        if not menu:
            results["bed context menu opens"] = "FAIL (no popup)"
            return m7.m7_verdict(results)
        hwnd, hmenu = menu
        labels = [l for _i, l in m7.list_menu(hmenu)]
        print(f"{LOG} bed menu rows: {labels}")
        results["bed context menu opens"] = (
            "PASS" if any("add primitive" in l.lower() for l in labels)
            else "FAIL (no Add Primitive)")

        got = m7.click_menu_row(session, hwnd, hmenu, "add primitive",
                                nested=True)
        results["Add Primitive submenu opens"] = "PASS" if got else "FAIL"
        if not got:
            m7.dismiss_menus(session)
            return m7.m7_verdict(results)
        _idx, (shwnd, shmenu) = got
        sub_rows = [l for _i, l in m7.list_menu(shmenu)]
        print(f"{LOG} primitive rows: {sub_rows}")
        m7.click_menu_row(session, shwnd, shmenu, "cube")
        time.sleep(2.5)

        # a single small cube reads ~0.24% colored on 2.4.0 (empty bed
        # ~0.06%) — gate RELATIVE to the measured empty-bed fraction: a
        # fixed 0.25% gate sat right on the measured value (09-22: 0.242%
        # vs 0.0025 -> false FAIL while the cube WAS on the plate)
        deadline = time.monotonic() + 12
        frac1 = m7.model_colored_frac(session)
        while frac1 < frac0 + 0.0015 and time.monotonic() < deadline:
            time.sleep(1.0)
            frac1 = m7.model_colored_frac(session)
        print(f"{LOG} colored fraction after cube: {frac1:.3%} "
              f"(empty bed {frac0:.3%})")
        results["new model appears on plate"] = (
            "PASS" if frac1 > frac0 + 0.0015
            else f"FAIL ({frac1:.3%} vs {frac0:.3%})")

        started = click_slice_start(session)
        results["slice accepts the new model"] = (
            "PASS" if started else "FAIL")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
