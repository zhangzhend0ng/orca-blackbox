"""Render the run record from the template and the evidence files.

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/finalize_record.py [--repo .] [--evidence <folder>] [--out <record>]

Reads scripts/run-record.template.md, ledger.jsonl and the JSON tables of the evidence folder, runs
record_rows.py for the per-row table, and writes the record (by default
docs/runs/glm54-nine-hour-run-2026-11-25.md). Every @@PLACEHOLDER@@ of the template is replaced from
those files; what the template says outside the placeholders was written by hand and is checked
against the tables by the verification step of the session, not here.

Run it last, after build_stage.py, build_native.py, build_family.py and build_feishu.py.
"""
from __future__ import annotations

import argparse
import collections
import subprocess
import sys
from pathlib import Path

from build_common import EVIDENCE, MACHINE_TEXT, f3, read_json, role_of

RECORD = "docs/runs/glm54-nine-hour-run-2026-11-25.md"


def seconds(clock):
    hour, minute, second = clock.split(":")
    return int(hour) * 3600 + int(minute) * 60 + int(second)


def verdict_text(count):
    return "，".join("%s %d" % (key, count[key]) for key in ("SHADOW", "NON_GREEN", "派发失败") if count.get(key))


def machine_stats(ledger, receipts):
    stats = {}
    for machine in ("win11-test", "fa706g3"):
        runs = sorted((r for r in ledger.values() if r["machine"] == machine), key=lambda r: r["started"])
        wall = sum(seconds(r["ended"]) - seconds(r["started"]) for r in runs)
        process = sum(r["process_seconds"] for r in runs)
        in_machine = sum(receipts[r["run_id"]]["seconds"]["guest"] for r in runs
                         if r["run_id"] in receipts and receipts[r["run_id"]]["seconds"]["guest"] is not None)
        action = sum(receipts[r["run_id"]]["seconds"]["script_action"] for r in runs
                     if r["run_id"] in receipts and receipts[r["run_id"]]["seconds"]["script_action"] is not None)
        span = seconds(max(r["ended"] for r in runs)) - seconds(runs[0]["started"])
        gaps = sorted(((seconds(b["started"]) - seconds(a["ended"]), a["run_id"][:8]) for a, b in zip(runs, runs[1:])), reverse=True)
        verdicts = collections.Counter(r.get("release_verdict") or r.get("verdict") or "派发失败" for r in runs)
        stats[machine] = {"runs": len(runs), "first": runs[0]["started"], "last": max(r["ended"] for r in runs), "wall": wall,
                          "process": process, "in_machine": in_machine, "action": action, "span": span, "gaps": gaps,
                          "verdicts": verdicts}
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--evidence", default=str(EVIDENCE))
    parser.add_argument("--out", default=RECORD)
    args = parser.parse_args(argv)
    repo, evidence, out = Path(args.repo), Path(args.evidence), Path(args.out)
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
    summary, counts, fc = feishu["summary"], family["counts"], family["counts"]

    guest, fa = machine_stats(ledger, receipts)["win11-test"], machine_stats(ledger, receipts)["fa706g3"]
    progress = family["in_progress"]
    intro = ("进行中的两批孪生场景（客机自有模型 %d 个 run、fa706g3 多形状夹具 %d 个 run）本版不计。"
             % (len(progress["twins"]), len(progress["shapes"])))

    partial, speed, failed, recovered, regression = (summary["partial_evidence_filled"], summary["speed_only"],
                                                     summary["failed_or_pending"], summary["recovered_failed_rounds"],
                                                     summary["regression_final_engine"])
    list_of = lambda rows: "、".join("#%d" % n for n in rows)      # noqa: E731
    regress_failed_runs = summary["failed_or_pending"]["regression_failure_runs"]
    failed_by_row = collections.defaultdict(list)
    for run in regress_failed_runs:
        failed_by_row[run["feishu_row"]].append("%s `%s`" % ("客机" if run["machine"] == "guest" else run["machine"], run["run_id"][:8]))
    fourway = "\n".join([
        "四类汇总按飞书记录 ID 去重，一行可以落在不止一类里：",
        "",
        "- 本轮新增完整覆盖 %d 条。" % summary["new_full_coverage"]["count"],
        "- 补齐部分证据 %d 条：%s。都是补覆盖：脚本在空闲机器上多跑一次，过了自检并导出；单独记账，不计闭环，也不改 11‑24 对照表的覆盖列。"
        % (partial["count"], list_of(partial["rows"])),
        "- 纯提速 %d 条：%s。同机、同构建线、同初态，动作秒分别省约 40 秒和 15 秒；最终引擎 `2a17376` 上复核过，节省还在（第 3 节）。"
        % (speed["count"], list_of(speed["rows"])),
        "- 失败或待确认 %d 条：%s 的原生模型对照都是 NON_GREEN，配对 0 次；%s。Mac 的壁环数运行不对应飞书原行，不计入行数。"
        % (failed["count"], list_of(failed["native_rows"]), "；".join(
            "#%d 在最终引擎回归里是 NON_GREEN（%s），它是 11‑24 就开着的行，不是这次改动造成的" % (row, "、".join(runs))
            for row, runs in sorted(failed_by_row.items()))),
        "- 已恢复的失败轮 %d 条：%s。在 `d5fc2fa` 上失败过，重试通过，最终引擎 `2a17376` 上的回归也通过（第 3 节）。"
        % (len(recovered["rows"]), list_of(recovered["rows"])),
        "",
        "最终引擎回归的 %d 行（%d 行 SHADOW）只确认引擎改动没有破坏该行已有的写入和导出，不进这四类，见第 5 节。"
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

    regress = ("42 行在 `2a17376` 上两台机器分跑，每行在分到的那台机器上跑一次（客机 21 行、fa706g3 21 行），客机另给 #294 加跑了一次："
               "%d 行 SHADOW（客机 %d 行全部，fa706g3 %d 行），NON_GREEN %d 行（%s）。" % (
                   len(regression["shadow_rows"]), fc["per_machine"]["guest"]["SHADOW"], fc["per_machine"]["fa706g3"]["SHADOW"],
                   len(regression["failed_rows"]), "；".join("#%d：%s" % (row, "、".join(runs)) for row, runs in sorted(failed_by_row.items()))))
    # the in-progress batches are only mentioned; a run of them that did not pass is named, not hidden
    def verdict_of(entry):
        return (receipts.get(entry["run_id"], {}).get("verdicts", {}).get("release_verdict") if entry["run_id"] in receipts else None) \
            or entry.get("verdict")
    not_passed = [entry for entry in ledger.values() if role_of(entry.get("label")) in ("twins", "shapes")
                  and verdict_of(entry) and verdict_of(entry) != "SHADOW"]
    in_progress = ("进行中、本版不计：标签 `guest-twins`（客机 8 个自有模型的孪生场景）和 `fa-shapes`（fa706g3 的多形状夹具孪生场景）"
                   "在本文写成时还在跑，台账复制时各有 %d 个和 %d 个 run%s。" % (
                       len(progress["twins"]), len(progress["shapes"]),
                       "；其中没通过的有 " + "、".join(
                           "%s `%s`（`%s`，%s）" % ("客机" if entry["machine"] == "win11-test" else "fa706g3", entry["run_id"][:8],
                                                  entry["scenario"], entry.get("worker_error")) for entry in not_passed)
                       + "，同样留给以后补" if not_passed else ""))
    occupancy = (
        "人工分钟未测。台账能算出的机器占用（到 %s）：客机第一条 %s 开始、最后一条 %s 结束，%d 个 run 的宿主编排秒合计 %.0f 秒（%.1f 分钟），占这段时间的 %.1f%%；"
        "fa706g3 第一条 %s 开始、最后一条 %s 结束，%d 个 run 从投递到收割合计 %.0f 秒（%.1f 分钟），占 %.1f%%。"
        "按机内 `process.json` 算，客机合计 %.0f 秒，fa706g3 %.0f 秒；脚本动作分别 %.0f 秒和 %.0f 秒。"
        "台账只有每个 run 的启动和结束时刻，没有派工时刻，所以算不出排队时间，只能算相邻两个 run 之间的空档：客机合计 %d 秒（最长 %d 秒，`%s` 之后），fa706g3 合计 %d 秒（最长 %d 秒，`%s` 之后）。"
        "宿主编排里启动应用和收割各占多少没有分开记；fa706g3 的合计含 10 秒一次的轮询；Mac 的 `ledger.txt` 只有起始时刻，没有时长。" % (
            max(guest["last"], fa["last"]), guest["first"], guest["last"], guest["runs"], guest["process"], guest["process"] / 60,
            guest["wall"] / guest["span"] * 100, fa["first"], fa["last"], fa["runs"], fa["process"], fa["process"] / 60,
            fa["wall"] / fa["span"] * 100, guest["in_machine"], fa["in_machine"], guest["action"], fa["action"],
            sum(gap for gap, _ in guest["gaps"] if gap > 0), guest["gaps"][0][0], guest["gaps"][0][1],
            sum(gap for gap, _ in fa["gaps"] if gap > 0), fa["gaps"][0][0], fa["gaps"][0][1]))

    text = (evidence / "scripts" / "run-record.template.md").read_text(encoding="utf-8")
    for key, value in (("@@INTRO@@", intro), ("@@G_RUNS@@", str(guest["runs"])), ("@@G_VERDICTS@@", verdict_text(guest["verdicts"])),
                       ("@@F_RUNS@@", str(fa["runs"])), ("@@F_VERDICTS@@", verdict_text(fa["verdicts"])), ("@@FOURWAY@@", fourway),
                       ("@@ROWS@@", rows), ("@@FINAL2@@", "；".join(confirmations) + "。"), ("@@REPRO@@", "；".join(repro) + "。"),
                       ("@@REGRESS@@", regress), ("@@INPROGRESS@@", in_progress), ("@@OCCUPANCY@@", occupancy)):
        assert text.count(key) == 1, key
        text = text.replace(key, value)
    assert "@@" not in text
    out.write_text(text, encoding="utf-8", newline="\n")
    print("wrote %s (%d lines)" % (out.as_posix(), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
