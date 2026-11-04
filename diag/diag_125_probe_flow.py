#!/usr/bin/env python3
# diag_125_probe_flow.py — #125 机制探针：辅材冲突 → 切片门禁 → 「允许高低温混用」偏好
#
# 已定位的坐标/文案（前三轮）:
#   * 辅材 = 工艺 Support 页的 `Filament for Supports`（值控件是个组合框，默认显示 `Default`）；
#     Multimaterial 页还有 `Filament for Features`；这两行**只在对应 tab 被渲染时存在**
#     （要先用真实尺寸过滤，别点到零尺寸幽灵）。
#   * 偏好 = 标题栏 [File]/汉堡（约 (85,8)）→ 菜单里 `Preferences Ctrl+P` →
#     对话框 General 页里的 **`Allow high/low temperature filament mixing`**
#     （标签矩形 (717,461,986,477)，开关是它左边那个自绘控件）。
#
# 本轮要回答:
#   Q1 把工艺全局辅材设成**高温**槽（Generic ABS），主材保持低温 → 切片按钮是否置灰 / 横幅？
#      （即门禁认不认“辅材”这条链路）
#   Q2 打开 `Allow high/low temperature filament mixing` 后，切片是否被放行？
#   Q3 开关控件的确切点击点（标签左侧哪一列），以及关掉后门禁是否恢复。
#
# 只读勘察 + 可逆改动：只切辅材/开关，收尾全部还原；不保存工程。

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

LOG = "[p125f]"
user32 = winutil.user32
PREF_LABEL = "allow high/low temperature filament mixing"


def screen_bgr():
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)


def box_mean(rect):
    import numpy as np
    img = screen_bgr()
    x0, y0, x1, y1 = [int(v) for v in rect]
    patch = img[max(0, y0):y1, max(0, x0):x1]
    if not patch.size:
        return None
    return tuple(int(v) for v in np.mean(patch.reshape(-1, 3), axis=0))


def open_hamburger_menu():
    click_pt(85, 8, 1.4)
    return next((t for t in toplevels() if t[0] == "#32768"), None)


def open_preferences():
    pop = open_hamburger_menu()
    if not pop:
        return None
    rows = ocr(pop[2])
    print(f"{LOG} hamburger rows: {[(j[:28], r) for j, r in rows]}")
    pref = next((r for j, r in rows if "preference" in j.lower()), None)
    if not pref:
        return None
    click_pt((pref[0] + pref[2]) // 2, (pref[1] + pref[3]) // 2, 2.5)
    return export_util.wait_toplevel(SESSION.pid, lambda c, t, r: c == "#32770", timeout_s=5.0)


def click_real_size(text, ymin=560, ymax=780, xmax=430):
    for t, r, _c, _h in band(0, xmax, ymin, ymax):
        if t == text and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 10:
            click_pt((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.5)
            return r
    return None


def set_support_filament(value_text):
    """Support tab -> `Filament for Supports` combo -> pick the row `value_text`."""
    tab = click_real_size("Support", ymax=780)
    print(f"{LOG} Support tab rect: {tab}")
    time.sleep(1.2)
    lab = next(((t, r) for t, r, _c, _h in band(0, 430, 560, 1100)
                if "filament for supports" in t.lower()), None)
    print(f"{LOG} aux label: {lab}")
    if not lab:
        return None
    rows = band(0, 430, lab[1][3] - 4, lab[1][3] + 90)
    combo = next(((t, r) for t, r, c, _h in rows
                  if c == "wxWindowNR" and (r[2] - r[0]) > 60 and t), None)
    print(f"{LOG} aux combo: {combo}")
    if not combo:
        return None
    before = {t[3] for t in toplevels()}
    click_pt((combo[1][0] + combo[1][2]) // 2, (combo[1][1] + combo[1][3]) // 2, 1.5)
    new = [t for t in toplevels() if t[3] not in before]
    print(f"{LOG} dropdown toplevels: {[(t[0], t[1], t[2]) for t in new]}")
    for t in new:
        rows2 = ocr(t[2])
        print(f"{LOG}   rows: {[(j[:24], r) for j, r in rows2]}")
        hit = next((r for j, r in rows2
                    if j.strip().lower().startswith(value_text.lower())), None)
        if hit:
            click_pt((hit[0] + hit[2]) // 2, (hit[1] + hit[3]) // 2, 1.8)
            print(f"{LOG} picked {value_text!r} from the aux dropdown")
            return hit
        kids = [(x.strip(), r) for x, r, _h in all_children(t[3]) if x.strip()]
        print(f"{LOG}   kids: {kids[:14]}")
    return None


def toggle_pref(dlg, want_on=None):
    """Find the switch for PREF_LABEL and flip it, verifying by pixels."""
    lab = next(((t, r) for t, r, _h in all_children(dlg[3]) if PREF_LABEL in t.lower()), None)
    print(f"{LOG} pref label: {lab}")
    if not lab:
        return False
    _t, r = lab
    cy = (r[1] + r[3]) // 2
    for dx in (-17, -27, -37, r[2] - r[0] + 17):
        x = r[0] + dx
        probe = (x - 9, cy - 9, x + 9, cy + 9)
        before = box_mean(probe)
        click_pt(x, cy, 1.2)
        after = box_mean(probe)
        print(f"{LOG} toggle candidate dx={dx} @({x},{cy}): {before} -> {after}")
        if before != after and (before is not None and after is not None):
            diff = sum(abs(a - b) for a, b in zip(before, after))
            if diff > 12:
                print(f"{LOG} toggle flipped at dx={dx} (diff={diff})")
                return True
    return False


def gate_state(session, tag):
    from m8c_temp_mix_gate import slice_rejected
    rejected = slice_rejected(session)
    img = None
    ocr_hit = False
    try:
        from harness import mix_dialog_util as mdu
        img = screen_bgr()
        words = mdu.ocr_words_img(img, scale=2)
        text = " ".join(w for w, *_ in words).lower()
        ocr_hit = ("high and low" in text) or ("temperature" in text and "detected" in text)
    except Exception as exc:
        print(f"{LOG} banner OCR failed: {exc}")
    print(f"{LOG} [{tag}] slice rejected={rejected} banner_ocr={ocr_hit}")
    return rejected, ocr_hit


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = p3.SESSION = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives: {ok}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m7.step_delete_all(session, {})
        m7.op_add_primitive(session, "cube")
        time.sleep(1.2)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], s['combo'][0]) for s in slots]}")

        # 主材 = 默认槽（低温）；把一个**没被用到**的槽切成高温 Generic ABS 当"辅材"
        now = m8.switch_filament_preset(session, slot=2, target_substr="Generic ABS")
        print(f"{LOG} slot2 preset -> {now!r}")
        time.sleep(1.5)
        try:
            from m7_common import dismiss_transfer_dialog
            dismiss_transfer_dialog(session)
        except Exception:
            pass

        base = gate_state(session, "no aux conflict (baseline)")
        # Q1: 全局辅材 -> 槽 2（ABS，高温）
        set_support_filament("2")
        time.sleep(1.5)
        g1 = gate_state(session, "aux=slot2 ABS, pref OFF")

        # Q2: 打开偏好
        dlg = open_preferences()
        print(f"{LOG} preferences: {dlg[1] if dlg else None}")
        flipped = False
        if dlg:
            flipped = toggle_pref(dlg)
            winutil.close_window(dlg[3])
            time.sleep(1.2)
        g2 = gate_state(session, "aux=slot2 ABS, pref ON") if flipped else (None, None)

        # Q3: 再点一次还原
        if flipped:
            dlg2 = open_preferences()
            if dlg2:
                toggle_pref(dlg2)
                winutil.close_window(dlg2[3])
                time.sleep(1.0)
            g3 = gate_state(session, "pref restored OFF")
        print(f"{LOG} summary: base={base} aux_conflict={g1} pref_on={g2}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
