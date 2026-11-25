"""The 216-row Feishu comparison table with the columns of the nine-hour run (2026-11-25).

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_feishu.py --repo <checkout with the registry> --combined <combined.json of 11-24>
                                               [--snapshot <216-row ndjson>] [--evidence <folder>]

Reads the 11-24 table (--combined, outside the repository: artifacts/ is git-ignored), the committed
Feishu snapshot, and ledger.jsonl, receipts/, stage-timings.json, facts.json,
negative-controls.json and native-pairing.json of the evidence folder; runs
tools/param_closure_list.py of --repo (read-only) to map scenario names to Feishu rows. Writes
feishu-216-ninehour.json and .md next to scripts/. Run build_stage.py first: the seconds come from
stage-timings.json.

What the table keeps: the 216 rows in their order, and columns 1-15 of every row exactly as the
11-24 table has them (checked below). The seven new columns are null for a row no run of tonight
belongs to. A run is the LAST ledger line written for its run id.

What a run counts as (操作类型):
  speed            baseline, timed build or candidate of #276 / #264
  night_baseline   a compare_* baseline of another row
  backlog          an extra run on an idle machine early in the night (label backlog-*)
  twins, twins_b   the guest's own-model twins of rows whose 11-24 evidence was fa706g3's
                   (labels guest-twins, guest-twins-b)
  shapes           fa706g3's twins on the shapes plate (label fa-shapes)
  regress          the regression run of the row on the machine it was assigned to, on the final
                   engine (label regress-final, ledger commit 2a17376 or 62cddee: the same engine)
  regress_other    the same regression scenario on the other machine: the guest's cross-run of a
                   fa706g3 row (regress-final on 62cddee), fa706g3's second sample of a guest row
                   (label second-sample). Re-evidencing: it does not change the row's result.
  final2           the confirmation runs on the final engine (label final2-*)
  retry            the repeats after a failed run (label retry-*)
  regress_d5fc2fa  a regression run on d5fc2fa, before the fix: not the final engine, superseded
  final_d5fc2fa    a confirmation run on d5fc2fa (label final-*): not the final engine
  native           the native model actor
backlog, twins, twins_b and shapes are coverage: their own account, never closure.
A run without a receipt never reached the GUI. It is a failed dispatch with no verdict: it is not
put under any run class, only counted and listed with its row.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import sys
from pathlib import Path

from build_common import (EVIDENCE, MACHINE_OF_LEDGER, MACHINE_TEXT, RECEIPTS, SNAPSHOT, assigned_side, dump,
                          family_rows, feishu_row_of, f3, ledger_facts, load_ledger, load_receipts, load_snapshot,
                          read_json, role_of, short, write)

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
KIND_ORDER = ("speed", "night_baseline", "backlog", "twins", "twins_b", "shapes", "regress", "regress_other",
              "final2", "retry", "regress_d5fc2fa", "final_d5fc2fa", "native")
COVERAGE_KINDS = ("backlog", "twins", "twins_b", "shapes")
OP_TEXT = {
    "speed": "提速对照", "backlog": "补覆盖（空闲机器）", "twins": "补覆盖（客机自有模型孪生）",
    "twins_b": "补覆盖（客机自有模型孪生，第二批）", "shapes": "补覆盖（fa706g3 多形状夹具孪生）",
    "regress": "最终引擎回归", "regress_other": "另一台机器上的回归运行（复核）", "final2": "最终引擎复核",
    "retry": "失败后的重试", "regress_d5fc2fa": "d5fc2fa 上的回归（不是最终引擎）",
    "final_d5fc2fa": "d5fc2fa 上的复核（不是最终引擎）", "native": "原生模型对照（失败）", "night_baseline": "同夜基线",
}
# What each coverage batch is, for the 未通过项 column. The 11-24 verdicts of the twin rows are read
# from the committed table named in TWINS_B_SOURCE; the wording here only says what a SHADOW means.
COVERAGE_NOTE = {
    "backlog": "只过了脚本自检并导出，未对照飞书预期核对；原有缺口见「未覆盖项与适用边界」",
    "twins": "这 %d 行 11-24 的自有模型运行都在 fa706g3 上；客机 SHADOW 说明在回归证据机上写入、保存、重开、切片和导出走通了，"
             "补上了「只有 fa706g3 证据」这一条，11-24 对照表里逐项预期的缺口仍在",
    "twins_b": "这 %d 行 11-24 在 fa706g3 上的判定是有出入或看不到（`docs/runs/evidence/feishu-expect-vs-gcode-2026-11-24/own-models-verdicts.md`）；"
               "客机 SHADOW 只说明在那里写入、保存、重开、切片和导出走通了，不说明预期已经满足",
    "shapes": "多形状夹具上的同一个场景，只过了脚本自检并导出，未对照飞书预期核对",
}
THIS_FOLDER = "docs/runs/evidence/ninehour-2026-11-25"


def machines(runs):
    """'客机 win11-test ×2、fa706g3 ×1': each machine once, with how many of the runs."""
    count = collections.Counter(run["machine"] for run in runs)
    return "、".join("%s ×%d" % (MACHINE_TEXT[machine], number) for machine, number in sorted(count.items()))


def ordered(count, first):
    return {key: count[key] for key in list(first) + sorted(set(count) - set(first)) if key in count}


def kind(run, side_of):
    """What a run counts as, for the 操作类型 column (see the module docstring)."""
    role = run["role"]
    if role == "regress":
        if not run["on_final_engine"]:
            return "regress_d5fc2fa"
        return "regress" if side_of.get(run["scenario"]) == run["machine"] else "regress_other"
    if role == "second_sample":
        return "regress_other" if run["on_final_engine"] else "regress_d5fc2fa"
    if role in ("backlog", "twins", "twins_b", "shapes", "final2", "retry", "native"):
        return role
    if role == "final":
        return "final_d5fc2fa"
    if run["scenario"] in SPEED_SCENARIOS:
        return "speed"
    return "night_baseline"


def failed_checks(receipt):
    """{check: 'status: detail'} of a run whose checks are not all pass, read from its result.json."""
    try:
        checks = read_json(Path(receipt["run_dir"]) / "result.json").get("checks") or {}
    except (OSError, ValueError):
        return None
    return {name: "%s: %s" % (check.get("status"), str(check.get("detail"))[:160])
            for name, check in checks.items() if check.get("status") != "pass"}


def collect(ledger, receipts, family, side_of):
    """{feishu row: [run]} of every ledger run with a verdict that belongs to a Feishu row, and
    {feishu row: [dispatch]} of the ledger runs without one."""
    rows, dispatches = collections.defaultdict(list), collections.defaultdict(list)
    for run_id, entry in ledger.items():
        row = feishu_row_of(entry["scenario"].strip(), family)
        if row is None:
            continue
        scenario = entry["scenario"].strip()
        receipt = receipts.get(run_id)
        base = {
            "run_id": run_id, "role": role_of(entry.get("label")), "label": entry.get("label"), "scenario": scenario,
            "machine": MACHINE_OF_LEDGER.get(entry["machine"], entry["machine"]),
            "commit": (receipt["identity"]["source_commit"] if receipt else None) or entry.get("commit"),
            "on_final_engine": bool((entry.get("commit") or "").startswith(("2a17376", "62cddee"))),
            "started": entry.get("started"),
        }
        if receipt is None:        # never reached the GUI: no verdict, no run class
            dispatches[row].append(dict(base, ledger_dispatch_failed=entry.get("dispatch_failed"),
                                        ledger_scenario_raw=entry["scenario"]))
            continue
        run = dict(base, verdict=receipt["verdicts"]["release_verdict"], verified_pass=receipt["verdicts"]["verified_pass"],
                   worker_error=entry.get("worker_error") or None)
        run["kind"] = kind(run, side_of)
        run["failed_checks"] = failed_checks(receipt) if run["verdict"] != "SHADOW" else None
        rows[row].append(run)
    for runs in rows.values():
        runs.sort(key=lambda run: (run["started"] or "", run["run_id"]))
    for items in dispatches.values():
        items.sort(key=lambda item: (item["started"] or "", item["run_id"]))
    return rows, dispatches


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


def verdicts_of(runs):
    return "/".join(sorted({str(run["verdict"]) for run in runs if run["verdict"]}))


def with_failed_checks(runs):
    """; ...: the non-SHADOW runs with the check that failed, when there are any."""
    bad = [run for run in runs if run["verdict"] and run["verdict"] != "SHADOW"]
    if not bad:
        return ""
    parts = []
    for run in bad:
        checks = run["failed_checks"] or {}
        text = "、".join("%s %s" % (name, value) for name, value in checks.items() if name != "visual" and value != "unknown: not checked")
        parts.append("`%s`（%s）%s" % (short(run["run_id"]), MACHINE_TEXT[run["machine"]],
                                      "：" + "；".join(part for part in (run["worker_error"], text) if part) if run["worker_error"] or text else ""))
    return "；没通过的是 " + "；".join(parts)


def coverage_note(key, picked, rows_count):
    """What the coverage runs of one batch on one row show. COVERAGE_NOTE describes a SHADOW run (the script
    check and the export passed); a run that did not pass is said so, its reason follows in the same cell."""
    note = COVERAGE_NOTE[key] % rows_count if key in ("twins", "twins_b") else COVERAGE_NOTE[key]
    passed = [run for run in picked if run["verdict"] == "SHADOW"]
    if len(passed) == len(picked):
        return note
    where = {"backlog": "空闲机器上", "twins": "客机自有模型上", "twins_b": "客机自有模型上", "shapes": "多形状夹具上"}[key]
    failed = "%s的同一个场景没有通过（原因见后），同样未对照飞书预期核对" % where
    return ("SHADOW %d 次：%s；" % (len(passed), note) if passed else "") + failed


def rating(runs, dispatches):
    counts = collections.Counter((run["machine"], run["verdict"]) for run in runs if run["verdict"])
    text = "；".join("%s %s %d 次" % (MACHINE_TEXT[machine], verdict, count)
                    for (machine, verdict), count in sorted(counts.items(), key=lambda item: (item[0][0] != "guest", item[0][1])))
    if dispatches:
        text = (text + "；" if text else "") + "派发失败（无评级）%d 次（%s）" % (
            len(dispatches), "、".join(short(item["run_id"]) for item in dispatches))
    return text + "；都不是发布 GREEN" if counts else text


def build(ledger, receipts, family, original, stage, facts, controls, native, side_of):
    signatures = {run["run_id"]: run["failure_signature"] for run in native["runs"]}
    runs_by_row, dispatch_by_row = collect(ledger, receipts, family, side_of)
    for runs in runs_by_row.values():
        for run in runs:
            run["failure"] = signatures.get(run["run_id"])
    groups_by_row = collections.defaultdict(list)
    for group in stage["groups"]:
        groups_by_row[MODEL_OF[group["scenario"]]].append(group)
    # which rows each coverage batch touches, known before the notes are written
    coverage_rows = {key: sorted({row for row, runs in runs_by_row.items() if any(run["kind"] == key for run in runs)})
                     for key in COVERAGE_KINDS}
    rows, touched, detail = [], [], {}
    for row in original:
        runs, dispatches = runs_by_row.get(row[0], []), dispatch_by_row.get(row[0], [])
        if not runs and not dispatches:
            rows.append(list(row) + [None] * len(NEW_COLUMNS))
            continue
        of = lambda kind: [run for run in runs if run["kind"] == kind]      # noqa: E731
        kinds = [key for key in KIND_ORDER if of(key)]
        base, cand, saving = seconds_cells(groups_by_row.get(row[0], []))
        notes = []
        if row[0] == 276:
            notes.append(unmet_276(facts))
        if row[0] == 264:
            notes.append(unmet_264(facts, controls, stage))
        for key, name in (("backlog", "补覆盖（空闲机器）"), ("twins", "补覆盖（客机自有模型孪生）"),
                          ("twins_b", "补覆盖（客机自有模型孪生，第二批）"), ("shapes", "补覆盖（fa706g3 多形状夹具孪生）")):
            if of(key):
                notes.append("%s %d 次（%s）%s：%s%s" % (
                    name, len(of(key)), machines(of(key)), verdicts_of(of(key)),
                    coverage_note(key, of(key), len(coverage_rows[key])),
                    with_failed_checks(of(key))))
        if of("regress"):
            notes.append("最终引擎回归 %d 次（%s）%s：只验引擎，未核对飞书预期%s" % (
                len(of("regress")), machines(of("regress")), verdicts_of(of("regress")), with_failed_checks(of("regress"))))
        if of("regress_other"):
            notes.append("另一台机器上的回归运行 %d 次（%s）%s：同一个场景换一台机器再取证，不改变上面的结论%s" % (
                len(of("regress_other")), machines(of("regress_other")), verdicts_of(of("regress_other")),
                with_failed_checks(of("regress_other"))))
        if of("final2"):
            notes.append("最终引擎复核 %d 次（%s）%s" % (len(of("final2")), machines(of("final2")), verdicts_of(of("final2"))))
        if of("retry"):
            for final, name in ((True, "最终引擎上失败后的重试"), (False, "d5fc2fa 上失败后的重试")):
                picked = [run for run in of("retry") if run["on_final_engine"] == final]
                if picked:
                    notes.append("%s %d 次（%s，%s）%s" % (
                        name, len(picked), machines(picked), "、".join(sorted({run["scenario"] for run in picked})),
                        verdicts_of(picked)))
        if of("regress_d5fc2fa"):
            notes.append("d5fc2fa 上的回归 %d 次（%s）%s，不是最终引擎，已被取代%s" % (
                len(of("regress_d5fc2fa")), machines(of("regress_d5fc2fa")), verdicts_of(of("regress_d5fc2fa")),
                with_failed_checks(of("regress_d5fc2fa"))))
        if of("final_d5fc2fa"):
            notes.append("d5fc2fa 上的复核 %d 次（%s）%s，不是最终引擎" % (
                len(of("final_d5fc2fa")), machines(of("final_d5fc2fa")), verdicts_of(of("final_d5fc2fa"))))
        if of("night_baseline"):
            notes.append("同夜基线 %d 次（%s）%s：作为对照的基线，本身不新增飞书预期的核对" % (
                len(of("night_baseline")), machines(of("night_baseline")), verdicts_of(of("night_baseline"))))
        if of("native"):
            notes.append("原生模型对照 %d 次未取得经独立验证的 GUI 结果（%s），配对 0 次" % (
                len(of("native")), "；".join("%s %s" % (short(run["run_id"]), run["failure"]) for run in of("native"))))
        if not notes:
            notes.append("今晚只跑了基线，未对照飞书预期核对；原有缺口见「未覆盖项与适用边界」")
        if dispatches:
            notes.append("派发失败 %d 次（没有到 GUI，没有评级，不属于任何一类运行；见 dispatch-failures.md）" % len(dispatches))
        links = ["%s/%s.json" % (RECEIPTS, run["run_id"]) for run in runs]
        links += ["%s/%s" % (THIS_FOLDER, name) for name in ("stage-timings.md", "facts.json", "negative-controls.json") if row[0] in (264, 276)]
        rows.append(list(row) + ["；".join(OP_TEXT[key] for key in kinds), base, cand, saving, "；".join(notes),
                                 "\n".join(links) or None, rating(runs, dispatches)])
        touched.append(row[0])
        detail[str(row[0])] = {
            "record_id": row[14], "title": row[4], "feishu_status": row[1],
            "operations": [OP_TEXT[key] for key in kinds],
            "runs": runs, "dispatches": dispatches,
        }
    rows_with = lambda kind: {row for row, runs in runs_by_row.items() if any(run["kind"] == kind for run in runs)}   # noqa: E731
    speed = sorted(rows_with("speed"))
    coverage = {}
    for key in COVERAGE_KINDS:
        runs_of_batch = [run for runs in runs_by_row.values() for run in runs if run["kind"] == key]
        coverage[key] = {"rows": list(coverage_rows[key]), "runs": len(runs_of_batch),
                         "verdicts": dict(collections.Counter(str(run["verdict"]) for run in runs_of_batch))}
    covered = sorted({row for value in coverage.values() for row in value["rows"]})
    native_rows = sorted(rows_with("native"))
    regress = {row: [run for run in runs if run["kind"] == "regress"] for row, runs in runs_by_row.items()}
    regress = {row: runs for row, runs in regress.items() if runs}
    regress_other = {row: [run for run in runs if run["kind"] == "regress_other"] for row, runs in runs_by_row.items()}
    regress_other = {row: runs for row, runs in regress_other.items() if runs}
    regress_failed = {row: [run for run in runs if run["verdict"] != "SHADOW"] for row, runs in regress.items()}
    regress_failed = {row: runs for row, runs in regress_failed.items() if runs}
    regress_shadow = sorted(row for row, runs in regress.items() if any(run["verdict"] == "SHADOW" for run in runs))
    coverage_failed = {row: [run for run in runs if run["kind"] in COVERAGE_KINDS and run["verdict"] != "SHADOW"]
                       for row, runs in runs_by_row.items()}
    coverage_failed = {row: runs for row, runs in coverage_failed.items() if runs}
    superseded_failed = sorted({row for row, runs in runs_by_row.items()
                                if any(run["kind"] == "regress_d5fc2fa" and run["verdict"] != "SHADOW" for run in runs)})
    dispatches = [dict(item, feishu_row=row) for row, items in sorted(dispatch_by_row.items()) for item in items]
    verdicts = collections.Counter(receipt["verdicts"]["release_verdict"] for receipt in receipts.values())
    failed_rows = sorted(set(native_rows) | set(regress_failed) | set(coverage_failed))
    describe = lambda runs: [  # noqa: E731
        {"feishu_row": run.get("feishu_row"), "run_id": run["run_id"], "machine": run["machine"], "label": run["label"],
         "verdict": run["verdict"], "worker_error": run["worker_error"], "failed_checks": run["failed_checks"],
         "completed_edit_and_save": run["failed_checks"] is not None and run["worker_error"] is None}
        for run in runs]
    summary = {
        "rule": "按飞书记录 ID 去重，一行可以同时落在几类里（#264、#276 既有提速对照，也有补覆盖）。补覆盖（空闲机器、客机自有模型孪生、"
                "fa706g3 多形状夹具孪生）单独记账，不计闭环。回归行只确认引擎改动没有破坏该行已有的写入和导出，不进前三类；"
                "在 d5fc2fa 上失败、最终引擎上通过的行记作「已恢复的失败轮」，不进「失败或待确认」。派发失败没有评级，不属于任何一类。",
        "new_full_coverage": {"count": 0, "rows": [],
                              "note": "本轮没有发布 GREEN：收据里的评级只有 %s。" % "、".join("%s %d" % item for item in sorted(verdicts.items()))},
        "partial_evidence_filled": {
            "count": len(covered), "rows": covered, "by_batch": coverage,
            "kind": "都是补覆盖，单独记账，不计闭环，也不改 11-24 对照表的覆盖列："
                    "空闲机器上的额外运行、客机自有模型孪生（第一批 8 行、第二批 11 行）、fa706g3 多形状夹具孪生和客机早先的多形状夹具运行"},
        "speed_only": {"count": len(speed), "rows": speed, "kind": "纯提速：同机、同构建线、同初态上基线各跑一遍以上、候选各跑两遍；最终引擎上复核过"},
        "failed_or_pending": {
            "count": len(failed_rows), "rows": failed_rows,
            "native_rows": native_rows, "regression_rows": sorted(regress_failed), "coverage_rows": sorted(coverage_failed),
            "kind": "#265、#276 是原生模型对照失败（NON_GREEN）；#294 是最终引擎回归里 NON_GREEN，它是 11-24 就开着的行（机型不适用），不是回归；"
                    "#293 的多形状夹具孪生在两台机器上都没过，#254、#259 的多形状夹具孪生是 NON_GREEN，原因是判据在多对象板上答不出"
                    "（gcode_multiple_object_tools）。Mac 的壁环数运行没有对应的飞书行，不计入行数",
            "mac_note": "Mac 壁环数 2→3：1 次运行 NON_GREEN，随后的 8 次探针确认控制台会话锁屏后图形通道不可用；未对应飞书原行，不计入行数（来源：findings-sheet.md、mac/）",
            "regression_failure_runs": describe([dict(run, feishu_row=row) for row, runs in sorted(regress_failed.items()) for run in runs]),
            "coverage_failure_runs": describe([dict(run, feishu_row=row) for row, runs in sorted(coverage_failed.items()) for run in runs]),
        },
        "recovered_failed_rounds": {
            "rows": sorted(row for row in superseded_failed if row in regress_shadow),
            "kind": "d5fc2fa 上回归失败过，重试通过，最终引擎上的回归也通过",
        },
        "regression_final_engine": {
            "count": len(regress), "rows": sorted(regress), "shadow_rows": regress_shadow, "failed_rows": sorted(regress_failed),
            "runs_per_machine": dict(collections.Counter(run["machine"] for runs in regress.values() for run in runs)),
            "verdicts": dict(collections.Counter(str(run["verdict"]) for runs in regress.values() for run in runs)),
            "kind": "最终引擎上，在分到的机器上有回归运行的行",
            "other_machine": {
                "count": len(regress_other), "rows": sorted(regress_other), "failed_rows": sorted(
                    row for row, runs in regress_other.items() if any(run["verdict"] != "SHADOW" for run in runs)),
                "runs_per_machine": dict(collections.Counter(run["machine"] for runs in regress_other.values() for run in runs)),
                "verdicts": dict(collections.Counter(str(run["verdict"]) for runs in regress_other.values() for run in runs)),
                "kind": "同一个回归场景在另一台机器上的运行（客机对 fa706g3 那一半的加跑、fa706g3 对客机那一半的第二样本）：复核，不改变上面的结论",
            },
        },
        "regression_superseded_d5fc2fa": {"rows": sorted(rows_with("regress_d5fc2fa")), "kind": "d5fc2fa 上的回归运行，已被最终引擎上的结果取代"},
        "dispatch_failures": dispatches,
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
        "schema": "ninehour_feishu_216/3", "generated_by": "scripts/build_feishu.py",
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
    counts, s = data["counts"], data["summary"]
    rows_text = lambda rows: "、".join("#%d" % n for n in rows) or "无"      # noqa: E731
    counts_text = lambda count: "、".join("%s %d" % item for item in sorted(count.items())) or "无"      # noqa: E731
    batches = s["partial_evidence_filled"]["by_batch"]
    cov_fail = s["failed_or_pending"]["coverage_failure_runs"]
    lines = [
        "# 飞书 216 条对照表：九小时一轮（2026-11-25）触及的行", "",
        "全表 %d 行，与 11-24 23:34 的 combined.json 相同（行序和前 15 列原样保留，本轮没有改它们）：飞书状态 %s；核验覆盖 %s。" % (
            counts["rows"], "、".join("%s %d" % item for item in counts["by_feishu_status"].items()),
            "、".join("%s %d" % item for item in counts["by_coverage"].items())),
        "本轮触及 %d 行（下表），其余 %d 行的七个新列都是 null；全表见 `feishu-216-ninehour.json`。Mac 的壁环数运行没有对应的飞书行，不在这张表里。" % (
            counts["touched_tonight"], counts["untouched"]),
        "",
        "**四类汇总**（%s）" % s["rule"],
        "",
        "- 本轮新增完整覆盖：%d 条。%s" % (s["new_full_coverage"]["count"], s["new_full_coverage"]["note"]),
        "- 补齐部分证据：%d 条，%s。%s：空闲机器 %d 行 %d 次运行（%s）；客机自有模型孪生第一批 %d 行 %d 次运行（%s）、第二批 %d 行 %d 次运行（%s）；"
        "fa706g3 多形状夹具孪生 %d 行 %d 次运行（%s）。括号里是评级计数。" % (
            s["partial_evidence_filled"]["count"], rows_text(s["partial_evidence_filled"]["rows"]), s["partial_evidence_filled"]["kind"],
            len(batches["backlog"]["rows"]), batches["backlog"]["runs"], counts_text(batches["backlog"]["verdicts"]),
            len(batches["twins"]["rows"]), batches["twins"]["runs"], counts_text(batches["twins"]["verdicts"]),
            len(batches["twins_b"]["rows"]), batches["twins_b"]["runs"], counts_text(batches["twins_b"]["verdicts"]),
            len(batches["shapes"]["rows"]), batches["shapes"]["runs"], counts_text(batches["shapes"]["verdicts"])),
        "- 补覆盖各批的行：空闲机器 %s；客机自有模型孪生第一批 %s、第二批 %s；fa706g3 多形状夹具孪生 %s。" % (
            rows_text(batches["backlog"]["rows"]), rows_text(batches["twins"]["rows"]), rows_text(batches["twins_b"]["rows"]),
            rows_text(batches["shapes"]["rows"])),
        "- 纯提速：%d 条，%s。%s。" % (s["speed_only"]["count"], rows_text(s["speed_only"]["rows"]), s["speed_only"]["kind"]),
        "- 失败或待确认：%d 条，%s。%s。" % (s["failed_or_pending"]["count"], rows_text(s["failed_or_pending"]["rows"]),
                                          s["failed_or_pending"]["kind"]),
        "- 已恢复的失败轮：%s。%s。" % (rows_text(s["recovered_failed_rounds"]["rows"]), s["recovered_failed_rounds"]["kind"]),
        "- 最终引擎上的回归：%d 行，其中 SHADOW %d 行（%s），NON_GREEN %d 行（%s）。不计入前三类。" % (
            s["regression_final_engine"]["count"], len(s["regression_final_engine"]["shadow_rows"]),
            rows_text(s["regression_final_engine"]["shadow_rows"]), len(s["regression_final_engine"]["failed_rows"]),
            rows_text(s["regression_final_engine"]["failed_rows"])),
        "- 另一台机器上的回归运行（复核）：%d 行，评级计数 %s，其中 NON_GREEN %d 行（%s）。不改变上一条的结论。" % (
            s["regression_final_engine"]["other_machine"]["count"],
            counts_text(s["regression_final_engine"]["other_machine"]["verdicts"]),
            len(s["regression_final_engine"]["other_machine"]["failed_rows"]),
            rows_text(s["regression_final_engine"]["other_machine"]["failed_rows"])),
        "- 派发失败（没有到 GUI，无评级，不属于任何一类运行）：%d 条，见 `dispatch-failures.md`。" % len(s["dispatch_failures"]),
        "",
        "**列的口径**",
        "",
        "- 操作类型：提速对照（#276、#264 的基线与候选）、补覆盖（空闲机器、客机自有模型孪生两批、fa706g3 多形状夹具孪生；单独记账，不计闭环）、"
        "最终引擎回归（`2a17376`/`62cddee`，同一引擎；在分到的机器上每行一次）、另一台机器上的回归运行（复核）、最终引擎复核（`final2-*`）、"
        "失败后的重试、d5fc2fa 上的回归与复核（不是最终引擎，已被取代）、同夜基线、原生模型对照（失败）。",
        "- 基线秒数 / 候选秒数（两次） / 整轮节省：只有 #276、#264 有。客机是宿主整轮秒（含收割），fa706g3 是机内进程秒（它不写宿主摘要）；",
        "  #276 的链是 基线 → 就绪等待，Strength 初态单列；#264 的链是 基线 → K1 就绪等待 → K2 滚轮一次到位，K2 与 K1 比；逐阶段和最终引擎上的复核见 `stage-timings.md`。",
        "- 未通过项：只写文件里能查到的；「本轮没有核对」不等于通过。",
        "- 证据链接：`docs/runs/evidence/ninehour-2026-11-25/` 下的收据（每个 run 一份）。",
        "- 最终评级：客机是回归证据机；fa706g3 和 Mac 最高记 SHADOW（README 第 6 条）。本轮没有发布 GREEN，也就没有符合飞书回写条件（完整 GREEN / 已覆盖）的行。",
        "- 回归和补覆盖回答的都只是「写入、保存、重开、切片和导出走不走得通」：跑的是不带后缀的 `uia_param_<key>` 场景（立方体工程）或它的孪生场景，"
        "不是飞书前置条件里的模型和预设，也不逐项核对飞书预期。",
        "",
        "| 飞书编号 | record ID | 用例标题 | 飞书状态 | 操作类型 | 基线秒数 | 候选秒数（两次） | 整轮节省 | 未通过项 | 证据链接 | 最终评级 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    index = {name: i for i, name in enumerate(data["columns"])}
    for row in data["rows"]:
        if row[index["操作类型"]] is None and row[0] not in data["touched_rows"]:
            continue
        cell = lambda name: row[index[name]]      # noqa: E731
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
                 read_json(evidence / "negative-controls.json"), read_json(evidence / "native-pairing.json"),
                 assigned_side(args.repo))
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
