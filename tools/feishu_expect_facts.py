"""Per case: the Feishu expected results 2 and 3 next to what the case's
latest SHADOW run actually exported (offline, read-only).

    python tools/feishu_expect_facts.py <repo-root> [--ids 270,273] [--suffix _std02]

The closure count says a case's values were written, the other settings kept
and the slice exported; it says nothing about the row's own expected
results. This prints, for each case, the row's text and the measured facts
of its latest SHADOW run (gcode_facts.py), so the two can be compared by
eye. It does not judge: feeds above the fixture's volumetric ceiling, for
one, are cut by the slicer and the number shown is the cut one.
"""
import glob
import io
import json
import os
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from tools.gcode_facts import gcode_facts  # noqa: E402

HARVEST = Path(os.environ.get("ORCA_BB_HARVEST", str(root / "artifacts" / "windows_mcp_harvest")))
SNAPSHOT = root / "docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/tblKjIVV8KA53kUQ_20261122_024056_171.ndjson"
out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
suffix = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--suffix=")]
suffix = suffix[0] if suffix else ""
wanted = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--ids=")]
wanted = set(wanted[0].split(",")) if wanted else None

rows = {}
if SNAPSHOT.is_file():
    for line in SNAPSHOT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            try:
                rows[int(rec["用例编号"])] = rec
            except (KeyError, TypeError, ValueError):
                pass

runs = {}
for d in glob.glob(str(HARVEST / "*") + os.sep):
    try:
        r = json.load(open(d + "result.json", encoding="utf-8-sig"))
        s = json.load(open(d + "scope.json", encoding="utf-8-sig"))
    except (OSError, ValueError):
        continue
    sc = s.get("scenario")
    if sc and sc.startswith("uia_param_") and sc.endswith(suffix) and (not suffix or len(sc) > len(suffix)):
        runs.setdefault(sc, []).append((os.path.getmtime(d), d, r.get("release_verdict"),
                                        (r.get("checks", {}).get("business") or {}).get("detail") or ""))

TAG = {"External wall": "OW", "Outer wall": "OW", "Inner wall": "IW", "Sparse infill": "Sparse",
       "Top surface": "Top", "Bottom surface": "Bottom", "Internal solid infill": "Solid",
       "Internal Bridge": "IBridge", "Bridge": "Bridge", "Overhang bridge": "OvBridge",
       "Support": "Support", "Support interface": "SupIf", "Support base": "SupBase",
       "Ironing": "Iron", "Brim": "Brim", "Skirt": "Skirt", "Prime tower": "PTower",
       "Wipe tower": "PTower", "Gap infill": "Gap", "Custom": "Custom", "Mixed": "Mixed"}


def feeds(facts, bucket, limit=4):
    parts = []
    for kind in facts["feature_order"]:
        text = facts["features"][kind]["feed"][bucket]
        if text != "-":
            parts.append("%s %s" % (TAG.get(kind, kind[:8]), text.replace("F", "").replace(" x", "x")))
    return "; ".join(parts[:limit]) + ("; +%d" % (len(parts) - limit) if len(parts) > limit else "")


def short(text, n):
    return text if len(text) <= n else text[:n - 1] + "…"


covered = 0
for sc in sorted(runs):
    cid = re.search(r'"case_id": "param_(\d+)_', sorted(runs[sc])[-1][3])
    case_no = int(cid.group(1)) if cid else None
    if wanted is not None and (case_no is None or str(case_no) not in wanted):
        continue
    mine = sorted(runs[sc])
    latest = mine[-1]
    shadow = [x for x in mine if x[2] == "SHADOW"]
    rec = rows.get(case_no) if case_no else None
    out.write("## %s%s  run %s  %s\n" % (sc, " (#%d)" % case_no if case_no else "", Path(latest[1]).name[:8], latest[2]))
    if rec:
        out.write("  飞书预期: %s\n" % short(rec["预期结果"].replace("\n", " ⏎ "), 300))
    if not shadow:
        out.write("  (no SHADOW run on record; nothing to read)\n")
        continue
    d = shadow[-1][1]
    gcode = glob.glob(d + "exports/*.gcode")
    if not gcode:
        out.write("  (no exported G-code in the harvest)\n")
        continue
    f = gcode_facts(gcode[0])
    covered += 1
    out.write("  实测: 层 %d / 首 Z %s / 顶 Z %s | 首层进给: %s\n" % (f["layers"], f["z_first"], f["z_last"], feeds(f, "first")))
    out.write("        其它层进给: %s\n" % feeds(f, "other"))
    extra = []
    extra.append("空驶首层 %s / 其它 %s" % (f["travel"]["first"], f["travel"]["other"]))
    if f["tools"]:
        extra.append("工具 %s E%s" % (f["tools"], f["e_by_tool"]))
    if f["wipe"]["moves"]:
        extra.append("擦拭 %d 次 %s" % (f["wipe"]["moves"], f["wipe"]["feed"]))
    if f["arcs"]["extruding"]:
        extra.append("挤出圆弧 %d" % f["arcs"]["extruding"])
    if len(f["widths"]) > 1 or (f["widths"] and "0.820" not in f["widths"]):
        extra.append("变宽 %d 种" % len(f["widths"]))
    if f["accel"]:
        extra.append("加速度 %s" % ",".join(sorted(f["accel"], key=float)[-4:]))
    extra.append("风扇 %s" % " ".join("%s×%d" % kv for kv in sorted(f["fan"].items())))
    if len(f["temps"]) > 8:
        extra.append("温度 %d 条指令" % len(f["temps"]))
    if "Sparse infill" in f["features"]:
        parts = ["%s=%s" % (TAG[k], f["features"][k]["e_per_mm"]) for k in ("Outer wall", "Sparse infill")
                 if k in f["features"] and f["features"][k]["e_per_mm"]]
        if parts:
            extra.append("E/mm " + " ".join(parts))
    if f["object_labels"] or f["numbered_lines"]:
        extra.append("EXCLUDE_OBJECT %d / 行号 %d" % (f["object_labels"], f["numbered_lines"]))
    out.write("        %s\n" % " | ".join(extra))
out.write("cases read: %d\n" % covered)
out.flush()
