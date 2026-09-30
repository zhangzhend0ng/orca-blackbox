#!/usr/bin/env python3
# diag_137_probe_process_ui.py — #137 工艺侧流量面勘察（第二轮）
#
# 已知（上一轮）：耗材编辑器（Material settings）里 `[Standard flow] / [High flow]`
# 子 tab 已实测到，并且带标志参数确实分档（喷嘴温度 210/220、flow ratio 0.95/0.966）。
#
# 本轮要回答的是**工艺侧**：
#   Q1. 侧边栏「Process」面板的 tab 行（Quality/Strength/Support/Multimaterial/Others）
#       里没有 Speed —— 打开 Advanced 开关后会不会多出来？
#   Q2. 工艺预设名右边的第三个图标（卡片/编辑）打开的是不是工艺参数对话框？
#       该对话框里有没有 Speed tab、有没有 `[Standard flow] / [High flow]` 子 tab？
#   Q3. 侧边栏喷嘴区那个 `Flow | Standard` 组合框（带流量耗材时是可交互的）能否切
#       Standard/High flow？切了以后工艺侧带标志参数（速度类）是否跟着变？
#
# 全部只读式勘察：只点开关/切 tab，不改任何数值；结束前不保存、直接关掉 app。

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
sys.path.insert(0, str(HERE / "tests" / "topcap"))

from harness import export_util, winutil  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
import m8x_137_flow_param_tabs as c137  # noqa: E402

LOG = "[p137ui]"
SESSION = None


def kids(win=None, xmax=100000, ymin=0, ymax=100000):
    w = win if win else SESSION.hwnd
    out = []
    for t, r, h in export_util._children_texts(w):
        ts = t.strip()
        if not ts or r[0] > xmax or r[1] < ymin or r[1] > ymax:
            continue
        out.append((ts, r, h))
    return out


def dump(tag, win=None, xmax=100000, ymin=0):
    print(f"{LOG} --- {tag} ---")
    for ts, r, h in kids(win, xmax, ymin):
        print(f"{LOG}   {ts[:52]!r} rect={r} class={winutil.window_class(h)}")


def tabrow(tag, win=None, xmax=460):
    row = [(ts, r) for ts, r, _h in kids(win, xmax)
           if ts.lower() in ("quality", "strength", "support", "multimaterial",
                             "others", "speed", "速度",
                             "standard", "high", "[standard flow]", "[high flow]")
           or "flow" in ts.lower()]
    print(f"{LOG} {tag}: {row}")
    return row


def click_child(needle, win=None, contains=True, off=(0, 0)):
    w = win if win else SESSION.hwnd
    for ts, r, _h in kids(w):
        if (needle.lower() in ts.lower()) if contains else (ts.lower() == needle.lower()):
            x = (r[0] + r[2]) // 2 + off[0]
            y = (r[1] + r[3]) // 2 + off[1]
            if w == SESSION.hwnd:
                x, y = winutil.client_to_screen(w, x, y)
            c137.click_screen_point((x, y))
            print(f"{LOG} click child {ts!r} @({x},{y})")
            return True
    print(f"{LOG} click child {needle!r}: not found")
    return False


def edits(win):
    out = []
    for _t, r, h in export_util._children_texts(win):
        if winutil.window_class(h) == "Edit":
            v = winutil.edit_text(h).strip()
            if v:
                out.append((r, v))
    return out


def main() -> int:
    global SESSION
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    SESSION = session = boot_session(args, model=None)
    try:
        print(f"{LOG} boot ok (model={args.model!r})")
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        if not m7.op_add_primitive(session, "cube"):
            print(f"{LOG} cube FAILED")
            return 1

        # process preset -> 0.4 喷嘴流量包（沿用用例里已验证的重试配方）
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
        c137.shot("probe_00_presets")

        # --- Q1: Advanced 开关会不会放出 Speed tab -----------------------------
        tabrow("sidebar tabs (Advanced off)")
        if click_child("Advanced", off=(30, 0)):
            time.sleep(1.2)
            c137.shot("probe_01_advanced_on")
            tabrow("sidebar tabs (Advanced on)")
        else:
            print(f"{LOG} Advanced label not found; sidebar dump follows")
            dump("sidebar", xmax=440, ymin=250)

        # --- Q1b: 喷嘴区的 Flow 组合框（带流量耗材时可用）------------------------
        flow_cb = [(ts, r) for ts, r, _h in kids(xmax=440, ymin=250) if ts.lower() == "flow"]
        print(f"{LOG} nozzle Flow label/combo candidates: {flow_cb}")
        v0 = None
        if flow_cb:
            _ts, r = sorted(flow_cb, key=lambda c: c[1][1])[0]
            x, y = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            c137.click_screen_point((x + 60, y))          # the combo sits right of the label
            time.sleep(1.2)
            c137.shot("probe_02_flow_combo")
            dump("flow combo popup", xmax=1000)

        # --- Q2: 工艺预设编辑对话框 --------------------------------------------
        # 预设名右侧三个小图标（磁盘 / 卡片=编辑 / 放大镜），按结构找：组合框行、
        # x>330、宽 10..26 的小控件。
        combo_row = [(ts, r, h) for ts, r, h in kids(xmax=460, ymin=530)
                     if 10 <= (r[2] - r[0]) <= 30 and r[0] > 320]
        print(f"{LOG} combo-row small icons: {[(ts[:14], r) for ts, r, _h in combo_row]}")
        if combo_row:
            _ts, r, _h = sorted(combo_row, key=lambda c: c[1][0])[min(1, len(combo_row) - 1)]
            x, y = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            c137.click_screen_point((x, y))
            time.sleep(2.0)
            c137.shot("probe_03_after_card_icon")
            dlg = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770", timeout_s=6.0)
            print(f"{LOG} dialog after card icon: {dlg[1] if dlg else None} rect={dlg[2] if dlg else None}")
            if dlg:
                dump("process dialog", win=dlg[3])
                tabrow("process dialog tabs", win=dlg[3])
                if dlg[2][3] > 1080:
                    print(f"{LOG} NOTE dialog bottom {dlg[2][3]} is off-screen (<1080 visible)")
                # Speed tab -> 带标志参数（速度类）
                for want in ("speed", "速度"):
                    stage = next(((ts, r) for ts, r, _h in kids(dlg[3])
                                  if ts.lower() == want), None)
                    if stage:
                        x, y = (stage[1][0] + stage[1][2]) // 2, (stage[1][1] + stage[1][3]) // 2
                        c137.click_screen_point((x, y))
                        time.sleep(1.5)
                        c137.shot("probe_04_process_speed")
                        rows = [(ts, r) for ts, r, _h in kids(dlg[3])
                                if 0 < r[1] < 1100]
                        print(f"{LOG} rows after Speed click: {[t for t, _r in rows][:40]}")
                        break
                # 工艺侧 flow 子 tab 是否存在
                flowtabs = [(ts, r) for ts, r, _h in kids(dlg[3]) if "flow" in ts.lower()]
                print(f"{LOG} process-side flow tabs: {flowtabs}")
                if len(flowtabs) >= 2:
                    snap_a = edits(dlg[3])
                    print(f"{LOG} process edits (first tab): {[(t, v) for t, v in snap_a][:30]}")
                    std = next((r for ts, r in flowtabs if "standard" in ts.lower()), None)
                    hf = next((r for ts, r in flowtabs if "high" in ts.lower()), None)
                    if std:
                        c137.click_screen_point(((std[0] + std[2]) // 2, (std[1] + std[3]) // 2))
                        time.sleep(1.0)
                    snap_b = edits(dlg[3])
                    if hf:
                        c137.click_screen_point(((hf[0] + hf[2]) // 2, (hf[1] + hf[3]) // 2))
                        time.sleep(1.0)
                        c137.shot("probe_05_process_high_flow")
                    snap_c = edits(dlg[3])
                    print(f"{LOG} process moved std->high: "
                          f"{[(a, b) for a, b in _moved(snap_b, snap_c)]}")
                    print(f"{LOG} process moved initial->std: "
                          f"{[(a, b) for a, b in _moved(snap_a, snap_b)]}")
                # 关掉对话框（不改值）
                for needle in ("cancel", "取消"):
                    if click_child(needle, win=dlg[3]):
                        break
                time.sleep(1.0)
                print(f"{LOG} dialog still up: "
                      f"{export_util.wait_toplevel(session.pid, lambda c, t, r2: c == '#32770', timeout_s=1.0)}")
        else:
            print(f"{LOG} no combo-row icons found; sidebar dump follows")
            dump("sidebar", xmax=440, ymin=520)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


def _moved(a, b, tol=8):
    out = []
    for ra, va in a:
        cx, cy = (ra[0] + ra[2]) // 2, (ra[1] + ra[3]) // 2
        for rb, vb in b:
            if (abs(((rb[0] + rb[2]) // 2) - cx) <= tol
                    and abs(((rb[1] + rb[3]) // 2) - cy) <= tol):
                if va != vb:
                    out.append((va, vb))
                break
    return out


if __name__ == "__main__":
    raise SystemExit(main())
