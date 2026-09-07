#!/usr/bin/env python3
# m7j_change_filament.py — Feishu #21 (GUI业务, P1):
#   【正向】切换模型对象的耗材配置
#
# Source facts: the object context menu's 'Change Filament' item
# (GUI_Factories.cpp append_menu_item_change_filament:2061) is a nested
# submenu listing the physical filaments; picking one calls
# plater()->sidebar().change_filament(-2, i) — the whole object remaps.
# The exported 3mf carries per-volume extruder attributes, so the switch
# is externally observable as a CHANGED extruder set vs the fixture.
#
# Black-box path: boot mixed fixture -> capture the fixture's extruder
# attrs baseline (read from the vendored 3mf) -> select -> right-click >
# Change Filament (submenu rows enumerated) -> pick the LAST filament ->
# Save Project as -> the exported extruder attr set must differ.

import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
from m7_common import ART  # noqa: E402

LOG = "[m7j]"


import ctypes

MF_CHECKED = 0x8


def extruder_attrs(path_3mf: Path) -> list:
    """extruder attrs across ALL model xml parts (single-mesh objects carry
    none — the fixture serializes <mesh> directly under <object>)."""
    try:
        with zipfile.ZipFile(path_3mf) as z:
            out = []
            for name in z.namelist():
                if name.endswith(".model"):
                    out += re.findall(r'extruder="(\d+)"',
                                      z.read(name).decode("utf-8",
                                                          errors="replace"))
            return sorted(set(out))
    except Exception as exc:
        print(f"{LOG} 3mf read failed: {exc}")
        return []


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out3mf = ART / "m7j_out.3mf"
    if out3mf.exists():
        out3mf.unlink()
    baseline = extruder_attrs(MIXED_3MF)
    print(f"{LOG} fixture extruder attrs: {baseline}")

    session = boot_session(args, model=args.model)
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.5)

        if not m7.select_model(session):
            results["model selected"] = "FAIL"
            return m7.m7_verdict(results)
        results["model selected"] = "PASS"

        menu = m7.open_context_menu(session, where="model")
        if not menu:
            results["context menu opens"] = "FAIL (no popup)"
            return m7.m7_verdict(results)
        hwnd, hmenu = menu
        labels = [l for _i, l in m7.list_menu(hmenu)]
        results["context menu opens"] = (
            "PASS" if any("change filament" in l.lower() for l in labels)
            else "FAIL (no Change Filament row)")

        got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                                nested=True)
        results["Change Filament submenu opens"] = "PASS" if got else "FAIL"
        if not got:
            m7.dismiss_menus(session)
            return m7.m7_verdict(results)
        _idx, (shwnd, shmenu) = got
        rows = m7.list_menu(shmenu)
        print(f"{LOG} filament rows: {[l for _i, l in rows]}")
        results["filament options listed"] = (
            f"PASS ({len(rows)})" if len(rows) >= 2 else
            f"FAIL ({len(rows)} rows)")
        if len(rows) < 2:
            m7.dismiss_menus(session)
            return m7.m7_verdict(results)

        # pick the LAST non-separator row and read its check state before
        last_i, last_lbl = rows[-1]
        st_before = ctypes.WinDLL("user32").GetMenuState(shmenu, last_i,
                                                         0x400)
        m7.click_menu_row(session, shwnd, shmenu, last_lbl)
        print(f"{LOG} picked filament row {last_lbl!r} (state 0x{st_before:x})")
        time.sleep(2.0)

        # primary observable: the picked row is CHECKED when reopened (the
        # object's extruder remap is reflected in the submenu state; the
        # fixture's single-mesh object carries no extruder= attr to diff)
        remapped = False
        menu2 = m7.open_context_menu(session, where="model")
        if menu2:
            hwnd2, hmenu2 = menu2
            got2 = m7.click_menu_row(session, hwnd2, hmenu2, "change filament",
                                     nested=True)
            if got2:
                _i2, (shwnd2, shmenu2) = got2
                st_after = ctypes.WinDLL("user32").GetMenuState(
                    shmenu2, last_i, 0x400)
                print(f"{LOG} reopened row state 0x{st_after:x}")
                remapped = bool(st_after & MF_CHECKED) and                     not (st_before & MF_CHECKED)
                m7.dismiss_menus(session)
        results["extruder mapping changed"] = (
            "PASS (submenu check state)" if remapped else
            "FAIL (row not re-checked)")

        ok_save = m7.save_project_as(session, out3mf)
        results["3mf exported"] = "PASS" if ok_save else "FAIL"
        if ok_save:
            after = extruder_attrs(out3mf)
            print(f"{LOG} exported extruder attrs: {after}")
            if after and after != baseline:
                results["extruder mapping changed"] = (
                    "PASS (3mf extruder attrs)")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
