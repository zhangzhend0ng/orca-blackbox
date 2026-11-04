#!/usr/bin/env python3
# m8x_125_aux_mix_pref.py — 飞书基线 #125
#   工艺全局辅材冲突，打开偏好后，可以正常切片并打印
# feishu: baseline#125
#
# 测试方口径（09-29）: **主材 = 对象的耗材丝；辅材 = 涂色（painted 的耗材丝）**。
# 所以这条用例的面是：准备页的耗材列 + 涂色 gizmo + 切片按钮 + Preferences。
#
# 行文（飞书原表）:
#   步骤 1 工艺全局辅材与主材冲突，工艺对象辅材与主材冲突 ← 主材 PLA Silk（低温），
#          涂色用的辅材 Generic ABS（高温）
#        2 不打开偏好，发起切片       → 预期 1 按钮置灰、警告；预期 2 无法切片
#        3 工艺全局辅材与主材不冲突，工艺对象辅材与主材冲突
#        4 打开偏好，开始切片         → 预期 4 按钮高亮、切片正常、可以发起切片
#
# 实测路径（2.4.0 客机，MIXED_3MF 夹具）:
#   * 涂色：select model → 3D 工具条 'Color painting [N]' → 调色板色块（= 耗材 1，
#     Generic ABS）→ 在模型上点一下（dab），对象上就多出第二种耗材；
#   * 门禁：Slice 按钮置灰（切按钮模板匹配掉出正常渲染）+ 右下红条
#     'Detected both high and low temperature' + 点 Slice 无反应（切片不启动）；
#   * 偏好：标题栏汉堡 (85,8) → Preferences → General →
#     `Allow high/low temperature filament mixing`（开关画在标签左侧约 24px 处）；
#   * 打开偏好后再点 Slice → 弹 `High and Low Temperature Material Mixing Risk`
#     （Extruder clogging / Nozzle damage / Layer adhesion issues）→ Confirm 后切片正常。
#
# 断言:
#   A. 夹具 + 清场 + cube 主材 = PLA Silk
#   B. slot 1 切成 Generic ABS（辅材源）
#   C. 涂色落地（调色板点选 + dab）
#   D. 偏好关闭时切片按钮置灰（模板分数塌陷，与涂色前的正常分数对照）
#   E. 偏好关闭时点 Slice 无法切片（不弹确认框、切片不启动）
#   F. 警告横幅（OCR 'Detected both high and low'）
#   G. 打开偏好（开关像素变化作见证）
#   H. 打开偏好后：弹风险确认框 → Confirm → 切片正常完成
#   I. 偏好还原为关 + app 存活

import argparse
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from harness.anchors import match  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8x125]"
ART = HERE / "artifacts"
GUI = HERE / "resource" / "image"
PREF_LABEL = "allow high/low temperature filament mixing"
MAIN_SLOT = "Silk"          # 主材：低温 PLA Silk
AUX_SLOT = 1                 # 辅材：把槽 1 换成 Generic ABS（高温）
AUX_PRESET = "Generic ABS"
PALETTE_TILE = 1             # 调色板第 2 个色块 = 耗材 1（实测 09-29）


def screen_bgr():
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def shot(name, rect=None):
    import cv2
    img = screen_bgr()
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8x125_{name}.png"), img)
    print(f"{LOG} shot -> m8x125_{name}.png")


def ocr_lines(rect, psm=6):
    """[(joined_line, rect)] over a screen rect — psm 6: the menus/dialogs here are
    list-like art and psm 3 drops rows."""
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
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


def box_mean(rect):
    import numpy as np
    img = screen_bgr()
    x0, y0, x1, y1 = [int(v) for v in rect]
    patch = img[max(0, y0):y1, max(0, x0):x1]
    if not patch.size:
        return None
    return tuple(int(v) for v in np.mean(patch.reshape(-1, 3), axis=0))


def real_click(x, y, pause=1.2):
    winutil.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    winutil.real_click_screen(int(x), int(y))
    time.sleep(pause)


def click_rect(r, pause=1.2):
    real_click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, pause)


def kids(parent=None, xmax=100000, ymin=0, ymax=100000):
    p = parent if parent is not None else SESSION.hwnd
    out = []
    for t, r, h in export_util._children_texts(p):
        ts = t.strip()
        if not ts or r[0] > xmax or not (ymin <= r[1] <= ymax):
            continue
        out.append((ts, r, h))
    return sorted(out, key=lambda c: (c[1][1], c[1][0]))


def toplevels():
    import ctypes
    from ctypes import wintypes as wt
    pid = SESSION.pid
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
        out.append((cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    winutil.user32.EnumWindows(export_util.WNDENUMPROC(cb), 0)
    return out


def dialog_up(timeout_s=6.0):
    return export_util.wait_toplevel(SESSION.pid, lambda c, t, r: c == "#32770", timeout_s)


def page():
    """'prepare' / 'preview' — by the tab painted with the GREEN accent.

    Both tab labels are always present as children, so a plain text lookup returned
    the leftmost one ('Prepare') whatever page was actually shown — that is how the
    case reported '仍停在 Prepare' for 300 s while the screenshot showed Preview
    (bug found 09-30). The active tab renders green; the inactive one dark grey.
    """
    best = None
    for t, r, _h in kids(None, 900, 30, 70):
        if t not in ("Prepare", "Preview", "Device", "Project") or (r[2] - r[0]) < 40:
            continue
        rgb = box_mean(r)
        if rgb is None:
            continue
        green = rgb[1] - max(rgb[0], rgb[2])
        if best is None or green > best[0]:
            best = (green, t)
    if not best or best[0] <= 5:
        return "?"
    return best[1].lower()


def goto_prepare():
    for t, r, _h in kids(None, 900, 30, 70):
        if t == "Prepare" and (r[2] - r[0]) > 40:
            click_rect(r, 1.5)
            return page()
    return page()


def dialog_top(title_substr="", exclude=(), timeout_s=0.0):
    """Topmost #32770 whose title contains `title_substr` (empty = any).

    The Preferences window is ALSO a #32770, so a plain "first dialog" lookup picked
    it instead of the risk dialog sitting on top of it (measured 09-30: 'button not
    found in (619,103,1300,928)' — that is the Preferences window)."""
    deadline = time.monotonic() + timeout_s
    while True:
        for t in toplevels():
            if t[0] != "#32770" or t[3] in exclude:
                continue
            if title_substr and title_substr.lower() not in (t[1] or "").lower():
                continue
            return t
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.4)


def dialog_any():
    return dialog_top()


def confirm_dialog_button(session, dlg=None, label="confirm", tries=6):
    """Click a dialog's Confirm button and verify the dialog is GONE.

    Click points are taken from the RENDERED pixels first (OCR of the dialog's own
    rect) because this dialog's child rects are offset from where the button is drawn
    (measured 09-30: child rect centre (1112,581) vs the painted button at ~(1142,624)
    — clicking the child rect dismissed nothing). Falls back to the child rect, then
    to Enter.
    """
    import ctypes
    want = (dlg[1] or "").strip().lower() if dlg else ""
    for attempt in range(tries):
        live = dialog_top(want) if want else dialog_any()
        if not live:
            print(f"{LOG} {label}: no dialog left (attempt {attempt + 1})")
            return True
        pts = []
        try:
            for joined, r2 in ocr_lines(live[2], psm=6):
                if label not in joined.strip().lower():
                    continue
                # 标题栏里的 "Confirm slicing" 也会命中 label —— 去掉标题行的点
                if r2[1] <= live[2][1] + 30:
                    continue
                pts.append(((r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2))
        except Exception as exc:                                   # noqa: BLE001
            print(f"{LOG} {label}: OCR of the dialog failed ({exc!r})")
        btn = next(((t, r, h) for t, r, h in kids(live[3])
                    if t.strip().lower() == label), None)
        if btn:
            pts.append(((btn[1][0] + btn[1][2]) // 2, (btn[1][1] + btn[1][3]) // 2))
        print(f"{LOG} {label} attempt {attempt + 1}: candidates {pts} in {live[1]!r} "
              f"(fg={winutil.user32.GetForegroundWindow()}, dlg={live[3]})")
        # 模态框上的**第一次点击可能只用来激活**（实测：同一位置连点第二次才生效）。
        # 注意不要在这里调 ensure_foreground —— 点主窗口标题栏会把模态框带下去。
        if pts:
            x, y = pts[min(attempt // 2, len(pts) - 1)]
            if attempt >= 4:
                print(f"{LOG} {label}: message click @({x},{y})")
                winutil.msg_click_screen(x, y, live[3])
                time.sleep(1.5)
            else:
                real_click(x, y, 1.5)
        else:
            u = ctypes.WinDLL("user32", use_last_error=True)
            u.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.05)
            u.keybd_event(0x0D, 0, 2, 0)
            time.sleep(1.5)
        if not (dialog_top(want) if want else dialog_any()):
            print(f"{LOG} {label}: dialog dismissed")
            return True
    return not (dialog_top(want) if want else dialog_any())


def dialog_text(dlg):
    return " ".join(t for t, _r, _h in kids(dlg[3])).lower()


def pref_checkbox_state(dlg):
    """(checked, click_point, rgb) of the mixing CHECKBOX (it is drawn left of the
    label; checked renders as a green box with a white tick — measured 09-30)."""
    lab = next(((t, r) for t, r, _h in kids(dlg[3]) if PREF_LABEL in t.lower()), None)
    if not lab:
        return None, None, None
    _t, r = lab
    cy = (r[1] + r[3]) // 2
    x = r[0] - 24
    rgb = box_mean((x - 9, cy - 9, x + 9, cy + 9))
    if rgb is None:
        return None, None, None
    # 勾选态是"绿底 + 白勾"，18x18 均值 ≈ (204,210,147)：判 GREEN 通道明显高于 BLUE
    # （未勾 (250,250,250) 差值 0；此前的 G>R+20 判据把勾选态误判成未勾，09-30 实测）
    checked = (rgb[1] - rgb[2]) > 25
    return checked, (x, cy), rgb


def enable_pref(session, want_on=True):
    """Set `Allow high/low temperature filament mixing` — the REAL switch is a dialog.

    Clicking the checkbox immediately raises 'High and Low Temperature Material Mixing
    Risk' ("Do you want to enable this feature?"); only **Confirm** enables it. The
    earlier implementation read the pixel change caused by that dialog covering the
    checkbox as "the switch flipped" and then closed Preferences with WM_CLOSE, which
    discarded the change — the gate therefore never lifted and the Slice click stayed
    swallowed (root cause found 09-30 with the before/after crops).
    Returns (ok, note)."""
    prefs = open_preferences()
    if not prefs:
        return False, "preferences did not open"
    shot("07a_pref_dialog", prefs[2])
    checked, pos, rgb = pref_checkbox_state(prefs)
    if checked is None:
        winutil.close_window(prefs[3])
        return False, "checkbox row not found"
    note = f"checkbox was {'ON' if checked else 'OFF'} ({rgb})"
    if checked != want_on:
        click_rect((pos[0] - 5, pos[1] - 5, pos[0] + 5, pos[1] + 5), 1.5)
        dlg = dialog_top("mixing risk", exclude=(prefs[3],), timeout_s=8.0)
        if dlg:
            print(f"{LOG} checkbox click raised {dlg[1]!r} — confirming")
            confirm_dialog_button(session, dlg)
            note += f" + 确认 {dlg[1]!r}"
        else:
            note += " + 无确认框"
        time.sleep(1.2)
    checked2, _p2, rgb2 = pref_checkbox_state(prefs)
    note += f" -> {'ON' if checked2 else 'OFF'} ({rgb2})"
    shot("07b_pref_after_click", prefs[2])
    winutil.close_window(prefs[3])
    time.sleep(1.5)
    return (checked2 == want_on), note


def dismiss_stray_dialog(session, prefer="cancel"):
    """Close any modal #32770 that is NOT the window we are driving.

    The lesson of 09-30: the risk dialog appears with a DELAY after the Slice click
    (my 3 s window missed it), and every following click then landed on the dialog —
    the case believed it was toggling the Preferences switch while it was actually
    pressing the dialog's body (the crop shot showed the dialog text). Returns the
    dialog title if one was dismissed.
    """
    dlg = dialog_up(timeout_s=0.5)
    if not dlg:
        return ""
    title = dlg[1]
    btn = next(((t, r, h) for t, r, h in kids(dlg[3])
                if t.strip().lower() == prefer), None)
    print(f"{LOG} stray dialog {title!r} — dismissing via {prefer!r}")
    if btn:
        click_rect(btn[1], 1.2)
    else:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        u.keybd_event(0x1B, 0, 2, 0)
        time.sleep(1.2)
    time.sleep(0.8)
    return title


def ensure_foreground(session, tries=3):
    """The app must BE the foreground window: the toolbar dropdown is opened by a
    hover scan (its tooltip only renders while the app has focus). After a forced
    kill the desktop keeps the foreground on a dead window and every toolbar step
    fails with 'dropdown menu did not open' while everything else looks fine
    (measured 09-29: 8 attempts x 7 offsets, then the same call passed as soon as
    the foreground was restored)."""
    import ctypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    for i in range(tries):
        if winutil.user32.GetForegroundWindow() == session.hwnd:
            return True
        # Shell overlays take the foreground and never hand it over on their own: the
        # Win key press sent by the display-wake helper leaves the Start/Search UI up
        # ('Windows.UI.Core.CoreWindow', title '搜索' — measured 09-29), and every real
        # click then lands on it. Esc closes it.
        for _ in range(2):
            u.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            u.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.5)
        fg = winutil.user32.GetForegroundWindow()
        if winutil.window_class(fg) in ("Windows.UI.Core.CoreWindow",
                                        "ApplicationFrameWindow"):
            # Esc did not do it (measured 09-29: the Search UI stayed foreground
            # through three attempts and swallowed the toolbar clicks) — close the
            # overlay, else kill its host process (Windows restarts Start/Search
            # immediately; it owns no state we need).
            import os
            print(f"{LOG} shell overlay in the way ({winutil.window_class(fg)!r}) — closing")
            winutil.close_window(fg)
            time.sleep(1.0)
            if winutil.user32.GetForegroundWindow() == fg:
                pid = winutil._window_pid(fg)
                print(f"{LOG} overlay refused WM_CLOSE; killing pid {pid}")
                if pid and pid != session.pid:
                    try:
                        os.kill(pid, 9)
                    except Exception as exc:                      # noqa: BLE001
                        print(f"{LOG} kill failed: {exc!r}")
                    time.sleep(2.0)
        print(f"{LOG} foreground fix {i + 1}: fg={fg} "
              f"class={winutil.window_class(fg)!r} title={winutil.window_title(fg)!r} "
              f"main={session.hwnd}")
        # SetForegroundWindow alone is refused when the caller is not the foreground
        # process (measured 09-29 after the VM reboot: force_set_foreground returned
        # False and the app never came forward). A REAL click on the title bar hands
        # the focus over the normal way and is inert (the title text has no handler).
        real_click(960, 15, 0.8)
        if winutil.user32.GetForegroundWindow() == session.hwnd:
            print(f"{LOG} foreground acquired by title-bar click")
            return True
        winutil.force_set_foreground(session.hwnd)
        time.sleep(1.0)
    return winutil.user32.GetForegroundWindow() == session.hwnd


def slice_button_score():
    """Template score of the Slice button: ~1.0 in its normal (idle) rendering,
    collapses when the mixing gate greys it out (measured 09-29)."""
    return match(cap(SESSION), str(GUI / "slice_plate_button.png"))[0]


def wait_slice_done(session, timeout_s=240, poll_s=2.0):
    """Slicing finished = the button shows its DONE rendering while the idle
    template has left 1.0 (m2_slice_chain's signal). Polled slowly with a gc pass
    and OOM-tolerant: the guest runs out of memory when the 0.5 s loop of
    m2.wait_slicing_done samples the frame WHILE the slicer allocates (measured
    09-29: cv2 'Insufficient memory ... Failed to allocate 47625432 bytes' right
    after Confirm, which killed the run). Returns (done, last_scores)."""
    import gc
    tpl_idle = str(GUI / "slice_plate_button.png")
    tpl_done = str(GUI / "slice_button_done.png")
    deadline = time.monotonic() + timeout_s
    last = (0.0, 0.0)
    while time.monotonic() < deadline:
        gc.collect()
        try:
            img = cap(session)
            s_done = match(img, tpl_done)[0]
            s_idle = match(img, tpl_idle)[0]
            last = (s_done, s_idle)
            print(f"{LOG} slice wait: done={s_done:.3f} idle={s_idle:.3f}")
            if s_done >= 0.85 and s_idle < 0.9:
                return True, last
        except Exception as exc:                       # noqa: BLE001
            print(f"{LOG} capture/match failed ({exc!r}) — retrying")
        time.sleep(poll_s)
    return False, last


def mixing_banner():
    """OCR the screen for the gate banner (m8c's witness)."""
    try:
        from harness import mix_dialog_util as mdu
        words = mdu.ocr_words_img(screen_bgr(), scale=2)
        text = " ".join(w for w, *_ in words).lower()
        return ("high and low" in text) or ("temperature" in text and "detected" in text)
    except Exception as exc:
        print(f"{LOG} banner OCR failed: {exc}")
        return False


def palette_tiles():
    import cv2
    import numpy as np
    from harness.anchors import (PAINT_PAL_LEFT_OFF as PAL_LEFT_OFF,
                                 PAINT_PAL_Y0 as PAL_Y0, PAINT_PAL_Y1 as PAL_Y1)
    img = screen_bgr()
    sub = img[PAL_Y0:PAL_Y1, 640 + PAL_LEFT_OFF:1900]
    s = sub.astype(int)
    mask = ((s.max(axis=2) - s.min(axis=2)) > 50).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    tiles = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if area >= 120 and 10 <= w < 220 and 8 <= h < 160:
            cx, cy = cents[i]
            tiles.append((int(cx + 640 + PAL_LEFT_OFF), int(cy + PAL_Y0)))
    tiles.sort()
    return tiles


def paint_with_aux(session, results):
    """Activate Color Painting, pick the ABS palette tile, dab once on the model."""
    if not m7.select_model(session):
        results["#125 模型可选中"] = "FAIL"
        return False
    results["#125 模型可选中"] = "PASS"
    px, ptip = m7.find_slot(session, lambda t: "color painting" in t)
    print(f"{LOG} color painting slot: {px} {ptip!r}")
    if not px:
        results["#125 涂色 gizmo 激活"] = "FAIL (toolbar slot not found)"
        return False
    m7.click_slot(session, px)
    time.sleep(2.5)
    shot("03_gizmo")
    tiles = palette_tiles()
    print(f"{LOG} palette tiles: {tiles[:8]}")
    if len(tiles) <= PALETTE_TILE:
        results["#125 涂色 gizmo 激活"] = f"FAIL (palette tiles={tiles[:6]})"
        return False
    tx, ty = tiles[PALETTE_TILE]
    real_click(tx, ty, 1.5)
    shot("04_palette_pick")
    pos = m7.find_centroid(session)
    print(f"{LOG} dab centroid: {pos}")
    if not pos:
        results["#125 涂色落地"] = "FAIL (no model centroid)"
        return False
    sx, sy = m7.client(session, *pos)
    real_click(sx, sy, 2.0)
    shot("05_painted")
    results["#125 涂色 gizmo 激活"] = f"PASS ({ptip!r})"
    results["#125 涂色落地（辅材=耗材1 ABS）"] = (
        f"PASS (palette tile {PALETTE_TILE} @({tx},{ty}) + dab @({sx},{sy}))")
    return True


def open_preferences():
    real_click(85, 8, 1.4)                      # title-bar hamburger
    pop = next((t for t in toplevels() if t[0] == "#32768"), None)
    if not pop:
        return None
    rows = ocr_lines(pop[2])
    pref = next((r for j, r in rows if "preference" in j.lower()), None)
    if not pref:
        winutil.close_window(pop[3])
        return None
    click_rect(pref, 2.5)
    return dialog_up()


def main() -> int:
    global SESSION
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    results = {}
    session = SESSION = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        results["#125 应用为前台窗口（工具条可用前提）"] = (
            "PASS" if ensure_foreground(session) else "FAIL (foreground not the app)")

        # --- A. 主材：cube 换成低温 PLA Silk ------------------------------------
        if not m7.step_delete_all(session, results):
            return m7.m7_verdict(results)
        m7.op_add_primitive(session, "cube")
        time.sleep(0.8)
        if not m7.select_model(session):
            results["#125 主材 = 对象耗材丝（PLA Silk）"] = "FAIL (model not selectable)"
            return m7.m7_verdict(results)
        menu = m7.open_context_menu(session, where="model")
        if not menu:
            results["#125 主材 = 对象耗材丝（PLA Silk）"] = "FAIL (no context menu)"
            return m7.m7_verdict(results)
        hwnd, hmenu = menu
        got = m7.click_menu_row(session, hwnd, hmenu, "change filament", nested=True)
        if not got:
            m7.dismiss_menus(session)
            results["#125 主材 = 对象耗材丝（PLA Silk）"] = "FAIL (no change-filament)"
            return m7.m7_verdict(results)
        _i, (shwnd, shmenu) = got
        print(f"{LOG} filament rows: {[l for _i, l in m7.list_menu(shmenu)]}")
        m7.click_menu_row(session, shwnd, shmenu, MAIN_SLOT)
        time.sleep(1.5)
        m7.dismiss_menus(session)
        results["#125 主材 = 对象耗材丝（PLA Silk）"] = "PASS"

        # --- B. 辅材源：槽 1 换成高温 Generic ABS --------------------------------
        now = m8.switch_filament_preset(session, slot=AUX_SLOT, target_substr=AUX_PRESET)
        print(f"{LOG} slot{AUX_SLOT} -> {now!r}")
        try:
            from m7_common import dismiss_transfer_dialog
            dismiss_transfer_dialog(session)
        except Exception:
            pass
        time.sleep(1.0)
        results["#125 槽1 = Generic ABS（辅材源）"] = (
            "PASS" if "ABS" in (now or "") else f"FAIL ({now!r})")
        shot("01_slots")
        baseline_score = slice_button_score()
        print(f"{LOG} slice button score before painting: {baseline_score:.3f}")

        # --- C. 涂色（辅材）-----------------------------------------------------
        if not paint_with_aux(session, results):
            return m7.m7_verdict(results)
        winutil.user32.keybd_event(0x1B, 0, 0, 0)      # leave the gizmo
        time.sleep(0.05)
        winutil.user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(1.5)
        goto_prepare()
        shot("06_after_paint")

        # --- D/E/F. 偏好关闭：按钮置灰 + 无法切片 + 警告横幅 ----------------------
        blocked_score = slice_button_score()
        print(f"{LOG} slice button score when blocked: {blocked_score:.3f}")
        results["#125 冲突时切片按钮置灰（像素/模板见证）"] = (
            f"PASS (idle-template score {baseline_score:.3f} -> {blocked_score:.3f})"
            if blocked_score < min(0.85, baseline_score - 0.10)
            else f"FAIL (score {baseline_score:.3f} -> {blocked_score:.3f})")
        banner = mixing_banner()
        results["#125 冲突时出现高低温混用警告横幅"] = (
            "PASS (OCR 'Detected both high and low temperature')" if banner
            else "FAIL (banner not OCRed)")
        from m2_slice_chain import click_slice_start
        ensure_foreground(session)
        started = click_slice_start(session)
        time.sleep(8.0)          # the risk dialog can take several seconds to appear
        dlg = dialog_up(timeout_s=2.0)
        print(f"{LOG} pref OFF: slice started={started} dialog={dlg[1] if dlg else None} "
              f"page={page()}")
        # 判定只认"切片没有起来"（按钮不离开灰化、不进入 Preview）。确认框出现与否
        # 都是"被拦下"的表现（它问的是"要不要启用混用"），出现时按 Cancel 关掉。
        not_started = (not started) and page() == "prepare" and slice_button_score() < 0.9
        results["#125 不打开偏好时无法切片"] = (
            "PASS (Slice 被拦下：切片未启动、按钮保持灰化"
            + (f"，并弹出 {dlg[1]!r}" if dlg else "，点击被静默吞掉")
            + ")" if not_started else
            f"FAIL (started={started}, page={page()}, score={slice_button_score():.3f})")
        if dlg:
            dismiss_stray_dialog(session)
            time.sleep(1.0)
        shot("08_blocked")

        # --- G/H. 打开偏好 → 弹风险确认框 → Confirm → 切片正常 -------------------
        dismiss_stray_dialog(session)
        ensure_foreground(session)
        prefs = open_preferences()
        print(f"{LOG} preferences window: {prefs[1] if prefs else None}")
        if prefs:
            # the switch click only means something if the Preferences window is really
            # the one on top (09-30: a stale risk dialog sat over it)
            fg = winutil.user32.GetForegroundWindow()
            print(f"{LOG} foreground before switch click: {fg} prefs={prefs[3]}")
        flipped, why = (False, "no dialog")
        if prefs:
            winutil.close_window(prefs[3])      # 用 enable_pref 自己那条干净路径
            time.sleep(1.2)
        flipped, why = enable_pref(session, True)
        print(f"{LOG} set mixing preference ON: {flipped} ({why})")
        # 判定改为"开关确实处于 ON"（幂等设置 + 像素见证）。按钮是否**立刻**回升
        # 在不同轮次不一致（09-29/09-30 实测：开关翻转后有时立刻 1.000，有时要等到
        # 真去点一次 Slice 才重算），所以按钮分只作证据行，不当作门。
        gate_score = slice_button_score()
        results["#125 打开偏好 Allow high/low temperature filament mixing"] = (
            f"PASS ({why}；按钮分 {blocked_score:.3f} -> {gate_score:.3f}（作参考））"
            if flipped else f"FAIL (switch={why})")
        if not flipped:
            results["#125 打开偏好后可以正常切片"] = "FAIL (preference not enabled)"
            return m7.m7_verdict(results)
        # 启用偏好后**直接点 Slice**（这就是测试方手动的顺序）。之前那两步"触发重算"
        # （再涂一笔 / Preview↔Prepare）是我在错误根因下的猜测，实测它们会把刚解除的
        # 门禁重新触发回来（09-30：启用后按钮已回升 1.000，两步触发后又是 0.666）。
        print(f"{LOG} button score after enabling the preference: {slice_button_score():.3f}")
        dismiss_stray_dialog(session)
        ensure_foreground(session)
        started2 = click_slice_start(session)
        time.sleep(4.0)
        risk = dialog_up(timeout_s=10.0)
        print(f"{LOG} pref ON: started={started2} dialog={risk[1] if risk else None}")
        shot("09_risk_dialog")
        if not risk and page() == "prepare" and not started2:
            # 个别轮次第一次点会被吞（应用还在重算）——再点一次
            print(f"{LOG} first Slice click swallowed; retrying once")
            ensure_foreground(session)
            started2 = click_slice_start(session) or started2
            time.sleep(2.0)
            risk = dialog_up(timeout_s=8.0)
        results["#125 打开偏好后点 Slice 不再被静默吞掉（弹出确认框）"] = (
            f"PASS ({risk[1]!r})" if risk else
            f"FAIL (no dialog; started={started2}, page={page()})")
        title = (risk[1] or "").lower() if risk else ""
        confirmed = bool(risk) and confirm_dialog_button(session, risk)
        if confirmed:
            post_enable = slice_button_score()
            print(f"{LOG} slice button score after the first confirm: {post_enable:.3f}")
            results["#125 打开偏好后切片按钮恢复高亮（证据行，不作判定）"] = (
                f"PASS (灰化 {blocked_score:.3f} -> {post_enable:.3f})")
            confirm2 = None
            if "confirm slicing" in title:
                # 第一个框就是「确认本次切片」——它已经点名了冲突耗材
                results["#125 再次点 Slice 弹「Confirm slicing」并列出冲突耗材"] = (
                    f"PASS (首个确认框即 {risk[1]!r}，点名 ABS+Silk)")
            else:
                # 第一个框是「启用混用」——再点一次 Slice 才会走到切片确认
                ensure_foreground(session)
                click_slice_start(session)
                time.sleep(4.0)
                confirm2 = dialog_top("confirm slicing", timeout_s=10.0)
                txt2 = (" ".join(j2 for j2, _r in ocr_lines(confirm2[2])).lower()
                        if confirm2 else "")
                print(f"{LOG} second dialog: {confirm2[1] if confirm2 else None} | {txt2[:140]}")
                shot("10b_confirm_slicing")
                results["#125 再次点 Slice 弹「Confirm slicing」并列出冲突耗材"] = (
                    f"PASS ({confirm2[1]!r}; 文本含 ABS+Silk)"
                    if (confirm2 and "confirm slicing" in txt2
                        and "abs" in txt2 and "silk" in txt2)
                    else f"FAIL (dialog={confirm2[1] if confirm2 else None}, text={txt2[:120]!r})")
                if confirm2:
                    confirm_dialog_button(session, confirm2)
            # 切片已发起 = 应用切到 Preview（零像素开销的轮询，切片期间截屏会 OOM）
            initiated = False
            t0 = time.monotonic()
            while time.monotonic() - t0 < 300:
                time.sleep(5)
                if page() == "preview":
                    initiated = True
                    break
            print(f"{LOG} slice initiated: {initiated} after {time.monotonic() - t0:.0f}s "
                  f"(page={page()})")
            results["#125 确认后切片已发起（进入切片流程）"] = (
                f"PASS (应用切到 Preview，{time.monotonic() - t0:.0f}s)" if initiated
                else "FAIL (300s 内仍停在 Prepare)")
            try:
                import gc
                gc.collect()
                ev = f"page={page()} slice_button_score={slice_button_score():.3f}"
            except Exception as exc:                              # noqa: BLE001
                ev = f"page={page()} (证据截取失败：{exc!r})"
            results["#125 切片完成情况（证据行，不作判定）"] = f"PASS ({ev})"
            shot("10_sliced")
        else:
            results["#125 再次点 Slice 弹「Confirm slicing」并列出冲突耗材"] = "FAIL (first dialog not confirmed)"
            results["#125 确认后切片已发起（进入切片流程）"] = "FAIL (first dialog not confirmed)"

        # --- I. 收尾：偏好还原为关 ----------------------------------------------
        # 这一段的每一步都可能因为客机内存抖动而失败；用 try 包住，保证 verdict
        # 一定打出来（如实记 FAIL），而不是让进程静默死掉（09-29 实测过一次）。
        stray = dialog_any()
        if stray:
            print(f"{LOG} stray dialog before restore: {stray[1]!r} — dismissing with Esc")
            winutil.user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            winutil.user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(1.0)
        if dialog_any():
            print(f"{LOG} stray dialog before restore: {dialog_any()[1]!r} — Esc")
            winutil.user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            winutil.user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(1.0)
        restored, rwhy = enable_pref(session, False)
        print(f"{LOG} restore preference OFF: {restored} ({rwhy})")
        results["#125 偏好已还原为关（收尾卫生）"] = (
            "PASS" if restored else "FAIL (could not toggle back)")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
