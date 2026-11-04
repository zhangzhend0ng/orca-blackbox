#!/usr/bin/env python3
# diag_125_probe_paint2.py — #125 机制探针（第三版：夹具 + 先涂色后切片 + 页面状态守卫）
#
# 前两版的教训:
#   * 空 boot 的预置列表里没有 `Generic ABS`（播种的 user 预置是流量测试包）→ 切片门禁
#     这条链要用 **MIXED_3MF 夹具**（m8c 用它切 ABS 成功）；
#   * `slice_rejected` 会真的点一次 Slice：**切成功后应用会跳到 Preview 页**，此后
#     工具条/gizmo 都读不到（"rotate slot not found"），涂色必然失败，而且下一次
#     "rejected=True" 只是"在 Preview 页点 Slice 没反应"的假阳性 → 每次切片后必须
#     **回到 Prepare 页**再继续；
#   * 因此顺序必须是：**先涂色，再验门禁**。
#
# 本轮顺序:
#   1 夹具启动 → 清场 → 加 cube A，主材 = Silk 槽（低温）
#   2 slot1 → 'Generic ABS'（高温，对象不用它，留给涂色）
#   3 涂色：select model → Color painting gizmo → （必要时点调色板色块）→ 在模型上点一下
#   4 门禁：Prepare 页上 Slice 是否被吞 / 横幅 OCR / 截图
#   5 Preferences → Allow high/low temperature filament mixing 打开 → 再验一次切片
#   6 还原偏好开关
#
# 可逆：只切槽/涂色/开关，收尾还原；不保存工程。

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
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from diag_125_probe_aux3 import all_children, band, click_pt, ocr, toplevels  # noqa: E402
import diag_125_probe_aux3 as p3  # noqa: E402

LOG = "[p125q]"
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


def page():
    """'prepare' / 'preview' / '?' by the page-tab row."""
    for t, r, _c, _h in band(0, 900, 30, 70):
        if t in ("Prepare", "Preview", "Device", "Project") and (r[2] - r[0]) > 40:
            return t.lower()
    return "?"


def goto_prepare():
    for t, r, _c, _h in band(0, 900, 30, 70):
        if t == "Prepare" and (r[2] - r[0]) > 40:
            click_pt((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.5)
            return page()
    return page()


def dialogs_up():
    return [(t[1], t[2]) for t in toplevels() if t[0] == "#32770"]


def gate_state(tag):
    from m8c_temp_mix_gate import slice_rejected
    if page() != "prepare":
        print(f"{LOG} [{tag}] not on Prepare ({page()}) — going back")
        goto_prepare()
        time.sleep(1.0)
    ups = dialogs_up()
    rejected = slice_rejected(p3.SESSION)
    time.sleep(0.5)
    ocr_hit = False
    try:
        from harness import mix_dialog_util as mdu
        words = mdu.ocr_words_img(screen_bgr(), scale=2)
        text = " ".join(w for w, *_ in words).lower()
        ocr_hit = ("high and low" in text) or ("temperature" in text and "detected" in text)
    except Exception as exc:
        print(f"{LOG} banner OCR failed: {exc}")
    print(f"{LOG} [{tag}] page={page()} rejected={rejected} banner_ocr={ocr_hit} "
          f"dialogs={dialogs_up()}")
    shot(f"gate_{tag.replace(' ', '_')}")
    return rejected, ocr_hit


def palette_tiles():
    import cv2
    import numpy as np
    from harness.anchors import (PAINT_PAL_LEFT_OFF as PAL_LEFT_OFF,
                                 PAINT_PAL_Y0 as PAL_Y0, PAINT_PAL_Y1 as PAL_Y1)
    img = screen_bgr()
    sub = img[PAL_Y0:PAL_Y1, 640 + PAL_LEFT_OFF:1900]
    if not sub.size:
        return []
    s = sub.astype(int)
    mask = ((s.max(axis=2) - s.min(axis=2)) > 50).astype(np.uint8) * 255
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


def paint(session, tile=-1):
    if not m7.select_model(session):
        print(f"{LOG} model not selectable")
        return False
    px, ptip = m7.find_slot(session, lambda t: "color painting" in t)
    print(f"{LOG} color-painting slot: {px} {ptip!r}")
    if not px:
        return False
    m7.click_slot(session, px)
    time.sleep(2.5)
    shot("05_gizmo")
    tiles = palette_tiles()
    print(f"{LOG} palette tiles: {tiles[:8]}")
    if tile >= 0 and len(tiles) > tile:
        x, y, _a = tiles[tile]
        print(f"{LOG} clicking palette tile #{tile} @({x},{y})")
        click_pt(x, y, 1.5)
        shot(f"06_tile{tile}")
    pos = m7.find_centroid(session)
    print(f"{LOG} centroid: {pos}")
    if not pos:
        return False
    sx, sy = m7.client(session, *pos)
    click_pt(sx, sy, 2.0)
    shot("07_painted")
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


def toggle_pref(dlg, tag):
    lab = next(((t, r) for t, r, _h in all_children(dlg[3]) if PREF_LABEL in t.lower()), None)
    print(f"{LOG} [{tag}] pref label: {lab}")
    if not lab:
        return False
    _t, r = lab
    crop = (r[0] - 60, r[1] - 10, r[2] + 30, r[3] + 10)
    shot(f"pref_row_{tag}", crop)
    cy = (r[1] + r[3]) // 2
    for dx in (-24, -17, -31):
        x = r[0] + dx
        b = box_mean((x - 10, cy - 8, x + 10, cy + 8))
        click_pt(x, cy, 1.2)
        a = box_mean((x - 10, cy - 8, x + 10, cy + 8))
        d = 0 if (a is None or b is None) else sum(abs(p - q) for p, q in zip(b, a))
        print(f"{LOG} [{tag}] toggle dx={dx} @({x},{cy}): {b} -> {a} diff={d}")
        if d > 20:
            shot(f"pref_after_{tag}")
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


def add_cube_and_assign(session, slot_substr, results, key):
    """m8c 的配方：加 cube 并把它的耗材丝换成匹配 slot_substr 的那行。"""
    m7.op_add_primitive(session, "cube")
    time.sleep(0.8)
    if slot_substr and not m7.select_model(session):
        results[key] = "FAIL (not selectable)"
        return False
    if slot_substr:
        menu = m7.open_context_menu(session, where="model")
        if not menu:
            results[key] = "FAIL (no menu)"
            return False
        hwnd, hmenu = menu
        got = m7.click_menu_row(session, hwnd, hmenu, "change filament", nested=True)
        if not got:
            m7.dismiss_menus(session)
            results[key] = "FAIL (no change-filament)"
            return False
        _i, (shwnd, shmenu) = got
        rows = m7.list_menu(shmenu)
        print(f"{LOG} filament rows: {[l for _i, l in rows]}")
        m7.click_menu_row(session, shwnd, shmenu, slot_substr)
        time.sleep(1.5)
        m7.dismiss_menus(session)
    results[key] = "PASS"
    return True


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    ap.add_argument("--tile", type=int, default=-1, help="palette tile index to click first")
    args = ap.parse_args()
    session = p3.SESSION = boot_session(args, model=args.model)
    results = {}
    try:
        ok, _frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives: {ok} page={page()}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m7.step_delete_all(session, results)
        add_cube_and_assign(session, "Silk", results, "cube on PLA slot")
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], s['combo'][0]) for s in slots]}")
        shot("00_before")

        now = m8.switch_filament_preset(session, slot=1, target_substr="Generic ABS")
        print(f"{LOG} slot1 -> {now!r}")
        time.sleep(1.5)
        try:
            from m7_common import dismiss_transfer_dialog
            dismiss_transfer_dialog(session)
        except Exception:
            pass
        shot("01_slot1_abs")
        print(f"{LOG} page after slot switch: {page()}")

        # --- 涂色（先涂后切）----------------------------------------------------
        painted = paint(session, tile=args.tile)
        print(f"{LOG} painted: {painted}")
        # 关掉 gizmo，回到普通视图
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(1.2)
        shot("08_after_paint")

        # --- 门禁 ---------------------------------------------------------------
        g1 = gate_state("painted")
        dlg = open_preferences()
        print(f"{LOG} preferences: {dlg[1] if dlg else None}")
        flipped = False
        if dlg:
            flipped = toggle_pref(dlg, "on")
            winutil.close_window(dlg[3])
            time.sleep(1.2)
        print(f"{LOG} pref flipped: {flipped}")
        g2 = gate_state("pref_on") if flipped else (None, None)
        if flipped:
            dlg2 = open_preferences()
            if dlg2:
                toggle_pref(dlg2, "off")
                winutil.close_window(dlg2[3])
                time.sleep(1.0)
        print(f"{LOG} summary painted={g1} pref_on={g2}")
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
