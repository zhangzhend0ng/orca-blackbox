#!/usr/bin/env python3
"""diag_137_probe_behavior.py — for #137, MEASURE the flow-mode semantics of a
process parameter instead of trusting the (painted, unreadable) flow-nozzle icon.

Experiment: read Layer height in Standard -> set 0.30 -> switch Flow to High Flow
-> read again -> switch back -> read again. Independent means the value set in one
mode does NOT appear in the other; synced means it does.

    C:\Python311\python.exe diag\diag_137_probe_behavior.py
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[d137b]"
OUT = HERE / "artifacts" / "m8x_137"


def screen_bgr():
    sw, sh, buf = winutil.screen_grab()
    return cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                        cv2.COLOR_BGRA2BGR)


def shot(name):
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / (name if name.endswith(".png") else name + ".png")), screen_bgr())
    print(f"{LOG} shot -> {name}")


def row_field(session, label):
    """(edit hwnd, screen rect, value) for the process row labelled `label`.

    The process panel lives in the SIDEBAR (client coordinates) and its rows are
    label + spin on the same line; the edit is enumerated as a child, so the
    field is found structurally and located by the label's OCR rect."""
    img = screen_bgr()
    # psm 6 (uniform block): the default psm 3 silently DROPS rows next to the
    # panel's divider art — the first run read only the sidebar's upper half and
    # never saw 'Layer height' (mdu.ocr_words_img documents this trap).
    words = mdu.ocr_words_img(img[0:1040, 0:520], scale=2, psm=6)
    # OCR splits a label into SEPARATE words ('Layer' + 'height'), so rows are
    # matched on the joined per-line text — and the row (not the section header)
    # is the one whose line carries a value after the label.
    lines = {}
    for t, x, y, w, h in words:
        key = None
        for k in lines:
            if abs(k - y) <= 12:
                key = k
                break
        key = y if key is None else key
        lines.setdefault(key, []).append((x, t))
    lab = None
    for y in sorted(lines):
        parts = [t for _x, t in sorted(lines[y])]
        joined = " ".join(parts)
        if (joined.lower().startswith(label.lower())
                and any(ch.isdigit() for ch in joined)):
            xs = [x for x, _t in sorted(lines[y])]
            lab = (min(xs), y, max(xs) + 40, y + 16)
            print(f"{LOG} matched row: {joined!r} at y={y}")
            break
    if not lab:
        print(f"{LOG} label {label!r} not found; OCR rows in the process area: "
              f"{[' '.join(t for _x, t in sorted(v)) for k, v in sorted(lines.items()) if k > 640][:12]}")
        return None, None, None
    lcy = (lab[1] + lab[3]) // 2
    cands = []
    for _t, r, h in export_util._children_texts(session.hwnd):
        if winutil.window_class(h) != "Edit":
            continue
        if abs(((r[1] + r[3]) // 2) - lcy) < 14 and r[0] > lab[0]:
            cands.append((h, r))
    if not cands:
        print(f"{LOG} no Edit on the {label!r} row (label rect {lab})")
        return None, None, None
    h, r = sorted(cands, key=lambda c: c[1][0])[0]
    print(f"{LOG} {label!r}: label={lab} edit={r} value={winutil.edit_text(h)!r}")
    return h, r, winutil.edit_text(h)


def set_field(session, edit_hwnd, rect, text):
    """Type into a SIDEBAR panel field with m7.type_into_field.

    Hand-rolled clearing (real VK_END + backspaces, then WM_CHAR digits) cleared
    the value but left the field EMPTY — the panel spin is not the same control
    type as the #123 dialog edit, and the app then raised 'Snapmaker Orca error'
    on the next flow switch (measured 09-29). type_into_field is the helper built
    for exactly these panel fields: client coordinates, a real click, and several
    input recipes with read-back retries."""
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    m7.type_into_field(session, (cx, cy), text, old_len=len(winutil.edit_text(edit_hwnd)))


def flow_mode(session):
    """Current flow mode via the nozzle section's readout (the control is a
    wxWindowNR, not a ComboBox — the first cut looked for ComboBox and read '')."""
    try:
        return m8.nozzle_reads(session).get("flow") or ""
    except Exception as exc:  # noqa: BLE001
        print(f"{LOG} nozzle_reads failed: {exc}")
        return ""


def switch_flow(session, target):
    """Switch the nozzle Flow combo with a REAL click on its arrow, falling back
    to the message click m8.switch_flow_combo uses.

    m8's helper is message-level only; on this build/state it reported
    'popup did not open' four times in a row (measured 09-29) while the same
    control opens fine for m8f/m8g — the #123 lesson (real click for widgets that
    ignore injected messages) applies here too."""
    for attempt in range(3):
        reads = m8.nozzle_reads(session)
        rect = reads.get("flow_rect")
        if not rect:
            print(f"{LOG} flow combo not found")
            return ""
        cx, cy = rect[2] - 12, (rect[1] + rect[3]) // 2
        if attempt == 0:
            sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            winutil.real_click_screen(sx, sy)
        else:
            winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            print(f"{LOG} flow attempt {attempt + 1}: popup did not open")
            time.sleep(0.6)
            continue
        if m8.click_popup_row(session, popup[2], target, popup_hwnd=popup[3]):
            time.sleep(1.0)
            now = m8.nozzle_reads(session).get("flow") or ""
            print(f"{LOG} flow -> {now!r}")
            return now
    return m8.nozzle_reads(session).get("flow") or ""


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrives={ok} ({frac:.3%})")
        m7.ensure_maximized(session)
        m8.wait_slots(session)
        time.sleep(1.0)
        shot("10_panel")

        eh, er, before = row_field(session, "Layer height")
        if not eh:
            return 1
        print(f"{LOG} flow combo before: {flow_mode(session)!r}")
        set_field(session, eh, er, "0.30")
        shot("11_after_set")
        # read back through the SAME edit control: after the edit the OCR line
        # came back as 'Layer eight' (no digit) and the OCR-based matcher failed
        # even though the value was there — the control is the reliable reader.
        after_set = winutil.edit_text(eh)
        print(f"{LOG} standard after set (via edit): {after_set!r}")
        if "0.3" not in after_set:
            print(f"{LOG} retrying the edit with recipe 2")
            m7.type_into_field(session, ((er[0] + er[2]) // 2, (er[1] + er[3]) // 2),
                               "0.30", old_len=4, recipe=2)
            after_set = winutil.edit_text(eh)
            print(f"{LOG} after retry: {after_set!r}")

        # switch to High Flow and read the same row
        final = switch_flow(session, "High Flow")
        print(f"{LOG} switch_flow -> {final!r}")
        m8.confirm_flow_dialog(session)
        time.sleep(1.5)
        shot("12_high_flow")
        in_hf = winutil.edit_text(eh)
        print(f"{LOG} HIGH FLOW Layer height (via edit): {in_hf!r}")

        # back to Standard
        final2 = switch_flow(session, "Standard")
        m8.confirm_flow_dialog(session)
        time.sleep(1.5)
        shot("13_back_standard")
        back = winutil.edit_text(eh)
        print(f"{LOG} back to Standard (via edit): {back!r} (combo {final2!r})")
        print(f"{LOG} VERDICT-MEASURE: set 0.30 in Standard -> HF shows {in_hf!r} "
              f"-> back in Standard {back!r}; "
              f"{'SYNCED' if in_hf and '0.30' in in_hf else 'INDEPENDENT'}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
