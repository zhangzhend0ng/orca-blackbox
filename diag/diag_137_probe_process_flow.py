#!/usr/bin/env python3
# diag_137_probe_process_flow.py — #137 工艺侧流量面勘察（第四轮 · 喷嘴 Flow 组合框 + 工艺对话框入口）
#
# 第三轮的结论：工艺预设名右侧三个图标 = [保存][删除][搜索]（点中间那个弹出的是
# "Delete Preset" 确认框），所以工艺参数对话框不是从那里进。
#
# 前两轮还实测到：侧边栏喷嘴区的 `Diameter | Flow [Standard]` 组合框**能展开**
# Standard / High Flow 两个选项（probe_02 截图）。本轮把这条路走完，回答：
#   Q1 选 High Flow 之后，侧边栏**工艺参数**里那一批带标志的速度参数是否换档？
#      （包里定义：outer_wall_speed 550/500、top_surface_speed 550/200 …）
#   Q2 侧边栏里那两个零尺寸的 `[Standard flow] / [High flow]` 子 tab 会不会变成实体
#      （有没有可点的流量 tab）？
#   Q3 工艺参数对话框到底怎么进：右键预设名 / 双击预设名，哪个能出对话框？
#
# 只读勘察：只在 Standard/High flow 之间切（最后切回 Standard），不保存任何改动。

import argparse
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))
sys.path.insert(0, str(HERE / "tests" / "topcap"))

from harness import export_util, winutil  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
import m8x_137_flow_param_tabs as c137  # noqa: E402
from diag_137_probe_process_dialog import all_children  # noqa: E402

LOG = "[p137flw]"
SESSION = None
SIDE_X, SIDE_Y0 = 430, 240


def side_children():
    return sorted([(t.strip(), r, h) for t, r, h in all_children(SESSION.hwnd)
                   if r[0] < SIDE_X and r[1] >= SIDE_Y0],
                  key=lambda c: (c[1][1], c[1][0]))


def dump_side(tag):
    print(f"{LOG} --- sidebar {tag} ---")
    for t, r, h in side_children():
        zero = "" if (r[2] - r[0]) and (r[3] - r[1]) else " ZERO-SIZE"
        print(f"{LOG}   {t[:44]!r} rect={r} class={winutil.window_class(h)}{zero}")


def side_values():
    """(rect, value) for every readable control in the sidebar band — Edit
    (WM_GETTEXT) and also plain text children (checkbox/spin display text)."""
    out = []
    for t, r, h in side_children():
        cls = winutil.window_class(h)
        if cls == "Edit":
            v = winutil.edit_text(h).strip()
        else:
            v = t.strip()
        if v:
            out.append(((r[0] // 4, r[1] // 4), v, r))
    return out


def moved(a, b):
    am = {k: (v, r) for k, v, r in a}
    out = []
    for k, v, r in b:
        if k in am and am[k][0] != v:
            out.append((am[k][0], v, r))
    return out


def click(r):
    c137.click_screen_point(((r[0] + r[2]) // 2, (r[1] + r[3]) // 2))


def set_flow(want):
    """Open the nozzle-row Flow combo and pick `want` ('Standard'/'High Flow')."""
    lab = next(((t, r, h) for t, r, h in side_children()
                if t == "Flow" and 270 <= r[1] <= 330), None)
    if not lab:
        print(f"{LOG} nozzle Flow label not found")
        return None
    _t, r, _h = lab
    click((r[0] + 62, r[1] + 9, r[0] + 62, r[1] + 9))     # the combo sits right of the label
    time.sleep(1.2)
    c137.shot(f"pflw_flow_combo_{want.replace(' ', '')}")
    pop = export_util.wait_popup(SESSION.pid, timeout_s=3.0)
    if not pop:
        print(f"{LOG} flow combo popup did not open")
        return None
    rows = [(t.strip(), r, h) for t, r, h in all_children(pop[3]) if t.strip()]
    print(f"{LOG} flow popup rows: {[(t, r) for t, r, _h in rows]}")
    hit = next((x for x in rows if x[0].lower() == want.lower()), None)
    if not hit:
        winutil.close_window(pop[3])
        return None
    click(hit[1])
    time.sleep(2.0)
    return hit[0]


def main() -> int:
    global SESSION
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    SESSION = session = boot_session(args, model=None)
    try:
        print(f"{LOG} boot ok")
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        if not m7.op_add_primitive(session, "cube"):
            print(f"{LOG} cube FAILED")
            return 1
        from m7_common import dismiss_transfer_dialog
        from harness import process_panel as pp
        for attempt in range(4):
            pp.switch_process_preset(session, c137.PROC_STD)
            dismiss_transfer_dialog(session)
            _r, _c, now = pp.find_process_preset_combo(session)
            print(f"{LOG} process preset try {attempt + 1}: {now!r}")
            if "STD-TEST" in (now or ""):
                break
        fil = m8.switch_filament_preset(session, slot=2, target_substr="- ST")
        dismiss_transfer_dialog(session)
        print(f"{LOG} filament preset: {fil!r}")
        time.sleep(1.5)

        # --- 基准态（Flow=Standard）--------------------------------------------
        dump_side("Flow=Standard")
        base = side_values()
        print(f"{LOG} sidebar values ({len(base)}): {[v for _k, v, _r in base][:44]}")

        # --- Q1/Q2: 切 High Flow ------------------------------------------------
        got = set_flow("High Flow")
        print(f"{LOG} flow combo -> {got!r}")
        time.sleep(1.5)
        c137.shot("pflw_after_high_flow")
        dump_side("Flow=High Flow")
        hi = side_values()
        print(f"{LOG} sidebar values ({len(hi)}): {[v for _k, v, _r in hi][:44]}")
        print(f"{LOG} sidebar moved Standard->High flow: {moved(base, hi)}")

        # --- 恢复 Flow=Standard --------------------------------------------------
        back = set_flow("Standard")
        print(f"{LOG} flow combo -> {back!r}")
        time.sleep(1.0)
        restored = side_values()
        print(f"{LOG} moved High flow->Standard: {moved(hi, restored)}")

        # --- Q3: 工艺对话框入口：右键 / 双击预设名 --------------------------------
        name = next(((t, r, h) for t, r, h in side_children()
                     if "STD-TEST" in t and r[1] < 600), None)
        print(f"{LOG} preset name child: {name[:2] if name else None}")
        if name:
            r = name[1]
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            winutil.real_right_click_screen(cx, cy)
            time.sleep(1.2)
            c137.shot("pflw_right_click_name")
            menu = export_util.wait_toplevel(session.pid,
                                             lambda c, t, r2: c == "#32768", timeout_s=3.0)
            if menu:
                items = [(t.strip(), r2) for t, r2, _h in all_children(menu[3]) if t.strip()]
                print(f"{LOG} context menu items: {items}")
                winutil.close_window(menu[3])
            else:
                print(f"{LOG} no context menu on right-click")
            # 双击预设名
            click(r)
            time.sleep(0.15)
            click(r)
            time.sleep(2.0)
            c137.shot("pflw_dbl_click_name")
            top = export_util.wait_toplevel(
                session.pid,
                lambda c, t, r2: c == "#32770" or ("setting" in (t or "").lower()),
                timeout_s=4.0)
            print(f"{LOG} after double click -> {top[1] if top else None} {top[2] if top else ''}")
            if top:
                dump_side("dialog children")
                for t, r2, h in all_children(top[3]):
                    print(f"{LOG}   dlg {t.strip()[:44]!r} rect={r2} class={winutil.window_class(h)}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
