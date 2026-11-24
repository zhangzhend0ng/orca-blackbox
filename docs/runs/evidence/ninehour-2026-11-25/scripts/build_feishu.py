"""The 216-row Feishu comparison table with the columns of the nine-hour run (2026-11-25).

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_feishu.py --repo <checkout at d5fc2fa> --combined <combined.json of 11-24>
                                               [--snapshot <216-row ndjson>] [--evidence <folder>]

Reads the 11-24 table (--combined, outside the repository: artifacts/ is git-ignored), the committed
Feishu snapshot, and ledger.jsonl, receipts/, stage-timings.json, facts.json and
negative-controls.json of the evidence folder; runs tools/param_closure_list.py of --repo (read-only)
to map scenario names to Feishu rows. Writes feishu-216-ninehour.json and .md next to scripts/.
Run build_stage.py first: the seconds come from stage-timings.json.

What the table keeps: the 216 rows in their order, and columns 1-15 of every row exactly as the
11-24 table has them (checked below). The seven new columns are null for a row no run of tonight
belongs to. A run is the LAST ledger line written for its run id; a run without a receipt (nothing
was harvested) is still listed, as a failed dispatch.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import sys
from pathlib import Path

from build_common import (EVIDENCE, MACHINE_OF_LEDGER, MACHINE_TEXT, RECEIPTS, SNAPSHOT, commit_text, dump, family_rows,
                          feishu_row_of, f3, ledger_facts, load_ledger, load_receipts, load_snapshot, read_json, role_of,
                          short, write)

EXISTING_COLUMNS = ["用例编号", "飞书状态", "核验覆盖", "证据类型", "飞书用例标题", "仓库用例或近似入口", "已有实跑或核查结论",
                    "未覆盖项与适用边界", "运行记录与原判", "证据或排查出处", "飞书前置条件", "飞书测试步骤", "飞书预期结果",
                    "功能模块", "飞书 record_id"]
NEW_COLUMNS = ["操作类型", "基线秒数", "候选秒数（两次）", "整轮节省", "未通过项", "证据链接", "最终评级"]
SPEED_SCENARIOS = ("compare_276_quality", "compare_276_strength", "uia_param_overhang_speeds",
                   "uia_param_overhang_speeds_fdmt")
SCENARIO_SHORT = {"compare_276_quality": "Quality", "compare_276_strength": "Strength",
                  "uia_param_overhang_speeds": "立方体", "uia_param_overhang_speeds_fdmt": "FDM 测试模型"}
MODEL_OF = {"compare_276_quality": 276, "compare_276_strength": 276, "uia_param_overhang_speeds": 264,
            "uia_param_overhang_speeds_fdmt": 264}
STATUS_ORDER = ["已自动化", "部分自动化", "空白", "不适用", "待实现"]
COVERAGE_ORDER = ["完整", "部分", "未证实", "不适用"]
LEVEL_ORDER = ["有业务实证", "仅同族旁证", "仅适用性实测", "未定位"]
MACHINE_SHORT = {"guest": "客机", "fa706g3": "fa706g3"}
WHOLE_RUN = {"guest": ("host_wall", "宿主整轮秒"), "fa706g3": ("process", "机内进程秒")}
OP_TEXT = {"speed": "提速对照", "backlog": "补覆盖", "regress": "最终引擎回归", "final": "最终引擎复核",
           "native": "原生模型对照（失败）", "night_baseline": "同夜基线"}
THIS_FOLDER = "docs/runs/evidence/ninehour-2026-11-25"


def machines(runs):
    """'客机 win11-test ×2、fa706g3 ×1': each machine once, with how many of the runs."""
    count = collections.Counter(run["machine"] for run in runs)
    return "、".join("%s ×%d" % (MACHINE_TEXT[machine], number) for machine, number in sorted(count.items()))


def ordered(count, first):
    return {key: count[key] for key in list(first) + sorted(set(count) - set(first)) if key in count}


def kind(run):
    """What a run did tonight, for the 操作类型 column."""
    if run["role"] in ("backlog", "regress", "final", "native"):
        return run["role"]
    if run["scenario"] in SPEED_SCENARIOS:
        return "speed"
    return "night_baseline"


def collect(ledger, receipts, family):
    """{feishu row: [run]} of every ledger run that belongs to a Feishu row."""
    rows = collections.defaultdict(list)
    for run_id, entry in ledger.items():
        row = feishu_row_of(entry["scenario"].strip(), family)
        if row is None:
            continue
        receipt = receipts.get(run_id)
        rows[row].append({
            "run_id": run_id, "role": role_of(entry.get("label")), "label": entry.get("label"),
            "scenario": entry["scenario"].strip(), "machine": MACHINE_OF_LEDGER.get(entry["machine"], entry["machine"]),
            "commit": (receipt["identity"]["source_commit"] if receipt else None) or entry.get("commit"),
            "started": entry.get("started"),
            "verdict": receipt["verdicts"]["release_verdict"] if receipt else None,
            "verified_pass": receipt["verdicts"]["verified_pass"] if receipt else None,
            "worker_error": entry.get("worker_error"),
            "kind": kind({"role": role_of(entry.get("label")), "scenario": entry["scenario"].strip()}),
        })
    for runs in rows.values():
        runs.sort(key=lambda run: (run["started"] or "", run["run_id"]))
    return rows


def seconds_cells(groups):
    """基线秒数, 候选秒数（两次）, 整轮节省: the whole-run seconds of the stage groups of one row."""
    if not groups:
        return None, None, None
    base, cand, saving = [], [], []
    for group in groups:
        runs, measure = group["runs"], WHOLE_RUN[group["machine"]][0]
        where = "%s %s" % (SCENARIO_SHORT[group["scenario"]], MACHINE_SHORT[group["machine"]])
        alone = "（单列）" if group["scenario"] == "compare_276_strength" else ""
        reference = [run for run in runs if run["role"] == group["whole_run_reference"]]
        if group["whole_run_reference"] == "baseline":
            base.append("%s %s%s" % (where, " / ".join(f3(run["seconds"][measure]) for run in reference), alone))
        else:
            base.append("%s 无 636a733 基线，计时版 %s" % (where, " / ".join(f3(run["seconds"][measure]) for run in reference)))
        parts = []
        for role, name in (("wait276", "候选"), ("wait264", "K1"), ("burst264", "K2")):
            picked = [run for run in runs if run["role"] == role]
            if picked:
                parts.append("%s %s" % (name, " / ".join(f3(run["seconds"][measure]) for run in picked)))
        cand.append("%s %s%s" % (where, "、".join(parts), alone))
        parts = ["%s %s" % (link["text"], f3(link["whole_run"][measure]["saving"])) for link in group["links"]]
        saving.append("%s %s%s" % (where, "、".join(parts), alone))
    action = []
    for group in groups:
        where = "%s %s" % (SCENARIO_SHORT[group["scenario"]], MACHINE_SHORT[group["machine"]])
        action.append("%s %s" % (where, "、".join("%s %s" % (link["text"], f3(link["whole_run"]["action"]["saving"]))
                                                   for link in group["links"])))
    joiner = "；"
    return (joiner.join(base), joiner.join(cand),
            joiner.join(saving) + "。动作秒：" + joiner.join(action) + "。客机为宿主整轮秒（含收割），fa706g3 为机内进程秒")


def unmet_276(facts):
    run = facts["runs"]["eebdf238d72e401b9636b161bad6c465"]["per_row"]
    strength = facts["runs"]["5359abcadafa48a2bc493ee3acf56114"]["per_row"]
    pair = facts["pairs"]["5359abca vs e9aa6f88"]
    one, two, three = run["expectation_1"], run["expectation_2"], run["expectation_3"]
    walls = "eebdf238、5359abca"          # the two runs whose per_row facts hold expectation_3
    arithmetic = two["arithmetic"]
    return "；".join([
        "预期 1：五个目标值都写入保存件并与导出件配置块一致（%d 个），其中层高、外墙线宽、X 上限本来就是步骤值，看不到编辑" % len(one["targets_matching_feishu"]),
        "预期 2 未达到：外墙峰值 %.3f mm/s，不是约 178（按矩形截面 15÷(0.20×0.42)=%.3f；切片按截面积 %.6f mm² 得 %.3f）" % (
            two["peak_outer_wall_speed_mm_s"], arithmetic["feishu_rectangular_section_speed_at_cap_mm_s (15/(0.20x0.42))"],
            arithmetic["slicer_section_area_mm2"], arithmetic["cap/(h*(w-h*(1-pi/4))*flow_ratio) mm_s"]),
        "预期 3 未激发：X 分量峰值 %.3f mm/s，没有一段接近 500 mm/s，「超限部分降速」无从观察" % three["max_x_component_speed_mm_s"],
        "预期 3 的「路径不变」：外墙路径与固定基线 e9aa6f88 相同（facts.json 对 %s 都是如此：%s）；整份导出件有 1 次不同：Strength 基线 5359abca 的挤出移动 %d 段，对基线 %d 段，%d 个「类型 × 层」格不同，差在内部实心填充（见 stage-timings.md「切片复现」），原因未查"
        % (walls, "是" if run["expectation_3"]["outer_wall_paths_and_flow_same_as_fixed_baseline"]
           and strength["expectation_3"]["outer_wall_paths_and_flow_same_as_fixed_baseline"] else "否",
           pair["extruding_moves"][1], pair["extruding_moves"][0], pair["type_layer_cells_whose_length_or_filament_differ"]),
        "预览未核对（visual: not checked）",
    ]) + "。来源：facts.json（runs.eebdf238….per_row、pairs.5359abca vs e9aa6f88）"


def unmet_264(facts, controls, stage):
    run = facts["runs"]["b697f7c24c6c49849c05b22c2a8ed1a3"]
    family = next((f for f in stage["reproducibility"] if f["model"] == "264 FDM 测试模型"), None)
    one, two, three = run["per_row"]["expectation_1"], run["per_row"]["expectation_2"], run["per_row"]["expectation_3"]
    bridge, cooling = three["bridge"], three["layer_cooling_slowdown"]
    # how much of the bridge left F3000: the F3000 length of the default slice minus the run's
    off = bridge["top_F_by_length_mm"]["baseline"][0][1] - bridge["top_F_by_length_mm"]["case"][0][1]
    holes = sorted({item["control"] for item in controls["accepted_where_rejection_was_expected"]
                    if item["group"] == "264 fdmt" and item["control"].startswith("6")})
    return "；".join([
        "预期 1 缺一项：overhang_totally_speed=5 没有写入，2.4.0 没有这个参数（其余 %d 个目标值写入并与导出件一致）" % len(one["targets_matching_feishu"]),
        "预期 2 未达到：Overhang wall 段（%d 段、%d 条移动）只有 F%s，没有 F2400/1800/1200/600/300" % (
            run["row264"]["overhang_wall"]["sections"], run["row264"]["overhang_wall"]["extruding_moves"],
            "/".join("%.0f" % value for value in run["row264"]["overhang_wall"]["F_values_mm_min"])),
        "预期 3 的桥接区不成立：桥接段共 %.1f mm，其中 F3000 从默认切片的 %.1f mm 降到 %.1f mm，少 %.1f mm" % (
            bridge["extruded_length_mm"][1], bridge["top_F_by_length_mm"]["baseline"][0][1],
            bridge["top_F_by_length_mm"]["case"][0][1], off),
        "非悬垂区的 F 也变了：%d 个比较层里 %d 层的非墙进给变快（slow_down_for_layer_cooling）" % (
            cooling["layers_compared"], cooling["layers_non_wall_feed_higher_in_case"]),
        "立方体夹具上没有 Overhang wall 段，预期 2 在立方体上看不到",
        "判据不读本行导出件的 G-code：反例 %s 被接受（negative-controls.json）" % "、".join(holes),
        "FDM 测试模型当晚 %d 次运行里有 %d 次切片聚合签名相同，另 %d 次（%s）内部实心填充少 %d 段，原因未查；拿一次导出件当基线逐行比时要先算进去（stage-timings.md「切片复现」）" % (
            family["runs_total"], family["runs_same_as_reference"], len(family["runs"]) - family["runs_same_as_reference"],
            "、".join(short(row["run_id"]) for row in family["runs"] if "signature" in row and not row["signature"]["same"]),
            family["runs"][0]["internal_solid_infill_moves"] - min(
                row["internal_solid_infill_moves"] for row in family["runs"] if "signature" in row))
        if family else "",
        "预览未核对",
    ]) + "。来源：facts.json（runs.b697f7c2…）、negative-controls.json"


def rating(runs):
    counts = collections.Counter((run["machine"], run["verdict"]) for run in runs if run["verdict"])
    text = "；".join("%s %s %d 次" % (MACHINE_TEXT[machine], verdict, count)
                    for (machine, verdict), count in sorted(counts.items(), key=lambda item: (item[0][0] != "guest", item[0][1])))
    failed = [run for run in runs if not run["verdict"]]
    if failed:
        text = (text + "；" if text else "") + "未收割 %d 次（%s）" % (len(failed), "、".join(short(run["run_id"]) for run in failed))
    return text + "；都不是发布 GREEN" if counts else text


def build(ledger, receipts, family, original, stage, facts, controls, native):
    signatures = {run["run_id"]: run["failure_signature"] for run in native["runs"]}
    runs_by_row = collect(ledger, receipts, family)
    for runs in runs_by_row.values():
        for run in runs:
            run["failure"] = signatures.get(run["run_id"])
    groups_by_row = collections.defaultdict(list)
    for group in stage["groups"]:
        groups_by_row[MODEL_OF[group["scenario"]]].append(group)
    rows, touched, detail = [], [], {}
    for row in original:
        runs = runs_by_row.get(row[0], [])
        if not runs:
            rows.append(list(row) + [None] * len(NEW_COLUMNS))
            continue
        kinds = [key for key in ("speed", "night_baseline", "backlog", "regress", "final", "native") if any(run["kind"] == key for run in runs)]
        base, cand, saving = seconds_cells(groups_by_row.get(row[0], []))
        notes = []
        if row[0] == 276:
            notes.append(unmet_276(facts))
        if row[0] == 264:
            notes.append(unmet_264(facts, controls, stage))
        regress = [run for run in runs if run["kind"] == "regress" and run["verdict"]]
        backlog = [run for run in runs if run["kind"] == "backlog"]
        if backlog:
            notes.append("补覆盖 %d 次（%s）%s：只过了脚本自检并导出，未对照飞书预期核对；原有缺口见「未覆盖项与适用边界」" % (
                len(backlog), machines(backlog), "/".join(sorted({run["verdict"] for run in backlog}))))
        if regress:
            notes.append("最终引擎回归 %d 次（%s）%s：只验引擎，未核对飞书预期" % (
                len(regress), machines(regress),
                "/".join(sorted({run["verdict"] for run in regress}))))
        finals = [run for run in runs if run["kind"] == "final"]
        if finals:
            notes.append("最终引擎复核 %d 次（%s）%s：只验引擎，未核对飞书预期" % (
                len(finals), machines(finals), "/".join(sorted({run["verdict"] for run in finals}))))
        night = [run for run in runs if run["kind"] == "night_baseline"]
        if night:
            notes.append("同夜基线 %d 次（%s）%s：作为对照的基线，本身不新增飞书预期的核对" % (
                len(night), machines(night), "/".join(sorted({run["verdict"] for run in night}))))
        native = [run for run in runs if run["kind"] == "native"]
        if native:
            notes.append("原生模型对照 %d 次未取得经独立验证的 GUI 结果（%s），配对 0 次" % (
                len(native), "；".join("%s %s" % (short(run["run_id"]), run["failure"]) for run in native)))
        if not notes:
            notes.append("今晚只跑了基线或复核，未对照飞书预期核对；原有缺口见「未覆盖项与适用边界」")
        links = ["%s/%s.json" % (RECEIPTS, run["run_id"]) for run in runs if run["verdict"]]
        links += ["%s/%s" % (THIS_FOLDER, name) for name in ("stage-timings.md", "facts.json", "negative-controls.json") if row[0] in (264, 276)]
        rows.append(list(row) + ["；".join(OP_TEXT[key] for key in kinds), base, cand, saving, "；".join(notes),
                                 "\n".join(links) or None, rating(runs)])
        touched.append(row[0])
        detail[str(row[0])] = {
            "record_id": row[14], "title": row[4], "feishu_status": row[1],
            "operations": [OP_TEXT[key] for key in kinds],
            "runs": runs,
        }
    by_role_rows = collections.defaultdict(set)
    for row, runs in runs_by_row.items():
        for run in runs:
            by_role_rows[run["role"]].add(row)
    speed = sorted(by_role_rows["wait276"] | by_role_rows["wait264"] | by_role_rows["burst264"])
    backlog = sorted(by_role_rows["backlog"] - set(speed))
    native = sorted(by_role_rows["native"])
    regress = sorted(row for row, runs in runs_by_row.items() if any(run["role"] == "regress" and run["verdict"] for run in runs))
    regress_failed = sorted(row for row, runs in runs_by_row.items()
                            if any(run["kind"] == "regress" and run["verdict"] and run["verdict"] != "SHADOW" for run in runs))
    verdicts = collections.Counter(receipt["verdicts"]["release_verdict"] for receipt in receipts.values())
    summary = {
        "rule": "一行可以同时出现在几类里（#265、#276 既有别的操作，又有失败的原生模型对照）；回归行只确认引擎改动没有破坏已有覆盖，不计入前三类。",
        "new_full_coverage": {"count": 0, "rows": [],
                              "note": "本轮没有发布 GREEN：收据里的评级只有 %s。" % "、".join("%s %d" % item for item in sorted(verdicts.items()))},
        "partial_evidence_filled": {"count": len(backlog), "rows": backlog,
                                    "kind": "补覆盖：空闲机器上的额外运行，单独记账，不计闭环，也不改 11-24 的覆盖列"},
        "speed_only": {"count": len(speed), "rows": speed, "kind": "纯提速：同机、同构建线、同初态上基线各跑一遍以上、候选各跑两遍"},
        "failed_or_pending": {"count": len(native), "rows": native, "kind": "原生模型对照失败（NON_GREEN）；Mac 的壁环数运行没有对应的飞书行，不计入行数",
                              "mac_note": "Mac 壁环数 2→3：1 次运行 NON_GREEN，随后的 8 次探针确认控制台会话锁屏后图形通道不可用；未对应飞书原行，不计入行数（来源：findings-sheet.md、mac/）",
                              "regression_failure_rows": regress_failed,
                              "regression_failure_runs": [
                                  {"feishu_row": row, "run_id": run["run_id"], "machine": run["machine"], "label": run["label"],
                                   "worker_error": run["worker_error"]}
                                  for row, runs in sorted(runs_by_row.items()) for run in runs
                                  if run["kind"] == "regress" and run["verdict"] and run["verdict"] != "SHADOW"]},
        "regression_rows": {"count": len(regress), "rows": regress, "kind": "最终引擎回归已出结果的行"},
        "verdicts_of_all_receipts": dict(sorted(verdicts.items())),
    }
    counts = {
        "rows": len(original),
        "by_feishu_status": ordered(collections.Counter(row[1] for row in original), STATUS_ORDER),
        "by_coverage": ordered(collections.Counter(row[2] for row in original), COVERAGE_ORDER),
        "by_level": ordered(collections.Counter(row[3] for row in original), LEVEL_ORDER),
        "touched_tonight": len(touched), "untouched": len(original) - len(touched),
    }
    return {
        "schema": "ninehour_feishu_216/1", "generated_by": "scripts/build_feishu.py",
        "source_table": {
            "sha256": hashlib.sha256(Path(COMBINED_PATH).read_bytes()).hexdigest(),
            "built": "2026-11-24 23:34 on f03e614 (merge_audit.py and workbook.mjs of the audit folder)",
            "note": "artifacts/ is git-ignored: the 11-24 file is not in the repository; columns 1-15 of all %d rows are copied unchanged and the order is kept" % len(original),
        },
        "ledger": ledger_facts(ledger),
        "columns": EXISTING_COLUMNS + NEW_COLUMNS,
        "counts": counts, "summary": summary, "touched_rows": touched, "touched_detail": detail, "rows": rows,
    }


COMBINED_PATH = None


def markdown(data):
    counts = data["counts"]
    lines = [
        "# 飞书 216 条对照表：九小时一轮（2026-11-25）触及的行", "",
        "全表 %d 行，与 11-24 23:34 的 combined.json 相同（行序和前 15 列原样保留，本轮没有改它们）：飞书状态 %s；核验覆盖 %s。" % (
            counts["rows"], "、".join("%s %d" % item for item in counts["by_feishu_status"].items()),
            "、".join("%s %d" % item for item in counts["by_coverage"].items())),
        "本轮触及 %d 行（下表），其余 %d 行的七个新列都是 null；全表见 `feishu-216-ninehour.json`。Mac 的壁环数运行没有对应的飞书行，不在这张表里。" % (
            counts["touched_tonight"], counts["untouched"]),
        "",
        "**四类汇总**（%s）" % data["summary"]["rule"],
        "",
        "- 本轮新增完整覆盖：%d 条。%s" % (data["summary"]["new_full_coverage"]["count"], data["summary"]["new_full_coverage"]["note"]),
        "- 补齐部分证据：%d 条，%s。%s。" % (data["summary"]["partial_evidence_filled"]["count"],
                                        "、".join("#%d" % n for n in data["summary"]["partial_evidence_filled"]["rows"]),
                                        data["summary"]["partial_evidence_filled"]["kind"]),
        "- 纯提速：%d 条，%s。%s。" % (data["summary"]["speed_only"]["count"], "、".join("#%d" % n for n in data["summary"]["speed_only"]["rows"]),
                                  data["summary"]["speed_only"]["kind"]),
        "- 失败或待确认：%d 条，%s。%s。" % (data["summary"]["failed_or_pending"]["count"],
                                          "、".join("#%d" % n for n in data["summary"]["failed_or_pending"]["rows"]),
                                          data["summary"]["failed_or_pending"]["kind"]),
        "- 最终引擎回归里出现过失败运行的行：%s（同行的其它运行见 `family-regression.md`）。" % (
            "、".join("#%d" % n for n in data["summary"]["failed_or_pending"]["regression_failure_rows"]) or "无"),
        "- 另：最终引擎回归已出结果 %d 行（%s），不计入前三类。" % (
            data["summary"]["regression_rows"]["count"], "、".join("#%d" % n for n in data["summary"]["regression_rows"]["rows"]) or "无"),
        "",
        "**列的口径**",
        "",
        "- 操作类型：提速对照（#276、#264 的基线与候选）、补覆盖（空闲机器上的额外运行，单独记账，不计闭环）、最终引擎回归（d5fc2fa 上每行一次）、最终引擎复核、同夜基线、原生模型对照（失败）。",
        "- 基线秒数 / 候选秒数（两次） / 整轮节省：只有 #276、#264 有。客机是宿主整轮秒（含收割），fa706g3 是机内进程秒（它不写宿主摘要）；",
        "  #276 的链是 基线 → 就绪等待，Strength 初态单列；#264 的链是 基线 → K1 就绪等待 → K2 滚轮一次到位，K2 与 K1 比；逐阶段见 `stage-timings.md`。",
        "- 未通过项：只写文件里能查到的；「本轮没有核对」不等于通过。",
        "- 证据链接：`docs/runs/evidence/ninehour-2026-11-25/` 下的收据（每个 run 一份）。",
        "- 最终评级：客机是回归证据机；fa706g3 和 Mac 最高记 SHADOW（README 第 6 条）。本轮没有发布 GREEN，也就没有符合飞书回写条件（完整 GREEN / 已覆盖）的行。",
        "- 「补覆盖」是空闲机器上的额外运行：脚本自检通过并导出，单独记账，不计闭环。「最终引擎回归」回答的是引擎改动有没有破坏该行已有的写入和导出，不逐项核对飞书预期。",
        "",
        "| 飞书编号 | record ID | 用例标题 | 飞书状态 | 操作类型 | 基线秒数 | 候选秒数（两次） | 整轮节省 | 未通过项 | 证据链接 | 最终评级 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    index = {name: i for i, name in enumerate(data["columns"])}
    for row in data["rows"]:
        if row[index["操作类型"]] is None and row[0] not in data["touched_rows"]:
            continue
        cell = lambda name: row[index[name]]
        ids = [line.rsplit("/", 1)[1][:-5] for line in (cell("证据链接") or "").splitlines() if "/receipts/" in line]
        links = "收据 %d 份（`receipts/<run ID>.json`）：%s" % (len(ids), "、".join(short(i) for i in ids)) if ids else "-"
        values = [str(row[0]), "`%s`" % cell("飞书 record_id"), cell("飞书用例标题"), cell("飞书状态"), cell("操作类型") or "-",
                  cell("基线秒数") or "-", cell("候选秒数（两次）") or "-", cell("整轮节省") or "-", cell("未通过项") or "-", links,
                  cell("最终评级") or "-"]
        lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", "<br>") for v in values) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    global COMBINED_PATH
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", default=str(EVIDENCE))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--combined", required=True)
    parser.add_argument("--snapshot", default=SNAPSHOT)
    args = parser.parse_args(argv)
    evidence, COMBINED_PATH = Path(args.evidence), args.combined
    original = read_json(args.combined)
    assert all(len(row) == len(EXISTING_COLUMNS) for row in original), "the 11-24 table must have 15 columns per row"
    family = {scenario: number for number, case, scenario in family_rows(args.repo)}
    data = build(load_ledger(evidence / "ledger.jsonl"), load_receipts(evidence), family, original,
                 read_json(evidence / "stage-timings.json"), read_json(evidence / "facts.json"),
                 read_json(evidence / "negative-controls.json"), read_json(evidence / "native-pairing.json"))
    # columns 1-15 of every row are the 11-24 row, untouched
    for before, after in zip(original, data["rows"]):
        assert after[:len(EXISTING_COLUMNS)] == before and len(after) == len(EXISTING_COLUMNS) + len(NEW_COLUMNS)
    for number in data["touched_rows"]:
        assert any(row[index] is not None for row in data["rows"] if row[0] == number for index in range(15, 22)), number
    write(evidence, "feishu-216-ninehour.json", dump(data))
    write(evidence, "feishu-216-ninehour.md", markdown(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
