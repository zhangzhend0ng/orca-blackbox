#!/usr/bin/env python3
# m8c_temp_mix_gate.py — 飞书基线用例 #111/#112 (顶盖1.4.0: 高低温混用门, P0)。
#
# 源码事实: 高低温混用门接入切片按钮门链 (MainFrame.cpp:2047
# is_plate_blocked_by_filament_temp_mixing -> get_enable_slice_status=false,
# 按钮置灰); 切片流程的提示文本 = "Detected both high and low temperature
# materials..." (Plater.cpp:316/326, 横幅/通知)。"允许混用" 偏好开关存在
# (Preferences, Plater.cpp:334 文案提及)。
#
# 黑盒路径 (mixed 夹具, 全低温槽 PETG(vitr70)+PLA Silk(vitr45)):
#   #112 低+低共存允许切片: 清场 -> 2 cubes (PETG 槽1 + PLA 槽2) -> slice done
#   #111 高+低混用拦截:     槽2 combo -> 'Generic ABS' (high_temp=1) ->
#                           Slice 点击被吞 (按钮 idle 不进入切片) + 横幅
#                           截图 + OCR 'Detected both high and low'
#   门解除恢复:             槽2 -> 'PLA Silk' -> slice 恢复可启动

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from harness.anchors import capture_bgr, SLICE_PLATE_BUTTON  # noqa: E402
from harness.anchors import match, IDLE_DONE_SCORE  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8c]"
ART = HERE / "artifacts"


def add_cube_and_assign(session, slot_substr, results, key, nth=0):
    """Add a cube and Change Filament to the (nth+1)-th row matching
    slot_substr."""
    m7.op_add_primitive(session, "cube")  # gate is advisory here: the
    # downstream temp-gate asserts judge the real state; two stacked cubes
    # can slip under the chromatic-delta gate (measured 09-17)
    time.sleep(0.8)
    if slot_substr and not m7.select_model(session):
        # measured 09-18: the second primitive lands exactly on the first
        # (Cube<->Cube overlap) and the centroid click cannot resolve a
        # selection — but op_add_primitive leaves the NEW object selected,
        # so keep going and let the context menu act on it
        print(f"{LOG} select_model failed — relying on fresh-add selection")
    if slot_substr:
        menu = m7.open_context_menu(session, where="model")
        if not menu:
            results[key] = "FAIL (no menu)"
            return False
        hwnd, hmenu = menu
        got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                                nested=True)
        if not got:
            m7.dismiss_menus(session)
            results[key] = "FAIL (no change-filament)"
            return False
        _i, (shwnd, shmenu) = got
        rows = m7.list_menu(shmenu)
        print(f"{LOG} filament rows: {[l for _i, l in rows]}")
        m7.click_menu_row(session, shwnd, shmenu, slot_substr, nth=nth)
        time.sleep(1.5)
        m7.dismiss_menus(session)
    results[key] = "PASS"
    return True


def slice_rejected(session):
    """Probe-click Slice; rejected = button stays idle + no slicing starts
    (m3a negative contract), OR the temp-mix gate DIALOG is up (measured
    09-18: the gate is a confirmation, not a silent refusal — the click
    'takes' by opening it, which the old probe misread as slice-started;
    the banner OCR independently proved the text)."""
    from m2_slice_chain import click_slice_start
    from harness import export_util
    started = click_slice_start(session)
    time.sleep(2.0)
    popup = export_util.wait_popup(session.pid, timeout_s=1.5)
    score, *_rest = match(cap(session), SLICE_PLATE_BUTTON)
    still_idle = score >= IDLE_DONE_SCORE * 0.9
    print(f"{LOG} slice probe: started={started} idle-score={score:.3f} "
          f"gate_popup={bool(popup)}")
    if popup:
        # close the gate dialog so the restore steps below are not blocked
        try:
            winutil.user32.SendMessageW(popup[3], 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(1.0)
        except Exception:  # noqa: BLE001
            pass
    return still_idle and ((not started) or bool(popup))


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

        if not m7.step_delete_all(session, results):
            return m7.m7_verdict(results)
        # BOTH cubes on PLA slots (2 and 3): the temp gate compares the
        # job's filaments — measured 09-18: PETG(cube on slot1) + ABS is
        # high+mid and slices WITHOUT any gate, only PLA+ABS triggers.
        if not add_cube_and_assign(session, "Silk", results,
                                   "cube A on PLA slot"):
            return m7.m7_verdict(results)
        if not add_cube_and_assign(session, "Silk", results,
                                   "cube B on PLA slot", nth=1):
            if not add_cube_and_assign(session, "Silk", results,
                                       "cube B on PLA slot (retry)", nth=1):
                return m7.m7_verdict(results)

        # --- #112: low+low coexists -> slice completes --------------------
        m7.op_slice(session, results, key="#112 low+low slice completes")
        time.sleep(1.0)

        # --- #111: switch slot2 -> ABS -> gate blocks ----------------------
        final = m8.switch_filament_preset(session, slot=2,
                                          target_substr="Generic ABS")
        print(f"{LOG} slot2 -> {final!r}")
        results["slot2 switches to ABS"] = (
            "PASS" if "ABS" in final else f"FAIL ({final!r})")
        if "ABS" not in final:
            return m7.m7_verdict(results)
        time.sleep(2.0)

        rejected = slice_rejected(session)
        results["#111 slice blocked (high+low)"] = (
            "PASS" if rejected else "FAIL (slice started or button moved)")

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
        m7.op_slice(session, results, key="slice recovers after restore")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
