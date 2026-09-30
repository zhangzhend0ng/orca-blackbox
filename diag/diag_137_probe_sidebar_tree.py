#!/usr/bin/env python3
# diag_137_probe_sidebar_tree.py — #137 工艺侧流量面勘察（第五轮 · 侧边栏全量参数树 + 参数搜索）
#
# 第四轮的教训：
#   * 喷嘴 Flow 组合框的下拉**不是** export_util.wait_popup 认的那个 wxWindowNR/'panel'
#     （wait_popup 返回 None → 没选中 → 侧边栏 diff 全是幽灵控件的噪声）。本轮改成
#     "扫所有顶层窗口，谁的孩子里有 'High Flow' 就是它"。
#   * 工艺预设名的右键菜单没有、双击没反应。
#   * 侧边栏（Process 面板）的孩子树一直延伸到 y≈3000+（滚动区），里面能看到
#     'Wall generator'/'Bridging'/'Overhangs' 等整页参数 → 本轮把全树打出来，
#     找速度类参数（Outer wall speed / Inner wall speed / Sparse infill speed /
#     Top surface speed / Travel speed …）到底在哪个 y、属于哪个 tab。
#   * 预设名右边的放大镜是「参数搜索」入口（Bambu/Orca 惯例），它列出的每条结果都带
#     "在哪个 tab"，是定位「工艺→速度 tab」最直接的黑盒证据。本轮点开它看看。
#
# 只读勘察：只点开/搜索/切模式（最后切回 Standard），不改任何值。

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

LOG = "[p137tree]"
SESSION = None
SPEED_WORDS = ("speed", "acceleration", "jerk", "volumetric")


def toplevels():
    """Every visible top-level of the app pid: (class, title, rect, hwnd)."""
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


def find_toplevel_with(text):
    for tup in toplevels():
        try:
            for t, _r, _h in all_children(tup[3]):
                if text.lower() in t.strip().lower():
                    return tup
        except Exception:
            continue
    return None


def click(r):
    c137.click_screen_point(((r[0] + r[2]) // 2, (r[1] + r[3]) // 2))


def live_side():
    """Sidebar controls with a REAL size (the ghost/zero-size children are
    destroyed dialogs' leftovers and must not enter a differential)."""
    out = []
    for t, r, h in all_children(SESSION.hwnd):
        if r[0] >= 430 or r[1] < 560:
            continue
        if (r[2] - r[0]) < 6 or (r[3] - r[1]) < 6:
            continue
        cls = winutil.window_class(h)
        v = winutil.edit_text(h).strip() if cls == "Edit" else t.strip()
        if v and cls in ("Edit", "Static", "wxWindowNR", "Button", "ComboBox", "ComboLbox"):
            out.append(((r[0], r[1]), v, r))
    return sorted(out, key=lambda x: (x[2][1], x[2][0]))


def diff(a, b, tol=6):
    am = {k: (v, r) for k, v, r in a}
    out = []
    for k, v, r in b:
        for k2, (v2, r2) in am.items():
            if abs(k2[0] - k[0]) <= tol and abs(k2[1] - k[1]) <= tol:
                if v2 != v:
                    out.append((v2, v, r))
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
        c137.shot("tree_00_presets")

        # --- A. 侧边栏全量树：找速度类参数在哪一段 -----------------------------
        rows = [(t, r, h) for t, r, h in all_children(session.hwnd)
                if r[0] < 430 and r[1] > 560 and (r[2] - r[0]) > 20 and (r[3] - r[1]) > 6]
        print(f"{LOG} sidebar rows: {len(rows)}")
        prev = None
        for t, r, h in sorted(rows, key=lambda c: c[1][1]):
            ts = t.strip()
            if ts and ts != prev:
                print(f"{LOG}   y={r[1]:5d} x={r[0]:4d} {ts[:52]!r} {winutil.window_class(h)}")
                prev = ts
        hits = [(t.strip(), r) for t, r, _h in rows if any(w in t.lower() for w in SPEED_WORDS)]
        print(f"{LOG} speed-ish rows: {[(t[:34], r[1]) for t, r in hits]}")

        # --- B. 参数搜索（预设名右侧放大镜）------------------------------------
        icons = [(t, r, h) for t, r, h in all_children(session.hwnd)
                 if 330 <= r[0] <= 420 and 545 <= r[1] <= 600 and 10 <= (r[2] - r[0]) <= 34
                 and (r[3] - r[1]) >= 10]
        print(f"{LOG} preset-row icons: {[(t.strip()[:10], r) for t, r, _h in icons]}")
        if icons:
            _t, r, _h = sorted(icons, key=lambda c: c[1][0])[-1]     # 最右 = 放大镜
            click(r)
            time.sleep(1.5)
            c137.shot("tree_01_search_open")
            top = find_toplevel_with("search") or find_toplevel_with("parameter")
            print(f"{LOG} search toplevel: {top[1] if top else None}")
            for tup in toplevels():
                kids = [t.strip() for t, _r, _h in all_children(tup[3]) if t.strip()]
                if any("search" in k.lower() for k in kids):
                    print(f"{LOG} SEARCH WIN {tup[1]!r} rect={tup[2]} kids={kids[:14]}")
                    top = tup
            if top:
                edit = next((h for t, r, h in all_children(top[3])
                             if winutil.window_class(h) == "Edit"), None)
                if edit:
                    winutil.msg_text(edit, "speed")
                    time.sleep(2.0)
                    c137.shot("tree_02_search_speed")
                    res = [(t.strip(), r) for t, r, _h in all_children(top[3]) if t.strip()]
                    print(f"{LOG} search results for 'speed': {res[:24]}")
                    # 点第一条结果 -> 看侧边栏跳到哪
                    hit = next((r for t, r in res if "speed" in t.lower()), None)
                    if hit:
                        click(hit)
                        time.sleep(1.5)
                        c137.shot("tree_03_search_jump")
                        tabs = [(t.strip(), r) for t, r, _h in all_children(session.hwnd)
                                if t.strip() in ("Quality", "Strength", "Speed", "Support",
                                                 "Multimaterial", "Others") and r[1] < 640]
                        print(f"{LOG} tab row after jump: {tabs}")
                winutil.close_window(top[3])
                time.sleep(0.8)

        # --- C. 喷嘴 Flow 组合框：正确切到 High Flow 并做干净 diff --------------
        base = live_side()
        print(f"{LOG} live sidebar values ({len(base)}): {[v for _k, v, _r in base][:30]}")
        lab = next(((t, r) for t, r, _h in all_children(session.hwnd)
                    if t.strip() == "Flow" and 280 <= r[1] <= 320), None)
        print(f"{LOG} Flow label: {lab}")
        if lab:
            click((lab[1][0] + 62, lab[1][1] + 9, lab[1][0] + 62, lab[1][1] + 9))
            time.sleep(1.5)
            c137.shot("tree_04_flow_dropdown")
            pop = find_toplevel_with("High Flow")
            print(f"{LOG} flow popup: {(pop[1], pop[2]) if pop else None}")
            if pop:
                rows2 = [(t.strip(), r) for t, r, _h in all_children(pop[3]) if t.strip()]
                print(f"{LOG} flow popup rows: {rows2}")
                hit = next((r for t, r in rows2 if t.lower().startswith("high")), None)
                if hit:
                    click(hit)
                    time.sleep(2.5)
                    c137.shot("tree_05_after_high_flow")
                    hi = live_side()
                    mv = diff(base, hi)
                    print(f"{LOG} sidebar moved Standard->High flow ({len(mv)}): {mv[:24]}")
                    print(f"{LOG} process preset now: "
                          f"{pp.find_process_preset_combo(session)}")
                    # 切回
                    click((lab[1][0] + 62, lab[1][1] + 9, lab[1][0] + 62, lab[1][1] + 9))
                    time.sleep(1.2)
                    pop2 = find_toplevel_with("Standard")
                    if pop2:
                        rr = [(t.strip(), r) for t, r, _h in all_children(pop2[3]) if t.strip()]
                        hit2 = next((r for t, r in rr if t.lower().startswith("standard")), None)
                        if hit2:
                            click(hit2)
                            time.sleep(1.5)
                            print(f"{LOG} restored -> {diff(hi, live_side())[:8]}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
