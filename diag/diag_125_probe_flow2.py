#!/usr/bin/env python3
# diag_125_probe_flow2.py — #125 机制探针第二轮
#
# 上一轮的教训:
#   * 辅材组合框点到了 `mm` 包装层（(241,930,361,956)），下拉没开（dropdown toplevels=[]）；
#     行内候选是 ['mm'(241,930) 'Default'(246,937) 'mm'(241,948) 'Default'(246,967)] —— 要按
#     文字挑 'Default' 那一层；
#   * `slice rejected=True` 但**横幅没有 OCR 命中** → 很可能是别的模态框（或切换到 ABS 时留下的
#     传输/重切提示）吞掉了点击，不是门禁。所以每步都要截图 + 检查有没有 #32770 挡着。
#
# 本轮：带截图、带对话框守卫，逐行把 Support 页的辅材行/控件几何打清楚，并走完
#       「辅材=高温槽 → 门禁 → 偏好开关 → 放行」这条链。

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
sys.path.insert(0, str(HERE / "diag"))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402
from diag_125_probe_aux3 import all_children, band, click_pt, ocr, toplevels  # noqa: E402
import diag_125_probe_aux3 as p3  # noqa: E402

LOG = "[p125g]"
ART = HERE / "artifacts"
user32 = winutil.user32
PREF_LABEL = "allow high/low temperature filament mixing"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8x125_{name}.png"), img)
    print(f"{LOG} shot -> m8x125_{name}.png")


def dialogs_up():
    out = []
    for t in toplevels():
        if t[0] == "#32770":
            out.append((t[1], t[2]))
    return out


def clear_dialogs(tag):
    ups = dialogs_up()
    if ups:
        print(f"{LOG} [{tag}] dialogs up: {ups}")
        for _t, r in ups:
            click_pt((r[0] + r[2]) // 2 - 40, r[3] - 30, 1.0)   # usually Cancel/No side
        time.sleep(1.0)
        print(f"{LOG} [{tag}] after clearing: {dialogs_up()}")
    return ups


def gate_state(session, tag):
    from m8c_temp_mix_gate import slice_rejected
    clear_dialogs(tag)
    rejected = slice_rejected(session)
    time.sleep(0.5)
    ups = dialogs_up()
    ocr_hit = False
    try:
        import cv2
        import numpy as np
        from harness import mix_dialog_util as mdu
        sw, sh, buf = winutil.screen_grab()
        img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
        words = mdu.ocr_words_img(img, scale=2)
        text = " ".join(w for w, *_ in words).lower()
        ocr_hit = ("high and low" in text) or ("temperature" in text and "detected" in text)
    except Exception as exc:
        print(f"{LOG} banner OCR failed: {exc}")
    print(f"{LOG} [{tag}] rejected={rejected} banner_ocr={ocr_hit} dialogs={ups}")
    shot(f"gate_{tag.replace(' ', '_')}")
    return rejected, ocr_hit, ups


def support_rows():
    """Every child of the Support page in the sidebar band, label→control."""
    return [(t, r, c) for t, r, c, _h in band(0, 430, 560, 1046) if (r[2] - r[0]) > 4]


def open_preferences():
    click_pt(85, 8, 1.4)
    pop = next((t for t in toplevels() if t[0] == "#32768"), None)
    if not pop:
        return None
    rows = ocr(pop[2])
    pref = next((r for j, r in rows if "preference" in j.lower()), None)
    if not pref:
        return None
    click_pt((pref[0] + pref[2]) // 2, (pref[1] + pref[3]) // 2, 2.5)
    return export_util.wait_toplevel(SESSION.pid, lambda c, t, r: c == "#32770", timeout_s=6.0)


def main() -> int:
    global SESSION
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    ap.add_argument("--aux", type=int, default=2, help="slot to use as the support filament")
    args = ap.parse_args()
    want_slot = args.aux
    SESSION = session = p3.SESSION = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives: {ok}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        m7.step_delete_all(session, {})
        m7.op_add_primitive(session, "cube")
        time.sleep(1.2)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], s['combo'][0]) for s in slots]}")
        shot("00_boot")

        print(f"{LOG} baseline gate: {gate_state(session, 'baseline')}")

        # slot2 -> Generic ABS（高温），cube 仍在默认槽（低温）
        now = m8.switch_filament_preset(session, slot=2, target_substr="Generic ABS")
        print(f"{LOG} slot2 -> {now!r}")
        time.sleep(1.5)
        try:
            from m7_common import dismiss_transfer_dialog
            dismiss_transfer_dialog(session)
        except Exception:
            pass
        shot("01_slot2_abs")
        print(f"{LOG} after slot2=ABS gate: {gate_state(session, 'slot2_abs_no_aux')}")

        # Support 页几何
        for t, r, _c, _h in band(0, 430, 560, 780):
            if t == "Support" and (r[2] - r[0]) > 10 and (r[3] - r[1]) > 10:
                click_pt((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.8)
                break
        shot("02_support_tab")
        rows = support_rows()
        print(f"{LOG} Support page rows:")
        for t, r, c in rows:
            print(f"{LOG}   {t[:40]!r} @{r} cls={c}")

        # 辅材：找 'Default' 那一层逐个试
        lab = next(((t, r) for t, r, _c in rows if "filament for supports" in t.lower()), None)
        print(f"{LOG} aux label: {lab}")
        if lab:
            cands = [(t.strip(), r) for t, r, c, _h in
                     band(0, 430, lab[1][3] - 4, lab[1][3] + 90)
                     if c == "wxWindowNR" and (r[2] - r[0]) > 50 and t.strip()]
            print(f"{LOG} aux value candidates: {[(t[:16], r) for t, r in cands]}")
            for t, r in cands:
                before = {x[3] for x in toplevels()}
                click_pt((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.5)
                new = [x for x in toplevels() if x[3] not in before]
                print(f"{LOG} click {t!r} @{r} -> new toplevels {[(x[0], x[1], x[2]) for x in new]}")
                if new:
                    shot(f"03_aux_dropdown_{t[:8]}")
                    for x in new:
                        rows2 = ocr(x[2])
                        print(f"{LOG}   rows: {[(j[:24], rr) for j, rr in rows2]}")
                        kids = [(y.strip(), rr) for y, rr, _h in all_children(x[3]) if y.strip()]
                        print(f"{LOG}   kids: {kids[:14]}")
                        hit = next((rr for j, rr in rows2
                                    if j.strip() == str(want_slot)), None)
                        if hit:
                            click_pt((hit[0] + hit[2]) // 2, (hit[1] + hit[3]) // 2, 2.0)
                            print(f"{LOG} picked aux = slot {want_slot}")
                            shot("04_aux_set")
                            time.sleep(1.0)
                            print(f"{LOG} after aux change: "
                                  f"{gate_state(session, 'aux_slot' + str(want_slot))}")
                    break
                time.sleep(0.4)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    except Exception as exc:
        import traceback
        print(f"{LOG} EXC {exc!r}")
        traceback.print_exc()
        shot("99_exc")
        return 1
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
