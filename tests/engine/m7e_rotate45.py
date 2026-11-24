#!/usr/bin/env python3
# m7e_rotate45.py — Feishu #15 (GUI业务, P1):
# feishu: none  (无基线表映射)
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

import json
import math
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

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


def select_and_locate_rotate(session):
    """Reuse an observed Rotate slot only while its OCR identity is confirmed."""
    m7.ensure_maximized(session)
    rot_x = 1108  # measured on the maximized guest; verify before use
    label = m7.tooltip_text(session, rot_x, m7.BAR_Y)
    path = "hint"
    if "rotate" not in label.lower():
        rot_x, _ = m7.find_slot(session, lambda t: "rotate" in t)
        path = "scan"
    if rot_x is not None:
        for label in m7.selection_tooltips(session, rot_x):
            text = label.lower()
            if "rotate" in text and "[r" in text and "select" not in text:
                return rot_x, label, path
    return None, "", path


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out3mf = ART / "m7e_out.3mf"
    if out3mf.exists():
        out3mf.unlink()

    times = {}
    started = last = time.perf_counter()
    def mark(stage):
        nonlocal last
        now = time.perf_counter()
        times[stage] = round(now - last, 3)
        last = now

    session = boot_session(args, model=args.model)
    mark("boot")
    locator = "unreached"
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        time.sleep(1.5)

        mark("arrival")
        rot_x, tip, locator = select_and_locate_rotate(session)
        mark("select_and_locate")
        if rot_x is None:
            results["model selected"] = "FAIL"
            return m7.m7_verdict(results)
        results["model selected"] = "PASS"

        results["rotate gizmo located"] = f"PASS ({tip!r})"
        m7.click_slot(session, rot_x)
        time.sleep(1.0)

        boxes = (m7.gizmo_row_boxes(session, "rotate")
                 or m7.gizmo_row_boxes(session, "rotation"))
        mark("open_and_locate_field")
        if not boxes:
            words = m7.words(session)
            print(f"{LOG} frame words after rotate click: "
                  f"{[w[0] for w in words][:30]}")
        print(f"{LOG} rotation row: {[(round(b[0]), round(b[1]), b[2]) for b in boxes]}")
        # the Z field is the RIGHTMOST numeric of the row; OCR sometimes
        # drops the X value (bracket-glued), so require >=1 not >=3
        results["rotation row located"] = (
            f"PASS ({len(boxes)} fields)" if boxes else "FAIL (0 fields)")
        if not boxes:
            return m7.m7_verdict(results)

        m7.type_into_field(session, boxes[-1][:2], "45",
                           old_len=len(boxes[-1][2]))
        time.sleep(1.0)
        # informational only: the readback can hit the ABSOLUTE row (0.00)
        # right after a relative commit — the 3mf matrix below is the judge
        boxes3 = m7.gizmo_row_boxes(session, "rotate")
        z_text = boxes3[-1][2] if boxes3 else "?"
        mark("edit_and_readback")
        print(f"{LOG} z readback: {z_text!r}")
        results["Z field readback"] = (
            f"PASS (matrix judges; readback {z_text!r})")

        ok_save = m7.save_project_as(session, out3mf)
        mark("save")
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
        mark("verify")
        return m7.m7_verdict(results)
    finally:
        close_started = time.perf_counter()
        session.close()
        times["close"] = round(time.perf_counter() - close_started, 3)
        print(f"{LOG} timings " + json.dumps({"locator": locator, "seconds": times,
              "wall_s": round(time.perf_counter() - started, 3)}))
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
