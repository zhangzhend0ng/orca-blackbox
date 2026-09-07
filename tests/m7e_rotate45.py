#!/usr/bin/env python3
# m7e_rotate45.py — Feishu #15 (GUI业务, P1):
#   【正向】通过旋转工具旋转模型角度（Z 轴 45 度）
#
# Source facts: the Rotate gizmo (GLGizmoRotate3D, toolbar tooltip
# 'Rotate [R]') opens the ImGui manipulation window with a Rotation row of
# 3 numeric fields (X/Y/Z, m6a's field-entry lesson: focus needs a REAL
# click, text goes through wxEVT_CHAR on the canvas child). The rotation
# lands in the exported 3mf's <build><item transform> as the instance
# matrix (Format/3mf.cpp TRANSFORM_ATTR) — a Z rotation by 45° shows as
# cos/sin 0.7071 in the upper-left 3x3.
#
# Black-box path: boot -> select -> Rotate slot -> type 45 into the
# THIRD rotation field -> OCR confirms 45 -> Save Project as -> parse the
# build-item matrix: |m00| and |m10| ~= 0.7071 (45°), |det rotation| ~= 1.

import math
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m7_common as m7  # noqa: E402
from m7_common import ART  # noqa: E402

LOG = "[m7e]"
C45 = math.cos(math.radians(45.0))
TOL = 0.02


def build_item_matrix(path_3mf: Path):
    with zipfile.ZipFile(path_3mf) as z:
        data = z.read("3D/3dmodel.model").decode("utf-8", errors="replace")
    m = re.search(r"<item[^>]*\stransform=\"([^\"]+)\"", data)
    if not m:
        return None
    vals = [float(v) for v in m.group(1).split()]
    return vals if len(vals) == 12 else None


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out3mf = ART / "m7e_out.3mf"
    if out3mf.exists():
        out3mf.unlink()

    session = boot_session(args, model=args.model)
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.5)

        if not m7.select_model(session):
            results["model selected"] = "FAIL"
            return m7.m7_verdict(results)
        results["model selected"] = "PASS"

        rot_x, tip = m7.find_slot(session, lambda t: "rotate" in t)
        results["rotate gizmo located"] = (
            f"PASS ({tip!r})" if rot_x else "FAIL")
        if rot_x is None:
            return m7.m7_verdict(results)
        m7.click_slot(session, rot_x)
        time.sleep(1.0)

        boxes = (m7.gizmo_row_boxes(session, "rotation")
                 or m7.gizmo_row_boxes(session, "rotate"))
        if len(boxes) < 3:
            words = m7.words(session)
            print(f"{LOG} frame words after rotate click: "
                  f"{[w[0] for w in words][:30]}")
        print(f"{LOG} rotation row: {[(round(b[0]), round(b[1]), b[2]) for b in boxes]}")
        results["rotation row located"] = (
            f"PASS ({len(boxes)} fields)" if len(boxes) >= 3 else
            f"FAIL ({len(boxes)} fields)")
        if len(boxes) < 3:
            return m7.m7_verdict(results)

        m7.type_into_field(session, boxes[2][:2], "45",
                           old_len=len(boxes[2][2]))
        time.sleep(1.0)
        boxes2 = m7.gizmo_row_boxes(session, "rotation")
        z_text = boxes2[2][2] if len(boxes2) >= 3 else "?"
        results["Z field commits 45"] = (
            "PASS" if z_text.startswith("45") else f"FAIL (now {z_text!r})")

        ok_save = m7.save_project_as(session, out3mf)
        results["3mf exported"] = "PASS" if ok_save else "FAIL"
        if not ok_save:
            return m7.m7_verdict(results)

        mat = build_item_matrix(out3mf)
        if mat is None:
            results["matrix is a 45deg Z rotation"] = "FAIL (no build item)"
        else:
            m00, m10 = mat[0], mat[1]
            rot_ok = (abs(abs(m00) - C45) < TOL
                      and abs(abs(m10) - C45) < TOL
                      and abs(mat[2]) < TOL)
            results["matrix is a 45deg Z rotation"] = (
                f"PASS (m00={m00:.4f} m10={m10:.4f})" if rot_ok
                else f"FAIL (m00={m00:.4f} m10={m10:.4f})")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
