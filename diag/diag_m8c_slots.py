#!/usr/bin/env python3
"""diag_m8c_slots.py — find a black-box route to a multi-slot job (needed
for the #111 temp-mix gate: Plater.cpp:22313 needs used slots of BOTH
high/low classes, which the mixing fixture never produces because its
objects reference the out-of-range virtual mixing slot).

Probes, one boot:
  1. delete-all + 3 cubes -> slice+export -> used_filaments: do fresh
     primitives distribute across slots 1/2/3 or all land on 1?
  2. cube + Change Filament (real-click submenu row) -> slice+export:
     does the 09-16 merge migrate the object to another slot?
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[dc]"
ART = HERE / "artifacts"


def slice_used(session, tag):
    g = ART / f"m8c_diag_{tag}.gcode"
    g.unlink(missing_ok=True)
    results = {}
    if not m7.op_slice(session, results, key=f"{tag} slice", export_to=g):
        print(f"{LOG} {tag}: slice/export FAILED ({results})")
        return None
    used = m8.used_filaments(g.read_bytes())
    print(f"{LOG} {tag}: used={used}")
    return used


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        if not m8.wait_arrival(session)[0]:
            print(f"{LOG} arrival FAIL")
            return 1
        m7.ensure_maximized(session)
        ensure_gl_ready(session)

        def delete_all(retries=3):
            for i in range(retries):
                if m7.step_delete_all(session, {}):
                    return True
                print(f"{LOG} delete-all retry {i + 1}")
                time.sleep(2.0)
            return False

        def add_cube(retries=3):
            for i in range(retries):
                if m7.op_add_primitive(session, "cube"):
                    return True
                print(f"{LOG} cube add retry {i + 1}")
                time.sleep(2.0)
            return False

        # --- probe 1: three fresh cubes --------------------------------
        if not delete_all():
            print(f"{LOG} delete-all FAIL")
            return 1
        for i in range(3):
            if not add_cube():
                print(f"{LOG} cube{i} add FAIL")
            time.sleep(1.0)
        used = slice_used(session, "threecubes")

        # --- probe 2: merge migration -----------------------------------
        if not delete_all():
            print(f"{LOG} delete-all(2) FAIL")
            return 1
        if not add_cube():
            print(f"{LOG} cube add FAIL")
            return 1
        time.sleep(1.0)
        if not m7.select_model(session):
            print(f"{LOG} select FAIL (fresh-add selection assumed)")
        menu = m7.open_context_menu(session, where="model")
        if not menu:
            print(f"{LOG} no context menu")
            return 1
        hwnd, hmenu = menu
        got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                                nested=True)
        if not got:
            m7.dismiss_menus(session)
            print(f"{LOG} no change-filament submenu")
            return 1
        _i, (shwnd, shmenu) = got
        rows = m7.list_menu(shmenu)
        print(f"{LOG} filament rows: {[l for _i, l in rows]}")
        # real-click the row labelled 2 (second physical slot)
        hit = m7.click_menu_row(session, shwnd, shmenu, "2")
        time.sleep(2.0)
        m7.dismiss_menus(session)
        print(f"{LOG} merge row-click hit: {hit}")
        slice_used(session, "aftermerge")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
