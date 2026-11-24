"""The 42 parameter rows of the regression on the final engine (nine-hour run, 2026-11-25).

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_family.py --repo <checkout at d5fc2fa> [--snapshot <ndjson>] [--evidence <folder>]

Reads ledger.jsonl and receipts/<run_id>.json of the evidence folder and the committed Feishu
snapshot; runs tools/param_closure_list.py of --repo (read-only) for the 42 case ids and their
scenario names. Writes family-regression.json and family-regression.md next to scripts/.

The file says "in progress" because the regression was still running when the ledger was copied:
only what the ledger holds is filled in, a row without a run stays empty.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from build_common import (EVIDENCE, MACHINE_OF_LEDGER, MACHINE_TEXT, SNAPSHOT, commit_text, dump, family_queues, f3,
                          ledger_facts, load_ledger, load_receipts, load_snapshot, role_of, short, write)

ENGINE = {"integration_commit": "d5fc2fad9ed919467e096a3a7d4c2ec746d6c7e0", "engine_commit": "e3bfdfe",
          "note": "git diff --stat e3bfdfe d5fc2fa 只列出 tools/ninehour_receipts.py 和它的单测；引擎相同。"}


def build(ledger, receipts, repo, snapshot):
    queues = family_queues(repo)
    rows = []
    for side in ("guest", "fa706g3"):
        for order, (number, case, scenario) in enumerate(queues[side], 1):
            runs = []
            for run_id, entry in ledger.items():
                # every regression or retry run of the scenario, on either machine (a retry can land on the other half)
                if role_of(entry.get("label")) != "regress" or entry["scenario"].strip() != scenario:
                    continue
                receipt = receipts.get(run_id)
                runs.append({
                    "run_id": run_id, "label": entry.get("label"), "commit": entry.get("commit"),
                    "started": entry.get("started"), "ended": entry.get("ended"),
                    "ledger_line": entry["_line"], "ledger_scenario_raw": entry["scenario"],
                    "machine": MACHINE_OF_LEDGER.get(entry["machine"], entry["machine"]),
                    "verdict": receipt["verdicts"]["release_verdict"] if receipt else entry.get("verdict"),
                    "verified_pass": receipt["verdicts"]["verified_pass"] if receipt else None,
                    "cleanup_confirmed": receipt["verdicts"]["cleanup_confirmed"] if receipt else None,
                    "process_seconds": receipt["seconds"]["guest"] if receipt else None,
                    "host_wall_seconds": receipt["seconds"]["host_wall"] if receipt else None,
                    "script_action_seconds": receipt["seconds"]["script_action"] if receipt else None,
                    "host_orchestration_seconds": entry.get("process_seconds"),
                    "dispatch_error": None if receipt else (entry.get("worker_error") or "no result.json"),
                    "worker_error": entry.get("worker_error"),
                })
            runs.sort(key=lambda run: (run["started"] or "", run["run_id"]))
            done = [run for run in runs if run["verdict"]]
            failed = [run for run in done if run["verdict"] != "SHADOW" or run["verified_pass"] is False]
            status = ("done_with_failure" if failed else "done") if done else ("dispatch_failed" if runs else "not_run_yet")
            rows.append({
                "order": order, "machine": side, "machine_text": MACHINE_TEXT[side], "feishu_row": number,
                "case_id": case, "scenario": scenario,
                "record_id": snapshot.get(number, {}).get("record_id"), "title": snapshot.get(number, {}).get("title"),
                "feishu_status": snapshot.get(number, {}).get("status"), "runs": runs,
                "status": status,
            })
    done = [row for row in rows if row["status"] in ("done", "done_with_failure")]
    counts = {
        "rows": len(rows), "per_machine": {side: len(queues[side]) for side in queues},
        "done": len(done),
        "done_per_machine": dict(collections.Counter(row["machine"] for row in done)),
        "done_by_verdict": dict(collections.Counter(run["verdict"] for row in done for run in row["runs"] if run["verdict"])),
        "done_with_failure": sorted(row["feishu_row"] for row in rows if row["status"] == "done_with_failure"),
        "failed_runs": [{"feishu_row": row["feishu_row"], "run_id": run["run_id"], "machine": row["machine"],
                         "label": run["label"], "verdict": run["verdict"], "worker_error": run["worker_error"]}
                        for row in rows for run in row["runs"] if run["verdict"] and run["verdict"] != "SHADOW"],
        "dispatch_failed_runs": sorted(run["run_id"] for row in rows for run in row["runs"] if run["dispatch_error"]),
        "rows_with_a_failed_dispatch": sorted(row["feishu_row"] for row in rows if any(run["dispatch_error"] for run in row["runs"])),
        "rows_only_dispatch_failed": sorted(row["feishu_row"] for row in rows if row["status"] == "dispatch_failed"),
        "not_run_yet": sorted(row["feishu_row"] for row in rows if row["status"] == "not_run_yet"),
    }
    return dict(ledger_facts(ledger), **{
        "schema": "ninehour_family_regression/1", "generated_by": "scripts/build_family.py",
        "status": "in_progress", "placeholder": True,
        "placeholder_note": "最终引擎上的 42 行参数族回归仍在进行。本文件在台账复制时生成，只填台账里已有的结果；没有结果的行留空，由总控在回归结束后补入。",
        "engine": ENGINE, "counts": counts, "rows": rows,
    })


def markdown(data):
    counts = data["counts"]
    lines = [
        "# 参数族 42 行在最终引擎上的回归（进行中，占位）", "",
        "**状态：进行中。** %s" % data["placeholder_note"], "",
        "引擎：合并提交 d5fc2fa。%s" % data["engine"]["note"],
        "台账复制时共 %d 行、%d 个 run，末行结束于 %s。两台机器分跑，每行计划一次（失败后的重试也列在该行里）：客机 win11-test %d 行，fa706g3 %d 行"
        "（客机是回归证据机；fa706g3 最高记 SHADOW）。" % (
            data["ledger_lines"], data["ledger_runs"], data["ledger_last_ended"],
            counts["per_machine"]["guest"], counts["per_machine"]["fa706g3"]), "",
        "已出结果 %d 行（客机 %d，fa706g3 %d；评级计数 %s），其中出现过失败运行的 %d 行（%s）。尚未出结果 %d 行（%s）。派发失败 %d 次（%s），落在 %s。" % (
            counts["done"], counts["done_per_machine"].get("guest", 0), counts["done_per_machine"].get("fa706g3", 0),
            ", ".join("%s %d" % item for item in sorted(counts["done_by_verdict"].items())) or "无",
            len(counts["done_with_failure"]), "、".join("#%d" % n for n in counts["done_with_failure"]) or "无",
            len(counts["not_run_yet"]), "、".join("#%d" % n for n in counts["not_run_yet"]) or "无",
            len(counts["dispatch_failed_runs"]), "、".join(short(run_id) for run_id in counts["dispatch_failed_runs"]) or "无",
            "、".join("#%d" % n for n in counts["rows_with_a_failed_dispatch"]) or "无"),
        "",
        "- 「出现过失败运行」的行：该行在最终引擎上至少一次运行不是 SHADOW。重试用 `retry-` 标签记，算作同一行的回归运行；重试落在另一台机器时，在该行里注出机器。",
        "- 「派发失败」是队列脚本把行尾的 CR 带进了场景名（台账场景名以 `\\r` 结尾，`native_save_run.py` 打印用法后退出，没有 `result.json`，没有收据），不是用例失败；队列脚本修正后重派。",
        "- 回归只回答「引擎改动有没有破坏这 42 行已有的写入和导出」，不逐项核对飞书预期；预期核对见 `feishu-216-ninehour.md` 的「未通过项」和 11-24 的对照表。",
        "- 评级取收据的 `release_verdict`；fa706g3 上的 SHADOW 按 README 第 6 条不作为发布证据。",
        "",
        "| 飞书编号 | record ID | 用例标题 | 飞书状态 | 场景 | 机器 | 顺序 | run ID | 提交 | 起 | 止 | 宿主整轮秒 | 机内进程秒 | 动作秒 | 评级 | 状态 |",
        "|---|---|---|---|---|---|---:|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in data["rows"]:
        base = [str(row["feishu_row"]), "`%s`" % row["record_id"], row["title"] or "-", row["feishu_status"] or "-",
                row["scenario"], row["machine_text"], str(row["order"])]
        if not row["runs"]:
            lines.append("| " + " | ".join(base + ["-"] * 9) + " |")
            continue
        for index, run in enumerate(row["runs"]):
            cells = base if index == 0 else [""] * 7
            lines.append("| " + " | ".join(cells + [
                "`%s`" % run["run_id"], commit_text(run["commit"]), run["started"] or "-", run["ended"] or "-",
                f3(run["host_wall_seconds"]), f3(run["process_seconds"]), f3(run["script_action_seconds"]),
                run["verdict"] or "-",
                "%s %s" % (run["label"], run["worker_error"] or "") if run["dispatch_error"] else
                "%s%s%s" % (run["label"], "" if run["machine"] == row["machine"] else "（%s）" % MACHINE_TEXT[run["machine"]],
                            "" if run["verdict"] == "SHADOW" and run["verified_pass"] is not False else "（失败）")]) + " |")
    lines += ["", "来源：`family-regression.json`（`scripts/build_family.py`）。"]
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
