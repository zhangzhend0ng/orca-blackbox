"""The 42 parameter rows of the regression on the final engine (nine-hour run, 2026-11-25).

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_family.py --repo <checkout with the registry> [--snapshot <ndjson>] [--evidence <folder>]

Reads ledger.jsonl and receipts/<run_id>.json of the evidence folder, the committed Feishu snapshot
and, through the run_dir a receipt names, each non-SHADOW run's result.json (for the check that
failed); runs tools/param_closure_list.py of --repo (read-only) for the 42 case ids and their
scenario names. Writes family-regression.json and family-regression.md next to scripts/.

How a run is placed:
  * regression run: label `regress-final`. It is on the final engine when the ledger's commit says
    2a17376 or 62cddee (the same engine); anything else (d5fc2fa) is the earlier partial
    regression, which the final table supersedes and which is listed apart.
  * assigned run / other machine: of the final-engine regression runs of a row, the one on the half
    the row was assigned to is its result; a run of the other machine (the guest's cross-run of a
    fa706g3 row) is listed beside it. For a guest row the other machine's run is fa706g3's
    `second-sample`. Both machines' runs are evidence of the same scenario; they do not change the
    row's result.
  * retry: label `retry-*`, the repeats after a failed run; listed with the row they repeat.
  * A run without a receipt never reached the GUI. It is a failed dispatch with no verdict and is
    not listed under any run class (see dispatch-failures.md).
A run is the LAST ledger line written for its run id.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from build_common import (EVIDENCE, MACHINE_OF_LEDGER, MACHINE_SHORT, MACHINE_TEXT, SNAPSHOT, commit_text, dump,
                          family_queues, f3, ledger_facts, load_ledger, load_receipts, load_snapshot, read_json,
                          role_of, short, write)

ENGINE = {
    "final_engine": "2a1737689ff519686b90c588d52d96519e76f370",
    "first_push": "62cddee803c595a2a46323286ed37fb06bdcff72",
    "same_engine": "62cddee 是 2a17376 和文档分支的合并，harness、tools、unit_tests 等引擎文件与 2a17376 相同"
                   "（git diff --stat 2a17376 62cddee 只列出 README.md 和 docs/runs）",
    "fix": "2a17376 的父提交是 d5fc2fa，二者只差一个提交：5b38c80 的拣选，改 harness/process_panel.py 的 "
           "scroll_group_into_view 循环体和 unit_tests/test_param_flow.py",
}


def failed_checks(receipt):
    """{check: 'status: detail'} of a run whose checks are not all pass, read from its result.json."""
    try:
        checks = read_json(Path(receipt["run_dir"]) / "result.json").get("checks") or {}
    except (OSError, ValueError):
        return None
    return {name: "%s: %s" % (check.get("status"), str(check.get("detail"))[:160])
            for name, check in checks.items() if check.get("status") != "pass"}


def run_of(entry, receipt):
    return {
        "run_id": entry["run_id"], "label": entry.get("label"), "role": role_of(entry.get("label")),
        "machine": MACHINE_OF_LEDGER.get(entry["machine"], entry["machine"]),
        "commit": (receipt["identity"]["source_commit"] if receipt else None) or entry.get("commit"),
        "on_final_engine": bool((entry.get("commit") or "").startswith(("2a17376", "62cddee"))),
        "started": entry.get("started"), "ended": entry.get("ended"), "ledger_line": entry["_line"],
        "ledger_scenario_raw": entry["scenario"],
        "verdict": receipt["verdicts"]["release_verdict"] if receipt else None,
        "verified_pass": receipt["verdicts"]["verified_pass"] if receipt else None,
        "cleanup_confirmed": receipt["verdicts"]["cleanup_confirmed"] if receipt else None,
        "host_wall_seconds": receipt["seconds"]["host_wall"] if receipt else None,
        "process_seconds": receipt["seconds"]["guest"] if receipt else None,
        "script_action_seconds": receipt["seconds"]["script_action"] if receipt else None,
        "host_orchestration_seconds": entry.get("process_seconds"),
        "dispatch_failed": entry.get("dispatch_failed"),
        "worker_error": entry.get("worker_error") or None,
        "failed_checks": (failed_checks(receipt) if receipt and receipt["verdicts"]["release_verdict"] != "SHADOW" else None),
    }


def row_status(final_runs):
    """The row's result on the machine it was assigned to."""
    if not final_runs:
        return "not_run"
    verdicts = {run["verdict"] for run in final_runs if run["verdict"]}
    if "SHADOW" in verdicts:
        return "SHADOW_after_a_failure" if "NON_GREEN" in verdicts else "SHADOW"
    return "NON_GREEN" if "NON_GREEN" in verdicts else "no_verdict"


def build(ledger, receipts, repo, snapshot):
    queues = family_queues(repo)
    rows = []
    for side in ("guest", "fa706g3"):
        for order, (number, case, scenario) in enumerate(queues[side], 1):
            runs = sorted((run_of(entry, receipts.get(run_id)) for run_id, entry in ledger.items()
                           if role_of(entry.get("label")) in ("regress", "retry", "second_sample")
                           and entry["scenario"].strip() == scenario),
                          key=lambda run: (run["started"] or "", run["run_id"]))
            ran = [run for run in runs if run["verdict"]]                 # a run without a verdict never reached the GUI
            final_runs = [run for run in ran if run["role"] == "regress" and run["on_final_engine"]]
            assigned = [run for run in final_runs if run["machine"] == side]
            other = [run for run in final_runs if run["machine"] != side]
            if side == "guest":
                other += [run for run in ran if run["role"] == "second_sample" and run["on_final_engine"]]
            rows.append({
                "order": order, "machine": side, "machine_text": MACHINE_TEXT[side], "feishu_row": number,
                "case_id": case, "scenario": scenario,
                "record_id": snapshot.get(number, {}).get("record_id"), "title": snapshot.get(number, {}).get("title"),
                "feishu_status": snapshot.get(number, {}).get("status"),
                "status": row_status(assigned), "runs_final_engine": assigned, "runs_other_machine": other,
                "runs_on_d5fc2fa": [run for run in ran if run["role"] == "regress" and not run["on_final_engine"]],
                "retries": [run for run in ran if run["role"] == "retry"],
                "dispatches": [run["run_id"] for run in runs if not run["verdict"]],
            })
    final_runs = [dict(run, feishu_row=row["feishu_row"]) for row in rows for run in row["runs_final_engine"]]
    other_runs = [dict(run, feishu_row=row["feishu_row"], assigned_machine=row["machine"])
                  for row in rows for run in row["runs_other_machine"]]
    old_runs = [dict(run, feishu_row=row["feishu_row"]) for row in rows for run in row["runs_on_d5fc2fa"]]
    retries = [dict(run, feishu_row=row["feishu_row"]) for row in rows for run in row["retries"]]

    def side_count(machine):
        mine = [row for row in rows if row["machine"] == machine]
        with_other = [row for row in mine if row["runs_other_machine"]]
        return {"rows": len(mine), "SHADOW": sum(1 for row in mine if row["status"].startswith("SHADOW")),
                "NON_GREEN": sum(1 for row in mine if row["status"] == "NON_GREEN"),
                "without_a_verdict": sum(1 for row in mine if row["status"] in ("not_run", "no_verdict")),
                "rows_with_a_run_on_the_other_machine": len(with_other),
                "rows_without_one": sorted(row["feishu_row"] for row in mine if not row["runs_other_machine"]),
                "other_machine_verdicts": dict(collections.Counter(
                    run["verdict"] for row in with_other for run in row["runs_other_machine"])),
                "other_machine_runs": sum(len(row["runs_other_machine"]) for row in with_other)}

    counts = {
        "rows": len(rows), "rows_by_status": dict(collections.Counter(row["status"] for row in rows)),
        "per_machine": {side: side_count(side) for side in ("guest", "fa706g3")},
        "final_engine_runs": len(final_runs),
        "final_engine_verdicts": dict(collections.Counter(run["verdict"] for run in final_runs if run["verdict"])),
        "final_engine_commits": dict(collections.Counter(commit_text(run["commit"]) for run in final_runs)),
        "rows_with_a_non_shadow_run": sorted(
            row["feishu_row"] for row in rows
            if any(run["verdict"] and run["verdict"] != "SHADOW" for run in row["runs_final_engine"])),
        "other_machine_runs": len(other_runs),
        "other_machine_verdicts": dict(collections.Counter(run["verdict"] for run in other_runs if run["verdict"])),
        "other_machine_commits": dict(collections.Counter(commit_text(run["commit"]) for run in other_runs)),
        "rows_with_both_machines": sum(1 for row in rows if row["runs_final_engine"] and row["runs_other_machine"]),
        "other_machine_non_shadow_runs": [
            {"feishu_row": run["feishu_row"], "run_id": run["run_id"], "machine": run["machine"], "verdict": run["verdict"],
             "failed_checks": run["failed_checks"]} for run in other_runs if run["verdict"] != "SHADOW"],
        "d5fc2fa_runs": len(old_runs),
        "d5fc2fa_rows_shadow": {side: sorted({run["feishu_row"] for run in old_runs
                                              if run["machine"] == side and run["verdict"] == "SHADOW"})
                                for side in ("guest", "fa706g3")},
        "d5fc2fa_failed_runs": [run["run_id"] for run in old_runs if run["verdict"] and run["verdict"] != "SHADOW"],
        "retries": len(retries),
        "retries_per_machine": dict(collections.Counter(run["machine"] for run in retries)),
        "retries_verdicts": dict(collections.Counter(str(run["verdict"]) for run in retries)),
        "dispatches_of_these_rows": sorted(run_id for row in rows for run_id in row["dispatches"]),
    }
    return dict(ledger_facts(ledger), **{
        "schema": "ninehour_family_regression/3", "generated_by": "scripts/build_family.py",
        "status": "final", "placeholder": False, "engine": ENGINE, "counts": counts, "rows": rows,
    })


def verdict_cell(run):
    if not run["verdict"]:
        return "派发失败（无评级）"
    text = run["verdict"]
    if run["worker_error"]:
        text += "：`%s`" % run["worker_error"]
    if run["failed_checks"]:
        text += "；" + "、".join("%s %s" % (name, value) for name, value in run["failed_checks"].items() if name != "visual")
    return text


def other_cell(row):
    """The other machine's run(s) of the row: machine, run, commit, verdict, seconds."""
    if not row["runs_other_machine"]:
        return "-"
    return "；".join("%s `%s`（%s）%s，动作 %s 秒，%s %s 秒" % (
        MACHINE_SHORT[run["machine"]], run["run_id"], commit_text(run["commit"]),
        verdict_cell(run), f3(run["script_action_seconds"]),
        "宿主整轮" if run["machine"] == "guest" else "机内进程",
        f3(run["host_wall_seconds"] if run["machine"] == "guest" else run["process_seconds"]))
        for run in row["runs_other_machine"])


def markdown(data):
    c = data["counts"]
    failed = [row for row in data["rows"] if row["status"] == "NON_GREEN"]
    shadow = sum(1 for row in data["rows"] if row["status"].startswith("SHADOW"))
    guest, fa = c["per_machine"]["guest"], c["per_machine"]["fa706g3"]
    lines = [
        "# 参数族 42 行在最终引擎上的回归（两台机器）", "",
        "**结论：42 行里 %d 行 SHADOW，%d 行 NON_GREEN。** 按各行分到的机器算：客机 win11-test 的 %d 行里 %d 行 SHADOW；fa706g3 的 %d 行里 %d 行 SHADOW、%d 行 NON_GREEN。"
        "fa706g3 的结果按 README 第 6 条最高记 SHADOW，不作为发布证据。" % (
            shadow, len(failed), guest["rows"], guest["SHADOW"], fa["rows"], fa["SHADOW"], fa["NON_GREEN"]),
        "",
        "- 引擎：最终引擎是 2a17376（%s）。%s。" % (data["engine"]["fix"], data["engine"]["same_engine"]),
        "- 台账复制时共 %d 行、%d 个 run，末行结束于 %s。分到的机器上的回归运行共 %d 次（提交：%s），评级计数 %s。" % (
            data["ledger_lines"], data["ledger_runs"], data["ledger_last_ended"], c["final_engine_runs"],
            "、".join("%s %d" % item for item in sorted(c["final_engine_commits"].items())),
            "、".join("%s %d" % item for item in sorted(c["final_engine_verdicts"].items()))),
    ]
    for row in failed:
        for run in row["runs_final_engine"]:
            lines.append("- #%d `%s`（分在 %s 的行）%s `%s`，%s 起，动作 %s 秒：%s。" % (
                row["feishu_row"], row["scenario"], MACHINE_SHORT[row["machine"]], MACHINE_TEXT[run["machine"]],
                run["run_id"], run["started"], f3(run["script_action_seconds"]), verdict_cell(run)))
    if any(row["feishu_row"] == 294 for row in failed):
        lines.append("- #294 是 11‑24 就开着的那一行，不是这次改动造成的回归：11‑24 的对照里它记为「机型不适用」（Timelapse 行只在 BBL 机型上有），"
                     "写入通过的是 41 条（`docs/runs/evidence/feishu-expect-vs-gcode-2026-11-24/own-models-verdicts.md`）。")
    lines += [
        "- 另一台机器上的运行是同一个场景换一台机器再取证（复核），不改变上面的结论：客机把 fa706g3 那一半跑了 %d 行 %d 次运行（%s；没跑的 %d 行：%s），"
        "fa706g3 把客机那一半跑了 %d 行 %d 次运行（%s；没跑的 %d 行：%s）。队列被总控用 STOP 文件停下，没跑的行不再补。" % (
            fa["rows_with_a_run_on_the_other_machine"], fa["other_machine_runs"],
            "、".join("%s %d" % item for item in sorted(fa["other_machine_verdicts"].items())),
            len(fa["rows_without_one"]), "、".join("#%d" % n for n in fa["rows_without_one"]) or "无",
            guest["rows_with_a_run_on_the_other_machine"], guest["other_machine_runs"],
            "、".join("%s %d" % item for item in sorted(guest["other_machine_verdicts"].items())),
            len(guest["rows_without_one"]), "、".join("#%d" % n for n in guest["rows_without_one"]) or "无"),
        "- 回归只回答引擎改动有没有破坏该行已有的写入和导出：队列跑的是不带后缀的 `uia_param_<key>` 场景，打开的是立方体工程，"
        "不是飞书前置条件里各自的模型和预设；它不逐项核对飞书预期。",
        "",
        "## 最终引擎上的回归（每行两个机器）", "",
        "| 飞书编号 | record ID | 用例标题 | 飞书状态 | 场景 | 机器 | run ID | 提交 | 起 | 止 | 宿主整轮秒 | 机内进程秒 | 动作秒 | 评级 | 另一台机器上的运行 |",
        "|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in data["rows"]:
        base = [str(row["feishu_row"]), "`%s`" % row["record_id"], row["title"] or "-", row["feishu_status"] or "-",
                row["scenario"], row["machine_text"]]
        if not row["runs_final_engine"]:
            lines.append("| " + " | ".join(base + ["-"] * 9) + " |")
            continue
        for index, run in enumerate(row["runs_final_engine"]):
            cells = base if index == 0 else [""] * 6
            lines.append("| " + " | ".join(cells + [
                "`%s`" % run["run_id"], commit_text(run["commit"]), run["started"] or "-", run["ended"] or "-",
                f3(run["host_wall_seconds"]), f3(run["process_seconds"]), f3(run["script_action_seconds"]), verdict_cell(run),
                other_cell(row) if index == 0 else ""]) + " |")
    lines += [
        "",
        "## 不是最终引擎上的回归（d5fc2fa，已被上表取代）", "",
        "这是修正提交之前先跑的那一部分，不计入最终引擎的结果。SHADOW 的行：客机 %d 行（%s），fa706g3 %d 行（%s）。"
        "fa706g3 上失败 %d 次（%s），之后两台机器重试 %d 次（客机 %d、fa706g3 %d；%s）。" % (
            len(c["d5fc2fa_rows_shadow"]["guest"]), "、".join("#%d" % n for n in c["d5fc2fa_rows_shadow"]["guest"]) or "无",
            len(c["d5fc2fa_rows_shadow"]["fa706g3"]), "、".join("#%d" % n for n in c["d5fc2fa_rows_shadow"]["fa706g3"]) or "无",
            len(c["d5fc2fa_failed_runs"]), "、".join("`%s`" % short(run_id) for run_id in c["d5fc2fa_failed_runs"]) or "无",
            c["retries"], c["retries_per_machine"].get("guest", 0), c["retries_per_machine"].get("fa706g3", 0),
            "、".join("%s %d" % item for item in sorted(c["retries_verdicts"].items()))),
        "",
        "| 机器 | 飞书编号 | 场景 | run ID | 标签 | 起 | 动作秒 | 评级 |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for row in data["rows"]:
        for run in sorted(row["runs_on_d5fc2fa"] + row["retries"], key=lambda run: (run["started"] or "", run["run_id"])):
            lines.append("| %s | #%d | %s | `%s` | %s | %s | %s | %s |" % (
                MACHINE_TEXT[run["machine"]], row["feishu_row"], row["scenario"], run["run_id"], run["label"],
                run["started"] or "-", f3(run["script_action_seconds"]), verdict_cell(run)))
    lines += [
        "",
        "没有收割件的派发（没有到 GUI，没有评级，不属于任何一类运行）见 [dispatch-failures.md](dispatch-failures.md)，"
        "其中带着回归标签、场景是这 42 行之一的有 %d 条（%s）。" % (
            len(c["dispatches_of_these_rows"]), "、".join("`%s`" % short(run_id) for run_id in c["dispatches_of_these_rows"]) or "无"),
        "",
        "来源：`family-regression.json`（`scripts/build_family.py`）。",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", default=str(EVIDENCE))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--snapshot", default=SNAPSHOT)
    args = parser.parse_args(argv)
    evidence = Path(args.evidence)
    data = build(load_ledger(evidence / "ledger.jsonl"), load_receipts(evidence), args.repo, load_snapshot(args.snapshot))
    write(evidence, "family-regression.json", dump(data))
    write(evidence, "family-regression.md", markdown(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
