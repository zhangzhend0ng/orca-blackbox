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

KIND_TEXT = {"backlog": "补覆盖", "regress": "最终引擎 2a17376 回归", "final2": "最终引擎复核", "native": "原生模型对照"}
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
    """The text after `start` and before the earliest of the `stop` markers (a string or a tuple of them);
    the whole text when `start` is missing."""
    if start not in text:
        return text.strip()
    rest = text.split(start, 1)[1]
    markers = (stop,) if isinstance(stop, str) else tuple(stop or ())
    found = [index for index in (rest.find(marker) for marker in markers) if index >= 0]
    return rest[:min(found)].strip() if found else rest.strip()


def model_of(precondition):
    """The precondition's model, verbatim: what follows '添加' up to where the sentence goes on."""
    return between(precondition, "添加", ("，作为", "，并保存", "，保存", "；", "。"))


def runs_text(runs):
    """The '今晚的运行' cell: the runs on the final engine with their ids; the d5fc2fa runs as a count."""
    out = []
    for kind in ("backlog", "regress", "final2", "native"):
        picked = [run for run in runs if run["kind"] == kind]
        if not picked:
            continue
        verdicts = sorted({str(run["verdict"]) for run in picked if run["verdict"]})
        failed = [run for run in picked if not run["verdict"]]
        machines = "、".join(sorted({MACHINE_TEXT[run["machine"]] for run in picked}))
        if len(verdicts) > 1:      # not one verdict for all: name it per run
            text = "%s %d 次（%s）：%s" % (KIND_TEXT[kind], len(picked), machines, "、".join(
                "`%s`（%s）%s" % (short(run["run_id"]), MACHINE_TEXT[run["machine"]], run["verdict"] or "派发失败，无评级")
                for run in picked))
        else:
            text = "%s %d 次（%s，%s%s%s）" % (
                KIND_TEXT[kind], len(picked), machines, "、".join("`%s`" % short(run["run_id"]) for run in picked),
                "" if kind == "native" or not verdicts else "，" + "/".join(verdicts),
                "；其中派发失败 %d 次（无评级）" % len(failed) if failed else "")
        out.append(text)
    old = [run for run in runs if run["kind"] in ("retry", "regress_d5fc2fa", "final_d5fc2fa") and run["verdict"]]
    dispatch = [run for run in runs if not run["verdict"]]
    if old:
        verdicts = sorted({str(run["verdict"]) for run in old})
        out.append("d5fc2fa 上另有 %d 次（%s，不是最终引擎%s；明细见 family-regression.md）" % (
            len(old), "/".join(verdicts), "，含一次失败和重试" if any(verdict != "SHADOW" for verdict in verdicts) else ""))
    if dispatch:
        out.append("派发失败 %d 次（没有到 GUI，无评级；明细见 family-regression.md）" % len(dispatch))
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
            model_of(record["前置条件"]),
            between(record["测试步骤"], "设置测试参数：", "\n2."),
            expectations(record["预期结果"]),
            runs_text(data["touched_detail"][str(number)]["runs"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
