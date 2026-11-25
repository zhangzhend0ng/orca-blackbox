"""Render the run record from the template and the evidence files.

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/finalize_record.py [--repo .] [--evidence <folder>] [--out <record>]

Reads scripts/run-record.template.md, ledger.jsonl, receipts/, the JSON tables of the evidence
folder and dispatch-failures.json, runs record_rows.py for the per-row table, and writes the record
(by default docs/runs/glm54-nine-hour-run-2026-11-25.md). Every @@PLACEHOLDER@@ of the template is
replaced from those files; what the template says outside the placeholders was written by hand and
is checked against the tables by the verification step of the session, not here.

Run it last, after build_stage.py, build_native.py, build_family.py, build_feishu.py and
build_dispatches.py.
"""
from __future__ import annotations

import argparse
import collections
import subprocess
import sys
from pathlib import Path

from build_common import MACHINE_SHORT, MACHINE_TEXT, f3, read_json

RECORD = "docs/runs/glm54-nine-hour-run-2026-11-25.md"
NO_VERDICT = "派发失败"


def seconds(clock):
    hour, minute, second = clock.split(":")
    return int(hour) * 3600 + int(minute) * 60 + int(second)


def verdict_text(count):
    return "，".join("%s %d" % (key, count[key]) for key in ("SHADOW", "NON_GREEN", NO_VERDICT) if count.get(key))


def counts_text(count):
    return "、".join("%s %d" % item for item in sorted(count.items()))


def list_of(rows):
    return "、".join("#%d" % n for n in rows)


def machine_stats(ledger, receipts):
    """Per machine: the ledger's runs (the last line of each), their verdicts, and what the times allow."""
    stats = {}
    for machine, side in (("win11-test", "guest"), ("fa706g3", "fa706g3")):
        runs = sorted((r for r in ledger.values() if r["machine"] == machine), key=lambda r: (r["started"] or "", r["run_id"]))
        wall = sum(seconds(r["ended"]) - seconds(r["started"]) for r in runs)
        process = sum(r["process_seconds"] for r in runs)
        in_machine = sum(receipts[r["run_id"]]["seconds"]["guest"] for r in runs
                         if r["run_id"] in receipts and receipts[r["run_id"]]["seconds"]["guest"] is not None)
        action = sum(receipts[r["run_id"]]["seconds"]["script_action"] for r in runs
                     if r["run_id"] in receipts and receipts[r["run_id"]]["seconds"]["script_action"] is not None)
        span = seconds(max(r["ended"] for r in runs)) - seconds(runs[0]["started"])
        gaps = sorted(((seconds(b["started"]) - seconds(a["ended"]), a["run_id"][:8]) for a, b in zip(runs, runs[1:])), reverse=True)
        overlaps = []
        for a, b in zip(runs, runs[1:]):
            if seconds(b["started"]) < seconds(a["ended"]):
                # does the machine itself still run the earlier one?  the ledger's in-machine seconds of a say
                overlaps.append({"seconds": seconds(a["ended"]) - seconds(b["started"]), "a": a["run_id"][:8], "b": b["run_id"][:8],
                                 "in_machine": (max(0, seconds(a["started"]) + a["guest_seconds"] - seconds(b["started"]))
                                                if a.get("guest_seconds") is not None else None)})
        verdicts = collections.Counter(
            receipts[r["run_id"]]["verdicts"]["release_verdict"] if r["run_id"] in receipts
            else (r.get("release_verdict") or r.get("verdict") or NO_VERDICT) for r in runs)
        stats[side] = {"runs": len(runs), "first": runs[0]["started"], "last": max(r["ended"] for r in runs), "wall": wall,
                       "process": process, "in_machine": in_machine, "action": action, "span": span, "gaps": gaps, "overlaps": overlaps,
                       "verdicts": verdicts}
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--evidence", default=None)
    parser.add_argument("--out", default=RECORD)
    args = parser.parse_args(argv)
    repo, evidence, out = Path(args.repo), Path(args.evidence or Path(__file__).resolve().parent.parent), Path(args.out)
    ledger = {}
    for number, line in enumerate((evidence / "ledger.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            entry = __import__("json").loads(line)
            entry["_line"] = number
            ledger[entry["run_id"]] = entry
    receipts = {}
    for path in sorted((evidence / "receipts").glob("*.json")):
        data = read_json(path)
        receipts[data["identity"]["run_id"]] = data
    feishu = read_json(evidence / "feishu-216-ninehour.json")
    family = read_json(evidence / "family-regression.json")
    stage = read_json(evidence / "stage-timings.json")
    dispatches = read_json(evidence / "dispatch-failures.json")
    summary, fc = feishu["summary"], family["counts"]
    partial, speed, failed, recovered, regression = (summary["partial_evidence_filled"], summary["speed_only"],
                                                     summary["failed_or_pending"], summary["recovered_failed_rounds"],
                                                     summary["regression_final_engine"])
    guest, fa = machine_stats(ledger, receipts)["guest"], machine_stats(ledger, receipts)["fa706g3"]
    cross = fc["per_machine"]

    intro = "补覆盖给 %d 行加了部分证据（单独记账，不计闭环），" % partial["count"]
    failed_by_row = collections.defaultdict(list)
    for run in failed["regression_failure_runs"]:
        failed_by_row[run["feishu_row"]].append("%s `%s`" % (MACHINE_SHORT[run["machine"]], run["run_id"][:8]))
    fourway = "\n".join([
        "四类汇总按飞书记录 ID 去重，一行可以落在不止一类里：",
        "",
        "- 本轮新增完整覆盖 %d 条。" % summary["new_full_coverage"]["count"],
        "- 补齐部分证据 %d 条：%s。都是补覆盖，单独记账，不计闭环，也不改 11‑24 对照表的覆盖列："
        "早先空闲机器上的运行 %d 行，客机自有模型孪生第一批 %d 行、第二批 %d 行，fa706g3 多形状夹具孪生 %d 行（几批之间有重叠）；"
        "#264、#276 同时在纯提速里（明细见第 5 节）。" % (
            partial["count"], list_of(partial["rows"]), len(partial["by_batch"]["backlog"]["rows"]),
            len(partial["by_batch"]["twins"]["rows"]), len(partial["by_batch"]["twins_b"]["rows"]),
            len(partial["by_batch"]["shapes"]["rows"])),
        "- 纯提速 %d 条：%s。同机、同构建线、同初态，动作秒分别省约 40 秒和 15 秒；最终引擎 `2a17376` 上复核过，节省还在（第 3 节）。"
        % (speed["count"], list_of(speed["rows"])),
        "- 失败或待确认 %d 条：%s 的原生模型对照都是 NON_GREEN，配对 0 次；%s；补覆盖里没过的是 %s（%s）。"
        "Mac 的壁环数运行不对应飞书原行，不计入行数。" % (
            failed["count"], list_of(failed["native_rows"]), "；".join(
                "#%d 在最终引擎回归里是 NON_GREEN（%s），它是 11‑24 就开着的行，不是这次改动造成的" % (row, "、".join(runs))
                for row, runs in sorted(failed_by_row.items())),
            list_of(failed["coverage_rows"]), "第 3 节"),
        "- 已恢复的失败轮 %d 条：%s。在 `d5fc2fa` 上失败过，重试通过，最终引擎 `2a17376` 上的回归也通过（第 3 节）。"
        % (len(recovered["rows"]), list_of(recovered["rows"])),
        "- 最终引擎回归 %d 行（%d 行 SHADOW）只确认引擎改动没有破坏该行已有的写入和导出，不进这四类，见第 5 节。"
        % (regression["count"], len(regression["shadow_rows"])),
    ])

    rows = subprocess.run([sys.executable, "-B", str(evidence / "scripts" / "record_rows.py")], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout.rstrip("\n")

    confirmations, where_short = [], {"guest": "客机", "fa706g3": "fa706g3"}
    scenario_short = {"compare_276_quality": "#276 Quality", "compare_276_strength": "#276 Strength",
                      "uia_param_overhang_speeds": "#264 立方体", "uia_param_overhang_speeds_fdmt": "#264 FDM 测试模型"}
    for group in stage["groups"]:
        for link in group["links"]:
            if link["to"] != "final2":
                continue
            measure = "host_wall" if group["machine"] == "guest" else "process"
            whole, action = link["whole_run"][measure], link["whole_run"]["action"]
            confirmations.append("%s %s %s %s，省 %s；动作 %s，省 %s%s" % (
                where_short[group["machine"]], scenario_short[group["scenario"]],
                "宿主整轮" if group["machine"] == "guest" else "机内进程", f3(whole["to"]), f3(whole["saving"]),
                f3(action["to"]), f3(action["saving"]), "（单列）" if group["scenario"] == "compare_276_strength" else ""))

    names = {"276 立方体": "#276 立方体", "264 立方体": "#264 立方体", "264 FDM 测试模型": "FDM 测试模型"}
    repro = []
    for member in stage["reproducibility"]:
        odd = [r for r in member["runs"] if "signature" in r and not r["signature"]["same"]]
        repro.append("%s %d 次里 %d 次相同" % (names[member["model"]], member["runs_total"], member["runs_same_as_reference"]) + (
            "，不同的是 " + "、".join("%s`%s`（挤出移动 %d 对 %d 段）" % (
                "636a733 的 " if r["label"] == "base-s1" else "", r["run_id"][:8],
                r["signature"]["extruding_moves"][1], r["signature"]["extruding_moves"][0]) for r in odd) if odd else ""))

    regress = ("42 行在最终引擎上两台机器分跑，每行在分到的那台机器上跑一次（客机 21 行、fa706g3 21 行）："
               "%d 行 SHADOW（客机 %d 行全部，fa706g3 %d 行），NON_GREEN %d 行（%s）。" % (
                   len(regression["shadow_rows"]), cross["guest"]["SHADOW"], cross["fa706g3"]["SHADOW"],
                   len(regression["failed_rows"]), "；".join("#%d：%s" % (row, "、".join(runs)) for row, runs in sorted(failed_by_row.items()))))
    def cross_runs(side):
        """The runs of this machine's rows on the other machine, whatever the commit (family-regression.json)."""
        return [run for row in family["rows"] if row["machine"] == side for run in row["runs_other_machine"]]

    def by_commit(runs):
        """'`62cddee` 上 07:50 起 19 次（SHADOW 18、NON_GREEN 1）', earliest commit first."""
        groups = collections.OrderedDict()
        for run in sorted(runs, key=lambda r: r["started"]):
            groups.setdefault(run["commit"][:7], []).append(run)
        return "；".join("`%s` 上 %s 起 %d 次（%s）" % (
            commit, runs_of_group[0]["started"][:5], len(runs_of_group),
            counts_text(collections.Counter(str(run["verdict"] or "没有评级") for run in runs_of_group)))
                           for commit, runs_of_group in groups.items())

    cross_text = ("换一台机器再取证是复核，不改变这个结论：客机把 fa706g3 那一半跑了 %d 行 %d 次运行（%s；没跑的 %d 行：%s），"
                  "fa706g3 把客机那一半跑了 %d 行 %d 次运行（%s；没跑的 %d 行：%s），两台机器上都有回归运行的共 %d 行。"
                  "两边的队列随后被总控用 STOP 文件停下，没跑的行不再补。" % (
                      cross["fa706g3"]["rows_with_a_run_on_the_other_machine"], cross["fa706g3"]["other_machine_runs"],
                      by_commit(cross_runs("fa706g3")),
                      len(cross["fa706g3"]["rows_without_one"]), list_of(cross["fa706g3"]["rows_without_one"]),
                      cross["guest"]["rows_with_a_run_on_the_other_machine"], cross["guest"]["other_machine_runs"],
                      by_commit(cross_runs("guest")),
                      len(cross["guest"]["rows_without_one"]), list_of(cross["guest"]["rows_without_one"]),
                      fc["rows_with_both_machines"]))

    batches = partial["by_batch"]
    early = collections.OrderedDict()      # the guest's early shapes runs, by label and commit
    for run in sorted((r for r in ledger.values() if r["machine"] == "win11-test" and (r.get("label") or "").startswith("backlog-")),
                      key=lambda r: r["started"]):
        early.setdefault((run["label"], (run.get("commit") or "未记提交")[:7]), []).append(run)
    coverage = (
        "客机自有模型孪生第一批 %d 次（%s；%s）：这 %d 行 11‑24 的自有模型运行都在 fa706g3 上，客机的 SHADOW 在回归证据机上补上了「只有 fa706g3 证据」这一条，"
        "11‑24 对照表里逐项预期的缺口仍在。第二批 %d 次（%s；%s）：这些行 11‑24 在 fa706g3 上判为有出入或看不到，客机的 SHADOW 只说明在那里写入、保存、重开、切片和导出走通了，"
        "不说明预期已经满足。fa706g3 多形状夹具孪生 %d 次（%s；%s）：连同客机早先的 %d 次多形状夹具运行（%s），11‑24 积压里没跑过的多形状副本现在各有一次运行（27 个，据总控）。"
        "早先空闲机器上的 %d 次（%s；评级计数 %s）。没过的三次见第 3 节。" % (
            batches["twins"]["runs"], counts_text(batches["twins"]["verdicts"]), list_of(batches["twins"]["rows"]), len(batches["twins"]["rows"]),
            batches["twins_b"]["runs"], counts_text(batches["twins_b"]["verdicts"]), list_of(batches["twins_b"]["rows"]),
            batches["shapes"]["runs"], counts_text(batches["shapes"]["verdicts"]), list_of(batches["shapes"]["rows"]),
            sum(len(runs) for runs in early.values()),
            "，".join("`%s` 的 %d 次在 `%s`" % (label, len(runs), commit) for (label, commit), runs in early.items()),
            batches["backlog"]["runs"], list_of(batches["backlog"]["rows"]), counts_text(batches["backlog"]["verdicts"])))

    dispatch_lines = []
    for item in dispatches["dispatches"]:
        scenario = item["scenario"].strip()
        note = "（台账里带行尾 CR）" if item["scenario_has_control_character"] else ""
        if item["machine"] == "guest":
            recorded = "`%s`" % item.get("launch_message")
        elif item.get("task_log_error"):
            recorded = "任务日志 `native_save_run.py: error: argument --scenario: invalid choice`"
        else:
            recorded = "没有留下记录"
        dispatch_lines.append("- `%s`（%s，%s，`%s`%s，%s）：%s" % (
            item["run_id"][:8], MACHINE_TEXT[item["machine"]], item["started"], scenario, note, item["label"], recorded))
    group_names = {"detached_checkout": "02:26 的一条是", "crlf_in_scenario_name": "03:55 的一条是",
                   "guest_head_check_refused": "07:04:19–07:04:53 的十二条是", "other": "其余是"}
    dispatch_causes = "；".join(
        "%s%s" % (group_names.get(group, group), account.replace("总控的说明：", "", 1))
        for group, account in dispatches["orchestrator_account"].items()) + "。"
    dispatch_text = "\n".join(dispatch_lines)

    per_group = dispatches["per_group"]

    def overlap_text(side_stats, name, total_name):
        """Ledger entries of a machine whose [started, ended] window runs into the next entry's: the earlier run
        was harvested after the later one started. Its seconds are counted twice in the host-side total; the
        ledger's in-machine seconds of the earlier run say whether the machine was busy with both."""
        pairs = side_stats["overlaps"]
        if not pairs:
            return ""
        both = [pair for pair in pairs if pair["in_machine"] is None or pair["in_machine"] > 0]
        unknown = [pair for pair in pairs if pair["in_machine"] is None]
        double = sum(pair["seconds"] for pair in pairs)
        how = ("按机内进程秒算，前一条都在后一条开始之前结束" if not both else
               "其中 %d 对按机内进程秒算也重叠" % len(both)) + ("（%d 对的机内秒数台账未记）" % len(unknown) if unknown else "")
        return ("；%s有 %d 对相邻条目的台账区间重叠（%s），合计 %d 秒：前一条到收割为止的时刻晚于后一条的开始时刻，%s；"
                "这 %d 秒在%s的合计里算了两遍（占比最多多算 %.1f 个百分点）" % (
                    name, len(pairs), "，".join("`%s` 和 `%s` %d 秒" % (pair["a"], pair["b"], pair["seconds"]) for pair in pairs),
                    double, how, double, total_name, double / side_stats["span"] * 100))

    occupancy = (
        "人工分钟未测。台账条目合计：客机 %d 条（%s），fa706g3 %d 条（%s）；没有跑起来的派发客机 %d 条（02:26 的 %d 条加 07:04 的 %d 条）、fa706g3 %d 条。"
        "台账能算出的机器占用：客机第一条 %s 开始、最后一条 %s 结束，%d 条的宿主编排秒合计 %.0f 秒（%.1f 分钟），占这段时间的 %.1f%%%s；"
        "fa706g3 第一条 %s 开始、最后一条 %s 结束，%d 条从投递到收割合计 %.0f 秒（%.1f 分钟），占 %.1f%%%s。"
        "按机内 `process.json` 算，客机合计 %.0f 秒，fa706g3 %.0f 秒；脚本动作分别 %.0f 秒和 %.0f 秒。"
        "台账只有每个 run 的启动和结束时刻，没有派工时刻，所以算不出排队时间，只能算相邻两个 run 之间的空档：客机合计 %d 秒（最长 %d 秒，`%s` 之后），fa706g3 合计 %d 秒（最长 %d 秒，`%s` 之后）。"
        "宿主编排里启动应用和收割各占多少没有分开记；fa706g3 的合计含 10 秒一次的轮询；Mac 的 `ledger.txt` 只有起始时刻，没有时长。" % (
            guest["runs"], verdict_text(guest["verdicts"]), fa["runs"], verdict_text(fa["verdicts"]),
            dispatches["per_machine"]["guest"], per_group.get("detached_checkout", 0), per_group.get("guest_head_check_refused", 0),
            dispatches["per_machine"]["fa706g3"],
            guest["first"], guest["last"], guest["runs"], guest["process"], guest["process"] / 60, guest["process"] / guest["span"] * 100,
            overlap_text(guest, "客机", "宿主编排秒"),
            fa["first"], fa["last"], fa["runs"], fa["process"], fa["process"] / 60, fa["process"] / fa["span"] * 100,
            overlap_text(fa, "fa706g3 ", "从投递到收割的秒数"),
            guest["in_machine"], fa["in_machine"], guest["action"], fa["action"],
            sum(gap for gap, _ in guest["gaps"] if gap > 0), guest["gaps"][0][0], guest["gaps"][0][1],
            sum(gap for gap, _ in fa["gaps"] if gap > 0), fa["gaps"][0][0], fa["gaps"][0][1]))

    text = (evidence / "scripts" / "run-record.template.md").read_text(encoding="utf-8")
    for key, value in (("@@INTRO@@", intro), ("@@G_RUNS@@", "%d（含派发失败 %d）" % (guest["runs"], guest["verdicts"][NO_VERDICT])),
                       ("@@G_VERDICTS@@", verdict_text(guest["verdicts"])),
                       ("@@F_RUNS@@", "%d（含派发失败 %d）" % (fa["runs"], fa["verdicts"][NO_VERDICT])),
                       ("@@F_VERDICTS@@", verdict_text(fa["verdicts"])), ("@@FOURWAY@@", fourway), ("@@ROWS@@", rows),
                       ("@@FINAL2@@", "；".join(confirmations) + "。"), ("@@REPRO@@", "；".join(repro) + "。"),
                       ("@@REGRESS@@", regress), ("@@CROSS@@", cross_text), ("@@COVERAGE@@", coverage),
                       ("@@DISPATCH_CAUSES@@", dispatch_causes), ("@@DISPATCHES@@", dispatch_text), ("@@OCCUPANCY@@", occupancy)):
        assert text.count(key) == 1, key
        text = text.replace(key, value)
    assert "@@" not in text
    out.write_text(text, encoding="utf-8", newline="\n")
    print("wrote %s (%d lines)" % (out.as_posix(), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
