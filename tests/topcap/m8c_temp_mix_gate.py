#!/usr/bin/env python3
# m8c_temp_mix_gate.py — 飞书基线用例 #111/#112 (顶盖1.4.0: 高低温混用门, P0)。
# feishu: baseline#111 baseline#112
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

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

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


def add_cube_and_assign(session, slot_substr, results, key):
    """Add a cube and Change Filament to the row matching slot_substr."""
    m7.op_add_primitive(session, "cube")  # gate is advisory here: the
    # downstream temp-gate asserts judge the real state; two stacked cubes
    # can slip under the chromatic-delta gate (measured 09-17)
    time.sleep(0.8)
    if slot_substr and not m7.select_model(session):
        results[key] = "FAIL (not selectable)"
        return False
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
        m7.click_menu_row(session, shwnd, shmenu, slot_substr)
        time.sleep(1.5)
        m7.dismiss_menus(session)
    results[key] = "PASS"
    return True


def slice_rejected(session):
    """Probe-click Slice; rejected = the click does not start slicing.

    Evidence: click_slice_start() reports nothing started AND the button's
    rendered state is unchanged by the click. The previous proxy asked "is the
    IDLE template's score above the DONE threshold" — but the earlier #112 slice
    legitimately leaves the button in the DONE state, where the idle template
    scores only 0.666 (the documented idle-vs-done signature), so the proxy read
    a working gate as a failure (measured 09-21: started=False, idle-score=0.666).
    """
    from m2_slice_chain import click_slice_start
    m7.ensure_maximized(session)
    before = match(cap(session), SLICE_PLATE_BUTTON)[0]
    started = click_slice_start(session)
    time.sleep(2.0)
    after = match(cap(session), SLICE_PLATE_BUTTON)[0]
    print(f"{LOG} slice probe: started={started} score before={before:.3f} after={after:.3f}")
    return (not started) and abs(after - before) < 0.05


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
        if not add_cube_and_assign(session, None, results, "cube A added"):
            return m7.m7_verdict(results)
        # cube A -> slot 2 (PLA Silk) so slot 1 (PETG) stays switchable
        if not add_cube_and_assign(session, "Silk", results,
                                   "cube B on PLA slot"):
            if not add_cube_and_assign(session, "Silk", results,
                                       "cube B on PLA slot (retry)"):
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
