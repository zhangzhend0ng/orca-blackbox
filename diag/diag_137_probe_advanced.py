#!/usr/bin/env python3
# diag_137_probe_advanced.py — #137 工艺侧流量面勘察（第六轮 · Advanced 开关 → Speed tab）
#
# 前几轮的实测：
#   * 侧边栏 Process 面板的 tab 行只有 Quality/Strength/Support/Multimaterial/Others，
#     没有 Speed —— 但第五轮把 Advanced 开关的点击位置量错了（开关实体在 x 317..340，
#     我点的是 311，差 6px 没点到）。
#   * 工艺测试包里 `process_flow_support: ['standard','high_flow']`，并且**速度类参数
#     才是两档值的**（outer_wall_speed 550/500、inner_wall_speed 550/600、
#     top_surface_speed 550/200、travel_speed 550/500 …）→ 测试方说的「切到速度 tab」
#     正好对上：Advanced 打开后侧边栏才会多出 Speed tab（Bambu/Orca 惯例），带流量
#     标志的速度参数在那一页里分档。
#
# 本轮验证：
#   Q1 点中 Advanced 开关后，tab 行是否多出 Speed？
#   Q2 有 Speed 的话，它的参数页里有没有 `[Standard flow] / [High flow]` 子 tab（实体尺寸）？
#   Q3 切 High flow 后，带标志的速度参数是否换档（期望 550→500 这类），不带标志的（如层高 0.2）不变？
#   Q4 顺带把「喷嘴 Flow 组合框下拉」的窗口身份打出来（上一轮 wait_popup/找 'High Flow'
#      都匹配到了主窗口，说明下拉不是独立顶层，得看它挂在谁下面）。
#
# 只读勘察：只切视图/切模式，不保存；结束关 app。

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
from diag_137_probe_process_dialog import all_children  # noqa: E402

LOG = "[p137adv]"
SESSION = None
TABS = ("Quality", "Strength", "Speed", "Support", "Multimaterial", "Others")


def tabs_now():
    seen = []
    for t, r, _h in all_children(SESSION.hwnd):
        ts = t.strip()
        if ts in TABS and r[1] < 660 and (r[2] - r[0]) > 0:
            seen.append((ts, r))
    return seen


def live_rows(ymin=560, ymax=1046):
    """Rows of the *visible* sidebar page (real size only)."""
    out = []
    for t, r, h in all_children(SESSION.hwnd):
        if r[0] >= 430 or not (ymin <= r[1] <= ymax):
            continue
        if (r[2] - r[0]) < 6 or (r[3] - r[1]) < 6:
            continue
        cls = winutil.window_class(h)
        v = winutil.edit_text(h).strip() if cls == "Edit" else t.strip()
        if v:
            out.append((v, r, cls))
    return sorted(out, key=lambda x: (x[1][1], x[1][0]))


def click(r):
    c137.click_screen_point(((r[0] + r[2]) // 2, (r[1] + r[3]) // 2))


def diff(a, b, tol=6):
    out = []
    for v, r, _c in b:
        for v2, r2, _c2 in a:
            if abs(r2[0] - r[0]) <= tol and abs(r2[1] - r[1]) <= tol:
                if v2 != v:
                    out.append((v2, v, r))
                break
    return out


def toplevels():
    import ctypes
    from ctypes import wintypes as wt
    u = winutil.user32
    pid = SESSION.pid
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not u.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(160)
        u.GetWindowTextW(hwnd, txt, 160)
        rc = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    u.EnumWindows(export_util.WNDENUMPROC(cb), 0)
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
        c137.shot("adv_00_presets")
        print(f"{LOG} tabs before Advanced: {tabs_now()}")

        # --- Q1: 点中 Advanced 开关（标签右侧那个开关控件）------------------------
        lab = next(((t, r) for t, r, _h in all_children(session.hwnd)
                    if t.strip() == "Advanced" and 500 <= r[1] <= 545), None)
        print(f"{LOG} Advanced label: {lab}")
        if lab:
            lr = lab[1]
            click((lr[2] + 12, lr[1] + 8, lr[2] + 12, lr[1] + 8))
            time.sleep(2.0)
            c137.shot("adv_01_advanced_on")
            print(f"{LOG} tabs after Advanced: {tabs_now()}")

        # --- Q2/Q3: Speed tab + 流量子 tab ---------------------------------------
        speed = next(((t, r) for t, r, _h in all_children(session.hwnd)
                      if t.strip() == "Speed" and r[1] < 660
                      and (r[2] - r[0]) > 0 and (r[3] - r[1]) > 0), None)
        print(f"{LOG} Speed tab: {speed}")
        if speed:
            click(speed[1])
            time.sleep(1.5)
            c137.shot("adv_02_speed_tab")
            rows = live_rows()
            print(f"{LOG} speed page rows: {[(v, r[1]) for v, r, _c in rows][:40]}")
            flows = [((t.strip()), r) for t, r, _h in all_children(session.hwnd)
                     if t.strip().startswith("[") and "flow" in t.lower()
                     and (r[2] - r[0]) > 0 and (r[3] - r[1]) > 0]
            print(f"{LOG} live flow sub-tabs: {flows}")
            if len(flows) >= 2:
                a = live_rows()
                std = next((r for t, r in flows if "standard" in t.lower()), None)
                hf = next((r for t, r in flows if "high" in t.lower()), None)
                if std:
                    click(std)
                    time.sleep(1.2)
                    a = live_rows()
                    c137.shot("adv_03_speed_standard_flow")
                if hf:
                    click(hf)
                    time.sleep(1.2)
                    b = live_rows()
                    c137.shot("adv_04_speed_high_flow")
                    mv = diff(a, b)
                    print(f"{LOG} speed page moved (standard->high flow) ({len(mv)}): {mv[:30]}")
                # 层高这类不带标志的参数应当不变（对照组）
                print(f"{LOG} layer-height-ish values now: "
                      f"{[(v, r[1]) for v, r, _c in b if v.replace('.', '').isdigit()][:10]}")
        else:
            print(f"{LOG} still no Speed tab after Advanced")

        # --- Q4: 喷嘴 Flow 下拉的窗口身份 ----------------------------------------
        lab2 = next(((t, r) for t, r, _h in all_children(session.hwnd)
                     if t.strip() == "Flow" and 280 <= r[1] <= 320), None)
        if lab2:
            before = {t[3] for t in toplevels()}
            click((lab2[1][0] + 62, lab2[1][1] + 9, lab2[1][0] + 62, lab2[1][1] + 9))
            time.sleep(1.5)
            c137.shot("adv_05_nozzle_flow_dropdown")
            print(f"{LOG} toplevels at dropdown time:")
            for tup in toplevels():
                print(f"{LOG}   {tup[0]!r} {tup[1]!r} rect={tup[2]} new={tup[3] not in before}")
            rows = [(t.strip(), r, winutil.window_class(h)) for t, r, h in all_children(session.hwnd)
                    if t.strip() in ("Standard", "High Flow", "High flow") ]
            print(f"{LOG} dropdown-ish rows in main tree: {rows}")
            winutil.user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            winutil.user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
