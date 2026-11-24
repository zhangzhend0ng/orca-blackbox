"""The per-row table of the run record (section 逐条对照), generated so that the quoted Feishu text
cannot drift from the snapshot.

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/record_rows.py [--evidence <folder>] [--snapshot <ndjson>]

Reads feishu-216-ninehour.json of the evidence folder (so run build_feishu.py first) and the
committed Feishu snapshot. Prints Markdown rows to stdout: every Feishu row touched tonight except
#264, #265 and #276, which the run record quotes in full. Steps 2-4 and expectation 1 of the
parameter rows are the same sentences for every row; the run record states them once.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from build_common import EVIDENCE, MACHINE_TEXT, SNAPSHOT, read_json, short

KIND_TEXT = {"backlog": "补覆盖", "regress": "最终引擎回归", "final": "最终引擎复核", "native": "原生模型对照"}
COLUMNS = ("用例编号", "record_id", "用例标题", "前置条件", "测试步骤", "预期结果")


def load_rows(path):
    """{feishu row: the snapshot record}."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            record = {key: value for key, value in __import__("json").loads(line).items() if key in COLUMNS}
            out[int(record["用例编号"])] = record
    return out


def between(text, start, stop):
    """The text after `start` and before `stop`; the whole text when either is missing."""
    found = re.search(re.escape(start) + r"(.*?)" + re.escape(stop), text, re.S) if stop else None
    if found:
        return found.group(1).strip()
    return text.split(start, 1)[1].strip() if start in text else text.strip()


def runs_text(runs):
    out = []
    for kind in ("backlog", "regress", "final", "native"):
        picked = [run for run in runs if run["kind"] == kind]
        if picked:
            verdicts = sorted({str(run["verdict"]) for run in picked if run["verdict"]})
            failed = [run for run in picked if not run["verdict"]]
            machines = "、".join(sorted({MACHINE_TEXT[run["machine"]] for run in picked}))
            if len(verdicts) > 1:      # not one verdict for all: name it per run
                text = "%s %d 次（%s）：%s" % (KIND_TEXT[kind], len(picked), machines, "、".join(
                    "`%s` %s" % (short(run["run_id"]), run["verdict"] or "未收割") for run in picked))
            else:
                text = "%s %d 次（%s，%s%s%s）" % (
                    KIND_TEXT[kind], len(picked), machines, "、".join("`%s`" % short(run["run_id"]) for run in picked),
                    "" if kind == "native" or not verdicts else "，" + "/".join(verdicts),
                    "；其中未收割 %d 次" % len(failed) if failed else "")
            out.append(text)
    return "；".join(out)


def expectations(text):
    """Expectations 2 and on, as the snapshot has them (expectation 1 is the same sentence in every parameter row)."""
    found = re.search(r"(?m)^2\.", text)
    return (text[found.start():] if found else text).replace("\n", " ")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", default=str(EVIDENCE))
    parser.add_argument("--snapshot", default=SNAPSHOT)
    args = parser.parse_args(argv)
    data, snapshot = read_json(Path(args.evidence) / "feishu-216-ninehour.json"), load_rows(args.snapshot)
    out = sys.stdout
    for number in data["touched_rows"]:
        if number in (264, 265, 276):
            continue
        record = snapshot[number]
        out.write("| #%d `%s` %s | %s | %s | %s | %s |\n" % (
            number, record["record_id"], record["用例标题"],
            between(record["前置条件"], "添加", "，作为同一测试对象"),
            between(record["测试步骤"], "设置测试参数：", "\n2."),
            expectations(record["预期结果"]),
            runs_text(data["touched_detail"][str(number)]["runs"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
