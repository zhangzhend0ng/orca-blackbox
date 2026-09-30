#!/usr/bin/env python3
# diag_137_probe_process_dialog.py — #137 工艺侧流量面勘察（第三轮 · 定位工艺参数对话框）
#
# 已确认的事实（前两轮 + 本地包定义）:
#   * 耗材侧：Material settings 对话框里有 `[Standard flow] / [High flow]` 子 tab，
#     带标志参数分档（喷嘴温度 210/220、flow_ratio 0.95/0.966），不带标志的同步。
#   * 工艺侧：测试包 `0.20mm Standard @Snapmaker U1 (0.4 nozzle) - STD-TEST` 里声明了
#     `process_flow_support: ['standard','high_flow']`，并且**一大批速度类参数是两档值**
#     （outer_wall_speed 550/500、inner_wall_speed 550/600、top_surface_speed 550/200、
#       travel_speed 550/500、sparse_infill_speed 550/600 …）。
#     → 测试方说的「工艺要切到速度 tab」正是指这些速度参数所在的 Speed 页。
#   * 侧边栏「Process」面板只有 Quality/Strength/Support/Multimaterial/Others 五个 tab，
#     没有 Speed（Advanced 开关也不改变，实测两轮）。所以工艺侧的流量面应该在**工艺参数
#     对话框**里（预设名右侧那三个小图标中的「编辑」）。
#
# 本轮目标：打开工艺参数对话框，回答
#   Q1 它有哪些 tab（有没有 Speed）？
#   Q2 有没有 `[Standard flow] / [High flow]` 子 tab？
#   Q3 切子 tab 后速度参数是否分档（期望 outer_wall_speed 550 → 500 之类）？
#   Q4 关闭对话框用哪个键（Cancel 按钮可能在屏幕外）——顺便验证 Esc 能关。
#
# 只读式勘察：只切 tab、只读值，所有改动都不保存（Esc 退出）；结束关 app。

import argparse
import ctypes
import sys
import time
from ctypes import wintypes as wt
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

LOG = "[p137dlg]"
SESSION = None
user32 = ctypes.WinDLL("user32")


def all_children(parent):
    """[(text, screen-rect, hwnd)] for EVERY child — including the text-less
    icon buttons, which _children_texts() drops (that is what broke the second
    probe: the preset-row icons have no window text)."""
    out = []

    def cb(hwnd, _lp):
        buf = ctypes.create_unicode_buffer(200)
        user32.GetWindowTextW(hwnd, buf, 200)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((buf.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), export_util.WNDENUMPROC(cb), 0)
    return out


def band(x0, x1, y0, y1, wmax=None, hmax=None, parent=None):
    p = parent if parent is not None else SESSION.hwnd
    out = []
    for t, r, h in all_children(p):
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (x0 <= r[0] <= x1 and y0 <= r[1] <= y1):
            continue
        if wmax is not None and w > wmax:
            continue
        if hmax is not None and hh > hmax:
            continue
        out.append((t, r, h))
    return sorted(out, key=lambda c: (c[1][0], c[1][1]))


def dump(tag, parent=None, xmax=100000, ymin=0):
    print(f"{LOG} --- {tag} ---")
    for t, r, h in all_children(parent if parent is not None else SESSION.hwnd):
        if r[0] > xmax or r[1] < ymin:
            continue
        print(f"{LOG}   {t.strip()[:46]!r} rect={r} class={winutil.window_class(h)}")


def click(r):
    x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    c137.click_screen_point((x, y))
    return x, y


def edits(parent):
    out = []
    for _t, r, h in all_children(parent):
        if winutil.window_class(h) == "Edit":
            v = winutil.edit_text(h).strip()
            if v:
                out.append((r, v))
    return out


def moved(a, b, tol=8):
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
        c137.shot("pdlg_00_presets")

        # 工艺预设名右侧的三个图标（无文本按钮）：组合框在同一行，图标在其右侧。
        icons = band(230, 421, 545, 600, wmax=34, hmax=34)
        print(f"{LOG} preset-row controls: {[(t.strip()[:12], r) for t, r, _h in icons]}")
        btns = [(t, r, h) for t, r, h in icons
                if (r[2] - r[0]) >= 8 and (r[3] - r[1]) >= 8
                and not t.strip()]
        print(f"{LOG} text-less icon buttons: {[r for _t, r, _h in btns]}")

        dlg = None
        for idx in ([1, 0, 2] if len(btns) >= 3 else list(range(len(btns)))):
            if idx >= len(btns):
                continue
            t, r, h = btns[idx]
            x, y = click(r)
            time.sleep(1.8)
            c137.shot(f"pdlg_01_icon{idx}")
            top = export_util.wait_toplevel(
                session.pid,
                lambda c, tt, rr: c == "#32770" or "setting" in (tt or "").lower(),
                timeout_s=4.0)
            print(f"{LOG} icon#{idx} @({x},{y}) -> toplevel {top[1] if top else None} {top[2] if top else ''}")
            if top:
                dlg = top
                break
        if not dlg:
            print(f"{LOG} no dialog opened by any icon; sidebar dump follows")
            dump("sidebar", xmax=430, ymin=520)
            return 0

        dump("process dialog", parent=dlg[3])
        print(f"{LOG} dialog tabs: "
              f"{[t.strip() for t, r, _h in all_children(dlg[3]) if t.strip() in ('Quality', 'Strength', 'Speed', 'Support', 'Multimaterial', 'Others')]}")
        print(f"{LOG} dialog flow tabs: "
              f"{[(t.strip(), r) for t, r, _h in all_children(dlg[3]) if 'flow' in t.lower() and t.strip().startswith('[')]}")

        # Speed tab -> 带标志的速度参数
        speed = next(((t.strip(), r, h) for t, r, h in all_children(dlg[3])
                      if t.strip() == "Speed"), None)
        if speed:
            click(speed[1])
            time.sleep(1.2)
            c137.shot("pdlg_02_speed")
            rows = [(t.strip(), r) for t, r, _h in all_children(dlg[3])
                    if t.strip() and r[1] > dlg[2][1]]
            print(f"{LOG} speed rows: {[t for t, _r in rows][:40]}")
        else:
            print(f"{LOG} no Speed tab in the dialog")

        # 子 tab 分档：Standard vs High flow
        flows = [(t.strip(), r) for t, r, _h in all_children(dlg[3])
                 if t.strip().startswith("[") and "flow" in t.lower()]
        if len(flows) >= 2:
            snap_a = edits(dlg[3])
            print(f"{LOG} edits now: {[v for _r, v in snap_a][:40]}")
            std = next((r for t, r in flows if "standard" in t.lower()), None)
            hf = next((r for t, r in flows if "high" in t.lower()), None)
            if std:
                click(std)
                time.sleep(1.0)
                snap_b = edits(dlg[3])
                print(f"{LOG} edits on Standard: {[v for _r, v in snap_b][:40]}")
                print(f"{LOG} moved (initial->standard): {moved(snap_a, snap_b)}")
                c137.shot("pdlg_03_std_flow")
            if hf:
                click(hf)
                time.sleep(1.0)
                snap_c = edits(dlg[3])
                print(f"{LOG} edits on High flow: {[v for _r, v in snap_c][:40]}")
                print(f"{LOG} moved (standard->high): {moved(snap_b, snap_c)}")
                c137.shot("pdlg_04_high_flow")
        else:
            print(f"{LOG} no [Standard flow]/[High flow] sub-tabs in the process dialog")

        # 关闭：先试 Cancel 按钮，再试 Esc（Cancel 可能在屏幕外）
        closed = False
        for t, r, h in all_children(dlg[3]):
            if t.strip().lower() in ("cancel", "取消"):
                print(f"{LOG} cancel rect {r} (screen height 1080 -> "
                      f"{'on' if r[3] <= 1080 else 'OFF'} screen)")
                if r[3] <= 1080 and r[2] <= 1920:
                    click(r)
                    time.sleep(1.2)
                    closed = not export_util.wait_toplevel(
                        session.pid, lambda c, tt, rr: tt == dlg[1], timeout_s=1.0)
                    print(f"{LOG} after Cancel click, closed={closed}")
                break
        if not closed:
            keys = ctypes.WinDLL("user32", use_last_error=True)
            keys.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            keys.keybd_event(0x1B, 0, 2, 0)
            time.sleep(1.2)
            gone = not export_util.wait_toplevel(
                session.pid, lambda c, tt, rr: tt == dlg[1], timeout_s=1.0)
            print(f"{LOG} after Esc, dialog gone={gone}")
            c137.shot("pdlg_05_after_esc")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
