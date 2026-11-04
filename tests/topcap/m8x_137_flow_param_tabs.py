#!/usr/bin/env python3
# m8x_137_flow_param_tabs.py — 飞书基线 #137
#   耗材丝配置、工艺配置有流量喷嘴标标志图的参数对比
# feishu: baseline#137
#
# 行文语义（测试方 09-29 更新后）:
#   * **耗材丝配置**与**工艺配置**里有 Standard / High Flow 两个 tab（打印机配置里没有）；
#   * 带"流量喷嘴标志"的参数：两模式各自独立（改一个不影响另一个）；
#   * 不带标志的参数：改一个两模式同步变更。
#
# 前提（实测踩出来的）:
#   * 流量控件**只在装了支持流量的耗材时才可用**：夹具自带的 `Snapmaker PLA Silk`
#     没有 `filament_flow_support` 声明时，编辑器里那个 `[Standard flow]` 是**零尺寸
#     隐藏元素**，喷嘴区的 Flow/Diameter 组合框也点不开（09-29 多轮实测）；
#   * 我们的测试包正好提供这条链路（m8f/m8g 已在用）：
#       process: `0.20mm Standard @Snapmaker U1 (0.4 nozzle) - STD-TEST`（0.4 喷嘴族）
#       filament: `Snapmaker PLA SnapSpeed @U1 - STD-TEST`（flow_support=[standard,high_flow]）
#   * STD-TEST 包里带标志的参数是**明确两档**：filament_max_volumetric_speed = ['30','40']、
#     nozzle_temperature = ['210','220'] …；不带标志的参数只有一个值（如软化温度）。
#
# 断言:
#   A. 两个预设切换成功（工艺 = 0.4 喷嘴族、耗材 = 流量包）
#   B. 耗材编辑器（Material settings）出现 Standard / High Flow 两个 tab
#   C. 带标志参数（喷嘴温度 210/220、flow ratio 0.95/0.966）：两模式各自独立
#   D. 不带标志参数（Idle temperature）：在一侧改值 → 另一侧读到同一新值（同步变更）
#   E. 工艺侧同样有这两个 tab：侧边栏 Process 面板 Advanced 打开后出现 **Speed** tab，
#     其页面上有 `[Standard flow] / [High flow]`；带标志的速度参数（包里声明的
#     60/50、550/600、550/500 …）在两模式取值不同。
#
# 实测踩点（09-29）:
#   * 耗材编辑器的 Cancel 按钮在 1920x1080 下**在屏幕外**，点不到 → 用 Esc 关并回读确认
#     （不关的话模态对话框会把后面所有侧边栏点击吃掉，这正是上一轮工艺侧 FAIL 的原因）；
#   * 工艺侧 Speed tab 默认**不显示**（Advanced 开关关着时只有 5 个 tab）；用例会在
#     开头确认、必要时打开展示，收尾再还原（避免污染其他用例的布局假设）；
#   * 工艺预设名右侧三个图标 = [保存][删除][搜索]（点中间那个弹的是 "Delete Preset"），
#     右键/双击预设名都没有参数对话框 → 工艺侧的流量面就在侧边栏 Speed 页。

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, mix_dialog_util as mdu, process_panel as pp, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

PROC_STD = "0.20mm Standard @Snapmaker U1 (0.4 nozzle) - STD-TEST"
FIL_STD = "Snapmaker PLA SnapSpeed @U1 - STD-TEST"
NZ_STD, NZ_HF = "210", "220"
SP_STD, SP_HF = "60", "50"          # initial_layer_speed = ['60','50'] in the process pack
SOFT_NEW = "5"

LOG = "[m8x137]"
ART = HERE / "artifacts"


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
    cv2.imwrite(str(ART / f"m8x137_{name}.png"), img)
    print(f"{LOG} shot -> m8x137_{name}.png")


def ocr_lines(rect, psm=6):
    """[(joined_line, rect_of_line)] for a screen rect (psm 6: psm 3 drops rows
    next to the dialog's divider art)."""
    x0, y0, x1, y1 = rect
    img = screen_bgr()[max(0, y0):y1, max(0, x0):x1]
    words = mdu.ocr_words_img(img, scale=2, psm=psm)
    lines = {}
    for t, x, y, w, h in words:
        key = next((k for k in lines if abs(k - y) <= 12), y)
        lines.setdefault(key, []).append((x + x0, y + y0, t, w, h))
    out = []
    for _k, v in sorted(lines.items()):
        v.sort()
        joined = " ".join(t for _x, _y, t, _w, _h in v)
        out.append((joined, (v[0][0], v[0][1], v[-1][0] + v[-1][3], v[-1][1] + v[-1][4])))
    return out


def real_keys(*vks):
    """Real keystrokes through the input queue.

    This dialog accepts WM_CHAR text but IGNORES message-level WM_KEYDOWN, so
    m7.type_into_field (message-level) cannot clear/commit a field here — #123 hit
    the same wall and used keybd_event; the Idle-temperature edit below reproduced
    it ('0' stayed '0', measured 09-29)."""
    import ctypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    for vk in vks:
        u.keybd_event(int(vk), 0, 0, 0)
        time.sleep(0.03)
        u.keybd_event(int(vk), 0, 2, 0)
        time.sleep(0.05)


def type_field(session, edit_hwnd, rect, text):
    """Type into the editor's spin field with REAL keys (see real_keys)."""
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.3)
    winutil.real_click_screen(cx, cy)
    time.sleep(0.5)
    real_keys(0x23)                                     # VK_END
    real_keys(*([0x08] * (len(winutil.edit_text(edit_hwnd)) + 3)))   # backspaces
    winutil.msg_text(edit_hwnd, text)
    time.sleep(0.4)
    real_keys(0x0D)                                     # VK_RETURN
    time.sleep(0.8)


def click_screen_point(pt):
    winutil.user32.SetCursorPos(int(pt[0]), int(pt[1]))
    time.sleep(0.25)
    winutil.real_click_screen(int(pt[0]), int(pt[1]))
    time.sleep(1.0)


def open_editor(session, slot=2):
    """Slot row button -> #32768 menu (first row = Edit) -> 'Material settings'."""
    slots = m8.wait_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    r = hit["picker"]
    sx, sy = winutil.client_to_screen(session.hwnd, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    winutil.real_click_screen(sx, sy)
    time.sleep(1.2)
    menu = export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32768", timeout_s=4.0)
    if not menu:
        return None
    mr = menu[2]
    winutil.user32.SetCursorPos(mr[0] + 20, mr[1] + 12)
    time.sleep(0.2)
    winutil.real_click_screen(mr[0] + 20, mr[1] + 12)
    time.sleep(1.6)
    return export_util.wait_toplevel(session.pid, lambda c, t, r2: c == "#32770", timeout_s=6.0)


def edit_children(parent):
    """[(rect, value, hwnd)] for every Edit child holding text.

    Values come from WM_GETTEXT (cross-process GetWindowTextW returns ''), so this
    sees ALL laid-out fields of the page without OCR."""
    out = []
    for _t, r, h in export_util._children_texts(parent):
        if winutil.window_class(h) != "Edit":
            continue
        v = winutil.edit_text(h).strip()
        if v:
            out.append((r, v, h))
    return out


def edit_snapshot(dlg):
    """[(rect, value)] for every Edit child of the dialog that holds text."""
    return [(r, v) for r, v, _h in edit_children(dlg[3])]


def same_field(snapshot, rect, tol=8):
    """(value, hwnd) of the field that sits where `rect` sits in `snapshot`."""
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for r, v, h in snapshot:
        if (abs(((r[0] + r[2]) // 2) - cx) <= tol
                and abs(((r[1] + r[3]) // 2) - cy) <= tol):
            return v, h
    return None, None


def row_label(parent, rect):
    """The label belonging to an Edit — either the one painted to its LEFT on the
    same line, or (sidebar layout) the one on the line ABOVE it in the same
    column. Rows are matched by geometry, not OCR, so the name stays stable when
    the page re-renders. Static text wins over the wx window wrappers that carry
    the same string as their own title (a wrapper returned 'panel' in a run,
    measured 09-29)."""
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    cands = {"left": [], "above": []}
    for t, r, h in export_util._children_texts(parent):
        ts = t.strip()
        cls = winutil.window_class(h)
        if not ts or cls == "Edit":
            continue
        ly = (r[1] + r[3]) // 2
        if abs(ly - cy) <= 10 and r[2] <= rect[0] + 4:
            cands["left"].append((ts, r, cls))
        elif 0 < cy - ly <= 45 and r[0] <= cx <= r[2] + 60:
            cands["above"].append((ts, r, cls))
    for where in ("left", "above"):
        pool = cands[where]
        if not pool:
            continue
        pool.sort(key=lambda c: (c[2] != "Static", -c[1][0]))
        return pool[0][0]
    return None


def ocr_row_name(rect):
    """The label PAINTED on the field's own line, left of it. The geometric
    lookup alone is not trustworthy: the sidebar keeps hidden pages whose controls
    overlap in screen space (a run returned 'Save to Filament Preset' for a speed
    row), so what the screen actually shows wins."""
    band = (0, rect[1] - 4, max(70, rect[0] - 6), rect[3] + 4)
    txt = " ".join(j for j, _r in ocr_lines(band, psm=6)).strip()
    return txt or None


def row_name(parent, rect):
    return ocr_row_name(rect) or row_label(parent, rect) or "?"


def snapshot_diff(a, b, tol=6):
    """[(va, vb, rect)] for edits that sit at (nearly) the same place in both
    snapshots but hold a different value — i.e. the per-tab marked parameters."""
    moved = []
    for ra, va in a:
        cx, cy = (ra[0] + ra[2]) // 2, (ra[1] + ra[3]) // 2
        for rb, vb in b:
            if (abs(((rb[0] + rb[2]) // 2) - cx) <= tol
                    and abs(((rb[1] + rb[3]) // 2) - cy) <= tol):
                if va != vb:
                    moved.append((va, vb, ra))
                break
    return moved


def tab_strip_colour(rects):
    """Mean BGR of the text rows of the given tab labels — the selected tab is
    painted with a different background, so a changed tuple proves the click on
    the High Flow label really moved the selection (guards the value comparison
    against passing vacuously when the click misses)."""
    import numpy as np
    img = screen_bgr()
    out = []
    for r in rects:
        patch = img[max(0, r[1]):r[3], max(0, r[0]):r[2]]
        if patch.size:
            out.append(tuple(int(v) for v in np.mean(patch.reshape(-1, 3), axis=0)))
    return tuple(out)


def scroll_editor(session, dlg, notches=-3):
    """Scroll the editor's own scroll area (real wheel over the dialog)."""
    cx, cy = (dlg[2][0] + dlg[2][2]) // 2, (dlg[2][1] + dlg[2][3]) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.2)
    import ctypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.mouse_event(0x0800, 0, 0, 120 * notches, 0)      # MOUSEEVENTF_WHEEL
    time.sleep(0.8)


def editor_value(session, dlg, label, scroll_tries=6):
    """(edit_hwnd, value, rect) for the editor row whose OCR line starts with label.

    Rows live in a scrollable area: 'Max volumetric speed' sits below the visible
    page for the flow pack (measured 09-29), so the dialog is scrolled until the
    row shows up."""
    for attempt in range(scroll_tries):
        lines = ocr_lines(dlg[2])
        lab = None
        for joined, rect in lines:
            if joined.lower().startswith(label.lower()):
                lab = rect
                print(f"{LOG} editor row {label!r}: {joined!r}")
                break
        if lab:
            break
        if attempt == 0:
            print(f"{LOG} editor row {label!r} not visible; scrolling the dialog")
        scroll_editor(session, dlg)
    if not lab:
        print(f"{LOG} editor row {label!r} still not found after scrolling; lines: "
              f"{[j for j, _r in ocr_lines(dlg[2])][:14]}")
        return None, None, None
    lcy = (lab[1] + lab[3]) // 2
    cands = [(h, r) for _t, r, h in export_util._children_texts(dlg[3])
             if winutil.window_class(h) == "Edit"
             and abs(((r[1] + r[3]) // 2) - lcy) < 16]
    if not cands:
        return None, None, None
    h, r = sorted(cands, key=lambda c: c[1][0])[0]
    return h, winutil.edit_text(h), r


def main() -> int:
    # EMPTY BOOT on purpose (m8f's proven path, measured 09-29): with the mixed
    # fixture project loaded, the process-preset list is filtered by the
    # project's machine (U1 0.8 nozzle), so the 0.4-nozzle flow pack
    # ('... - STD-TEST') is NOT in the list and trying to switch lands on a
    # neighbouring preset ('0.40mm Strength'). Booting without a project leaves
    # the datadir's machine in charge and the pack IS selectable.
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=None)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=None)
    try:
        if args.model is None:
            # empty boot: there is nothing to wait for — the cube is added below
            print(f"{LOG} empty boot (no fixture project)")
            results["empty boot (no fixture)"] = "PASS"
        else:
            ok, frac = m8.wait_arrival(session)
            results["model arrives"] = "PASS" if ok else "FAIL"
            if not ok:
                return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        shot("01_boot")
        # a model on the plate (the flow parameters are sliced, so the case needs
        # something to slice — m8f adds the cube the same way)
        if not m7.op_add_primitive(session, "cube"):
            results["cube created (right-click)"] = "FAIL"
            return m7.m7_verdict(results)
        results["cube created (right-click)"] = "PASS"
        time.sleep(1.0)

        # --- A. two presets: the flow-enabled combination ----------------------
        # m8f's proven recipe (its cases are GREEN on this rig):
        #   * the process switch is verified through the combo text and RETRIED —
        #     pp.switch_process_preset's row walk can mis-click a neighbouring
        #     preset (measured 09-29: it landed on '0.40mm Strength');
        #   * the filament search uses the SUFFIX ('STD-TEST'), not the full
        #     preset name: the popup rows OCR as fragments, so the long name
        #     never matches and the walk burns its budget in the top of the list.
        from m7_common import dismiss_transfer_dialog
        proc_ok, proc_now = False, ""
        for attempt in range(4):
            pp.switch_process_preset(session, PROC_STD)
            dismiss_transfer_dialog(session)
            _r, _c, proc_now = pp.find_process_preset_combo(session)
            print(f"{LOG} process preset attempt {attempt + 1}: {proc_now!r}")
            if "STD-TEST" in (proc_now or ""):
                proc_ok = True
                break
        results["#137 工艺预设 = 0.4 喷嘴流量包"] = (
            f"PASS ({proc_now})" if proc_ok else f"FAIL ({proc_now!r})")
        # the popup rows OCR TRUNCATED ("Snapmaker PLA SnapSpeed @U1 - ST..."), so the long
        # suffix never matches; "- ST" is unique among the three packs (- FL / - HF).
        fil_now = m8.switch_filament_preset(session, slot=2, target_substr="- ST")
        dismiss_transfer_dialog(session)
        print(f"{LOG} filament preset: {fil_now!r}")
        results["#137 耗材预设 = 流量测试包"] = (
            f"PASS ({fil_now})" if "STD-TEST" in (fil_now or "") else
            f"FAIL ({fil_now!r})")
        time.sleep(1.5)
        shot("02_after_presets")

        # --- B. the editor exposes the flow tabs ------------------------------
        dlg = open_editor(session, slot=2)
        if not dlg:
            results["#137 耗材编辑器出现 Standard/High Flow tab"] = "FAIL (editor did not open)"
            return m7.m7_verdict(results)
        shot("03_editor", dlg[2])
        # The flow tabs are REAL laid-out children ('[Standard flow]' / '[High flow]',
        # each ~110x18 — measured 09-29 once a flow-supporting filament is loaded);
        # OCR renders both on one line starting with '[', so the RECTS come from the
        # child enumeration and the names are matched on the child texts.
        flowtxt = [(t.strip(), r) for t, r, _h in export_util._children_texts(dlg[3])
                   if "flow" in t.strip().lower()]
        print(f"{LOG} flow-ish child texts: {flowtxt}")
        tabmap = {}
        for t, r in flowtxt:
            tl = t.strip().lower()
            if "standard" in tl and (r[2] - r[0]) > 20:
                tabmap["standard"] = (t, r)
            elif "high" in tl and (r[2] - r[0]) > 20:
                tabmap["high"] = (t, r)
        results["#137 耗材编辑器出现 Standard/High Flow tab"] = (
            f"PASS ({[tabmap[k][0] for k in ('standard', 'high') if k in tabmap]})"
            if len(tabmap) == 2 else
            f"FAIL (flow texts={flowtxt[:4]})")
        if len(tabmap) != 2:
            return m7.m7_verdict(results)
        std_pt = tabmap["standard"][1]
        hf_pt = tabmap["high"][1]

        # --- C. a flow-marked parameter differs per tab ------------------------
        # Nozzle temperature is one of the pack's two-value keys
        # (nozzle_temperature = ['210','220']) and sits on the editor's FIRST page,
        # so the comparison needs no scrolling (an earlier cut chased
        # 'Max volumetric speed' below the fold and scrolled 'Softening
        # temperature' out of view instead — measured 09-29).
        shot("04_standard_tab", dlg[2])
        # The marked parameters are exactly the ones whose VALUE differs between the
        # tabs, so they are found by DIFFERENTIAL SNAPSHOT instead of by locating a
        # row: read every Edit child of the dialog on the Standard tab, switch, read
        # again, and report the fields that moved (expected 210->220). The row
        # lookup through the OCR rect did not survive the screen-vs-child coordinate
        # mismatch — measured 09-29, the Nozzle row's edits all came back empty.
        snap_std = edit_snapshot(dlg)
        print(f"{LOG} standard tab edit values: {[v for _r, v in snap_std]}")
        tab_sel_before = tab_strip_colour((std_pt, hf_pt))
        click_screen_point(((hf_pt[0] + hf_pt[2]) // 2, (hf_pt[1] + hf_pt[3]) // 2))
        shot("04b_high_flow_tab", dlg[2])
        tab_sel_after = tab_strip_colour((std_pt, hf_pt))
        moved = snapshot_diff(snap_std, edit_snapshot(dlg))
        print(f"{LOG} fields differing between tabs: {[(a, b) for a, b, _r in moved]}")
        # A value-only comparison is vacuous if the tab click never landed, so the
        # tab strip is sampled for pixels before/after and reported as its own line.
        results["#137 点 High flow 后 tab 选中态确实切换"] = (
            "PASS (tab strip pixels changed)" if tab_sel_before != tab_sel_after
            else f"FAIL (tab strip unchanged: {tab_sel_before} vs {tab_sel_after})")
        results["#137 带标志参数在标准/高流量两模式取值不同"] = (
            "PASS (differing fields: " + ", ".join(f"{a}->{b}" for a, b, _r in moved[:4]) + ")"
            if moved else "FAIL (no edit value changed between the Standard and High Flow tabs)")
        results["#137 其中喷嘴温度 210->220（包内两档值）"] = (
            "PASS (210->220 observed)"
            if any(a == NZ_STD and b == NZ_HF for a, b, _r in moved)
            else f"FAIL (moved={[(a, b) for a, b, _r in moved][:6]})")

        # --- C2. EDIT a marked parameter: one mode must not touch the other -----
        # Reading two different numbers is not the same test as editing one of them:
        # the row asks for "两模式各自独立", so the Standard side is changed to a value
        # that appears in NEITHER mode (235) and the High Flow side must still read
        # its own 220 — then the Standard side must still hold 235 after coming back.
        std_click = lambda: click_screen_point(  # noqa: E731
            ((std_pt[0] + std_pt[2]) // 2, (std_pt[1] + std_pt[3]) // 2))
        hf_click = lambda: click_screen_point(  # noqa: E731
            ((hf_pt[0] + hf_pt[2]) // 2, (hf_pt[1] + hf_pt[3]) // 2))
        std_click()
        time.sleep(1.2)
        base_snap = edit_children(dlg[3])
        tgt_rect, tgt_h = None, None
        for r, v, h in base_snap:
            if v == NZ_STD:                      # the marked 210 field(s)
                tgt_rect, tgt_h = r, h
                break
        if tgt_h:
            tgt_name = row_name(dlg[3], tgt_rect)
            newv = "235"
            type_field(session, tgt_h, tgt_rect, newv)
            landed = winutil.edit_text(tgt_h).strip()
            print(f"{LOG} edited marked field {tgt_name!r} {NZ_STD} -> {landed!r}")
            hf_click()
            time.sleep(1.2)
            shot("04c_hf_after_edit", dlg[2])
            # Match by VALUE SET, not by position: switching tabs re-lays the rows out
            # (the positional lookup returned None, measured 09-29), but "the edit did
            # not leak" is exactly "235 is nowhere on the other side while its own 220
            # is still there".
            hf_vals = [v for _r, v, _h in edit_children(dlg[3])]
            std_click()
            time.sleep(1.2)
            std_vals = [v for _r, v, _h in edit_children(dlg[3])]
            print(f"{LOG} marked {tgt_name!r}: set {newv} on Standard -> high-flow values "
                  f"contain 235? {newv in hf_vals} (220 still there? {NZ_HF in hf_vals}); "
                  f"standard still has 235? {newv in std_vals}")
            results["#137 带标志参数改一侧不影响另一侧（两模式独立）"] = (
                f"PASS ({tgt_name}: standard {NZ_STD}->{newv}, high flow keeps its own "
                f"{NZ_HF} and never shows {newv}, standard still holds {newv})"
                if (landed == newv and newv not in hf_vals and NZ_HF in hf_vals
                    and newv in std_vals)
                else f"FAIL ({tgt_name}: landed={landed!r}, hf_has_new={newv in hf_vals}, "
                     f"hf_has_own={NZ_HF in hf_vals}, std_has_new={newv in std_vals})")
            # leave the preset as found (the run must not poison the shared packs)
            type_field(session, tgt_h, tgt_rect, NZ_STD)
            print(f"{LOG} restored {tgt_name!r} -> {winutil.edit_text(tgt_h).strip()!r}")
        else:
            results["#137 带标志参数改一侧不影响另一侧（两模式独立）"] = (
                f"FAIL (no field reading {NZ_STD} on the Standard tab)")
        hf_click()      # section D types on the High Flow side on purpose
        time.sleep(1.2)

        # --- D. an unmarked parameter syncs across tabs ------------------------
        # Idle temperature: single-valued in the pack and on the first page — the
        # "unmarked parameter" side of the row (Softening temperature sits on the
        # same page but the earlier scrolling variant kept pushing it off-screen).
        sh, soft_before, sr = editor_value(session, dlg, "Idle temperature")
        if sh and sr:
            cx, cy = (sr[0] + sr[2]) // 2, (sr[1] + sr[3]) // 2
            type_field(session, sh, sr, SOFT_NEW)
            soft_set = winutil.edit_text(sh)
            if not soft_set or soft_set.strip() == (soft_before or "").strip():
                print(f"{LOG} edit did not land ({soft_set!r}); retrying with real keys")
                type_field(session, sh, sr, SOFT_NEW)
                soft_set = winutil.edit_text(sh)
            # back to the Standard tab and read the same row
            click_screen_point(((std_pt[0] + std_pt[2]) // 2, (std_pt[1] + std_pt[3]) // 2))
            shot("05_back_standard", dlg[2])
            _h3, soft_std, _r3 = editor_value(session, dlg, "Idle temperature")
            print(f"{LOG} softening: set {soft_set!r} in HF tab -> standard tab reads {soft_std!r}")
            changed = bool(soft_set) and soft_set.strip() != (soft_before or "").strip()
            results["#137 不带标志参数(Idle temperature)两模式同步"] = (
                f"PASS ({soft_before!r} -> {soft_set!r} 两侧一致)"
                if (changed and soft_std and soft_std.strip() == soft_set.strip())
                else f"FAIL (before={soft_before!r}, set={soft_set!r}, other tab={soft_std!r})"
                     + ("" if changed else " [改值未生效→之前是假绿]"))
        else:
            results["#137 不带标志参数(Idle temperature)两模式同步"] = "FAIL (row not found)"
        # The material dialog's Cancel/OK row sits BELOW the screen (its bottom edge
        # is off-page at 1920x1080 — measured 09-29: the dialog stayed open and the
        # modal dialog then swallowed every later sidebar click, which is why the
        # process-side checks below failed in the previous run). Escape closes it;
        # the close is verified instead of assumed.
        real_keys(0x1B)
        time.sleep(1.5)
        gone = export_util.wait_toplevel(session.pid,
                                         lambda c, t, r2: c == "#32770", timeout_s=1.0)
        results["#137 耗材编辑器已关闭（Esc，Cancel 在屏幕外）"] = (
            "PASS (dialog gone)" if not gone else f"FAIL (still up: {gone[1]!r})")
        if gone:
            return m7.m7_verdict(results)
        time.sleep(0.8)
        shot("05b_back_sidebar")

        # --- E. the PROCESS side: the same two flow tabs in the Speed page ------
        # tester 09-29: 「工艺的话需要切换到速度tab」. Measured 09-29 with probes:
        #   * the sidebar Process panel shows 5 tabs (Quality/Strength/Support/
        #     Multimaterial/Others) while the Advanced switch is OFF and 6 (with
        #     **Speed**) once it is ON — Speed is an advanced-only tab;
        #   * on the Speed page a real `[Standard flow] / [High flow]` row appears
        #     (zero-size before the page renders);
        #   * the process pack declares the two-value SPEED keys
        #     (process_flow_support=['standard','high_flow'], initial_layer_speed=
        #     ['60','50'], inner_wall_speed=['550','600'], outer_wall_speed=
        #     ['550','500'] …), so switching that row must move those values.
        tabtxt = [(t.strip(), r) for t, r, _h in export_util._children_texts(session.hwnd)
                  if t.strip() in ("Quality", "Strength", "Speed", "Support",
                                   "Multimaterial", "Others")
                  and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 10]
        tabtxt = [(t, r) for t, r in tabtxt if r[1] < 660]
        print(f"{LOG} process panel tabs: {tabtxt}")
        toggled = False
        if not any(t == "Speed" for t, _r in tabtxt):
            lab = next(((t, r) for t, r, _h in export_util._children_texts(session.hwnd)
                        if t.strip() == "Advanced" and 500 <= r[1] <= 545), None)
            if lab:
                lr = lab[1]
                click_screen_point((lr[2] + 12, lr[1] + 8))   # the switch right of the label
                toggled = True
                time.sleep(2.0)
                tabtxt = [(t.strip(), r) for t, r, _h in export_util._children_texts(session.hwnd)
                          if t.strip() in ("Quality", "Strength", "Speed", "Support",
                                           "Multimaterial", "Others")
                          and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 10 and r[1] < 660]
                print(f"{LOG} tabs after Advanced ON: {tabtxt}")
            else:
                print(f"{LOG} 'Advanced' label not found")
        speed = next((r for t, r in tabtxt if t == "Speed"), None)
        results["#137 工艺面板 Advanced 后出现 Speed tab"] = (
            f"PASS (tabs: {[t for t, _r in tabtxt]})" if speed
            else f"FAIL (no Speed tab; tabs: {[t for t, _r in tabtxt]})")
        if speed:
            click_screen_point(((speed[0] + speed[2]) // 2, (speed[1] + speed[3]) // 2))
            time.sleep(1.8)
            shot("06_process_speed_tab")
            flows = [(t.strip(), r) for t, r, _h in export_util._children_texts(session.hwnd)
                     if t.strip().startswith("[") and "flow" in t.lower()
                     and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 10]
            print(f"{LOG} process-side flow tabs: {flows}")
            results["#137 工艺侧 Speed 页出现 Standard/High Flow 两个 tab"] = (
                f"PASS ({[t for t, _r in flows]})" if len(flows) >= 2
                else f"FAIL (flow tabs={flows})")
            std = next((r for t, r in flows if "standard" in t.lower()), None)
            hfr = next((r for t, r in flows if "high" in t.lower()), None)
            if std and hfr:
                # Read the visible speed page on each side and diff by position: the
                # marked parameters are exactly the rows whose value moves.
                def speed_values():
                    out = []
                    for t, r, h in export_util._children_texts(session.hwnd):
                        if winutil.window_class(h) != "Edit":
                            continue
                        if not (140 <= r[0] <= 430 and 645 <= r[1] <= 1046):
                            continue
                        v = winutil.edit_text(h).strip()
                        if v:
                            out.append(((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, v))
                    return out

                click_screen_point(((std[0] + std[2]) // 2, (std[1] + std[3]) // 2))
                time.sleep(1.8)
                shot("07_process_standard_flow")
                a_vals = speed_values()
                click_screen_point(((hfr[0] + hfr[2]) // 2, (hfr[1] + hfr[3]) // 2))
                time.sleep(1.8)
                shot("08_process_high_flow")
                b_vals = speed_values()
                print(f"{LOG} speed page values standard={[v for _x, _y, v in a_vals]}")
                print(f"{LOG} speed page values highflow={[v for _x, _y, v in b_vals]}")
                mv = []
                for x, y, v in b_vals:
                    for x2, y2, v2 in a_vals:
                        if abs(x - x2) <= 6 and abs(y - y2) <= 6:
                            if v2 != v:
                                mv.append((v2, v))
                            break
                print(f"{LOG} speed rows moved (standard->high flow): {mv}")
                # The pack's declared two-value speed keys (standard, high_flow):
                pack_pairs = {("60", "50"), ("100", "105"), ("550", "600"),
                              ("550", "500"), ("550", "200"), ("55", "50")}
                hit = [p for p in mv if p in pack_pairs]
                results["#137 工艺带标志速度参数在两模式取值不同"] = (
                    "PASS (moved rows: " + ", ".join(f"{a}->{b}" for a, b in mv[:6]) + ")"
                    if mv else "FAIL (no speed value changed between the two flow tabs)")
                results["#137 工艺速度参数命中包内两档值"] = (
                    "PASS (hit " + ", ".join(f"{a}->{b}" for a, b in hit[:4]) + ")"
                    if hit else f"FAIL (moved={mv[:8]} vs pack pairs={sorted(pack_pairs)})")
                # restore the Standard side so the fixture is left as found
                click_screen_point(((std[0] + std[2]) // 2, (std[1] + std[3]) // 2))
                time.sleep(1.0)

                # --- E2. EDIT a marked speed parameter, one mode only -------------
                # Same reasoning as C2: the row is about the two modes being
                # independent, so the Standard value is changed to one that exists in
                # neither mode (66 vs the pack's 60/50) and the High Flow side must
                # still read its own 50.
                def speed_fields():
                    return [t for t in edit_children(session.hwnd)
                            if 140 <= t[0][0] <= 430 and 645 <= t[0][1] <= 1046]

                fields = speed_fields()
                tgt = next(((r, v, h) for r, v, h in fields if v == SP_STD), None)
                if tgt:
                    tgt_rect2, tgt_h2 = tgt[0], tgt[2]
                    tgt_name2 = row_name(session.hwnd, tgt_rect2)
                    sp_new = "66"
                    type_field(session, tgt_h2, tgt_rect2, sp_new)
                    landed2 = winutil.edit_text(tgt_h2).strip()
                    print(f"{LOG} edited process field {tgt_name2!r} {SP_STD} -> {landed2!r}")
                    click_screen_point(((hfr[0] + hfr[2]) // 2, (hfr[1] + hfr[3]) // 2))
                    time.sleep(1.8)
                    shot("09_process_hf_after_edit")
                    hf_v2, _hh = same_field(speed_fields(), tgt_rect2)
                    click_screen_point(((std[0] + std[2]) // 2, (std[1] + std[3]) // 2))
                    time.sleep(1.8)
                    std_v2, _hs = same_field(speed_fields(), tgt_rect2)
                    print(f"{LOG} process {tgt_name2!r}: set {sp_new} on Standard -> "
                          f"High flow reads {hf_v2!r}, back on Standard reads {std_v2!r}")
                    results["#137 工艺带标志参数改一侧不影响另一侧"] = (
                        f"PASS ({tgt_name2}: standard {sp_new}, high flow still {hf_v2!r}, "
                        f"back to standard {std_v2!r})"
                        if (landed2 == sp_new and hf_v2 == SP_HF and std_v2 == sp_new)
                        else f"FAIL ({tgt_name2}: landed={landed2!r}, hf={hf_v2!r}, "
                             f"std={std_v2!r})")
                    type_field(session, tgt_h2, tgt_rect2, SP_STD)
                    print(f"{LOG} restored {tgt_name2!r} -> {winutil.edit_text(tgt_h2).strip()!r}")
                else:
                    results["#137 工艺带标志参数改一侧不影响另一侧"] = (
                        f"FAIL (no speed field reading {SP_STD} on the Standard side; "
                        f"fields={[(v, r[1]) for r, v, _h in fields][:14]})")
        if toggled:
            lab = next(((t, r) for t, r, _h in export_util._children_texts(session.hwnd)
                        if t.strip() == "Advanced" and 500 <= r[1] <= 545), None)
            if lab:
                click_screen_point((lab[1][2] + 12, lab[1][1] + 8))
                time.sleep(1.5)
                back = [t.strip() for t, r, _h in export_util._children_texts(session.hwnd)
                        if t.strip() in ("Quality", "Strength", "Speed", "Support",
                                         "Multimaterial", "Others")
                        and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 10 and r[1] < 660]
                results["#137 Advanced 开关已还原（收尾卫生）"] = (
                    f"PASS (tabs back to {back})" if "Speed" not in back else
                    f"FAIL (still advanced: {back})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
