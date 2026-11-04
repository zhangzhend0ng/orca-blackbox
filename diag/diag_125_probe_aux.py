#!/usr/bin/env python3
# diag_125_probe_aux.py — 飞书基线 #125 面定位（工艺全局/对象辅材 + 「允许混用」偏好）
#
# 行文（09-29 读飞书原表）:
#   标题  工艺全局辅材冲突，打开偏好后，可以正常切片并打印
#   路径  Orca > 准备页 > 耗材列/切片按钮
#   步骤  1 工艺全局辅材与主材冲突，工艺对象辅材与主材冲突
#         2 不打开偏好，发起切片
#         3 工艺全局辅材与主材不冲突，工艺对象辅材与主材冲突
#         4 打开偏好，开始切片
#   预期  1 按钮置灰，警告  2 无法切片  4 打开后按钮高亮，切片正常
#
# 同族的 m8c（#111/#112 高低温混用门）已实现：切片按钮置灰 + 横幅
# "Detected both high and low temperature materials..."，并注明「允许混用」偏好开关
# 存在于 Preferences（Plater.cpp:334 文案提及）。#125 是同一道门的**辅材**分支，
# 所以本轮要先把三件事的黑盒位置找出来：
#   Q1 「辅材」在工艺面板里叫什么（support filament / other filament / 辅助耗材…），
#      值控件是不是耗材槽下拉？
#   Q2 工艺面的 Global / Objects 两个作用域怎么切，对象级覆盖怎么开（对象辅材）；
#   Q3 Preferences 对话框怎么进（菜单栏哪一项 / Ctrl+P），里面跟"混用"有关的开关叫什么。
#
# 只读勘察：只点开菜单/面板、不改值不保存；结束关 app。

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

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[p125]"
SESSION = None
WORDS = ("filament", "aux", "support", "other", "flush", "wipe", "耗材", "辅")


def kids(parent=None, xmax=100000, ymin=0, ymax=100000):
    p = parent if parent is not None else SESSION.hwnd
    out = []
    for t, r, h in export_util._children_texts(p):
        ts = t.strip()
        if not ts or r[0] > xmax or not (ymin <= r[1] <= ymax):
            continue
        out.append((ts, r, winutil.window_class(h), h))
    return sorted(out, key=lambda c: (c[1][1], c[1][0]))


def dump_matching(tag, xmax=100000, ymin=0, words=WORDS, parent=None):
    print(f"{LOG} --- {tag} ---")
    hits = [(t, r, c) for t, r, c, _h in kids(parent, xmax, ymin) if any(w in t.lower() for w in words)]
    for t, r, c in hits:
        print(f"{LOG}   {t[:52]!r} rect={r} cls={c}")
    print(f"{LOG}   ({len(hits)} hit / {len(kids(parent, xmax, ymin))} children)")
    return hits


def click(r):
    x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(1.2)


def menus(tag, xs=(20, 55, 95, 145, 200, 260, 320)):
    """Click along the menu-bar band and dump whatever popup menu opens; if a row
    looks like Preferences, open it and dump the dialog."""
    print(f"{LOG} --- menu bar {tag} ---")
    for x in xs:
        winutil.user32.SetCursorPos(x, 15)
        time.sleep(0.2)
        winutil.real_click_screen(x, 15)
        time.sleep(1.0)
        top = export_util.wait_toplevel(SESSION.pid, lambda c, t, r: c == "#32768", timeout_s=1.5)
        if not top:
            print(f"{LOG}   x={x}: no menu")
            continue
        items = [lbl for _i, lbl in m7.list_menu(top[3])]
        print(f"{LOG}   x={x} -> {items}")
        pref = next((lbl for lbl in items
                     if "preference" in lbl.lower() or "设置" in lbl), None)
        if pref:
            got = click_menu_row_safe(top[3], pref)
            print(f"{LOG}   opened {pref!r}: {got}")
            time.sleep(1.5)
            dlg = export_util.wait_toplevel(SESSION.pid, lambda c, t, r: c == "#32770", timeout_s=4.0)
            print(f"{LOG}   preferences window: {dlg[1] if dlg else None}")
            if dlg:
                dump_matching("preferences dialog", parent=dlg[3],
                              words=("mix", "混", "allow", "允许", "temp", "温",
                                     "filament", "耗材"))
                print(f"{LOG}   preference tabs: "
                      f"{[t for t, _r, _c, _h in kids(dlg[3]) if (t[0].isupper() and len(t) < 26)]}")
                winutil.close_window(dlg[3])
                time.sleep(0.8)
            return True
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.4)
    # Ctrl+P as the keyboard path
    print(f"{LOG} trying Ctrl+P")
    u = winutil.user32
    u.keybd_event(0x11, 0, 0, 0)          # VK_CONTROL
    u.keybd_event(0x50, 0, 0, 0)          # 'P'
    time.sleep(0.08)
    u.keybd_event(0x50, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(1.8)
    top = export_util.wait_toplevel(SESSION.pid, lambda c, t, r: c == "#32770", timeout_s=3.0)
    print(f"{LOG} Ctrl+P -> {top[1] if top else None}")
    if top:
        dump_matching("Ctrl+P dialog", parent=top[3],
                      words=("mix", "混", "allow", "允许", "temp", "温", "filament", "耗材"))
        winutil.close_window(top[3])
        return True
    return False


def click_menu_row_safe(menu_hwnd, label):
    got = m7.click_menu_row(SESSION, menu_hwnd, menu_hwnd, label)
    return got is not None


def main() -> int:
    global SESSION
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    SESSION = session = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives: {ok}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        try:
            from m8c_temp_mix_gate import slice_rejected   # noqa: F401
            print(f"{LOG} m8c helpers importable")
        except Exception as exc:
            print(f"{LOG} m8c import: {exc}")

        # 工艺面板全量树（含隐藏页）里找「辅材」相关的行
        dump_matching("sidebar: filament-ish rows (all pages)", xmax=430, ymin=560)
        # 页签与作用域
        tabs = [(t, r) for t, r, c, _h in kids(xmax=430)
                if t in ("Quality", "Strength", "Speed", "Support", "Multimaterial",
                         "Others", "Global", "Objects", "Advanced")
                and (r[2] - r[0]) > 8 and (r[3] - r[1]) > 8]
        print(f"{LOG} process tabs/scopes: {tabs}")

        # 逐个 tab 点开，报告该页出现的 filament 行
        for name in ("Support", "Others", "Multimaterial"):
            hit = next((r for t, r in tabs if t == name), None)
            if not hit:
                continue
            click(hit)
            time.sleep(1.2)
            dump_matching(f"process tab {name}", xmax=430, ymin=560,
                          words=("filament", "aux", "support", "other"))

        # 作用域 Objects
        obj = next((r for t, r in tabs if t == "Objects"), None)
        if obj:
            click(obj)
            time.sleep(1.5)
            dump_matching("process scope Objects", xmax=430, ymin=560)
            glob = next((r for t, r in tabs if t == "Global"), None)
            if glob:
                click(glob)
                time.sleep(1.2)

        # Preferences 入口
        found = menus("first pass")
        print(f"{LOG} preferences found: {found}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
