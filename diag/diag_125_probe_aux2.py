#!/usr/bin/env python3
# diag_125_probe_aux2.py — #125 面定位第二轮：辅材控件 + Preferences 入口
#
# 第一轮的收获与教训:
#   * 工艺 Support 页有行 `Filament for Supports`（y=909 那条是**标签**，侧边栏是
#     “标签在上、控件在下”的布局），Multimaterial 页有 `Filament for Features`
#     —— 这两个就是“辅材”的候选面；
#   * 菜单栏那轮读法错了：把 #32768 的**窗口句柄**当 HMENU 用 → 全是空列表。
#     正确做法是 topbar_util.menu_hmenu()（MN_GETHMENU），菜单栏本体用
#     GetMenu(主窗口) 再逐项取子菜单；选中条目可以直接派发 WM_COMMAND
#     （topbar_util.activate_menu_item），避开坐标问题。
#
# 本轮目标:
#   Q1 `Filament for Supports` 的值控件是什么、下拉里有哪些选项（Default/1/2/3…）；
#      顺带看 `Filament for Features`。
#   Q2 主窗口菜单栏有哪些项、Preferences 在哪、点开后里面跟“混用/温度”有关的开关叫什么。
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

from harness import export_util, topbar_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[p125b]"
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
    out = []
    for t, r, h in all_children(p):
        if not (x0 <= r[0] <= x1 and y0 <= r[1] <= y1):
            continue
        out.append((t.strip(), r, winutil.window_class(h), h))
    return sorted(out, key=lambda c: (c[1][1], c[1][0]))


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


def click(r):
    x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(1.2)


def find_label(substr, ymin=560, xmax=430):
    for t, r, _c, _h in band(0, xmax, ymin, 1100):
        if substr.lower() in t.lower():
            return t, r
    return None, None


def probe_process_row(substr, extra_y=60):
    name, r = find_label(substr)
    print(f"{LOG} label {substr!r}: {name!r} @{r}")
    if not r:
        return
    rows = band(0, 430, r[1] - 8, r[3] + extra_y)
    print(f"{LOG}   row children: {[(t[:20], rr, c) for t, rr, c, _h in rows]}")
    # the control usually sits on the line BELOW the label
    ctrl = [x for x in rows if x[1][1] > r[3] and (x[1][2] - x[1][0]) > 40
            and x[2] not in ("Edit",)]
    print(f"{LOG}   control candidates: {[(t[:20], rr, c) for t, rr, c, _h in ctrl]}")
    if ctrl:
        t0, r0, _c0, _h0 = ctrl[0]
        before = {x[3] for x in toplevels()}
        click(r0)
        print(f"{LOG}   after click on {t0!r}:")
        for tup in toplevels():
            if tup[3] in before:
                continue
            print(f"{LOG}     NEW toplevel {tup[0]!r} {tup[1]!r} {tup[2]}")
            hmenu = topbar_util.menu_hmenu(tup[3])
            print(f"{LOG}     items: {[l for _i, l, _s in topbar_util.menu_items(hmenu)]}")
            kids = [(t.strip(), rr, c) for t, rr, c, _h in all_children(tup[3]) if t.strip()]
            print(f"{LOG}     kids: {[(t[:18], rr) for t, rr, c in kids][:12]}")
        winutil.user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)


def frame_menu():
    hmenu = user32.GetMenu(SESSION.hwnd)
    print(f"{LOG} frame HMENU: {hmenu}")
    items = topbar_util.menu_items(hmenu) if hmenu else []
    print(f"{LOG} menu bar: {[l for _i, l, _s in items]}")
    for i, label, _st in items:
        _id, sub = topbar_util.item_info(hmenu, i)
        if not sub:
            continue
        subs = [l for _j, l, _s in topbar_util.menu_items(sub)]
        print(f"{LOG}   {label!r} -> {subs}")


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
        if not m7.step_delete_all(session, {}):
            print(f"{LOG} delete-all failed")
        m7.op_add_primitive(session, "cube")
        time.sleep(1.2)
        m8.wait_slots(session)

        # --- Q1: 辅材控件 -------------------------------------------------------
        dump = band(0, 430, 560, 1046)
        for t, r, c, _h in dump:
            if any(w in t.lower() for w in ("filament for", "filament", "support", "flush")):
                print(f"{LOG} sidebar row {t[:44]!r} @{r} cls={c}")
        probe_process_row("Filament for Supports")
        # Support tab 可能要先点一下才渲染出该行
        for t, r, c, _h in band(0, 430, 560, 760):
            if t in ("Support", "Multimaterial"):
                click(r)
                time.sleep(1.0)
                probe_process_row("Filament for Supports")

        # --- Q2: 菜单栏 + Preferences ------------------------------------------
        frame_menu()
        hmenu = user32.GetMenu(session.hwnd)
        idx = topbar_util.find_item(hmenu, "file") if hmenu else None
        if idx is not None:
            _id, sub = topbar_util.item_info(hmenu, idx)
            rows = topbar_util.menu_items(sub)
            print(f"{LOG} File menu: {[l for _i, l, _s in rows]}")
            pi = next((i for i, l, _s in rows
                       if "preference" in l.lower() or "设置" in l), None)
            print(f"{LOG} Preferences index: {pi}")
            if pi is not None:
                topbar_util.activate_menu_item(session, sub, pi)
                time.sleep(2.5)
                dlg = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32770",
                                                timeout_s=5.0)
                print(f"{LOG} preferences window: {dlg[1] if dlg else None} {dlg[2] if dlg else ''}")
                if dlg:
                    kids = [(t.strip(), r, winutil.window_class(h))
                            for t, r, h in all_children(dlg[3]) if t.strip()]
                    print(f"{LOG} preferences children ({len(kids)}):")
                    for t, r, c in kids:
                        print(f"{LOG}   {t[:56]!r} @{r} cls={c}")
                    winutil.close_window(dlg[3])
                    time.sleep(1.0)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
