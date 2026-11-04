#!/usr/bin/env python3
# diag_125_probe_aux4.py — #125 面定位第四轮：标题栏菜单（汉堡）→ Preferences；辅材下拉
#
# 第三轮的收获:
#   * 顶上那行**不是菜单栏**：y 0..31 是应用自绘的标题栏，里面有 [File▾] 按钮、
#     一个汉堡图标（预设/菜单入口）、保存/撤销/重做、[Calibration]；
#     "File" 文字在 (9..44, 3..13)，汉堡图标约 (79..91, 3..13) —— 之前点 y=15 全落空；
#   * 辅材行 `Filament for Supports` 只在 **Support 页**渲染时才存在（要先点 Support tab）。
#
# 本轮目标:
#   Q1 点汉堡/File 打开菜单，OCR 出行，找 Preferences 并打开，dump 对话框控件树
#      （找“混用/温度/allow mixing”开关）。
#   Q2 Support 页那把 `Default` 组合框（辅材值控件）点开后的选项。
#
# 只读勘察：只点开看，不改值不保存；结束关 app。

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

LOG = "[p125d]"
user32 = winutil.user32


def dump_popup(tag, pop):
    print(f"{LOG} {tag}: popup {pop[0]!r} {pop[2]}")
    rows = ocr(pop[2])
    print(f"{LOG} {tag}: ocr rows: {[(j[:30], r) for j, r in rows]}")
    kids = [(t.strip(), r, winutil.window_class(h)) for t, r, h in all_children(pop[3]) if t.strip()]
    print(f"{LOG} {tag}: child controls: {[(t[:24], r, c) for t, r, c in kids][:20]}")
    return rows, kids


def open_title_item(x, y, tag):
    before = {t[3] for t in toplevels()}
    click_pt(x, y, 1.4)
    new = [t for t in toplevels() if t[3] not in before]
    print(f"{LOG} {tag}: new toplevels {[(t[0], t[1], t[2]) for t in new]}")
    if not new:
        return None, []
    return new[0], dump_popup(tag, new[0])


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
        m8.wait_slots(session)
        print(f"{LOG} title-bar controls: "
              f"{[(t[:16], r, c) for t, r, c, _h in band(0, 700, 0, 34)]}")

        # --- Q1: 汉堡 / File 菜单 -------------------------------------------------
        for (x, y, tag) in ((85, 8, "hamburger"), (26, 8, "File")):
            pop, res = open_title_item(x, y, tag)
            if not pop:
                continue
            rows = res[0] if res else []
            pref = next((r for j, r in rows if "preference" in j.lower() or "偏好" in j), None)
            print(f"{LOG} {tag}: preferences row = {pref}")
            if pref:
                click_pt((pref[0] + pref[2]) // 2, (pref[1] + pref[3]) // 2, 2.5)
                dlg = export_util.wait_toplevel(session.pid,
                                                lambda c, t, r: c == "#32770", timeout_s=5.0)
                print(f"{LOG} preferences window: {dlg[1] if dlg else None} {dlg[2] if dlg else ''}")
                if dlg:
                    kids = [(t.strip(), r, winutil.window_class(h))
                            for t, r, h in all_children(dlg[3]) if t.strip()]
                    print(f"{LOG} preferences children ({len(kids)}):")
                    for t, r, c in kids:
                        print(f"{LOG}   {t[:64]!r} @{r} cls={c}")
                    print(f"{LOG} preferences OCR: {[(j[:40], r[1]) for j, r in ocr(dlg[2])][:30]}")
                    winutil.close_window(dlg[3])
                    time.sleep(1.0)
                break
            usr32 = user32
            usr32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            usr32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.6)

        # --- Q2: 辅材下拉 ---------------------------------------------------------
        sup = next(((t, r) for t, r, _c, _h in band(0, 430, 560, 780) if t == "Support"), None)
        print(f"{LOG} Support tab: {sup}")
        if sup:
            click_pt((sup[1][0] + sup[1][2]) // 2, (sup[1][1] + sup[1][3]) // 2, 1.5)
            time.sleep(1.2)
        lab = next(((t, r) for t, r, _c, _h in band(0, 430, 560, 1100)
                    if "filament for supports" in t.lower()), None)
        print(f"{LOG} aux label: {lab}")
        if lab:
            rows = band(0, 430, lab[1][3] - 4, lab[1][3] + 80)
            print(f"{LOG} aux row children: {[(t[:22], r, c) for t, r, c, _h in rows]}")
            combo = next(((t, r, c) for t, r, c, _h in rows
                          if c == "wxWindowNR" and (r[2] - r[0]) > 60 and t), None)
            print(f"{LOG} aux combo: {combo}")
            if combo:
                before = {t[3] for t in toplevels()}
                click_pt((combo[1][0] + combo[1][2]) // 2, (combo[1][1] + combo[1][3]) // 2, 1.5)
                new = [t for t in toplevels() if t[3] not in before]
                print(f"{LOG} aux dropdown new toplevels: {[(t[0], t[1], t[2]) for t in new]}")
                for t in new:
                    dump_popup("aux dropdown", t)
                user32.keybd_event(0x1B, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(0x1B, 0, 2, 0)
                time.sleep(0.6)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
