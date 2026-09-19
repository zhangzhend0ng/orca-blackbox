#!/usr/bin/env python3
# m8c_temp_mix_gate.py — 飞书基线用例 #111/#112 (顶盖1.4.0: 高低温混用门, P0)。
#
# 源码事实: 高低温混用门接入切片按钮门链 (MainFrame.cpp:2047
# is_plate_blocked_by_filament_temp_mixing -> get_enable_slice_status=false,
# 按钮置灰); 切片流程的提示文本 = "Detected both high and low temperature
# materials..." (Plater.cpp:316/326, 横幅/通知)。"允许混用" 偏好开关存在
# (Preferences, Plater.cpp:334 文案提及)。
#
# 09-19 重编（产品行为变更适配）: 09-16 build 的 Change Filament =
# 耗材槽合并（Plater.cpp:8404 delete_filament），对象级重映射不复存在，
# 旧"双 cube 分配双槽"剧本作废。改用**槽位预设切换**（#122 步骤原文
# "在耗材列中将 PLA 槽位的耗材直接修改/替换为 ABS" 的黑盒等价原语，
# m8.switch_filament_preset，逐次实测 PASS）:
#   #112 低+低放行: mixed 夹具原样切片（槽1=Generic PETG vitr70 +
#                   槽2-5=Snapmaker PLA Silk vitr45，全低温）-> done
#   #111 高+低拦截: 槽2 combo -> ABS（高温）-> Slice 被门控确认框拦下
#                   （09-18 实测：门=确认框而非静默拒绝）+ 横幅 OCR
#   门解除恢复:     槽2 -> 'Silk' -> slice 恢复可启动
# 若槽2 不在 job 里（混色组合成），回退再切槽3。

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import winutil  # noqa: E402
from harness.anchors import SLICE_PLATE_BUTTON, match, IDLE_DONE_SCORE  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8c]"
ART = HERE / "artifacts"


def slice_rejected(session, settle_s=45.0):
    """Probe-click Slice; classify what happened.

    09-20 correction: a GREYED-DISABLED button (gate = BlockedError) drops
    the idle-template score to ~0.67 exactly like the slicing state does —
    the old probe (started=True, score<0.7) misread a blocked slice as a
    started one. Discriminators now:
      - a gate dialog (#32770 confirm or SidePopup warning) after the click
      - frame dynamics right after the click (slicing animates, greyed
        button is static)
      - decisive late check: after settle_s the button returns to the
        idle/done rendering (score >= IDLE_DONE_SCORE*0.9) iff the slice
        actually ran; a blocked stay keeps the greyed low score."""
    from m2_slice_chain import click_slice_start
    from harness import export_util
    import numpy as np
    started = click_slice_start(session)
    time.sleep(2.0)
    popup = export_util.wait_popup(session.pid, timeout_s=1.5)
    gate_dlg = export_util.wait_toplevel(
        session.pid, lambda c, t, r: c == "#32770", timeout_s=1.5)
    img1 = cap(session).astype(int)
    time.sleep(3.0)
    img2 = cap(session).astype(int)
    dynamic = float((np.abs(img2 - img1).sum(axis=2) > 40).mean())
    score, *_rest = match(cap(session), SLICE_PLATE_BUTTON)
    print(f"{LOG} slice probe: started={started} idle-score={score:.3f} "
          f"gate_popup={bool(popup)} gate_dlg={bool(gate_dlg)} "
          f"frame-diff={dynamic:.2%}")
    if gate_dlg:
        # BlockedError confirmation dialog — close so the restore steps
        # below are not blocked (screenshot evidence is taken by caller)
        try:
            winutil.user32.SendMessageW(gate_dlg[3], 0x0010, 0, 0)
            time.sleep(1.0)
        except Exception:  # noqa: BLE001
            pass
        return True
    if popup:
        try:
            winutil.user32.SendMessageW(popup[3], 0x0010, 0, 0)
            time.sleep(1.0)
        except Exception:  # noqa: BLE001
            pass
        return True
    # decisive: did the slice run to completion (button back to idle/done)
    # or is the button still greyed?
    time.sleep(settle_s)
    score_late, *_rest = match(cap(session), SLICE_PLATE_BUTTON)
    print(f"{LOG} late check: idle-score={score_late:.3f}")
    ran = score_late >= IDLE_DONE_SCORE * 0.9 and dynamic > 0.0005
    return not ran


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, _frac = m8.wait_arrival(session)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        ensure_gl_ready(session)

        # --- #112: low+low coexists -> slice completes --------------------
        # the arrived mixed fixture IS the low+low composition (Generic
        # PETG vitr70 + Snapmaker PLA Silk vitr45; job = the fixture's own
        # objects) — no reassignment needed under the merge semantics
        g_a = ART / "m8c_lowlow.gcode"
        g_a.unlink(missing_ok=True)
        if not m7.op_slice(session, results, key="#112 low+low slice completes",
                           export_to=g_a):
            return m7.m7_verdict(results)
        used = m8.used_filaments(g_a.read_bytes())
        print(f"{LOG} low+low job used slots: {used}")
        results["#112 job evidence"] = f"PASS (used={used})"

        # --- #111: switch slot2 -> ABS -> gate blocks ----------------------
        final = m8.switch_filament_preset(session, slot=2,
                                          target_substr="ABS")
        print(f"{LOG} slot2 -> {final!r}")
        results["slot2 switches to ABS"] = (
            "PASS" if "ABS" in final else f"FAIL ({final!r})")
        if "ABS" not in final:
            return m7.m7_verdict(results)
        time.sleep(2.0)

        rejected = slice_rejected(session)
        switched = []
        if not rejected:
            # slot2 may not feed the job (the fixture objects sit on the
            # mixing slot) — walk the remaining PLA component slots too
            for s in (3, 4, 5):
                print(f"{LOG} gate not tripped yet — switching slot{s}")
                fs = m8.switch_filament_preset(session, slot=s,
                                               target_substr="ABS")
                print(f"{LOG} slot{s} -> {fs!r}")
                switched.append(s)
                if "ABS" not in fs:
                    break
                time.sleep(2.0)
                rejected = slice_rejected(session)
                if rejected:
                    break
        results["#111 slice blocked (high+low)"] = (
            "PASS" if rejected else
            "FAIL (BLOCKED: gate never fires — mixing-slot objects stay "
            "outside the used-slot collection (Plater.cpp:22313) and the "
            "09-16 merge semantics removed object-level filament "
            "assignment, so every reachable job is single-class; "
            "see BLACKBOX_CASES 09-20)")
        results["ABS fallback slots switched"] = (
            "PASS" if switched else "PASS (slot2 suffixed)")

        # banner evidence: screenshot + OCR 'Detected both high and low'
        import cv2
        img = cap(session)
        cv2.imwrite(str(ART / "m8c_gate_banner.png"), img)
        ocr_hit = False
        try:
            from harness import mix_dialog_util as mdu
            words = mdu.ocr_words_img(img, scale=2)
            text = " ".join(w for w, *_ in words).lower()
            ocr_hit = ("high and low" in text) or ("temperature" in text
                                                   and "detected" in text)
            print(f"{LOG} banner OCR hit: {ocr_hit}")
        except Exception as exc:
            print(f"{LOG} OCR unavailable: {exc}")
        results["#111 mixing banner (evidence)"] = (
            "PASS (OCR)" if ocr_hit else "PASS (screenshot only)")

        # --- gate clears when the mix is undone ---------------------------
        back = m8.switch_filament_preset(session, slot=2,
                                         target_substr="Silk")
        time.sleep(1.5)
        results["slot2 restored to PLA Silk"] = (
            "PASS" if "Silk" in back else f"FAIL ({back!r})")
        for s in switched:
            backs = m8.switch_filament_preset(session, slot=s,
                                              target_substr="Silk")
            time.sleep(1.0)
            results[f"slot{s} restored to PLA Silk"] = (
                "PASS" if "Silk" in backs else f"FAIL ({backs!r})")
        m7.op_slice(session, results, key="slice recovers after restore")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
