#!/usr/bin/env python3
# m7t84.py — Feishu #84 主流程-模板: 打印机预设更改耗材合并
#   O-01 open -> O-03 printer preset change -> M-01 import STL -> M-02
#   slice -> O-02 close
# O-03 drives the SIDEBAR printer-preset combo (self-drawn rows probed at
# the m3e 28px pitch; the printer combo is the one whose text is exactly
# the U1 printer name, in the sidebar's top band). The 耗材合并 sub-step's
# black-box surface (mixing 'Merge with' / filament removal) is covered by
# m4d (mapped separately) and not duplicated here — recorded PARTIAL in the
# mapping. Asserts: printer combo switches, import lands, slice completes.

import sys
import ctypes
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from harness import export_util, winutil  # noqa: E402
from m3_common import HERE as ROOT, MIXED_3MF  # noqa: E402
import m7_common as m7  # noqa: E402

LOG = "[m7t84]"
STL = ROOT / "fixtures" / "Prusa.stl"


def find_printer_combo(session):
    """The sidebar printer combo: a child whose text contains the printer
    name but NOT a process-preset marker, in the sidebar's upper band."""
    hits = []
    for text, rect, ch in export_util._children_texts(session.hwnd):
        if "Snapmaker U1" in text and "Standard" not in text \
                and rect[1] < 400 and rect[3] - rect[1] < 60:
            hits.append((text, rect, ch))
    return hits[0] if hits else None


def switch_printer_preset(session, target_substr="0.4 nozzle") -> str:
    """Click through the printer combo popup rows until the text flips.
    Returns the final combo text ('' on failure)."""
    import ctypes
    user32 = ctypes.WinDLL("user32")
    hit = find_printer_combo(session)
    if not hit:
        print(f"{LOG} printer combo not found")
        return ""
    text, rect, ch = hit
    print(f"{LOG} printer combo: {text!r} @y{rect[1]}")
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for attempt in range(6):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            return text
        pr = popup[2]
        px, py = (pr[0] + pr[2]) // 2, pr[1] + 14 + attempt * 28
        winutil.msg_click_screen(px, py)
        time.sleep(0.8)
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(ch, buf, 256)
        text = buf.value
        if target_substr in text:
            return text
    return text


def import_stl(session):
    _ok, dlg = m7.file_menu_dispatch(session, "stl", expect_dialog=True,
                                     via="Import")
    if not dlg:
        return False
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(STL))
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)
    time.sleep(2.0)
    return True


def steps(session, results):
    if not m7.step_model_arrives(session, results):
        return
    final = switch_printer_preset(session)
    results["printer preset switches"] = (
        f"PASS ({final!r})" if "0.4 nozzle" in final
        else f"FAIL ({final!r})")
    results["import dispatches"] = (
        "PASS" if import_stl(session) else "FAIL")
    if not m7.step_model_arrives(session, results, timeout_s=120,
                                 min_frac=0.0025):
        return
    m7.op_slice(session, results)


if __name__ == "__main__":
    raise SystemExit(m7.run_template_case(steps, MIXED_3MF))
