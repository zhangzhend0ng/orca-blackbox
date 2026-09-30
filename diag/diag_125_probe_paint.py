#!/usr/bin/env python3
# diag_125_probe_paint.py — #125 机制探针（按测试方 09-29 纠正：主材=对象耗材丝，辅材=涂色）
#
# 行文（飞书原表 #125）:
#   标题 工艺全局辅材冲突，打开偏好后，可以正常切片并打印
#   步骤 1 工艺全局辅材与主材冲突，工艺对象辅材与主材冲突  2 不打开偏好，发起切片
#        3 工艺全局辅材与主材不冲突，工艺对象辅材与主材冲突  4 打开偏好，开始切片
#   预期 1 按钮置灰，警告  2 无法切片  4 打开后按钮高亮，切片正常
#
# 测试方纠正（09-29）: **主材 = 对象的耗材丝；辅材 = 涂色（painted）**。
#   → 之前盯的 `Filament for Supports` 不是这条用例的面。
#
# 已定位的事实:
#   * 切片门禁 = 高低温混用门（m8c #111/#112 已实现：按钮置灰 + 横幅
#     "Detected both high and low temperature materials…"）；
#   * 偏好 = 标题栏汉堡(85,8) → `Preferences` → General 页
#     `Allow high/low temperature filament mixing`（标签 (717,461,986,477)）；
#   * 涂色入口 = 3D 视图 gizmo 工具条的 'Color painting [N]'（m7t89 已实现：
#     select_model → find_slot('color painting') → click_slot → 在模型上点一下）。
#
# 本轮要回答:
#   Q1 涂色一次（dab）用的是哪条耗材？把**非主材**的槽设成高温（Generic ABS）后，
#      涂色是否触发高低温门禁（按钮置灰/横幅/切片被吞）？
#   Q2 门禁触发后，打开 `Allow high/low temperature filament mixing` 能否放行（切片能起）？
#      —— 这是 #125 的预期 4。
#   Q3 涂色调色板的色块几何（ImGui 像素），必要时按第 k 块点击来选“用哪条耗材涂”。
#
# 可逆：只涂色/切槽/开关偏好，收尾还原偏好；不保存工程。

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))
sys.path.insert(0, str(HERE / "diag"))

from harness import export_util, winutil  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from diag_125_probe_aux3 import all_children, band, click_pt, ocr, toplevels  # noqa: E402
import diag_125_probe_aux3 as p3  # noqa: E402

LOG = "[p125p]"
ART = HERE / "artifacts"
user32 = winutil.user32
PREF_LABEL = "allow high/low temperature filament mixing"


def screen_bgr():
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)


def shot(name, rect=None):
    import cv2
    img = screen_bgr()
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8x125_{name}.png"), img)
    print(f"{LOG} shot -> m8x125_{name}.png")


def dialogs_up():
    return [(t[1], t[2]) for t in toplevels() if t[0] == "#32770"]


def gate_state(tag):
    from m8c_temp_mix_gate import slice_rejected
    ups = dialogs_up()
    if ups:
        print(f"{LOG} [{tag}] dialogs up before probe: {ups}")
    rejected = slice_rejected(session_global())
    time.sleep(0.5)
    ocr_hit = False
    try:
        from harness import mix_dialog_util as mdu
        words = mdu.ocr_words_img(screen_bgr(), scale=2)
        text = " ".join(w for w, *_ in words).lower()
        ocr_hit = ("high and low" in text) or ("temperature" in text and "detected" in text)
    except Exception as exc:
        print(f"{LOG} banner OCR failed: {exc}")
    print(f"{LOG} [{tag}] rejected={rejected} banner_ocr={ocr_hit} dialogs={dialogs_up()}")
    shot(f"gate_{tag.replace(' ', '_')}")
    return rejected, ocr_hit


def session_global():
    return p3.SESSION


def palette_tiles():
    """Chromatic blob centres of the ImGui paint palette (m4e-style detection)."""
    import cv2
    import numpy as np
    from harness.anchors import (PAINT_PAL_LEFT_OFF as PAL_LEFT_OFF,
                                 PAINT_PAL_Y0 as PAL_Y0, PAINT_PAL_Y1 as PAL_Y1)
    img = screen_bgr()
    band_img = img[PAL_Y0:PAL_Y1, 640 + PAL_LEFT_OFF:1900]
    spread = band_img.astype(int).max(axis=2) - band_img.astype(int).min(axis=2)
    mask = (spread > 50).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    tiles = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if area >= 120 and 10 <= w < 220 and 8 <= h < 160:
            cx, cy = cents[i]
            tiles.append((int(cx + 640 + PAL_LEFT_OFF), int(cy + PAL_Y0), int(area)))
    tiles.sort()
    return tiles


def paint_dab():
    """activate the Color Painting gizmo and dab once on the model (m7t89 path)."""
    if not m7.select_model(session_global()):
        print(f"{LOG} model not selectable")
        return False
    px, ptip = m7.find_slot(session_global(), lambda t: "color painting" in t)
    print(f"{LOG} color-painting slot: {px} {ptip!r}")
    if not px:
        return False
    m7.click_slot(session_global(), px)
    time.sleep(2.5)
    shot("05_gizmo_open")
    tiles = palette_tiles()
    print(f"{LOG} palette tiles: {tiles[:10]}")
    pos = m7.find_centroid(session_global())
    print(f"{LOG} centroid: {pos}")
    if not pos:
        return False
    sx, sy = m7.client(session_global(), *pos)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    winutil.real_click_screen(sx, sy)
    time.sleep(2.0)
    return True


def click_palette_tile(idx):
    tiles = palette_tiles()
    if len(tiles) <= idx:
        print(f"{LOG} palette has only {len(tiles)} tiles; cannot click #{idx}")
        return False
    x, y, _a = tiles[idx]
    print(f"{LOG} clicking palette tile #{idx} @({x},{y})")
    click_pt(x, y, 1.5)
    return True


def open_preferences():
    click_pt(85, 8, 1.4)
    pop = next((t for t in toplevels() if t[0] == "#32768"), None)
    if not pop:
        return None
    pref = next((r for j, r in ocr(pop[2]) if "preference" in j.lower()), None)
    if not pref:
        return None
    click_pt((pref[0] + pref[2]) // 2, (pref[1] + pref[3]) // 2, 2.5)
    return export_util.wait_toplevel(p3.SESSION.pid, lambda c, t, r: c == "#32770", timeout_s=6.0)


def toggle_pref(dlg):
    lab = next(((t, r) for t, r, _h in all_children(dlg[3]) if PREF_LABEL in t.lower()), None)
    print(f"{LOG} pref label: {lab}")
    if not lab:
        return False
    _t, r = lab
    cy = (r[1] + r[3]) // 2
    for dx in (-17, -27, -37):
        x = r[0] + dx
        b = box_mean((x - 9, cy - 9, x + 9, cy + 9))
        click_pt(x, cy, 1.2)
        a = box_mean((x - 9, cy - 9, x + 9, cy + 9))
        d = 0 if (a is None or b is None) else sum(abs(p - q) for p, q in zip(b, a))
        print(f"{LOG} toggle dx={dx} @({x},{cy}): {b} -> {a} diff={d}")
        if d > 12:
            return True
    return False


def box_mean(rect):
    import numpy as np
    img = screen_bgr()
    x0, y0, x1, y1 = [int(v) for v in rect]
    patch = img[max(0, y0):y1, max(0, x0):x1]
    if not patch.size:
        return None
    return tuple(int(v) for v in np.mean(patch.reshape(-1, 3), axis=0))


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    ap.add_argument("--tile", type=int, default=-1,
                    help="palette tile index to click before dabbing (-1 = skip)")
    ap.add_argument("--slot-abs", type=int, default=2, help="slot to set to Generic ABS")
    args = ap.parse_args()
    session = p3.SESSION = boot_session(args, model=None)
    try:
        print(f"{LOG} empty boot")
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        m7.op_add_primitive(session, "cube")
        time.sleep(1.2)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], s['combo'][0]) for s in slots]}")
        shot("00_boot_cube")

        now = m8.switch_filament_preset(session, slot=args.slot_abs, target_substr="Generic ABS")
        print(f"{LOG} slot{args.slot_abs} -> {now!r}")
        time.sleep(1.5)
        try:
            from m7_common import dismiss_transfer_dialog
            dismiss_transfer_dialog(session)
        except Exception:
            pass
        # 主材 = 立方体默认槽（低温），高温只放在另一条槽里等涂色用
        print(f"{LOG} gate before painting: {gate_state('before_paint')}")

        if args.tile >= 0:
            paint_dab()
            click_palette_tile(args.tile)
        else:
            paint_dab()
        time.sleep(1.0)
        g_painted = gate_state("painted")
        print(f"{LOG} gate after painting: {g_painted}")

        # 偏好 ON -> 能否放行
        dlg = open_preferences()
        print(f"{LOG} preferences: {dlg[1] if dlg else None}")
        flipped = False
        if dlg:
            flipped = toggle_pref(dlg)
            winutil.close_window(dlg[3])
            time.sleep(1.2)
        print(f"{LOG} pref flipped: {flipped}")
        if flipped:
            print(f"{LOG} gate with pref ON: {gate_state('pref_on')}")
            dlg2 = open_preferences()
            if dlg2:
                toggle_pref(dlg2)
                winutil.close_window(dlg2[3])
                time.sleep(1.0)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    except Exception as exc:
        import traceback
        print(f"{LOG} EXC {exc!r}")
        traceback.print_exc()
        shot("99_exc")
        return 1
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
