#!/usr/bin/env python3
# diag_125_confirm.py — #125 的关键疑问：Confirm 之后切片是不是还要再点一次 Slice？
#
# 现象（09-29 用例跑了两轮）：偏好打开 → 点 Slice → 弹
# "High and Low Temperature Material Mixing Risk" → 点 Confirm 后，切按钮在 60~240s 内
# 一直是 idle 渲染（模板 1.000），切片没起来。弹框问的是
# "Do you want to enable this feature?"，所以很可能 Confirm 只是**启用该功能**，
# 之后还要显式再点一次 Slice。
#
# 本轮：把这条链走一遍，Confirm 之后每 2s 记录按钮状态，30s 后若仍 idle 再点一次 Slice
# 并继续观察 60s，把结果打清楚（顺带打印 guest 上用例文件里是否含新补丁的字符串）。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))
sys.path.insert(0, str(HERE / "tests" / "topcap"))

from harness import export_util, winutil  # noqa: E402
from m2_slice_chain import click_slice_start  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
import m8x_125_aux_mix_pref as case  # noqa: E402

LOG = "[p125c2]"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = case.SESSION = boot_session(args, model=args.model)
    results = {}
    try:
        ok, _f = m8.wait_arrival(session)
        print(f"{LOG} arrival={ok}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        print(f"{LOG} foreground: {case.ensure_foreground(session)}")
        m7.step_delete_all(session, results)
        # 主材 + 辅材 + 涂色：直接复用用例里的步骤
        m7.op_add_primitive(session, "cube")
        time.sleep(0.8)
        m7.select_model(session)
        menu = m7.open_context_menu(session, where="model")
        if menu:
            hwnd, hmenu = menu
            got = m7.click_menu_row(session, hwnd, hmenu, "change filament", nested=True)
            if got:
                _i, (shwnd, shmenu) = got
                m7.click_menu_row(session, shwnd, shmenu, "Silk")
                time.sleep(1.5)
                m7.dismiss_menus(session)
        now = m8.switch_filament_preset(session, slot=1, target_substr="Generic ABS")
        print(f"{LOG} slot1 -> {now!r}")
        time.sleep(1.0)
        print(f"{LOG} painted={case.paint_with_aux(session, results)}")
        for k, v in results.items():
            print(f"{LOG} {k}: {v}")
        winutil.user32.keybd_event(0x1B, 0, 0, 0); time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0); time.sleep(1.5)
        case.goto_prepare()
        print(f"{LOG} blocked score: {case.slice_button_score():.3f}")

        case.ensure_foreground(session)
        prefs = case.open_preferences()
        print(f"{LOG} prefs={prefs[1] if prefs else None}")
        flipped = case.toggle_pref(prefs) if prefs else False
        if prefs:
            winutil.close_window(prefs[3]); time.sleep(1.2)
        print(f"{LOG} pref flipped={flipped}")

        case.ensure_foreground(session)
        started = click_slice_start(session)
        time.sleep(2.0)
        risk = case.dialog_up(timeout_s=6.0)
        print(f"{LOG} slice started={started} risk={risk[1] if risk else None}")
        if risk:
            btn = next(((t, r, h) for t, r, h in case.kids(risk[3]) if t.lower() == "confirm"), None)
            print(f"{LOG} confirm btn={btn[:2] if btn else None}")
            if btn:
                case.click_rect(btn[1], 1.5)
                time.sleep(1.5)
                still = [t for t in case.toplevels() if t[0] == "#32770" and t[2] == risk[2]]
                print(f"{LOG} dialog still up after confirm: {bool(still)}")
                if still:
                    cx, cy = (btn[1][0] + btn[1][2]) // 2, (btn[1][1] + btn[1][3]) // 2
                    winutil.msg_click_screen(cx, cy, risk[3])
                    time.sleep(1.5)
                    still2 = [t for t in case.toplevels() if t[0] == "#32770" and t[2] == risk[2]]
                    print(f"{LOG} after msg click, still up: {bool(still2)}")
        print(f"{LOG} --- phase 1: watch the button for 30 s after Confirm")
        for i in range(15):
            time.sleep(2)
            print(f"{LOG}   t+{(i + 1) * 2:>2}s score={case.slice_button_score():.3f}")
        print(f"{LOG} --- phase 2: click Slice again and watch for 60 s")
        case.ensure_foreground(session)
        again = click_slice_start(session)
        print(f"{LOG} second click accepted={again}")
        for i in range(30):
            time.sleep(2)
            print(f"{LOG}   t+{(i + 1) * 2:>2}s score={case.slice_button_score():.3f}")
        case.shot("confirm_probe")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
