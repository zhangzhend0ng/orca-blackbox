"""Dump the 44 Feishu rows in full (precondition, steps, expected) to a UTF-8 text file.

    python -B rows_dump.py <repo-root> <out.txt>
"""
import io
import sys

root, out_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, root + "/tools")
from feishu_model_fixtures import feishu_rows, row_plan, fixture_for  # noqa: E402

rows = feishu_rows(root)
plan = row_plan(root)
scenario_of = {}
for suffix, items in plan.items():
    for number, scenario in items:
        scenario_of[number] = (suffix, scenario)

with io.open(out_path, "w", encoding="utf-8") as out:
    out.write("rows: %d  numbers %d..%d\n" % (len(rows), min(rows), max(rows)))
    for number in sorted(rows):
        rec = rows[number]
        suffix, scenario = scenario_of.get(number, (None, None))
        out.write("=" * 100 + "\n")
        out.write("#%d  fixture %s  scenario %s\n" % (number, suffix, scenario))
        for key in ("用例标题", "前置条件", "测试步骤", "预期结果"):
            text = str(rec.get(key, ""))
            out.write("--- %s ---\n" % key)
            for line in text.split("\n"):
                if line.strip():
                    out.write("  " + line.rstrip() + "\n")
        other = {k: v for k, v in rec.items()
                 if k not in ("用例标题", "前置条件", "测试步骤", "预期结果") and v not in ("", None, [])}
        out.write("--- other fields ---\n  %s\n" % other)
