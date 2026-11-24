"""The 44 Feishu parameter rows against what their own model's export shows.

    python tools/feishu_rows_report.py <repo-root> [--csv <file>] [--ids 254,271]

For every row: the model its precondition names and the fixture that carries
it (tools/feishu_model_fixtures.py), the row's scenario, and the latest
harvested run of that scenario on that fixture - verdict, and the facts of its
exported G-code (tools/gcode_facts.py): layers, feeds per feature on the first
layer and the others, travels, tools, arcs, support / bridge blocks. Then a
tally: rows with a SHADOW on their own model, NON_GREEN, no run yet, no
fixture, no scenario.

Nothing here judges the row's expected results 2 and 3: they are printed next
to the facts to be compared by eye, and what is found is then written into the
pilots as an assertion (measure first, then pin). Read-only; the harvest is
looked up under <repo-root>/artifacts/windows_mcp_harvest."""
import csv
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
from feishu_model_fixtures import LABEL, feishu_rows, row_plan  # noqa: E402
from gcode_facts import gcode_facts  # noqa: E402
from harness.agent_protocol import FIXTURE_SUFFIXES  # noqa: E402

# the harvest normally sits in the main worktree while the code is read from another one
HARVEST = os.environ.get("ORCA_BB_HARVEST") or os.path.join(root, "artifacts", "windows_mcp_harvest")
wanted = set(sys.argv[sys.argv.index("--ids") + 1].split(",")) if "--ids" in sys.argv else None


def latest(scenario, sha):
    """(run id, verdict, error, dir) of the newest harvested run of `scenario`
    whose input fixture has `sha`, else None."""
    best = None
    for d in glob.glob(os.path.join(HARVEST, "*") + os.sep):
        try:
            scope = json.load(open(d + "scope.json", encoding="utf-8-sig"))
            proc = json.load(open(d + "process.json", encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if scope.get("scenario") != scenario or not proc.get("started_at_ns"):
            continue
        try:
            if hashlib.sha256(open(d + "input/fixture.3mf", "rb").read()).hexdigest() != sha:
                continue
        except OSError:
            continue
        if best is None or proc["started_at_ns"] > best[0]:
            best = (proc["started_at_ns"], d)
    if best is None:
        return None
    d = best[1]
    try:
        result = json.load(open(d + "result.json", encoding="utf-8-sig"))
        worker = json.load(open(d + "native_worker.json", encoding="utf-8-sig"))
    except (OSError, ValueError):
        result, worker = {}, {}
    detail = str(((result.get("checks") or {}).get("business") or {}).get("detail") or "")
    return os.path.basename(d.rstrip(os.sep))[:8], result.get("release_verdict") or "?", (worker.get("error") or detail)[:60], d


def feeds(facts, band, limit=5):
    parts = []
    for kind in facts["feature_order"]:
        text = facts["features"][kind]["feed"][band]
        if text != "-":
            parts.append("%s %s" % (kind[:9], text.replace("F", "").replace(" x", "x")))
    return "; ".join(parts[:limit]) + ("; +%d" % (len(parts) - limit) if len(parts) > limit else "")


def blocks(facts, *names):
    return "/".join(str(facts["features"][n]["blocks"]) if n in facts["features"] else "0" for n in names)


out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
rows_out = []
tally = {"shadow": [], "non_green": [], "no_run": [], "no_fixture": [], "no_scenario": []}
plan = row_plan(root)
feishu = feishu_rows(root)
for suffix, items in sorted(plan.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
    out.write("## %s - %s\n" % (suffix or "(no fixture)", LABEL.get(suffix, "no fixture carries this model yet")))
    for number, scenario in items:
        if wanted and str(number) not in wanted:
            continue
        rec = feishu[number]
        row = {"row": number, "fixture": suffix or "", "scenario": scenario or "", "run": "", "verdict": "", "layers": "",
               "first_layer_feeds": "", "other_layer_feeds": "", "travel": "", "tools": "", "arcs": "",
               "support_bridge_blocks": "", "outer_wall_all_feeds": "", "directions": "", "feature_z": "", "fan": "",
               "tools_by_feature": "", "special": "",
               "expected": rec["预期结果"].replace("\n", " / ")}
        if not scenario:
            tally["no_scenario"].append(number)
            out.write("#%d  (no scenario: %s)\n" % (number, rec["用例标题"][:30]))
        elif not suffix or suffix not in FIXTURE_SUFFIXES:
            tally["no_fixture"].append(number)
            out.write("#%d  %s  NO FIXTURE for its model yet\n" % (number, scenario))
        else:
            hit = latest(scenario + suffix, FIXTURE_SUFFIXES[suffix][1])
            if not hit:
                tally["no_run"].append(number)
                out.write("#%d  %s%s  NOT RUN on this fixture yet\n" % (number, scenario, suffix))
            else:
                run, verdict, error, d = hit
                row.update(run=run, verdict=verdict)
                gcode = glob.glob(d + "exports/*.gcode")
                facts = gcode_facts(gcode[0]) if gcode else None
                if facts:
                    row["layers"] = "%d / %s..%s" % (facts["layers"], facts["z_first"], facts["z_last"])
                    row["first_layer_feeds"] = feeds(facts, "first")
                    row["other_layer_feeds"] = feeds(facts, "other")
                    row["travel"] = "first %s | other %s" % (facts["travel"]["first"], facts["travel"]["other"])
                    row["tools"] = "%d changes, E %s" % (facts["tool_changes"], facts["e_by_tool"])
                    row["arcs"] = str(facts["arcs"]["extruding"])
                    row["support_bridge_blocks"] = "support %s, interface %s, bridge %s, overhang wall %s" % (
                        blocks(facts, "Support"), blocks(facts, "Support interface"), blocks(facts, "Bridge"),
                        blocks(facts, "Overhang wall"))
                    # what the rows' expected results 2 and 3 talk about: every feed of the
                    # outer walls (the overhang bands are interpolated), the direction of
                    # bridges and infill, where support starts and ends, the fan's steps
                    wall = facts["features"].get("Outer wall")
                    row["outer_wall_all_feeds"] = " ".join("%s x%d" % (f, n) for f, n in wall["feeds"]["other"]) if wall else ""
                    row["directions"] = "; ".join(
                        "%s: %s" % (name[:10], facts["features"][name]["angle_top"])
                        for name in ("Bridge", "Internal Bridge", "Sparse infill", "Outer wall", "Support")
                        if name in facts["features"] and facts["features"][name]["angle_top"])
                    row["feature_z"] = "; ".join(
                        "%s: %s..%s on %d layers" % (name[:10], f["z"][0], f["z"][1], f["layers_with"])
                        for name in ("Support", "Support interface", "Bridge", "Overhang wall")
                        for f in (facts["features"].get(name),) if f)
                    row["tools_by_feature"] = "; ".join(
                        "%s %s" % (name[:10], " ".join("T%s %d" % (t, v) for t, v in f["e_by_tool"].items()))
                        for name in ("Support", "Support interface", "Prime tower", "Bridge", "Sparse infill")
                        for f in (facts["features"].get(name),) if f and f["e_by_tool"])
                    row["special"] = "; ".join(
                        "%s %s blocks %s E/mm %s" % (name, facts["features"][name]["feed"]["other"],
                                                     facts["features"][name]["blocks"], facts["features"][name]["e_per_mm"])
                        for name in ("Ironing", "Skirt", "Brim", "Prime tower", "Support", "Support interface")
                        if name in facts["features"]) + ("; wipe %d moves %s" % (facts["wipe"]["moves"], facts["wipe"]["feed"]) if facts["wipe"]["moves"] else "")
                    row["fan"] = "%s | steps %s" % (
                        " ".join("%s x%d" % kv for kv in sorted(facts["fan"].items())),
                        " ".join("%d:%s" % (l, s) for l, s in facts["fan_changes"][:16]))
                if verdict == "SHADOW":
                    tally["shadow"].append(number)
                else:
                    tally["non_green"].append("%d(%s)" % (number, error[:28]))
                out.write("#%d  %s%s  %s  %s  %s\n" % (number, scenario, suffix, run, verdict, "" if verdict == "SHADOW" else error))
                if facts:
                    out.write("     layers %s | tools %s | arcs %s | %s\n" % (
                        row["layers"], row["tools"], row["arcs"], row["support_bridge_blocks"]))
                    out.write("     first layer: %s\n     travels: %s\n" % (row["first_layer_feeds"], row["travel"]))
                    out.write("     other layers: %s\n     outer wall, every feed: %s\n     directions: %s\n" % (
                        row["other_layer_feeds"], row["outer_wall_all_feeds"][:230], row["directions"]))
                    out.write("     where: %s\n     fan: %s\n     tools by feature: %s\n     special: %s\n" % (
                        row["feature_z"], row["fan"][:200], row["tools_by_feature"][:300], row["special"][:330]))
        out.write("     飞书预期: %s\n" % row["expected"][:200])
        rows_out.append(row)
out.write("\nTALLY of the 44 rows: SHADOW on their own model %d | NON_GREEN %d | not run yet %d | no fixture for the model %d | no scenario %d\n" % (
    len(tally["shadow"]), len(tally["non_green"]), len(tally["no_run"]), len(tally["no_fixture"]), len(tally["no_scenario"])))
for key in ("non_green", "no_run", "no_fixture", "no_scenario"):
    if tally[key]:
        out.write("   %-12s %s\n" % (key, " ".join("#" + str(x) for x in tally[key])))
out.flush()
if "--csv" in sys.argv:
    path = sys.argv[sys.argv.index("--csv") + 1]
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    out.write("csv: %s\n" % path)
    out.flush()
