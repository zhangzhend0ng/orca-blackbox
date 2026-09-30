#!/usr/bin/env python3
# diag_125_probe_aux3.py — #125 面定位第三轮：wx 自绘菜单栏 → Preferences；辅材下拉
#
# 第二轮的收获:
#   * 辅材控件找到了：工艺 Support 页 `Filament for Supports` 行的值控件是个组合框，
#     当前显示 `Default`（矩形 (246,937,366,963)）——点它旁边那层 'mm' 包装没用；
#   * **主窗口没有原生菜单栏**（GetMenu(主窗口)=0）。顶上的 File/Edit/… 是 wx 自绘的，
#     所以 MN_GETHMENU/GetMenu 都读不到，必须按文字点、再 OCR 弹层里的行。
#
# 本轮目标:
#   Q1 菜单栏都有哪些项（按文字列表），File 里的行 OCR 出来找 Preferences，点开它，
#      把对话框里的控件树打出来 —— 找“混用/温度”相关的开关（m8c 注释说 Plater.cpp:334
#      的文案提到这个偏好）。
#   Q2 `Filament for Supports` 那个 `Default` 组合框点开后的选项列表（Default/1/2/3…）。
#
# 只读勘察：只点开看，不改值不保存；结束关 app。

import argparse
import ctypes
import ctypes.wintypes as wt
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

LOG = "[p125c]"
SESSION = None
user32 = winutil.user32


def all_children(parent):
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


def band(x0, x1, y0, y1, parent=None):
    p = parent if parent is not None else SESSION.hwnd
    return sorted([(t.strip(), r, winutil.window_class(h), h) for t, r, h in all_children(p)
                   if x0 <= r[0] <= x1 and y0 <= r[1] <= y1], key=lambda c: (c[1][1], c[1][0]))


def click_pt(x, y, pause=1.2):
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def click(r, pause=1.2):
    click_pt((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, pause)


def toplevels():
    pid = SESSION.pid
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(160)
        user32.GetWindowTextW(hwnd, txt, 160)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def ocr(rect, psm=6):
    """[(joined_line, rect)] over a screen rect (psm 6 for list-like art)."""
    from harness import mix_dialog_util as mdu
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    x0, y0, x1, y1 = rect
    crop = img[max(0, y0):y1, max(0, x0):x1]
    words = mdu.ocr_words_img(crop, scale=2, psm=psm)
    lines = {}
    for t, x, y, w, h in words:
        key = next((k for k in lines if abs(k - y) <= 12), y)
        lines.setdefault(key, []).append((x + x0, y + y0, t, w, h))
    out = []
    for _k, v in sorted(lines.items()):
        v.sort()
        out.append((" ".join(t for _x, _y, t, _w, _h in v),
                    (v[0][0], v[0][1], v[-1][0] + v[-1][3], v[-1][1] + v[-1][4])))
    return out


def try_menu(label):
    """Click a wx-drawn menu-bar label by text and dump the popup rows (OCR)."""
    hit = next(((t, r) for t, r, _c, _h in band(0, 600, 0, 40) if t == label), None)
    print(f"{LOG} menu-bar item {label!r}: {hit}")
    if not hit:
        return None
    click(hit[1], 1.0)
    pop = next((t for t in toplevels()
                if t[0] == "#32768" or (t[1] == "panel" and t[2][0] > 0)), None)
    print(f"{LOG}   popup: {pop[0] if pop else None} {pop[2] if pop else None}")
    if not pop:
        return None
    rows = ocr(pop[2])
    print(f"{LOG}   rows: {[(j[:34], r) for j, r in rows]}")
    ctrl = [(t, r, c) for t, r, c, _h in band(pop[2][0], pop[2][2], pop[2][1], pop[2][3], parent=pop[3])]
    print(f"{LOG}   child controls: {[(t[:24], r, c) for t, r, c in ctrl][:16]}")
    return pop, rows


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
        m7.step_delete_all(session, {})
        m7.op_add_primitive(session, "cube")
        time.sleep(1.2)
        m8.wait_slots(session)

        # --- 菜单栏本体 ---------------------------------------------------------
        bar = band(0, 900, 0, 34)
        print(f"{LOG} menu-bar children: {[(t[:18], r, c) for t, r, c, _h in bar]}")

        # --- File 菜单 → Preferences -------------------------------------------
        got = None
        for label in ("File", "Edit", "Snapmaker Orca", "Orca", "Help"):
            res = try_menu(label)
            if not res:
                continue
            pop, rows = res
            pref = next((r for j, r in rows if "preference" in j.lower() or "偏好" in j), None)
            print(f"{LOG}   {label}: preferences row {pref}")
            if pref:
                click_pt((pref[0] + pref[2]) // 2, (pref[1] + pref[3]) // 2, 2.5)
                dlg = export_util.wait_toplevel(session.pid,
                                                lambda c, t, r: c == "#32770", timeout_s=5.0)
                print(f"{LOG}   dialog: {dlg[1] if dlg else None} {dlg[2] if dlg else ''}")
                if dlg:
                    kids = [(t.strip(), r, winutil.window_class(h))
                            for t, r, h in all_children(dlg[3]) if t.strip()]
                    print(f"{LOG}   preferences children ({len(kids)}):")
                    for t, r, c in kids:
                        print(f"{LOG}     {t[:60]!r} @{r} cls={c}")
                    winutil.close_window(dlg[3])
                    time.sleep(1.0)
                got = dlg
                break
            # 关掉这个菜单
            user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.6)

        # --- 辅材下拉 -----------------------------------------------------------
        lab = next(((t, r) for t, r, _c, _h in band(0, 430, 560, 1100)
                    if "filament for supports" in t.lower()), None)
        print(f"{LOG} aux label: {lab}")
        if lab:
            combo = next(((t, r, c) for t, r, c, _h in band(0, 430, lab[1][3], lab[1][3] + 90)
                          if c == "wxWindowNR" and (r[2] - r[0]) > 60), None)
            print(f"{LOG} aux combo candidate: {combo}")
            if combo:
                before = {x[3] for x in toplevels()}
                click(combo[1], 1.5)
                new = [x for x in toplevels() if x[3] not in before]
                print(f"{LOG} dropdown toplevels: {[(x[0], x[1], x[2]) for x in new]}")
                for x in new:
                    kids = [(t.strip(), r) for t, r, _h in all_children(x[3]) if t.strip()]
                    print(f"{LOG}   {x[0]!r} kids: {kids[:12]}")
                    print(f"{LOG}   {x[0]!r} ocr: {[(j[:26], r[1]) for j, r in ocr(x[2])][:12]}")
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
