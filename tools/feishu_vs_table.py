"""The values a Feishu row's steps name, next to the values its case carries.

    python tools/feishu_vs_table.py <repo-root> [--ids 265,276]

"Values written" is judged against the case table (tools/param_cases_export.
json): the pilot reads back the keys the table lists and no others. So a row
whose steps name a key the table does not carry passes without that value
ever being typed. This prints, per row, the step keys the table lacks and
the table keys the steps do not name, and a tally. It judges nothing about
whether a difference is justified (some are recorded deviations: a key with
no control on this machine, one that does not exist in this fork) - it makes
the list so none is forgotten. Read-only."""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root = sys.argv[1]
sys.path.insert(0, os.path.join(root, "tools"))
from feishu_model_fixtures import feishu_rows, row_plan  # noqa: E402


def step_keys(steps):
    """The parameter keys the row's '设置测试参数' line names, in order."""
    keys = []
    for line in (steps or "").split("\n"):
        if "设置测试参数" not in line:
            continue
        body = line.split("：", 1)[1] if "：" in line else line
        for part in re.split("[；;]", body):
            found = re.match(r"\s*([a-z_0-9]+)", part)
            if found:
                keys.append(found.group(1))
    return keys


def main():
    cases = json.load(io.open(os.path.join(root, "tools/param_cases_export.json"), encoding="utf-8"))["cases"]
    by_scenario = {case["scenario"]: case for case in cases}
    wanted = set(sys.argv[sys.argv.index("--ids") + 1].split(",")) if "--ids" in sys.argv else None
    rows, plan = feishu_rows(root), row_plan(root)
    lacking, extra, rows_lacking = [], [], []
    for _suffix, items in plan.items():
        for number, scenario in items:
            if wanted and str(number) not in wanted:
                continue
            keys = step_keys(rows[number]["测试步骤"])
            values = by_scenario.get(scenario, {}).get("values") if scenario else None
            table = set(values) if isinstance(values, dict) else set()
            missing = [key for key in keys if key not in table]
            more = sorted(table - set(keys))
            if not scenario:
                continue                      # no scenario: nothing was ever going to be written
            lacking += missing
            extra += more
            rows_lacking += [number] if missing else []
            if missing or more:
                print("#%d %s" % (number, scenario))
                if missing:
                    print("     step keys the table does not carry: %s" % " ".join(missing))
                if more:
                    print("     table keys the steps do not name:   %s" % " ".join(more))
    print("\nTALLY: %d rows name step keys the table lacks (%d keys in all); %d table keys are not step keys" % (
        len(rows_lacking), len(lacking), len(extra)))
    if rows_lacking:
        print("   rows: %s" % " ".join("#%d" % n for n in rows_lacking))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
