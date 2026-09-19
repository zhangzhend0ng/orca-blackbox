#!/usr/bin/env python3
# m8b_official_color.py — 飞书基线用例 #44/#46/#47/#48 + #55/#56/#58
# (4 耗材管理-官方颜色 / 模型渲染, P0)。
# 入口: 侧栏耗材行的 20DIP clr_picker 位图按钮 -> ChangeExtruderColor
# (PresetComboBoxes.cpp:1045) — 仅 Snapmaker 命名预设打开官方
# FilamentColorDialog (色卡库 = filaments_colours.json, 21 耗材/178 色),
# 否则回退传统 wx 取色器。夹具 = mixed (槽2-5 = Snapmaker PLA Silk)。
#
#   #48 模态弹窗布局: 弹窗出现 + 背景(画布)点击不改状态 + OCR 含 SKU/色名
#   #46 确定生效: 选色卡 -> OK -> 重开弹窗当前选中色变化 (swatch 像素)
#   #47 取消不登记: 选色卡 -> Cancel -> swatch 像素不变
#   #44 颜色列表: 弹窗 OCR 断言分类/官方色名 (证据级)
#   #55 双拼耗材切换: 槽2 combo -> Dual 行 (下拉无 Snapmaker Rainbow,
#      09-19 全序扫描实证) -> combo 文本
#   #56 模型渲染双拼主色: 槽色块像素非灰 (色度) — 弱断言
#   #58 双拼耗材切片: Delete All + cube -> 槽1 同步 Dual -> slice -> gcode 落盘
#   (#59 预览主色 = 视觉冒烟, PARTIAL 不在本用例断言面)

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness.anchors import capture_bgr  # noqa: E402
from harness import winutil  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8b]"
ART = HERE / "artifacts"


def swatch_rgb(session, slot=2):
    """Average RGB of the slot's picker button area (its bitmap = the
    current filament color)."""
    import numpy as np
    slots = m8.filament_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["picker"]:
        return None
    r = hit["picker"]
    img = cap(session)
    region = img[r[1] + 3:r[3] - 3, r[0] + 3:r[2] - 3]
    if region.size == 0:
        return None
    mean = region.reshape(-1, 3).mean(axis=0)
    return [int(v) for v in mean]


def open_dialog_and_dump(session, tag):
    dlg = m8.click_color_picker(session, slot=2)
    if not dlg:
        return None
    import cv2
    img = cap(session)
    cv2.imwrite(str(ART / f"m8b_dialog_{tag}.png"), img)
    return dlg


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        time.sleep(1.0)

        # --- #48: dialog opens, modal, first row content -----------------
        # Measured 09-19 (diag_m8b_picker): the chip IS the clr_picker and
        # opens the official FilamentColorDialog directly — #32770, ~380px
        # wide, whose name/SKU labels and OK/Cancel buttons ALL carry
        # window text ('Mint Lemonade' / 'sku 34205' / 'OK' / 'Cancel').
        base_swatch = swatch_rgb(session, slot=2)
        print(f"{LOG} slot2 swatch rgb: {base_swatch}")
        dlg = open_dialog_and_dump(session, "first")
        if not dlg:
            results["#48 dialog opens"] = "FAIL (no popup)"
            return m7.m7_verdict(results)
        drect = dlg[2]
        print(f"{LOG} dialog rect: {drect}")
        results["#48 dialog opens"] = "PASS"

        from harness import winutil as _wu

        def dialog_kids(d):
            return [(t.strip(), r, h) for t, r, h in
                    __import__("harness").export_util._children_texts(d[3])]

        kids = dialog_kids(dlg)
        texts = [t for t, _r, _h in kids if t]
        print(f"{LOG} dialog texts: {texts[:14]}")
        # swatch panels are self-drawn wxWindowNR children whose window
        # text is 'panel' (measured 09-19 diag) — not empty strings
        swatches = [r for t, r, _h in kids
                    if t in ("", "panel") and 24 <= r[2] - r[0] <= 36
                    and 24 <= r[3] - r[1] <= 36]
        print(f"{LOG} swatch panels: {len(swatches)}")
        sku_txt = next((t for t in texts if "sku" in t.lower()), None)
        official = any("official" in t.lower() for t in texts)
        # #48 row-1 contract: color card + color name + SKU code. The
        # dialog exposes the name ('Mint Lemonade') and SKU as Static text;
        # the card is the 60x60 preview Static.
        name_txt = next((t for t in texts
                         if t not in ("OK", "Cancel", "panel")
                         and "official" not in t.lower()
                         and "sku" not in t.lower()), None)
        preview = [r for t, r, _h in kids
                   if not t and 50 <= r[2] - r[0] <= 70
                   and 50 <= r[3] - r[1] <= 70]
        results["#48 first row card+name+SKU"] = (
            "PASS (text)" if (sku_txt and name_txt and preview) else
            "FAIL (name={name_txt!r}, sku={sku_txt!r})")

        # modal check: REAL-click the canvas; the dialog must stay. 09-19:
        # checked against the dialog's own hwnd (the old wait_popup looked
        # for a SidePopup and could never see this #32770 — the recorded
        # 'non-modal' finding was an artifact of that wrong predicate).
        cx, cy = m7.client(session, m7.VIEWPORT_X0 + 300, 400)
        _wu.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        _wu.real_click_screen(cx, cy)
        time.sleep(0.8)
        still = _wu.user32.IsWindowVisible(dlg[3])
        results["#48 modal blocks canvas"] = (
            "PASS" if still else "FAIL (dialog gone after canvas click)")
        if not still:
            print(f"{LOG} #48 NON-MODAL confirmed against the real dialog")
            # re-open and carry on: #46/#47 need the dialog, and the modal
            # sub-item must not blind the whole case (09-18 rerun)
            dlg = m8.click_color_picker(session, slot=2)
            if not dlg:
                return m7.m7_verdict(results)
            kids = dialog_kids(dlg)
            swatches = [r for t, r, _h in kids
                        if t in ("", "panel")
                        and 24 <= r[2] - r[0] <= 36
                        and 24 <= r[3] - r[1] <= 36]

        # --- #46: pick a different color card -> OK ----------------------
        # swatches are self-drawn 30px panels in a 10-col grid (source
        # BuildUi); click the LAST (bottom-right-ish) so the new color is
        # far from the default first-row selection
        clicked = False
        if swatches:
            r = sorted(swatches, key=lambda r: (r[1], r[0]))[-1]
            winutil.msg_click_screen((r[0] + r[2]) // 2,
                                     (r[1] + r[3]) // 2)
            time.sleep(0.6)
            clicked = True
            names_after = [t for t, _r, _h in dialog_kids(dlg)
                           if t and "sku" not in t.lower()
                           and t not in ("OK", "Cancel")
                           and "official" not in t.lower()]
            print(f"{LOG} #46 name label after click: {names_after[:2]}")
        ok_ok = m8.close_dialog_by_button(dlg, "OK")
        time.sleep(1.0)
        new_swatch = swatch_rgb(session, slot=2)
        print(f"{LOG} #46 swatch {base_swatch} -> {new_swatch}")
        results["#46 confirm applies color"] = (
            "PASS" if (clicked and ok_ok and new_swatch and base_swatch
                       and new_swatch != base_swatch) else
            f"FAIL (clicked={clicked}, ok={ok_ok})")

        # --- #47: pick -> Cancel keeps the old color ---------------------
        before47 = swatch_rgb(session, slot=2)
        dlg2 = open_dialog_and_dump(session, "cancel")
        if dlg2:
            sw2 = [r for t, r, _h in dialog_kids(dlg2)
                   if t in ("", "panel") and 24 <= r[2] - r[0] <= 36
                   and 24 <= r[3] - r[1] <= 36]
            if sw2:
                r = sorted(sw2, key=lambda r: (r[1], r[0]))[0]
                winutil.msg_click_screen((r[0] + r[2]) // 2,
                                         (r[1] + r[3]) // 2)
                time.sleep(0.6)
            m8.close_dialog_by_button(dlg2, "Cancel")
            time.sleep(1.0)
            after47 = swatch_rgb(session, slot=2)
            print(f"{LOG} #47 swatch {before47} -> {after47}")
            results["#47 cancel keeps color"] = (
                "PASS" if after47 == before47 else
                f"FAIL ({before47} -> {after47})")
        else:
            results["#47 cancel keeps color"] = "FAIL (no dialog)"

        # --- #44: official list evidence (text labels + swatch grid) -----
        results["#44 official color list"] = (
            "PASS (evidence)" if official and sku_txt
            and len(swatches) >= 10 else
            f"FAIL (official={official}, sku={sku_txt!r}, "
            f"swatches={len(swatches)})")

        # --- #55/#56/#58: dual-color preset + render + slice --------------
        # 09-19 full-list sweeps (coarse ramp + binary search over the whole
        # 65-row alphabetical list): the dropdown carries NO Snapmaker
        # system rows at all — 'Snapmaker PLA Rainbow' exists in the staged
        # profile dir but never surfaces. The dual-color rows that DO exist
        # ('PolyLite Dual PLA', 'PolyTerra Dual PLA') satisfy #55's
        # precondition (双拼/渐变色耗材) — select one of those.
        final = m8.switch_filament_preset(session, slot=2,
                                          target_substr="Dual",
                                          seek="PolyLite Dual PLA")
        print(f"{LOG} slot2 preset -> {final!r}")
        results["#55 dual-color preset selectable"] = (
            "PASS" if "Dual" in final else f"FAIL ({final!r})")
        time.sleep(1.5)
        sw = swatch_rgb(session, slot=2)
        colorful = sw and (max(sw) - min(sw)) > 30
        results["#56 gradient swatch colorful"] = (
            "PASS" if colorful else f"FAIL (rgb={sw})")

        # slice a fresh cube on the rainbow slot
        if not m7.step_delete_all(session, results):
            return m7.m7_verdict(results)
        # the Add-Primitive bed menu flakes under the demoted window (m7-era
        # known): op_add_primitive verifies the chromatic delta, so a False
        # means nothing landed — one retry is safe
        if not m7.op_add_primitive(session, "cube"):
            print(f"{LOG} cube add retry (bed-menu flake)")
            time.sleep(1.5)
            if not m7.op_add_primitive(session, "cube"):
                results["cube added"] = "FAIL"
                return m7.m7_verdict(results)
        results["cube added"] = "PASS"
        time.sleep(1.0)
        # Change Filament is merge-semantics on the 09-16 build (broken for
        # object remapping) — put the DUAL-COLOR preset on the cube's own
        # slot instead: the fresh cube defaults to slot 1, so switch slot 1
        # the same proven combo way #55 just did for slot 2
        final1 = m8.switch_filament_preset(session, slot=1,
                                           target_substr="Dual",
                                           seek="PolyLite Dual PLA")
        print(f"{LOG} slot1 preset -> {final1!r}")
        results["slot1 dual-color for slice"] = (
            "PASS" if "Dual" in final1 else f"FAIL ({final1!r})")
        gcode = ART / "m8b_rainbow.gcode"
        gcode.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
        m7.op_slice(session, results, key="#58 dual-color slice+export",
                    export_to=gcode)
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
