"""Which fixture each Feishu parameter row is meant to run on, from the row's own
precondition - and the scenario list to queue for one of them.

    python tools/feishu_model_fixtures.py <repo-root>                     # the table
    python tools/feishu_model_fixtures.py <repo-root> --suffix _boat      # space-separated scenarios
    python tools/feishu_model_fixtures.py <repo-root> --suffix _boat --csv  # one scenario per line

A row's precondition names a model ("添加实用模型 > 小船，作为同一测试对象" and
the like). The fixture that carries that model on the precondition settings is
registered in harness/agent_protocol (MODEL_FIXTURES, the precondition cube, the
two-object cube); a scenario named `<base><suffix>` runs the row's scenario on it.
"并设置2种颜色/耗材" / "并设置2种耗材" is read as two objects on extruders 1 and 3
(an interpretation, 2026-11-24: only then is there a tool change to see).

Rows are tied to scenarios through tools/param_cases_export.json (case_id
param_<n>_... / layer_pair_254). Importable: row_plan(root) and
fixture_for(precondition) are what tools/feishu_rows_report.py uses. Read-only."""
import io
import json
import os
import re
import sys

# precondition phrase -> fixture suffix (None: no fixture carries that model yet)
BY_PHRASE = [
    ("小船，并设置2种颜色/耗材", "_boat2"),
    ("小船", "_boat"),
    ("欧特克FDM测试，并设置2种耗材", "_fdmt2"),
    ("欧特克FDM测试", "_fdmt"),
    ("立方体，复制为2个对象", "_cubes2"),
    ("立方体", "_std02"),
    ("球", "_sphere"),
    ("圆柱体", "_cyl"),
    ("Orca误差测试", "_tol"),
    ("文字浮雕", "_text"),
    ("斯坦福兔子", "_bunny"),
    ("Orca拉丝地狱", "_hell"),
]
LABEL = {"_boat2": "two 3DBenchy, extruders 1 and 3", "_boat": "3DBenchy", "_fdmt2": "two FDM tests, extruders 1 and 3",
         "_fdmt": "the Autodesk FDM test (ksr_fdmtest_v4)", "_cubes2": "two 20 mm cubes, extruders 1 and 3",
         "_std02": "the precondition cube", "_sphere": "a generated sphere", "_cyl": "a generated cylinder",
         "_bunny": "the Stanford bunny", "_hell": "Orca string hell", "_tol": "the Orca tolerance test (from the STL)",
         "_text": "raised text (a dot-matrix stand-in for the slicer's Text tool)"}
SNAPSHOT = os.path.join("docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22",
                        "tblKjIVV8KA53kUQ_20261122_024056_171.ndjson")
ROWS = range(254, 298)          # the 常用工艺参数 supplement rows


def fixture_for(precondition):
    steps = [s for s in (precondition or "").split("\n") if s.strip()]
    model = steps[1] if len(steps) > 1 else ""
    for phrase, suffix in BY_PHRASE:
        if phrase in model:
            return suffix
    return None


def feishu_rows(root):
    """{number: record} of the parameter rows, from the Feishu snapshot."""
    rows = {}
    for line in io.open(os.path.join(root, SNAPSHOT), encoding="utf-8"):
        if line.strip():
            rec = json.loads(line)
            try:
                number = int(rec["用例编号"])
            except (KeyError, TypeError, ValueError):
                continue
            if number in ROWS:
                rows[number] = rec
    return rows


def row_plan(root):
    """{suffix or None: [(row number, scenario or None)]} in row order."""
    scenario_of_row = {}
    for case in json.load(io.open(os.path.join(root, "tools/param_cases_export.json"), encoding="utf-8"))["cases"]:
        found = re.search(r"(\d+)", case["case_id"])
        if found:
            scenario_of_row[int(found.group(1))] = case["scenario"]
    plan = {}
    for number, rec in sorted(feishu_rows(root).items()):
        plan.setdefault(fixture_for(rec["前置条件"]), []).append((number, scenario_of_row.get(number)))
    return plan


def main():
    root = sys.argv[1]
    sys.path.insert(0, root)
    from harness.agent_protocol import BASELINES, FIXTURE_SUFFIXES  # noqa: E402
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    plan = row_plan(root)
    if "--suffix" in sys.argv:
        want = sys.argv[sys.argv.index("--suffix") + 1]
        scenarios = [s + want for _n, s in plan.get(want, []) if s]
        out.write(("\n".join(scenarios) if "--csv" in sys.argv else " ".join(scenarios)) + "\n")
        out.flush()
        return 0
    for suffix, items in sorted(plan.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
        have = [n for n, s in items if s]
        missing = [n for n, s in items if not s]
        registered = suffix in FIXTURE_SUFFIXES
        where = LABEL.get(suffix, "no fixture carries this model yet") if suffix else "no fixture carries this model yet"
        if suffix and not registered:
            where += " - NOT REGISTERED yet"
        out.write("%-8s %2d rows  %-58s scenarios %d%s\n" % (
            suffix or "(none)", len(items), where, len(have),
            (", no scenario for #%s" % " #".join(map(str, missing))) if missing else ""))
        out.write("          " + " ".join("#%d" % n for n, _s in items) + "\n")
    out.write("fixtures registered: %s\n" % ", ".join(FIXTURE_SUFFIXES))
    out.write("baselines: %s\n" % " ".join(baseline for baseline, _case in BASELINES.values()))
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
