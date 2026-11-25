"""The per-row table of the run record (section 逐条对照), generated so that the quoted Feishu text
cannot drift from the snapshot.

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/record_rows.py [--evidence <folder>] [--snapshot <ndjson>]

Reads feishu-216-ninehour.json of the evidence folder (so run build_feishu.py first) and the
committed Feishu snapshot. Prints Markdown rows to stdout: every Feishu row touched tonight except
#264, #265 and #276, which the run record quotes in full. Steps 2-4 of the parameter rows are the same
three sentences for every row, and so is expectation 1 except in #292; the run record states them once.

The 今晚的运行 cell names the runs of the final engine and of the coverage batches with their ids
and verdicts; the d5fc2fa runs are a count (their list is family-regression.md). A dispatch that
never reached the GUI has no verdict and no run class: it is counted as 派发失败 only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from build_common import EVIDENCE, MACHINE_SHORT, SNAPSHOT, read_json, short

KIND_TEXT = {
    "backlog": "补覆盖（空闲机器）", "twins": "补覆盖（客机自有模型孪生）", "twins_b": "补覆盖（客机自有模型孪生，第二批）",
    "shapes": "补覆盖（fa706g3 多形状孪生）", "regress": "最终引擎回归（分到的机器）", "regress_other": "另一台机器上的回归运行",
    "final2": "最终引擎复核", "native": "原生模型对照",
}
KIND_ORDER = ("backlog", "twins", "twins_b", "shapes", "regress", "regress_other", "final2", "native")
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


def expectations(text):
    """Expectations 2 and on, as the snapshot has them (expectation 1 is left to the run record: one sentence in every parameter row except #292)."""
    found = re.search(r"(?m)^2\.", text)
    return (text[found.start():] if found else text).replace("\n", " ")


def named(picked):
    """'N 次（机器，run ID…，评级）'; with more than one verdict, each run with its own."""
    verdicts = sorted({str(run["verdict"]) for run in picked})
    machines = "、".join(sorted({MACHINE_SHORT[run["machine"]] for run in picked}))
    if len(verdicts) > 1:      # not one verdict for all: name it per run
        return "%d 次（%s）：%s" % (len(picked), machines, "、".join(
            "`%s`（%s）%s" % (short(run["run_id"]), MACHINE_SHORT[run["machine"]], run["verdict"]) for run in picked))
    return "%d 次（%s，%s，%s）" % (len(picked), machines, "、".join("`%s`" % short(run["run_id"]) for run in picked),
                                  "/".join(verdicts))


def runs_text(runs, dispatches):
    """The 今晚的运行 cell: final-engine and coverage runs with ids and verdicts; the rest as counts."""
    out = []
    for kind in KIND_ORDER:
        picked = [run for run in runs if run["kind"] == kind]
        if not picked:
            continue
        out.append("%s %s" % (KIND_TEXT[kind], named(picked)))

    retries_final = [run for run in runs if run["kind"] == "retry" and run["on_final_engine"]]
    if retries_final:
        out.append("最终引擎上失败后的重试 " + named(retries_final))
    old = [run for run in runs if run["kind"] in ("retry", "regress_d5fc2fa", "final_d5fc2fa")
           and not (run["kind"] == "retry" and run["on_final_engine"])]
    if old:
        verdicts = sorted({str(run["verdict"]) for run in old})
        out.append("d5fc2fa 上的运行和失败后的重试另有 %d 次（%s，不是最终引擎%s；明细见 family-regression.md）" % (
            len(old), "/".join(verdicts), "，含一次失败" if any(verdict != "SHADOW" for verdict in verdicts) else ""))
    if dispatches:
        out.append("派发失败 %d 次（没有到 GUI，无评级；见 dispatch-failures.md）" % len(dispatches))
    return "；".join(out)


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
        record, detail = snapshot[number], data["touched_detail"][str(number)]
        out.write("| #%d `%s` %s | %s | %s | %s | %s |\n" % (
            number, record["record_id"], record["用例标题"],
            model_of(record["前置条件"]),
            between(record["测试步骤"], "设置测试参数：", "\n2."),
            expectations(record["预期结果"]),
            runs_text(detail["runs"], detail["dispatches"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
