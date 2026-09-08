#!/usr/bin/env python3
# m7f_scale120.py — Feishu #16 (GUI业务, P1):
#   【正向】等比例缩放模型到指定比例（120%）+ 还原
#
# Source facts: the Scale gizmo (GLGizmoScale3D, tooltip 'Scale [S]') opens
# the manipulation window with a Scale row (% fields, uniform-linked) and a
# Reset control; the uniform scale lands in the exported 3mf build-item
# matrix as ~1.2 column norms in the upper-left 3x3.
#
# Black-box path: boot -> select -> Scale slot -> type 120 into the first
# Scale field -> OCR confirms 120 -> (reset: the window's Reset button if
# OCR finds one, else typing 100 — both restore; recorded which) -> OCR
# back to 100 -> Save Project as -> parse the matrix: all three column
# norms ~= 1.2.

import math
import re
import time
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
from m7_common import ART  # noqa: E402

LOG = "[m7f]"
TOL = 0.02


def build_item_matrix(path_3mf: Path):
    with zipfile.ZipFile(path_3mf) as z:
        data = z.read("3D/3dmodel.model").decode("utf-8", errors="replace")
    m = re.search(r"<item[^>]*\stransform=\"([^\"]+)\"", data)
    if not m:
        return None
    vals = [float(v) for v in m.group(1).split()]
    return vals if len(vals) == 12 else None


def col_norms(mat):
    cols = []
    for c in range(3):
        cols.append(math.sqrt(mat[c] ** 2 + mat[c + 4] ** 2 + mat[c + 8] ** 2))
    return cols


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out3mf = ART / "m7f_out.3mf"
    if out3mf.exists():
        out3mf.unlink()

    session = boot_session(args, model=args.model)
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.5)

        # cache the PRE-selection slot x: after select_model the toolbar
        # tooltips OCR as garbage (measured twice 09-08), while the layout
        # itself does not move on selection
        sc_x, tip = m7.find_slot(session, lambda t: "scale" in t)
        results["scale gizmo located"] = (
            f"PASS ({tip!r})" if sc_x else "FAIL")
        if sc_x is None:
            return m7.m7_verdict(results)

        if not m7.select_model(session):
            results["model selected"] = "FAIL"
            return m7.m7_verdict(results)
        results["model selected"] = "PASS"
        time.sleep(1.0)

        m7.click_slot(session, sc_x)
        time.sleep(1.0)

        boxes = (m7.gizmo_row_boxes(session, "scale")
                 or m7.gizmo_row_boxes(session, "size"))
        if not boxes:
            words = m7.words(session)
            print(f"{LOG} frame words after scale click: "
                  f"{[w[0] for w in words][:30]}")
        print(f"{LOG} scale row: {[(round(b[0]), round(b[1]), b[2]) for b in boxes]}")
        results["scale row located"] = (
            f"PASS ({len(boxes)} fields)" if boxes else "FAIL (no row)")
        if not boxes:
            return m7.m7_verdict(results)

        m7.type_into_field(session, boxes[0][:2], "120",
                           old_len=len(boxes[0][2]))
        time.sleep(1.0)
        boxes2 = m7.gizmo_row_boxes(session, "scale")
        cur = boxes2[0][2] if boxes2 else "?"
        results["scale commits 120"] = (
            "PASS" if cur.startswith("120") else f"FAIL (now {cur!r})")

        # --- restore: Reset button if present, else type 100 ---
        words = m7.words(session)
        reset_hit = next((w for w in words
                          if w[0].lower().startswith("reset")), None)
        restored = False
        if reset_hit:
            m7.click_slot(session, reset_hit[1] + 12, cy=reset_hit[2] + 6)
            restored = True
            print(f"{LOG} reset button clicked")
        else:
            b3 = m7.gizmo_row_boxes(session, "scale")
            if b3:
                m7.type_into_field(session, b3[0][:2], "100",
                                   old_len=len(b3[0][2]))
                restored = True
                print(f"{LOG} restore via typing 100")
        results["restore to original size"] = (
            "PASS (reset button)" if restored and reset_hit else
            "PASS (typed 100)" if restored else "FAIL")
        time.sleep(1.0)
        b4 = m7.gizmo_row_boxes(session, "scale")
        cur4 = b4[0][2] if b4 else "?"
        results["scale reads 100 after restore"] = (
            "PASS" if cur4.startswith("100") else f"FAIL (now {cur4!r})")

        # --- matrix evidence at 120 (typed before restore; re-apply) ---
        m7.type_into_field(session, b4[0][:2], "120",
                           old_len=len(b4[0][2])) if b4 else None
        time.sleep(1.0)
        ok_save = m7.save_project_as(session, out3mf)
        results["3mf exported"] = "PASS" if ok_save else "FAIL"
        if not ok_save:
            return m7.m7_verdict(results)

        mat = build_item_matrix(out3mf)
        if mat is None:
            results["matrix scale ~= 1.2"] = "FAIL (no build item)"
        else:
            norms = col_norms(mat)
            ok_n = all(abs(n - 1.2) < TOL for n in norms)
            results["matrix scale ~= 1.2"] = (
                "PASS (%.3f/%.3f/%.3f)" % tuple(norms) if ok_n
                else "FAIL (%.3f/%.3f/%.3f)" % tuple(norms))
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
