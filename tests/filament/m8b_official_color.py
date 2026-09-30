#!/usr/bin/env python3
# m8b_official_color.py — 飞书基线用例 #44/#46/#47/#48 + #55/#56/#58
# feishu: baseline#44 baseline#46 baseline#47 baseline#48 baseline#55 baseline#56 baseline#58
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
#   #55 渐变耗材切换: 槽1 combo -> 'PLA Rainbow' 行 -> combo 文本
#   #56 模型渲染渐变主色: 槽色块像素非灰 (色度) — 弱断言
#   #58 渐变耗材切片: Delete All + cube -> slice -> gcode 落盘
#   (#59 预览主色 = 视觉冒烟, PARTIAL 不在本用例断言面)

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

from harness.anchors import capture_bgr  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8b]"
ART = HERE / "artifacts"


def swatch_rgb(session, slot=2):
    """Mean BGR of the slot's colour CHIP — its background IS the filament
    colour, so it is the swatch these baseline rows talk about.

    The chip rect comes from the child tree (a numbered 'Button', window rects
    = SCREEN coordinates) and is sampled from a desktop grab. The old version
    read whichever small child `filament_slots` guessed (a fixed grey icon) and
    came back with a constant [213,213,211] before AND after colour changes
    (measured 09-24)."""
    return m8.slot_swatch_rgb(session, slot)


def official_popup_colour(dlg):
    """(name, sku) of the official popup's currently selected colour."""
    return m8.popup_colour_texts(dlg)


def is_native_picker(dlg):
    """True when the returned dialog is the legacy native picker (what a
    non-Snapmaker filament falls back to, probe 09-24: slot 1 'Generic PETG'
    -> dialog 'Please choose the filament color' with '&Basic colors:')."""
    texts = [t.strip().lower() for t, _r, _h
             in __import__("harness").export_util._children_texts(dlg[3])]
    return any("basic colors" in t for t in texts)


def pick_official_card(session, dlg, tries=40):
    """Click a colour card in the official popup and CONFIRM the pick by the
    popup's own colour name/SKU changing.

    The grid is OWNER-DRAWN (no child per swatch), so cells are reached by
    coordinate; the loop scans the region between the 'Official Filaments'
    label and the '+ Other Colors' button and accepts only a cell that
    actually changed the displayed colour — a blind click is never trusted.

    The cells ARE enumerable child panels (measured 09-28: 30x30 panels at
    (444,556)-(474,586), (479,...), … 'Official Filaments' above them), so the
    real rectangles are used when present and a coordinate scan is only the
    fallback for an owner-drawn grid."""
    from harness import winutil as wu
    kids = __import__("harness").export_util._children_texts(dlg[3])
    before = official_popup_colour(dlg)
    x0, y0, x1, y1 = dlg[2]
    label = next((r for t, r, _h in kids
                  if "official filaments" in t.strip().lower()), None)
    other = next((r for t, r, _h in kids
                  if "other colors" in t.strip().lower()), None)
    okb = next((r for t, r, _h in kids if t.strip().lower() == "ok"), None)
    top = (label[3] + 4) if label else (y0 + 70)
    bot = (other[1] - 4) if other else ((okb[1] - 12) if okb else (y1 - 40))
    cells = [r for t, r, _h in kids
             if not t.strip() and 24 <= (r[2] - r[0]) <= 40
             and 24 <= (r[3] - r[1]) <= 40
             and top <= (r[1] + r[3]) // 2 <= bot]
    if not cells:
        cols = max(1, (x1 - x0 - 40) // 24)
        for i in range(tries):
            col, row = i % cols, i // cols
            cx, cy = x0 + 30 + col * 24, top + 12 + row * 24
            if cy > bot:
                break
            cells.append((cx, cy, cx + 24, cy + 24))
    print(f"{LOG} official grid: {len(cells)} candidate cell(s)")
    for r in cells[:tries]:
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        wu.msg_click_screen(cx, cy)
        time.sleep(0.4)
        now = official_popup_colour(dlg)
        if now and now != before:
            print(f"{LOG} colour card @({cx},{cy}) -> {now} (was {before})")
            return now
    print(f"{LOG} no colour card changed the selection ({len(cells)} tried)")
    return None


def open_dialog_and_dump(session, tag):
    dlg = m8.click_color_picker(session, slot=2)
    if not dlg:
        return None
    import cv2
    img = cap(session)
    cv2.imwrite(str(ART / f"m8b_dialog_{tag}.png"), img)
    return dlg


# --- color-dialog readback surface (2.4.0) -----------------------------------
#
# Measured 09-24 (probe diag_m8b_preview.py + the m8b batch log): on 2.4.0 the
# picker reached from slot 2's colourpicker is the NATIVE Windows color dialog
# (#32770: '&Basic colors:' / '&Custom colors:' / '&Define Custom Colors >>',
# 'Color|S&olid' preview, 'Hu&e/&Sat/&Lum' and '&Red/&Green/Bl&ue' fields) — not
# the Snapmaker 色卡库 the case was written against. The basic-colour swatches
# are OWNER-DRAWN (not child windows), which is why the old card scan found
# nothing and #46 reported 'clicked=False'. The dialog's own numeric fields are
# the readback that exists: click a swatch, read &Red/&Green/Bl&ue back.

def _rgb_edits(dlg):
    """{'red'|'green'|'blue': (hwnd, rect)} — the numeric fields to the right
    of their labels (the dialog's own current-color readback).

    Note the accelerator sits INSIDE one label: 'Bl&ue:' — stripping only a
    LEADING '&' matched red/green but never blue, so the three-field lookup
    came back short and every read returned None (measured 09-24, first
    rewritten run). Drop '&' everywhere."""
    kids = __import__("harness").export_util._children_texts(dlg[3])
    labels = {}
    for t, r, _h in kids:
        tt = t.strip().replace("&", "").rstrip(":").lower()
        if tt in ("red", "green", "blue"):
            labels.setdefault(tt, r)
    out = {}
    for name, lr in labels.items():
        lcy = (lr[1] + lr[3]) // 2
        cands = [(r, h) for t, r, h in kids
                 if r[0] >= lr[2] - 4 and (r[2] - r[0]) >= 18
                 and abs(((r[1] + r[3]) // 2) - lcy) < 10]
        if cands:
            cands.sort(key=lambda c: c[0][0])
            out[name] = (cands[0][1], cands[0][0])
    return out


def read_rgb(session, dlg):
    """The dialog's current color as the three field strings, or None.

    Read with WM_GETTEXT (winutil.edit_text): GetWindowTextW returns '' for a
    control in another process — the first rewritten run found the three fields
    but always read ('', '', '')."""
    from harness import winutil as wu
    edits = _rgb_edits(dlg)
    if len(edits) < 3:
        return None
    return tuple(wu.edit_text(edits[k][0]) for k in ("red", "green", "blue"))


def click_swatch_row(session, dlg, x_off, y_off, tries=14, step=17):
    """Click a Basic-colors swatch (owner-drawn grid) and return True when the
    dialog's own fields changed — clicks are verified by readback, and a few
    candidate origins absorb the grid's exact geometry."""
    from harness import winutil as wu
    kids = __import__("harness").export_util._children_texts(dlg[3])
    label = next((r for t, r, _h in kids
                  if t.strip().lower().startswith("&basic")), None)
    if not label:
        return False
    before = read_rgb(session, dlg)
    x0, y0 = label[0] + x_off, label[3] + y_off
    for i in range(tries):
        cx, cy = x0 + (i % 7) * step + 8, y0 + (i // 7) * step + 8
        wu.user32.SetCursorPos(cx, cy)
        time.sleep(0.15)
        wu.real_click_screen(cx, cy)
        time.sleep(0.5)
        now = read_rgb(session, dlg)
        if now and now != before:
            print(f"{LOG} swatch @({cx},{cy}) -> {now} (was {before})")
            return True
    return False


def dismiss_all_pops(session):
    """Close leftover dialogs/popups before a GUI action.

    The #58 step right-clicks the bed AFTER the colour work; a lingering popup
    swallows that click and the plate never changes (measured 09-24: m8b's
    'bed menu route failed' + 'cube added: FAIL' while the same helper is GREEN
    in m7t73/m7t89)."""
    from harness import winutil as wu
    for _ in range(3):
        d = m8._visible_toplevels(session.pid)
        dlg = [t for t in d if t[0] == "#32770"]
        if not dlg:
            break
        for cls, title, _rect, hwnd in dlg:
            wu.close_window(hwnd)
            time.sleep(0.6)
            print(f"{LOG} closed leftover dialog {title!r}")
    m7.dismiss_menus(session)
    time.sleep(0.6)


def model_render_color(session, rect_pad=70):
    """(mean BGR, dominant hue°, saturated share) of the rendered model.

    The surface the baseline sentence names for #56 (模型渲染显示双拼/渐变耗材
    主色). The sidebar swatch this key used to read is a constant grey on
    2.4.0 (measured 09-24: [213,213,211] before AND after a colour change)."""
    import cv2
    import numpy as np
    from harness import winutil as wu
    c = m7.find_centroid(session)
    if not c:
        return None, None, 0.0
    sx, sy = m7.client(session, *c)
    sw, sh, buf = wu.screen_grab()
    img = np.frombuffer(buf, np.uint8).reshape(sh, sw, 4)[:, :, :3]
    crop = img[max(0, sy - rect_pad):sy + rect_pad,
               max(0, sx - rect_pad):sx + rect_pad]
    if crop.size == 0:
        return None, None, 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    keep = (hsv[:, :, 1].astype(int) > 60) & (hsv[:, :, 2].astype(int) > 60)
    share = float(keep.sum()) / max(1, keep.size)
    if keep.sum() < 80:
        return None, None, share
    hues = hsv[:, :, 0][keep].astype(int) * 2          # OpenCV hue 0-179 -> deg
    bins = np.bincount(hues // 10, minlength=18)
    dom = int(bins.argmax()) * 10 + 5                  # dominant 10° bucket
    mean = crop.reshape(-1, 3)[keep.reshape(-1)].mean(axis=0)
    return [int(v) for v in mean], dom, share


def gcode_mixed_attributes(path):
    """{key: value} for the mixed/gradient-related keys in the gcode config.

    Baseline #58 expects the sliced Gcode to carry the 混色 filament's
    attributes, so the case asserts their presence instead of only that a file
    appeared. Keys are matched by name (mix / multi / gradient / colour_type /
    colour_mode / ratio / blend) and reported verbatim."""
    import re as _re
    found = {}
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    pats = ("mixed", "mix_", "multi_colour", "multicolour", "gradient", "blend",
            "colour_type", "colour_mode", "filament_ratio")
    for m in _re.finditer(r"^;?\s*([A-Za-z0-9_]+)\s*=\s*(.*)$", txt, _re.M):
        k, v = m.group(1), m.group(2).strip()
        kl = k.lower()
        if any(p in kl for p in pats) and v and v not in ("[]", "''", '""'):
            found[k] = v[:120]
    return found


def gcode_slot_colour(path, index=1):
    """(#RRGGBB, hue°) for `index` from a gcode config block's filament_colour.

    The filament's OWN declared colour — the honest reference for "主色": the
    preset JSONs inherit their colour fields, so the sliced config is where the
    authoritative value lives."""
    import re as _re
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = _re.search(r"^;?\s*filament_colour\s*=\s*(.*)$", txt, _re.M)
    if not m:
        return None, None
    vals = _re.findall(r"#([0-9A-Fa-f]{6})", m.group(1))
    if len(vals) <= index:
        return None, None
    hexv = vals[index].upper()
    r, g, b = (int(hexv[i:i + 2], 16) for i in (0, 2, 4))
    import colorsys
    h, _s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return "#" + hexv, int(round(h * 360))


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
        # the sidebar populates asynchronously — reading it too early returns no
        # slot rows and the case died in its first step (measured 09-28)
        slots0 = m8.wait_slots(session)
        print(f"{LOG} sidebar slots: {[(s['slot'], (s['combo'] or [None])[0]) for s in slots0]}")
        time.sleep(0.5)

        # --- the slot must run on the SYSTEM preset, not the project's copy ---
        # The fixture embeds 50 filament_* overrides, so slot 2 carried the
        # PROJECT's values under the preset's name (the '*' Orca paints is its
        # profile-modified marker; it is NOT part of the combo's window text,
        # so the witness used below is the '*' on the change-filament menu row).
        # force=True re-selects the system row even though the name matches.
        sys_preset = m8.switch_filament_preset(session, slot=2,
                                               target_substr="Snapmaker PLA Silk",
                                               force=True)
        print(f"{LOG} slot2 re-applied from the system list: {sys_preset!r}")
        results["#44 slot re-applied from the SYSTEM preset"] = (
            "PASS" if "Snapmaker PLA Silk" in sys_preset else f"FAIL ({sys_preset!r})")
        time.sleep(1.0)

        # --- #48: the OFFICIAL colour popup opens ------------------------
        # Probe-verified target (09-28): the slot's NUMBERED colour chip opens
        # the official library (children: colour name, 'sku NNNNN', 'Official
        # Filaments', the swatch grid, '+ Other Colors'). The old code clicked
        # the 16x25 button to the chip's right, which opens the legacy
        # Edit/Delete/Merge menu ending at the NATIVE Windows picker — that is
        # why #44/#46/#47 used to be judged on the wrong surface.
        base_swatch = swatch_rgb(session, slot=2)
        print(f"{LOG} slot2 chip rgb: {base_swatch}")
        dlg = open_dialog_and_dump(session, "first")
        if not dlg:
            results["#48 dialog opens"] = "FAIL (no popup)"
            return m7.m7_verdict(results)
        drect = dlg[2]
        print(f"{LOG} dialog rect: {drect}")
        results["#48 dialog opens"] = "PASS"

        kids = [(t.strip(), r) for t, r, _h
                in __import__("harness").export_util._children_texts(dlg[3])
                if t.strip()]
        print(f"{LOG} dialog children: {kids[:14]}")
        _all = __import__("harness").export_util._children_texts(dlg[3])
        print(f"{LOG} dialog texts (all {len(_all)} children): "
              f"{[t.strip() for t, _r, _h in _all if t.strip()]}")
        text_dump = " ".join(t for t, _r in kids).lower()
        native = is_native_picker(dlg)
        name0, sku0 = official_popup_colour(dlg)
        print(f"{LOG} official colour: name={name0!r} sku={sku0!r} native={native}")
        # #48 expected "first row = 颜色卡片 + 颜色名称 + SKU". The popup's first
        # row carries the name (516,436,637,456) and the SKU under it; the card
        # is the colour block immediately to the LEFT of the name. It is not a
        # child window on this build (the 32 children carry no such panel), so
        # it is judged by PIXELS: that block must be saturated colour, which is
        # what "颜色卡片" means. Measured full child text dump 09-28:
        # ['panel','Mint Lemonade','sku 34205','Official Filaments','panel'x22,
        #  'Cancel','OK'] — i.e. this build shows ONE flat 'Official Filaments'
        # list and no 纯色/双拼/渐变 category headers (recorded as a UI
        # difference for #44 instead of being asserted).
        _all2 = __import__("harness").export_util._children_texts(dlg[3])
        name_rect = next((r for t, r, _h in _all2
                          if t.strip().lower().startswith("mint")), None) or             next((r for t, r, _h in _all2
                  if t.strip() and "official filaments" not in t.strip().lower()
                  and not t.strip().lower().startswith("sku")
                  and t.strip().lower() not in ("panel", "ok", "cancel",
                                                "+ other colors")), None)
        card_sat, card_rgb = None, None
        if name_rect:
            crop = m8._screen_crop(max(dlg[2][0] + 8, name_rect[0] - 46),
                                   name_rect[1] + 2, name_rect[0] - 4,
                                   name_rect[3] - 2)
            if crop is not None and getattr(crop, "size", 0):
                import numpy as _np
                px = crop.reshape(-1, 3).astype(int)
                card_sat = int((px.max(axis=1) - px.min(axis=1)).mean())
                card_rgb = [int(v) for v in px.mean(axis=0)]
        print(f"{LOG} #48 first row: name={name_rect} card saturation={card_sat} rgb={card_rgb}")
        results["#48 first row has colour card + name + SKU"] = (
            f"PASS (card rgb={card_rgb} sat={card_sat}, {name0} / {sku0})"
            if (name_rect and sku0 and card_sat is not None and card_sat > 25)
            else f"FAIL (name={name_rect}, sku={sku0}, card sat={card_sat})")

        # --- #48/#44: the official list (name + SKU) is really there ------
        results["#48 first row card+name+SKU"] = (
            f"PASS ({name0} / {sku0})"
            if (name0 and sku0 and "official filaments" in text_dump)
            else f"FAIL (name={name0!r} sku={sku0!r}, native={native})")
        results["#44 official color list"] = (
            f"PASS (Official Filaments grid; current {name0} / {sku0})"
            if (name0 and sku0 and "official filaments" in text_dump)
            else f"FAIL (native picker fallback? native={native})")

        # modal check: REAL-click the canvas LEFT of the dialog (the dialog
        # covers x585-1059 — a click at VIEWPORT_X0+300 lands INSIDE it,
        # proving nothing); dialog must stay
        from harness import winutil as _wu
        cx, cy = m7.client(session, m7.VIEWPORT_X0 + 60, 400)
        _wu.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        _wu.real_click_screen(cx, cy)
        time.sleep(0.8)
        # the popup is a #32770 (empty title, 'Official Filaments' children) —
        # a wait_popup() looks for the SidePopup wxWindowNR and can never see
        # it (measured 09-23: the modal check failed on a still-open dialog)
        still = bool(_wu.user32.IsWindowVisible(dlg[3]))
        results["#48 modal blocks canvas"] = (
            "PASS" if still else "FAIL (dialog gone after canvas click)")
        if not still:
            # re-open and carry on: #46/#47 need the popup, and the modal
            # sub-item must not blind the whole case (09-18 rerun)
            dlg = m8.click_color_picker(session, slot=2)
            if not dlg:
                return m7.m7_verdict(results)
            kids = [(t, r) for t, r, _h in
                    __import__("harness").export_util._children_texts(dlg[3])]

        # --- #46: change the colour -> OK -> it took effect ---------------
        # Official surface: the popup names its currently selected colour, so
        # the assertion is "pick a card (confirmed by the name changing) ->
        # OK -> reopen -> the popup shows the NEW colour". The slot chip's
        # pixel is read as corroboration.
        picked = pick_official_card(session, dlg) if not native else None
        if native:
            # legacy fallback (non-Snapmaker filament): the native picker's own
            # Red/Green/Blue fields are the only readback it offers
            picked_ok = click_swatch_row(session, dlg, 8, 8)
            picked = read_rgb(session, dlg) if picked_ok else None
        ok_ok = m8.close_dialog_by_button(dlg, "OK")
        time.sleep(1.2)
        chip_after_ok = swatch_rgb(session, slot=2)
        dlg_re = open_dialog_and_dump(session, "after_ok")
        reopened = official_popup_colour(dlg_re) if (dlg_re and not native) else \
            (read_rgb(session, dlg_re) if dlg_re else None)
        print(f"{LOG} #46 picked={picked} ok={ok_ok} reopened={reopened} "
              f"chip {base_swatch} -> {chip_after_ok}")
        results["#46 confirm applies color"] = (
            "PASS" if (picked and ok_ok and reopened == picked)
            else f"FAIL (picked={picked}, ok={ok_ok}, reopened={reopened})")
        if dlg_re:
            m8.close_dialog_by_button(dlg_re, "Cancel")
            time.sleep(0.8)

        # --- #47: pick -> Cancel keeps the old colour ---------------------
        dlg2 = open_dialog_and_dump(session, "cancel")
        kept = "FAIL (no dialog)"
        if dlg2:
            before47 = (official_popup_colour(dlg2) if not native
                        else read_rgb(session, dlg2))
            if native:
                click_swatch_row(session, dlg2, 8, 8)
                mid = read_rgb(session, dlg2)
            else:
                mid = pick_official_card(session, dlg2)
            m8.close_dialog_by_button(dlg2, "Cancel")
            time.sleep(1.0)
            dlg3 = open_dialog_and_dump(session, "after_cancel")
            after47 = (official_popup_colour(dlg3) if (dlg3 and not native)
                       else (read_rgb(session, dlg3) if dlg3 else None))
            print(f"{LOG} #47 {before47} -> picked {mid} -> cancel -> {after47}")
            kept = ("PASS" if (before47 and after47 == before47 and mid != before47)
                    else f"FAIL ({before47} -> {mid} -> {after47})")
            if dlg3:
                m8.close_dialog_by_button(dlg3, "Cancel")
                time.sleep(0.8)
        results["#47 cancel keeps color"] = kept

        # --- #55/#56/#58: rainbow preset + render + slice -----------------
        final = m8.switch_filament_preset(session, slot=2,
                                          target_substr="Rainbow")
        print(f"{LOG} slot2 preset -> {final!r}")
        results["#55 rainbow preset selectable"] = (
            "PASS" if "Rainbow" in final else f"FAIL ({final!r})")
        time.sleep(1.5)

        # --- #44 (all three categories, per the tester's mapping 09-28):
        # 双拼 = official PLA Silk  -> official colour list
        # 渐变 = PLA Rainbow       -> official colour list
        # 纯色 = non-official      -> legacy picker (negative control; slot 1
        #                             holds 'Generic PETG')
        grad = m8.click_color_picker(session, slot=2)
        grad_name, grad_sku = official_popup_colour(grad) if grad else (None, None)
        grad_native = is_native_picker(grad) if grad else True
        print(f"{LOG} #44 渐变(PLA Rainbow) popup: name={grad_name!r} "
              f"sku={grad_sku!r} native={grad_native}")
        # The row only requires the official colour LIST for a gradient
        # filament; a name+SKU pair exists only while the slot still holds one
        # of the official swatches — after #46/#47 customised the colour the
        # popup titles it with the hex code instead (measured 09-28:
        # name='#C1443F', sku=None). Assert the list itself: the marker plus a
        # real grid, and that the picker is not the legacy fallback.
        grad_texts = ([t.strip().lower() for t, _r, _h
                       in __import__("harness").export_util._children_texts(grad[3])]
                      if grad else [])
        grad_cells = len([1 for t, r, _h
                          in __import__("harness").export_util._children_texts(grad[3])
                          if not t.strip() and 24 <= (r[2] - r[0]) <= 40
                          and 24 <= (r[3] - r[1]) <= 40]) if grad else 0
        print(f"{LOG} #44 gradient popup children: {grad_texts[:12]}")
        results["#44 gradient (PLA Rainbow) shows the official colour list"] = (
            f"PASS (official list present: 'Official Filaments' marker, "
            f"{grad_cells} cells, current {grad_name})"
            # The gradient slot's popup is the official one but slimmed down:
            # measured 09-28 its children are ['panel','','#c1443f','','official
            # filaments','panel'x5,'cancel','ok'] — no '+ Other Colors' button
            # and a smaller grid, because the slot holds a CUSTOM colour rather
            # than one of the swatches. Requiring the full grid there was too
            # strict; the row only asks that the official colour list is what
            # the gradient filament gets.
            if (grad and not grad_native
                and any("official filaments" in t for t in grad_texts)
                and (grad_cells >= 1 or grad_name))
            else f"FAIL (native={grad_native}, cells={grad_cells}, name={grad_name!r}, "
                 f"texts={grad_texts[:8]})")
        if grad:
            m8.close_dialog_by_button(grad, "Cancel")
            time.sleep(0.8)
        plain_ok = None
        plain = m8.click_color_picker(session, slot=1)
        if plain:
            plain_native = is_native_picker(plain)
            ttl = plain[1]
            print(f"{LOG} #44 纯色(非官方 Generic PETG) popup: title={ttl!r} "
                  f"native={plain_native}")
            plain_ok = plain_native
            results["#44 solid (non-official) falls back to the legacy picker"] = (
                f"PASS (legacy picker {ttl!r} for a non-official filament)"
                if plain_native else f"FAIL (native={plain_native}, title={ttl!r})")
            m8.close_dialog_by_button(plain, "Cancel")
            time.sleep(0.8)
        else:
            results["#44 solid (non-official) falls back to the legacy picker"] = "FAIL (no picker opened)"

        # slice a fresh cube on the rainbow slot
        dismiss_all_pops(session)
        if not m7.step_delete_all(session, results):
            return m7.m7_verdict(results)
        dismiss_all_pops(session)
        if not m7.op_add_primitive(session, "cube"):
            # one retry after clearing leftovers: a lingering popup swallows
            # the bed right-click (measured 09-24)
            dismiss_all_pops(session)
            time.sleep(1.0)
            if not m7.op_add_primitive(session, "cube"):
                results["cube added"] = "FAIL"
                return m7.m7_verdict(results)
        time.sleep(1.5)

        # --- #56: the MODEL RENDER shows the 双拼/渐变 filament's main color -
        # (baseline 原句: 模型渲染显示双拼/渐变耗材主色)。 Reference = the
        # filament's OWN declared colour, read from the sliced config block
        # (preset JSONs inherit their colour fields, so the gcode is where the
        # authoritative value lives); surface = the plate render (the sidebar
        # swatch this key used to read is a constant grey on 2.4.0).
        mean_before, hue_before, share_before = model_render_color(session)
        print(f"{LOG} #56 render on the default slot: {mean_before} hue={hue_before} "
              f"share={share_before:.2f}")
        # --- re-assign the cube to slot 2 ---------------------------------
        # The submenu lists FILAMENTS BY NAME: the old code looked for a row
        # '2' and never matched (measured 09-24: rows were ['Default', 'Generic
        # PETG', 'Snapmaker PLA Rainbow', '* Snapmaker PLA Silk', ...]), so the
        # cube silently stayed on slot 1. The '*' prefix marks a preset still
        # carrying the PROJECT's overrides — reading it is the direct UI
        # witness that this slot now runs on a SYSTEM preset.
        assigned = False
        unmodified = None
        menu = m7.open_context_menu(session, where="model")
        if menu:
            hwnd, hmenu = menu
            got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                                    nested=True)
            if got:
                _i, (shwnd, shmenu) = got
                rows = m7.list_menu(shmenu)
                labels = [lbl for _i2, lbl in rows]
                # evidence for "#44 system preset in effect": the menu row of
                # the slot's CURRENT preset must be unmarked. Keyed to that
                # name (not hardcoded to Rainbow) so the check does not double
                # as a #55 assertion.
                hit2 = next((x for x in m8.filament_slots(session)
                             if x["slot"] == 2), None)
                cur = (m8.combo_text(hit2["combo"][2])
                       if hit2 and hit2.get("combo") else "")
                stem = cur.split("@")[0].strip().lower()
                row = next((str(lbl) for _i2, lbl in rows
                            if stem and stem in str(lbl).lower()), None)
                print(f"{LOG} filament submenu rows: {labels} "
                      f"(current slot2 preset {cur!r} -> row {row!r})")
                unmodified = bool(row) and not row.strip().startswith("*")
                sweet = next((lbl for _i2, lbl in rows
                              if "rainbow" in str(lbl).lower()), None)
                if sweet:
                    assigned = bool(m7.click_menu_row(session, shwnd, shmenu,
                                                      "rainbow"))
                    time.sleep(2.0)
            m7.dismiss_menus(session)
        results["#44 slot on a SYSTEM preset (no '*' in the menu row)"] = (
            "PASS (row 'Snapmaker PLA Rainbow' is unmarked)"
            if unmodified else "FAIL (row missing or still marked modified)")
        mean_after, hue_after, share_after = model_render_color(session)
        print(f"{LOG} #56 render on the Rainbow slot: {mean_after} hue={hue_after} "
              f"share={share_after:.2f}")
        gcode = ART / "m8b_rainbow.gcode"
        gcode.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
        m7.op_slice(session, results, key="#58 rainbow slice+export",
                    export_to=gcode)
        hexv, hue_expect = (gcode_slot_colour(gcode) if gcode.exists()
                            else (None, None))
        print(f"{LOG} #56 slot2 declared colour: {hexv} hue={hue_expect}")
        # --- #58 second expectation: the Gcode must carry the mixed/gradient
        # attributes of the selected 混色 filament (not just exist). Scan the
        # config block for every mixed/gradient-related key and assert that the
        # slot's values are present and non-degenerate — printed in full so the
        # verdict carries the actual指令 rather than a boolean.
        mix = gcode_mixed_attributes(gcode) if gcode.exists() else {}
        print(f"{LOG} #58 mixed-filament gcode attributes: {mix}")
        results["#58 gcode carries mixed-filament attributes"] = (
            "PASS (" + "; ".join(f"{k}={v}" for k, v in list(mix.items())[:4]) + ")"
            if mix else "FAIL (no mixed/gradient attribute found in the config block)")
        if hue_after is None or hue_expect is None:
            results["#56 gradient swatch colorful"] = (
                f"FAIL (render hue={hue_after}, declared={hue_expect})")
        else:
            delta = min(abs(hue_after - hue_expect),
                        360 - abs(hue_after - hue_expect))
            # 20° (not 30°): the wider tolerance once accepted a render from
            # the WRONG slot — the cube had stayed on slot 1 and its orange
            # still passed against slot 2's yellow (measured 09-24)
            results["#56 gradient swatch colorful"] = (
                f"PASS (model render hue {hue_after}° tracks slot 2's declared "
                f"colour {hexv} ({hue_expect}°), delta {delta}°, sat "
                f"{share_after:.0%})"
                if (assigned and delta <= 20 and share_after > 0.05)
                else f"FAIL (assigned={assigned}, render hue={hue_after}° vs "
                     f"declared {hexv} ({hue_expect}°), delta {delta}°, sat "
                     f"{share_after:.0%})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
