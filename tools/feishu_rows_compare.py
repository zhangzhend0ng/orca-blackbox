"""Each Feishu parameter row's run on its own model, next to its fixture's
baseline, reduced to the facts that row's expected results talk about.

    python tools/feishu_rows_compare.py <repo-root> [--ids 263,264] [--all]

For every row: the fixture its precondition names (tools/feishu_model_fixtures),
the latest harvested run of its scenario on that fixture, and the same
fixture's save-only baseline. Both exports are read with tools/gcode_facts.py;
each fact is printed "baseline -> run", so a change the row caused stands out
(`bridge direction 0 -> 45`, `support blocks 0 -> 549`). Which facts are
printed is chosen by the row's own wording (speeds, support, bridge, layers,
fan, tool, skirt, brim, ironing, width / E); --all prints every fact.

It does not judge: it puts the row's expected results next to the numbers.
The harvest is looked up under ORCA_BB_HARVEST, else under
<repo-root>/artifacts/windows_mcp_harvest. Read-only."""
import glob
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root = sys.argv[1]
sys.path.insert(0, root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feishu_model_fixtures import feishu_rows, row_plan  # noqa: E402
from gcode_facts import gcode_facts  # noqa: E402
from harness.agent_protocol import BASELINES, FIXTURE_SUFFIXES  # noqa: E402

HARVEST = os.environ.get("ORCA_BB_HARVEST") or os.path.join(root, "artifacts", "windows_mcp_harvest")
SPEEDS = ("Outer wall", "Inner wall", "Sparse infill", "Top surface", "Internal solid infill", "Bridge", "Support",
          "Support interface", "Ironing")
BLOCKS = ("Support", "Support interface", "Bridge", "Internal Bridge", "Skirt", "Brim", "Prime tower", "Ironing",
          "Overhang wall")
SHORT = {"Outer wall": "OW", "Inner wall": "IW", "Sparse infill": "SI", "Top surface": "Top", "Gap infill": "Gap",
         "Internal solid infill": "Solid", "Bridge": "Br", "Internal Bridge": "IBr", "Support": "Sup",
         "Support interface": "SupIf", "Ironing": "Iron", "Skirt": "Skirt", "Brim": "Brim", "Prime tower": "Tower",
         "Overhang wall": "OvW", "Bottom surface": "Bot"}


def latest(scenario):
    best = None
    for d in glob.glob(os.path.join(HARVEST, "*") + os.sep):
        try:
            scope = json.load(open(d + "scope.json", encoding="utf-8-sig"))
            proc = json.load(open(d + "process.json", encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if scope.get("scenario") == scenario and proc.get("started_at_ns"):
            if best is None or proc["started_at_ns"] > best[0]:
                best = (proc["started_at_ns"], d)
    return best[1] if best else None


def facts_of(d):
    gcode = glob.glob(d + "exports/*.gcode") if d else []
    return (gcode_facts(gcode[0]), os.path.basename(d.rstrip(os.sep))[:8]) if gcode else (None, None)


def feeds(f, name, band="other", n=3):
    row = (f or {}).get("features", {}).get(name)
    return "/".join(str(feed) for feed, _moves in row["feeds"][band][:n]) if row else "-"


def blocks(f, name):
    row = (f or {}).get("features", {}).get(name)
    return str(row["blocks"]) if row else "0"


def direction(f, name):
    row = (f or {}).get("features", {}).get(name)
    return (row["angle_top"].split(",")[0].replace(" deg", "d") if row and row["angle_top"] else "-")


def tools_of(f, names=("Support", "Support interface", "Prime tower")):
    parts = []
    for name in names:
        row = (f or {}).get("features", {}).get(name)
        if row and row["e_by_tool"]:
            parts.append("%s=%s" % (SHORT[name], ",".join("T%s" % t for t in row["e_by_tool"])))
    return " ".join(parts) or "-"


def e_per_mm(f, names=("Outer wall", "Inner wall", "Sparse infill", "Top surface", "Bot")):
    return " ".join("%s=%.4f" % (SHORT.get(name, name[:3]), (f or {}).get("features", {}).get(name, {}).get("e_per_mm") or 0)
                    for name in names)


def moves(f, name):
    row = (f or {}).get("features", {}).get(name)
    return str(row["moves"]) if row else "0"


def focus(text):
    keys = set()
    if any(k in text for k in ("F", "速度", "mm/s", "流量")):
        keys.add("speeds")
    if any(k in text for k in ("支撑", "耗材", "工具", "擦料塔", "塔", "冲刷")):
        keys.add("support")
    if any(k in text for k in ("桥", "搭桥")):
        keys.add("bridge")
    if any(k in text for k in ("层", "Z=", "高度", "总高")):
        keys.add("layers")
    if "风扇" in text or "M106" in text:
        keys.add("fan")
    if any(k in text for k in ("裙边", "风挡")):
        keys.add("skirt")
    if "Brim" in text:
        keys.add("brim")
    if "熨烫" in text:
        keys.add("ironing")
    if any(k in text for k in ("线宽", "E/mm", "E按", "流量")):
        keys.add("emm")
    if any(k in text for k in ("空驶", "绕行")):
        keys.add("travel")
    if any(k in text for k in ("圆弧", "G2", "G3")):
        keys.add("arcs")
    if any(k in text for k in ("注释", "行号", "标签", "排除", "逐个", "逐件", "螺旋", "单墙")):
        keys.add("special")
    if "加速度" in text:
        keys.add("accel")
    if "抖动" in text or "Jerk" in text:
        keys.add("jerk")
    return keys or {"speeds", "support"}


def main():
    show_all = "--all" in sys.argv
    wanted = set(sys.argv[sys.argv.index("--ids") + 1].split(",")) if "--ids" in sys.argv else None
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    rows = feishu_rows(root)
    tally = {"shadow": 0, "non_green": [], "no_run": [], "no_fixture": [], "no_scenario": []}
    for suffix, items in row_plan(root).items():
        for number, scenario in items:
            if wanted and str(number) not in wanted:
                continue
            rec = rows[number]
            expected = rec["预期结果"]
            if not scenario:
                tally["no_scenario"].append(number)
                out.write("#%d  (no scenario)  %s\n" % (number, expected.replace("\n", " / ")[:120]))
                continue
            if not suffix or suffix not in FIXTURE_SUFFIXES:
                tally["no_fixture"].append(number)
                out.write("#%d  %s  NO FIXTURE for its model\n" % (number, scenario))
                continue
            d = latest(scenario + suffix)
            if not d:
                tally["no_run"].append(number)
                out.write("#%d  %s%s  NOT RUN\n" % (number, scenario, suffix))
                continue
            result = json.load(open(d + "result.json", encoding="utf-8-sig"))
            worker = json.load(open(d + "native_worker.json", encoding="utf-8-sig"))
            verdict = result.get("release_verdict")
            f, run = facts_of(d)
            base_dir = latest(BASELINES[suffix][0])
            b, base_run = facts_of(base_dir)
            if verdict == "SHADOW":
                tally["shadow"] += 1
            else:
                tally["non_green"].append("%d(%s)" % (number, (worker.get("error") or "")[:26]))
            out.write("#%d %s%s %s %s run %s (baseline %s)\n" % (number, scenario, suffix, verdict,
                                                                 "" if verdict == "SHADOW" else (worker.get("error") or "")[:50], run, base_run))
            keys = focus(expected) if f else set()
            parts = []
            if keys & {"layers"} or show_all:
                parts.append("layers %d->%d first Z %s->%s last Z %s->%s" % (
                    b["layers"], f["layers"], b["z_first"], f["z_first"], b["z_last"], f["z_last"]))
            if keys & {"speeds"} or show_all:
                same, changed = [], []
                for name in SPEEDS:
                    if name in f["features"] or name in b["features"]:
                        before, after = feeds(b, name), feeds(f, name)
                        (changed if before != after else same).append(
                            "%s %s->%s" % (SHORT[name], before, after) if before != after else SHORT[name])
                parts.append("; ".join(changed) + (" | unchanged: %s" % " ".join(same) if same and changed else
                                                 "feeds unchanged" if same else ""))
                if b["travel"]["other"] != f["travel"]["other"] or b["travel"]["first"] != f["travel"]["first"]:
                    parts.append("travel first %s->%s | other %s->%s" % (
                        b["travel"]["first"], f["travel"]["first"], b["travel"]["other"], f["travel"]["other"]))
            if keys & {"support"} or show_all:
                parts.append("blocks " + " ".join("%s %s->%s" % (SHORT[n], blocks(b, n), blocks(f, n))
                                                   for n in BLOCKS if n in f["features"] or n in b["features"]))
                if sorted(b["e_by_tool"]) != sorted(f["e_by_tool"]) or b["tool_changes"] != f["tool_changes"]:
                    parts.append("tool changes %d->%d | E by tool %s->%s" % (
                        b["tool_changes"], f["tool_changes"], b["e_by_tool"], f["e_by_tool"]))
                parts.append("tools of feature %s -> %s" % (tools_of(b), tools_of(f)))
                if "Support" in f["features"]:
                    parts.append("support Z %s..%s on %d layers" % (f["features"]["Support"]["z"][0], f["features"]["Support"]["z"][1], f["features"]["Support"]["layers_with"]))
            if keys & {"bridge"} or show_all:
                if (direction(b, "Bridge"), direction(b, "Internal Bridge"), direction(b, "Sparse infill")) != \
                        (direction(f, "Bridge"), direction(f, "Internal Bridge"), direction(f, "Sparse infill")):
                    parts.append("direction Br %s->%s | IBr %s->%s | SI %s->%s" % (
                        direction(b, "Bridge"), direction(f, "Bridge"), direction(b, "Internal Bridge"),
                        direction(f, "Internal Bridge"), direction(b, "Sparse infill"), direction(f, "Sparse infill")))
                else:
                    parts.append("direction unchanged (Br %s, IBr %s, SI %s)" % (
                        direction(f, "Bridge"), direction(f, "Internal Bridge"), direction(f, "Sparse infill")))
            if keys & {"fan"} or show_all:
                parts.append("fan %s->%s (fan lines %d->%d)" % (
                    " ".join("%s x%d" % kv for kv in sorted(b["fan"].items())), " ".join("%s x%d" % kv for kv in sorted(f["fan"].items())),
                    sum(b["fan"].values()), sum(f["fan"].values())))
            if keys & {"ironing"} or show_all:
                parts.append("ironing %s->%s moves" % (blocks(b, "Ironing"), blocks(f, "Ironing")))
            if keys & {"emm"} or show_all:
                parts.append("E/mm %s -> %s" % (e_per_mm(b), e_per_mm(f)))
            if keys & {"skirt", "brim"} or show_all:
                parts.append("skirt %s->%s brim %s->%s blocks | skirt moves %s->%s brim moves %s->%s" % (
                    blocks(b, "Skirt"), blocks(f, "Skirt"), blocks(b, "Brim"), blocks(f, "Brim"),
                    moves(b, "Skirt"), moves(f, "Skirt"), moves(b, "Brim"), moves(f, "Brim")))
            if keys & {"travel"} or show_all:
                parts.append("wipe moves %d->%d" % (b["wipe"]["moves"], f["wipe"]["moves"]))
            if keys & {"arcs", "special"} or show_all:
                parts.append("arcs %d->%d | EXCLUDE_OBJECT %d->%d | numbered %d->%d | widths %d->%d kinds" % (
                    b["arcs"]["extruding"], f["arcs"]["extruding"], b["object_labels"], f["object_labels"],
                    b["numbered_lines"], f["numbered_lines"], len(b["widths"]), len(f["widths"])))
            if keys & {"accel"} or show_all:
                top = lambda table: "/".join("%s x%d" % kv for kv in sorted(table.items(), key=lambda kv: -kv[1])[:8])
                parts.append("SET_VELOCITY_LIMIT ACCEL (mm/s^2 x lines) %s -> %s" % (top(b["accel"]), top(f["accel"])))
            if keys & {"jerk"} and not show_all:
                parts.append("jerk: not in a Klipper-flavour export (no command carries it)")
            for part in parts:
                out.write("     " + part[:420] + "\n")
            out.write("     飞书预期: " + expected.replace("\n", " / ")[:230] + "\n")
    out.write("\nTALLY of 44 rows on their own models: SHADOW %d | NON_GREEN %d | not run %d | no fixture %d | no scenario %d\n" % (
        tally["shadow"], len(tally["non_green"]), len(tally["no_run"]), len(tally["no_fixture"]), len(tally["no_scenario"])))
    for key in ("non_green", "no_run", "no_fixture", "no_scenario"):
        if tally[key]:
            out.write("   %-12s %s\n" % (key, " ".join("#" + str(x) for x in tally[key])))
    out.flush()


if __name__ == "__main__":
    main()
