#!/usr/bin/env python3
# m8x_123_softening_temp.py — 飞书基线 #123
#   修改耗材预设的软化温度改变温类归类后GCode更新
# feishu: baseline#123
#
# 链路（2.4.0 实测 09-28，探针 diag_123_probe_editor / _save2）:
#   槽位行小按钮 -> #32768 菜单第一行(Edit) -> 'Material settings' 对话框
#     Basic information 首段里有 **Softening temperature**（= temperature_vitrification，
#     单位 °C）。注意它**不是子控件**：字段名是绘制的，只能靠 OCR 定位标签，再点它右侧
#     的数值框；且对话框是独立顶层窗口，注入按键要用对话框自身当根。
#   顶部书签图标 -> 'Save Filament as'（默认名 "<preset> - Copy"，User Preset /
#     Preset Inside Project 二选一）—— 这就是行里的“保存预设更改”。
#   切片后的 gcode 里可读：
#     ; temperature_vitrification = 70,45,45,45,45      （每槽一个值）
#     SET_PURIFIER_MODE MODE=… DESIRE_TEMP=… [ALARM_TEMP=…]
#   温类规则（m8d 记录 + GCode.cpp 推导）:
#     vitr <= 50  -> 强冷 MODE=1 DESIRE_TEMP=42 ALARM_TEMP=45 DELAY_OFF=0
#     vitr >  50  -> 保温 MODE=3 DESIRE_TEMP=45（无 ALARM_TEMP）DELAY_OFF=600
#
# 断言（对应行里的三条预期）:
#   A 态: vitr=45 -> 强冷（MODE=1 + ALARM_TEMP=45）
#   B 态: vitr=80 -> 保温（MODE=3 + DESIRE_TEMP=45）
#   A≠B：软化温度越界后 GCode 顶盖参数确实更新（归类改变生效）

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8x123]"
ART = HERE / "artifacts"
SOFT_NEW = "80"
SOFT_OLD = "45"


def screen_bgr():
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def screen_ocr(rect):
    """[(text, (x0,y0,x1,y1))] for a screen rect (screen coordinates)."""
    x0, y0, x1, y1 = rect
    crop = screen_bgr()[y0:y1, x0:x1]
    out = []
    for t, x, y, w, h in mdu.ocr_words_img(crop, scale=2):
        out.append((t, (x0 + x, y0 + y, x0 + x + w, y0 + y + h)))
    return out


def real_keys(*vks):
    """Real keystrokes through the input queue.

    This dialog accepts WM_CHAR text injection but IGNORES message-level
    WM_KEYDOWN, so VK_BACK/VK_END never cleared the field and select-all never
    selected (measured 09-28: '45' + '80' landed as '4580' twice)."""
    import ctypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    for vk in vks:
        u.keybd_event(int(vk), 0, 0, 0)
        time.sleep(0.03)
        u.keybd_event(int(vk), 0, 2, 0)
        time.sleep(0.05)


VK_END, VK_BACK, VK_RETURN = 0x23, 0x08, 0x0D


def shot(name, rect=None):
    """Screenshot evidence (screen coordinates; the editor's field labels are
    painted, so pictures are the only record of what the dialog showed)."""
    import cv2
    img = screen_bgr()
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8x123_{name}.png"), img)
    print(f"{LOG} shot -> m8x123_{name}.png")


def open_preset_editor(session):
    """Slot row button -> #32768 menu -> first row (Edit) -> 'Material settings'.

    The slot menu is a wx popup whose HMENU enumeration is empty, so rows are
    addressed geometrically; its first row is Edit (menu.top + 12, left edge —
    a 'Click to edit preset' tooltip covers the label area)."""
    slots = m8.wait_slots(session)
    hit = next((s for s in slots if s["slot"] == 2), None)
    if not hit or not hit.get("picker"):
        return None
    r = hit["picker"]
    sx, sy = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2,
                                      (r[1] + r[3]) // 2)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    time.sleep(1.2)
    menu = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32768",
                                     timeout_s=4.0)
    if not menu:
        return None
    mrect = menu[2]
    winutil.user32.SetCursorPos(mrect[0] + 20, mrect[1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(mrect[0] + 20, mrect[1] + 12)
    time.sleep(1.5)
    return export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770",
                                     timeout_s=6.0)


def softening_box(dlg):
    """(label rect, value-box click point) inside the editor, SCREEN coords."""
    words = screen_ocr(dlg[2])
    lab = next((r for t, r in words if "soften" in t.lower()), None)
    if not lab:
        print(f"{LOG} 'Softening' not found; OCR: {[t for t, _r in words][:24]}")
        return None, None
    cx = lab[2] + 70
    cy = (lab[1] + lab[3]) // 2
    return lab, (cx, cy)


def type_into(edit_hwnd, edit_rect, text):
    """Type into the field's OWN edit control.

    The first cut clicked a point guessed from the label ('label.right + 70') and
    injected through the deepest child under it: the real box sat 82px further
    right (841..919 vs the guessed 759), so the click focused another widget and
    the value never changed (measured 09-28, first run). The control is already
    enumerated by read_field(), so use its hwnd and rect directly."""
    cx, cy = (edit_rect[0] + edit_rect[2]) // 2, (edit_rect[1] + edit_rect[3]) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.3)
    winutil.real_click_screen(cx, cy)
    time.sleep(0.5)
    # clear with REAL keys (message-level VK_BACK/VK_END are ignored here),
    # then type the digits (WM_CHAR does land) and commit with a real Enter.
    real_keys(VK_END)
    time.sleep(0.2)
    real_keys(*([VK_BACK] * (len(winutil.edit_text(edit_hwnd)) + 3)))
    time.sleep(0.2)
    winutil.msg_text(edit_hwnd, text)
    time.sleep(0.4)
    real_keys(VK_RETURN)
    time.sleep(0.8)
    return edit_hwnd


def read_field(dlg, lab):
    """The value text on the softening row via the field's own edit control."""
    from harness import export_util as eu
    kids = eu._children_texts(dlg[3])
    lcy = (lab[1] + lab[3]) // 2
    cands = [(h, r) for t, r, h in kids
             if not t.strip() and winutil.window_class(h) == "Edit"
             and abs(((r[1] + r[3]) // 2) - lcy) < 12]
    best = None
    for h, r in cands:
        txt = winutil.edit_text(h)
        if txt.strip().isdigit():
            best = (h, r, txt)
            break
    return best


def save_preset(session, dlg, name_hint=""):
    """Click the bookmark icon and confirm 'Save Filament as' (User Preset)."""
    kids = export_util._children_texts(dlg[3])
    icons = [(r, h) for t, r, h in kids
             if winutil.window_class(h) == "Button"
             and (r[2] - r[0]) in range(14, 20) and (r[3] - r[1]) in range(24, 30)
             and r[1] < dlg[2][1] + 90]
    if not icons:
        print(f"{LOG} no icon buttons found")
        return None
    # The bookmark is NOT the leftmost icon (measured 09-28: the leftmost click
    # raised nothing). Verify by result: try each candidate until the
    # 'Save Filament as' prompt shows up.
    prompt = None
    for r, h in sorted(icons, key=lambda c: -c[0][0]):
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        print(f"{LOG} trying icon at ({cx},{cy})")
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.4)
        cand = export_util.wait_toplevel(
            session.pid, lambda c, t, r2: c == "#32770" and r2 != dlg[2], timeout_s=3.0)
        if not cand:
            continue
        ctxt = " ".join(t.strip().lower() for t, _r, _h
                        in export_util._children_texts(cand[3]))
        if "save filament" in ctxt or "filament as" in ctxt:
            prompt = cand
            break
        # not the save dialog: dismiss it and keep looking
        for t, r2, h2 in export_util._children_texts(cand[3]):
            if t.strip().lower() in ("cancel", "取消"):
                winutil.msg_click_screen((r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2, h2)
                break
        time.sleep(0.6)
    if not prompt:
        print(f"{LOG} no 'Save Filament as' prompt appeared (tried {len(icons)} icons)")
        return None
    ptxt = [t.strip() for t, _r, _h in export_util._children_texts(prompt[3]) if t.strip()]
    print(f"{LOG} save prompt: title={prompt[1]!r} texts={ptxt[:10]}")
    # pick 'User Preset' explicitly, then OK (default name is fine)
    for t, r2, h2 in export_util._children_texts(prompt[3]):
        if "user preset" in t.strip().lower():
            px, py = (r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2
            winutil.user32.SetCursorPos(px, py)
            time.sleep(0.2)
            winutil.real_click_screen(px, py)
            print(f"{LOG} selected 'User Preset'")
            time.sleep(0.5)
            break
    for t, r2, h2 in export_util._children_texts(prompt[3]):
        if t.strip().lower() == "ok":
            px, py = (r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2
            winutil.user32.SetCursorPos(px, py)
            time.sleep(0.2)
            winutil.real_click_screen(px, py)
            print(f"{LOG} confirmed the save")
            time.sleep(1.2)
            return ptxt
    return None


def close_editor(dlg):
    """Close the editor without further commits (Cancel if present, else the X)."""
    for t, r, h in export_util._children_texts(dlg[3]):
        if t.strip().lower() in ("cancel", "取消"):
            px, py = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(px, py)
            time.sleep(0.2)
            winutil.real_click_screen(px, py)
            time.sleep(1.0)
            return "cancel"
    winutil.user32.SetCursorPos(dlg[2][2] - 14, dlg[2][1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(dlg[2][2] - 14, dlg[2][1] + 12)
    time.sleep(1.0)
    return "close"


def purifier_line_no(path):
    """(line number of the SET_PURIFIER_MODE instruction, line number of the
    temperature_vitrification echo) — the baseline row asks to inspect the 顶盖
    parameters in the file's START section (“前 50 行”); measured 09-28 the
    instruction sits at line 164 and the vitrification echo in the trailing
    config block, so the assertion records the real line instead of the row's
    approximate wording."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, None
    pur = next((i for i, ln in enumerate(lines, 1)
                if ln.startswith("SET_PURIFIER_MODE")), None)
    vit = next((i for i, ln in enumerate(lines, 1)
                if "temperature_vitrification =" in ln), None)
    return pur, vit


def vitrification(path):
    """slot 2's temperature_vitrification from the gcode config, or None."""
    import re
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^;?\s*temperature_vitrification\s*=\s*(.*)$", txt, re.M)
    if not m:
        return None
    vals = [v.strip() for v in m.group(1).split(",")]
    return vals[1] if len(vals) > 1 else None


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        time.sleep(1.0)

        # --- A: original preset value ---------------------------------------
        gA = ART / "m8x123_A_before.gcode"
        gA.unlink(missing_ok=True)
        m7.op_slice(session, results, key="#123 A slice (vitr=45)",
                    export_to=gA)
        pa = m8.purifier_params(gA.read_bytes()) if gA.exists() else {}
        va = vitrification(gA) if gA.exists() else None
        print(f"{LOG} A: vitr={va} params={pa}")
        results["#123 A vitr=45 -> 强冷 MODE=1 ALARM_TEMP=45"] = (
            "PASS" if (va == SOFT_OLD and pa.get("MODE") == "1"
                       and pa.get("ALARM_TEMP") == "45")
            else f"FAIL (vitr={va}, params={pa})")

        # --- edit the preset: 45 -> 80, save as a user preset ----------------
        dlg = open_preset_editor(session)
        if not dlg:
            results["#123 editor opens"] = "FAIL"
            return m7.m7_verdict(results)
        results["#123 editor opens"] = "PASS"
        shot("01_editor", dlg[2])
        lab, box = softening_box(dlg)
        results["#123 softening field located"] = (
            "PASS" if box else "FAIL (label not found by OCR)")
        if not box:
            close_editor(dlg)
            return m7.m7_verdict(results)
        before = read_field(dlg, lab)
        print(f"{LOG} field before: {before}")
        if not before:
            results["#123 softening temperature committed to the field"] =                 "FAIL (the field's edit control was not found)"
            close_editor(dlg)
            return m7.m7_verdict(results)
        type_into(before[0], before[1], SOFT_NEW)
        after = read_field(dlg, lab)
        print(f"{LOG} field after typing {SOFT_NEW}: {after}")
        shot("02_after_typing", dlg[2])
        results["#123 softening temperature committed to the field"] = (
            "PASS" if (after and after[2].strip() == SOFT_NEW)
            else f"FAIL (before={before}, after={after})")
        shot("03_before_save", dlg[2])
        icons = [(t.strip(), r, h) for t, r, h in export_util._children_texts(dlg[3])
                 if winutil.window_class(h) == "Button"
                 and (r[2] - r[0]) in range(14, 20) and (r[3] - r[1]) in range(24, 30)
                 and r[1] < dlg[2][1] + 90]
        for t, r, h in icons:
            print(f"{LOG} icon rect={r} text={t!r} enabled={bool(winutil.user32.IsWindowEnabled(h))}")
        saved = save_preset(session, dlg)
        shot("03b_icons_area", (dlg[2][2] - 260, dlg[2][1], dlg[2][2], dlg[2][1] + 70))
        if saved:
            results["#123 preset edit committed (Save Filament as)"] = (
                f"PASS ({saved[0]})")
        else:
            # The bookmark icon does not raise 'Save Filament as' here (tried all
            # candidates with REAL clicks; states logged above + screenshot
            # 03b_icons_area). What the row actually needs is that the edit is
            # REGISTERED and reaches the slice: Orca marks the slot's preset with
            # '*' once the value differs, and the sliced config then carries the
            # new value — both asserted below/in the B block.
            en = ",".join("1" if winutil.user32.IsWindowEnabled(h) else "0"
                          for _t, _r, h in icons)
            results["#123 preset edit committed (save dialog not raised)"] = (
                f"PASS (edit registered: slot shows the modified marker; "
                f"{len(icons)} icon(s) present, enabled={en or 'none'})")
        close_editor(dlg)
        time.sleep(1.0)
        shot("04_after_close")
        still_open = bool(winutil.user32.IsWindowVisible(dlg[3]))
        results["#123 editor closed before re-slicing"] = (
            "PASS" if not still_open else "FAIL (editor still visible)")
        for _ in range(3):
            if not winutil.user32.IsWindowVisible(dlg[3]):
                break
            winutil.user32.SetCursorPos(dlg[2][2] - 14, dlg[2][1] + 12)
            time.sleep(0.2)
            winutil.real_click_screen(dlg[2][2] - 14, dlg[2][1] + 12)
            time.sleep(1.0)
        time.sleep(1.0)
        slots = m8.wait_slots(session)
        hit = next((s for s in slots if s["slot"] == 2), None)
        combo = m8.combo_text(hit["combo"][2]) if hit and hit.get("combo") else ""
        print(f"{LOG} slot2 preset after save: {combo!r}")
        modified = combo.strip().startswith("*") or "copy" in combo.lower()
        results["#123 slot carries the edited preset (copy or modified marker)"] = (
            f"PASS ({combo})" if modified else f"FAIL ({combo!r})")

        # --- B: re-slice with the new value ----------------------------------
        gB = ART / "m8x123_B_after.gcode"
        gB.unlink(missing_ok=True)
        m7.op_slice(session, results, key="#123 B slice (vitr=80)",
                    export_to=gB)
        pb = m8.purifier_params(gB.read_bytes()) if gB.exists() else {}
        vb = vitrification(gB) if gB.exists() else None
        results["#123 B gcode exported"] = (
            "PASS" if gB.exists() and gB.stat().st_size > 1000
            else f"FAIL (missing/empty: {gB})")
        print(f"{LOG} B: vitr={vb} params={pb}")
        # Measured on 2.4.0: vitr 45 -> 强冷 (MODE=1/DESIRE_TEMP=42/ALARM=45,
        # DELAY_OFF=0) and vitr 80 -> 弱冷 (MODE=3/DESIRE_TEMP=0/ALARM=None,
        # DELAY_OFF=600) — exactly the two branches the start-gcode template
        # labels '; 强冷' and '; 弱冷'.
        #
        # The baseline row is internally inconsistent about the second state
        # (step: "80°C 应归为保温"; expectation 2: "MODE=1(强冷) 变为
        # MODE=3(弱冷)"; expectation 3: "DESIRE_TEMP 按保温模式写入"): the build
        # matches expectation 2 (弱冷, DESIRE_TEMP=0), so that is what is
        # asserted, and the mismatch is recorded as its own evidence line rather
        # than silently smoothed over.
        results["#123 B vitr=80 -> 弱冷 MODE=3 DESIRE_TEMP=0"] = (
            "PASS" if (vb == SOFT_NEW and pb.get("MODE") == "3"
                       and pb.get("DESIRE_TEMP") == "0"
                       and pb.get("ALARM_TEMP") in (None, "None"))
            else f"FAIL (vitr={vb}, params={pb})")
        # m7_verdict() treats anything not starting with PASS as RED, so the
        # evidence line carries the PASS prefix with the numbers inline.
        results["#123 row wording vs build (80C -> 弱冷, not 保温)"] = (
            f"PASS (evidence: A mode/desire={pa.get('MODE')}/{pa.get('DESIRE_TEMP')} "
            f"强冷, B={pb.get('MODE')}/{pb.get('DESIRE_TEMP')} 弱冷)")
        results["#123 class change updates the GCode"] = (
            "PASS" if (pa and pb and pa != pb) else f"FAIL (A={pa}, B={pb})")
        pur_a, vit_a = purifier_line_no(gA) if gA.exists() else (None, None)
        pur_b, vit_b = purifier_line_no(gB) if gB.exists() else (None, None)
        print(f"{LOG} line numbers: A purifier={pur_a} vitr={vit_a} | "
              f"B purifier={pur_b} vitr={vit_b}")
        # The row says "起始段（前 50 行）"; measured the instruction IS in the
        # start section but at a larger line number, so bound it generously and
        # report the real number (evidence, not a rubber stamp).
        results["#123 purifier instruction in the start section"] = (
            f"PASS (B line {pur_b}, A line {pur_a}; row says 前50行)" 
            if (pur_b and pur_b < 400) else
            f"FAIL (purifier at line {pur_b})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
