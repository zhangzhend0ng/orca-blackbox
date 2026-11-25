"""The dispatches that never ran: one line each, with no verdict and no run class.

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_dispatches.py [--evidence <folder>] [--artifacts <artifacts root>]

Reads ledger.jsonl and receipts/ of the evidence folder and, read-only, what the machines' launch
path left of each dispatch: for the guest <artifacts>/native_save_demo/<run_id>/launch.json and
launch.stages, for fa706g3 <artifacts>/windows_mcp_harvest/<run_id>/native_run.log. Writes
dispatch-failures.json and dispatch-failures.md next to scripts/.

A dispatch is a ledger run (the LAST line written for its run id) that has no receipt: nothing was
harvested, so it never reached the GUI. It has no verdict and belongs to no run class.
What the files recorded (message, error type, when it was refused) is kept apart from the cause,
which is the orchestrator's account of the session and is marked as such.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from build_common import EVIDENCE, MACHINE_TEXT, dump, ledger_facts, load_ledger, load_receipts, read_json, short, write

DEFAULT_ARTIFACTS = "C:/coil/Projects/SnapmakerOrca/external/orca-blackbox/artifacts"
# The orchestrator's account of each cause (not something the files say).
CAUSE_DETACHED = ("总控的说明：暂存 checkout 当时处在游离的 HEAD 上，hv_go 拒绝启动；切回分支后重跑，是 `778bbfa2`")
CAUSE_CRLF = ("总控的说明：队列脚本把一行的行尾（CR）带进了场景名，参数解析拒绝了它；修正队列脚本后重跑，是 `8352f74d`")
CAUSES = {}   # filled below: the full account once per group
CAUSE_HEAD = ("总控的说明：为第一次推送把暂存 checkout 快进到 62cddee 时，客机还在 2a17376 上，native_save_demo 的 HEAD 检查拒绝了每一次启动；"
              "之后把客机同步到 62cddee，guest-twins-b 的 11 个场景换了新的 run ID 重跑。这是总控的失误，这些 run 什么都没有跑")
UNKNOWN = "总控的说明：没有单独说明"
CAUSES = {"detached_checkout": CAUSE_DETACHED, "crlf_in_scenario_name": CAUSE_CRLF, "guest_head_check_refused": CAUSE_HEAD,
          "other": UNKNOWN}
CAUSE_SHORT = {
    "detached_checkout": "暂存 checkout 处在游离的 HEAD 上，hv_go 拒绝启动",
    "crlf_in_scenario_name": "场景名带行尾 CR，参数解析拒绝",
    "guest_head_check_refused": "客机的 HEAD 不是启动要求的提交，HEAD 检查拒绝",
    "other": "没有单独说明",
}


def group_of(entry):
    if entry["run_id"].startswith("467e62b1"):
        return "detached_checkout"
    if entry["run_id"].startswith("91175532"):
        return "crlf_in_scenario_name"
    if entry.get("dispatch_failed") == "launch_refused_by_precheck":
        return "guest_head_check_refused"
    return "other"


def guest_receipt(run_id, artifacts):
    """What the guest launch path recorded: launch.json's message and the stage times."""
    folder = Path(artifacts) / "native_save_demo" / run_id
    out = {}
    try:
        data = read_json(folder / "launch.json")
        out.update(launch_ok=data.get("ok"), launch_message=data.get("message"), launch_error_type=data.get("error_type"))
    except (OSError, ValueError):
        pass
    try:
        stages = (folder / "launch.stages").read_text(encoding="utf-8-sig", errors="replace").split()
        out["launch_stages"] = " ".join(stages[:2]) + " … " + " ".join(stages[-2:]) if len(stages) >= 4 else " ".join(stages)
    except OSError:
        pass
    return out, folder


def fa_log(run_id, artifacts):
    """The argparse error line of the fa706g3 task log, if there is one."""
    path = Path(artifacts) / "windows_mcp_harvest" / run_id / "native_run.log"
    try:
        # split at line feeds only (not splitlines()): a carriage return is part of the evidence
        lines = path.read_bytes().decode("utf-8-sig", errors="replace").split("\n")
    except OSError:
        return {}, path
    errors = [line for line in lines if "error:" in line]
    if errors:
        found = re.search(r"invalid choice: '([^']*)'", errors[-1])
        # argparse prints the rejected value with repr(): a carriage return shows as the two characters \r
        return {"task_log_error": errors[-1][:200], "scenario_as_parsed": found.group(1) if found else None,
                "scenario_as_parsed_has_cr": bool(found and found.group(1).endswith("\\r"))}, path
    return {"task_log_error": None}, path


def build(ledger, receipts, artifacts):
    items = []
    for run_id, entry in sorted(ledger.items(), key=lambda item: (item[1].get("started") or "", item[0])):
        if run_id in receipts:
            continue
        machine = "guest" if entry["machine"] == "win11-test" else entry["machine"]
        group = group_of(entry)
        item = {
            "run_id": run_id, "machine": machine, "started": entry.get("started"), "ended": entry.get("ended"),
            "scenario": entry["scenario"], "scenario_has_control_character": entry["scenario"] != entry["scenario"].strip(),
            "label": entry.get("label"), "ledger_commit": entry.get("commit"),
            "ledger_dispatch_failed": entry.get("dispatch_failed"), "ledger_worker_error": entry.get("worker_error"),
            "group": group, "cause_short": CAUSE_SHORT[group],
        }
        recorded, where = (guest_receipt(run_id, artifacts) if machine == "guest" else fa_log(run_id, artifacts))
        item.update(recorded)
        item["read_from"] = where.as_posix() if recorded else None
        items.append(item)
    groups = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item)
    return dict(ledger_facts(ledger), **{
        "schema": "ninehour_dispatch_failures/1", "generated_by": "scripts/build_dispatches.py",
        "note": "没有收据的 ledger run：什么都没有收割到，所以没有到 GUI。它们没有评级，不属于任何一类运行，只在这里逐条列出。"
                "「记录下来的」取自文件；「原因」是总控对当晚经过的说明，文件只能佐证其中的一部分。",
        "artifacts_root": Path(artifacts).as_posix(),
        "count": len(items),
        "per_machine": {machine: sum(1 for item in items if item["machine"] == machine) for machine in ("guest", "fa706g3")},
        "per_group": {group: len(members) for group, members in groups.items()},
        "orchestrator_account": {group: CAUSES[group] for group in groups},
        "dispatches": items,
    })


def recorded_text(item):
    """What the files recorded, short enough for one line."""
    if item["machine"] == "guest":
        text = "`%s`" % item.get("launch_message")
        if item.get("launch_stages"):
            times = item["launch_stages"].split()
            text += "（%s 起，%s 止）" % (times[1] if len(times) > 1 else "-", times[-1] if times else "-")
        return text
    if item.get("task_log_error"):
        return "任务日志 `native_save_run.py: error: argument --scenario: invalid choice`，解析出的场景名%s行尾 CR" % (
            "带" if item.get("scenario_as_parsed_has_cr") else "不带")
    return "没有留下记录"


def markdown(data):
    lines = [
        "# 没有跑起来的派发", "",
        "共 %d 条（客机 %d 条，fa706g3 %d 条）。它们没有收据，说明什么都没有收割到、没有到 GUI：没有评级，不属于任何一类运行，不记在 SHADOW 里，也不算失败轮。"
        "台账复制时共 %d 行、%d 个 run，末行结束于 %s。" % (
            data["count"], data["per_machine"]["guest"], data["per_machine"]["fa706g3"],
            data["ledger_lines"], data["ledger_runs"], data["ledger_last_ended"]),
        "",
        "| run ID | 机器 | 起 | 场景 | 标签 | 文件记录下来的 | 原因（一句话） |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in data["dispatches"]:
        scenario = "`%s`%s" % (item["scenario"].strip(), "（台账里带行尾 CR）" if item["scenario_has_control_character"] else "")
        lines.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
            item["run_id"], MACHINE_TEXT[item["machine"]], item["started"], scenario, item["label"],
            recorded_text(item), item["cause_short"]))
    lines += ["", "原因按组各记一次。前一半是文件里有的，后一半（总控的说明）是总控对当晚经过的交代：", ""]
    names = {"detached_checkout": "02:26 的一条", "crlf_in_scenario_name": "03:55 的一条",
             "guest_head_check_refused": "07:04:19–07:04:53 的十二条", "other": "其余"}
    for group, account in data["orchestrator_account"].items():
        lines.append("- %s：%s" % (names.get(group, group), account))
    lines += [
        "",
        "来源：`dispatch-failures.json`（`scripts/build_dispatches.py`，读台账副本、收据目录和 `%s` 下各 run 的启动回执或任务日志）。"
        % data["artifacts_root"],
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", default=str(EVIDENCE))
    parser.add_argument("--artifacts", default=DEFAULT_ARTIFACTS)
    args = parser.parse_args(argv)
    evidence = Path(args.evidence)
    data = build(load_ledger(evidence / "ledger.jsonl"), load_receipts(evidence), args.artifacts)
    write(evidence, "dispatch-failures.json", dump(data))
    write(evidence, "dispatch-failures.md", markdown(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
