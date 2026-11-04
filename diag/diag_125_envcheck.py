#!/usr/bin/env python3
# diag_125_envcheck.py — 环境体检：分辨率 / 主窗口矩形 / 顶层窗口 / 工具条下拉可点性
#
# 背景：j290 那把 `m7.step_delete_all` 连 8 次都打不开工具条下拉（"no menu"），
# 而同一把用例在 j284/j286 能过。先确认是不是**窗口几何/分辨率**变了（工具条按钮
# 与 anchors 的标定是按 1920x1080 最大化窗口做的）。
import argparse
import ctypes
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[env125]"
ART = HERE / "artifacts"


def shot(name):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    cv2.imwrite(str(ART / f"m8x125_{name}.png"), img)
    print(f"{LOG} shot -> m8x125_{name}.png ({sw}x{sh})")


def ocr_lines(rect, psm=6):
    import cv2
    import numpy as np
    from harness import mix_dialog_util as mdu
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    x0, y0, x1, y1 = [int(v) for v in rect]
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


def toplevels(pid):
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        winutil.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not winutil.user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        winutil.user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(160)
        winutil.user32.GetWindowTextW(hwnd, txt, 160)
        rc = wt.RECT()
        winutil.user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom)))
        return True

    winutil.user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrival={ok} frac={frac:.3f}")
        m7.ensure_maximized(session)
        sw, sh, _ = winutil.screen_grab()
        print(f"{LOG} screen: {sw}x{sh}")
        print(f"{LOG} main rect: {winutil.window_rect(session.hwnd)}")
        print(f"{LOG} dpi: {winutil.get_dpi_for_window(session.hwnd)}")
        print(f"{LOG} fg hwnd: {winutil.user32.GetForegroundWindow()} (main={session.hwnd})")
        print(f"{LOG} toplevels:")
        for t in toplevels(session.pid):
            print(f"{LOG}   {t[0]!r} {t[1]!r} {t[2]}")
        shot("env_boot")
        print(f"{LOG} topbar buttons: {[(t, r) for t, r, _h in export_util.topbar_buttons(session.hwnd)]}")

        # ① 恢复前台后再试一次工具条下拉
        fg0 = winutil.user32.GetForegroundWindow()
        ok_fg = winutil.force_set_foreground(session.hwnd)
        time.sleep(1.0)
        fg1 = winutil.user32.GetForegroundWindow()
        print(f"{LOG} force_set_foreground: {ok_fg} fg {fg0} -> {fg1} (main={session.hwnd})")
        got2 = m7.step_delete_all(session, {})
        print(f"{LOG} step_delete_all after foreground fix: {got2}")

        # ② 汉堡菜单 → Edit → Delete All（这条入口在 #125 用例里已验证可点）
        from harness.anchors import has_colored_content
        from m1_minimal_loop import capture_bgr
        winutil.user32.SetCursorPos(85, 8)
        time.sleep(0.25)
        winutil.real_click_screen(85, 8)
        time.sleep(1.4)
        pop = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32768", timeout_s=3.0)
        print(f"{LOG} hamburger popup: {pop[2] if pop else None}")
        done = False
        if pop:
            rows = ocr_lines(pop[2])
            print(f"{LOG} hamburger rows: {[(j[:26], r) for j, r in rows]}")
            edit = next((r for j, r in rows if j.strip().lower().startswith("edit")), None)
            if edit:
                winutil.real_click_screen((edit[0] + edit[2]) // 2, (edit[1] + edit[3]) // 2)
                time.sleep(1.4)
                sub = export_util.wait_toplevel(session.pid, lambda c, t, r: c == "#32768", timeout_s=3.0)
                srect = sub[2] if sub else (edit[2], edit[1], edit[2] + 320, edit[3] + 260)
                srows = ocr_lines(srect)
                print(f"{LOG} Edit submenu rows: {[(j[:26], r) for j, r in srows]}")
                row = next((r for j, r in srows if "delete all" in j.lower()), None)
                if row:
                    winutil.real_click_screen((row[0] + row[2]) // 2, (row[1] + row[3]) // 2)
                    time.sleep(2.5)
                    frac = has_colored_content(capture_bgr(session))
                    done = frac < m7.EMPTY_BED_FLOOR
                    print(f"{LOG} hamburger delete-all: colored_frac={frac:.4f} empty={done}")
        print(f"{LOG} RESULT toolbar_delete={got2} hamburger_delete={done}")
        shot("env_afterdelete")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
