"""Shared helpers of the table builders of the nine-hour evidence folder (2026-11-25).

Imported by build_stage.py, build_native.py, build_family.py and build_feishu.py. Read-only on
everything it opens; nothing is launched and no machine is reached.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
RECEIPTS = "docs/runs/evidence/ninehour-2026-11-25/receipts"
SNAPSHOT = "docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/tblKjIVV8KA53kUQ_20261122_024056_171.ndjson"

# label prefix -> role. The roles are the orchestrator's labels in the session ledger.
# "guest-twins-b" is tested before "guest-twins" so that the second batch keeps its own role.
ROLES = (
    ("base-", "baseline"), ("timed-", "timed"), ("cand-k1-", "wait264"), ("cand-k2-", "burst264"),
    ("cand-q-", "wait276"), ("cand-s-", "wait276"), ("cand-fa-", "wait276"),
    ("backlog-", "backlog"), ("regress", "regress"), ("retry-", "retry"), ("second-sample", "second_sample"),
    ("native-", "native"), ("final2-", "final2"), ("final-", "final"),
    ("guest-twins-b", "twins_b"), ("guest-twins", "twins"), ("fa-shapes", "shapes"),
)
ROLE_ORDER = ("baseline", "timed", "wait276", "wait264", "burst264", "final2", "final")
CANDIDATES = ("wait276", "wait264", "burst264")
TIMED_ROLES = ("baseline", "timed", "wait276", "wait264", "burst264", "final2", "final")
COVERAGE_ROLES = ("backlog", "twins", "twins_b", "shapes")     # extra coverage: its own account, never closure
ROLE_TEXT = {
    "baseline": "基线", "timed": "计时版", "wait276": "候选（#276 就绪等待）",
    "wait264": "K1（就绪等待）", "burst264": "K2（滚轮一次到位）",
    "final2": "最终引擎 2a17376 上的复核", "final": "d5fc2fa 上的复核（不是最终引擎）",
    "backlog": "补覆盖（早先的空闲机器运行）", "regress": "回归", "retry": "失败后的重试",
    "second_sample": "fa706g3 对客机那一半的第二样本", "native": "原生模型对照",
    "twins": "客机自有模型孪生（第一批）", "twins_b": "客机自有模型孪生（第二批）", "shapes": "fa706g3 多形状夹具孪生",
}
# The engine that was merged: d5fc2fa plus the cherry-pick of 5b38c80 (2a17376), and the first push
# 62cddee, a merge of 2a17376 with the documentation branch whose engine files are identical.
FINAL_ENGINE = "2a17376"
FINAL_ENGINES = ("2a17376", "62cddee")
MERGED_HEAD = "62cddee803c595a2a46323286ed37fb06bdcff72"
SUPERSEDED_ENGINE = "d5fc2fa"
MACHINE_TEXT = {"guest": "客机 win11-test", "fa706g3": "fa706g3"}
MACHINE_SHORT = {"guest": "客机", "fa706g3": "fa706g3"}
MACHINE_OF_LEDGER = {"win11-test": "guest", "fa706g3": "fa706g3"}


def role_of(label):
    for prefix, role in ROLES:
        if (label or "").startswith(prefix):
            return role
    return "other"


def engine_of(entry):
    """'final', 'd5fc2fa' or 'other': what the ledger's commit field says a run was on."""
    commit = entry.get("commit") or ""
    if commit.startswith(FINAL_ENGINES):
        return "final"
    return "d5fc2fa" if commit.startswith(SUPERSEDED_ENGINE) else "other"


def on_final_engine(entry):
    """Whether the ledger says a run was on the final engine (2a17376 or 62cddee: the same engine)."""
    return engine_of(entry) == "final"


def f3(value):
    return "-" if value is None else "%.3f" % value


def mean(values):
    values = [v for v in values if v is not None]
    return None if not values else sum(values) / len(values)


def short(run_id):
    return run_id[:8]


def commit_text(commit):
    return "台账未记" if not commit else commit[:7]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_ledger(path):
    """{run_id: entry}: the last line written for a run id wins; entry["_line"] is that line's number."""
    entries = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            entry = json.loads(line)
            entry["_line"] = number
            entries[entry["run_id"]] = entry
    return entries


def load_receipts(evidence):
    out = {}
    for path in sorted((evidence / "receipts").glob("*.json")):
        data = read_json(path)
        out[data["identity"]["run_id"]] = data
    return out


def write(evidence, name, text):
    path = evidence / name
    path.write_text(text, encoding="utf-8", newline="\n")
    print("wrote %s (%d lines)" % (path.as_posix(), len(text.splitlines())))


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def ledger_facts(ledger):
    return {"ledger_lines": max(entry["_line"] for entry in ledger.values()),
            "ledger_runs": len(ledger),
            "ledger_last_ended": max(entry.get("ended") or "" for entry in ledger.values())}


def family_rows(repo):
    """[(feishu_row, case_id, scenario)] of the parameter family, in the order the queue uses (case ids sorted as strings)."""
    listing = subprocess.run([sys.executable, "-B", "tools/param_closure_list.py"], cwd=repo, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), check=True).stdout
    keys = {}
    for line in listing.splitlines():
        found = re.match(r"\s*(param_\S+)\s+(\w+)\s", line)
        if found:
            keys[found.group(1)] = found.group(2)
    return [(int(re.findall(r"\d+", case)[-1]), case, "uia_param_" + keys[case]) for case in sorted(keys)]


def family_queues(repo):
    """The split of the session's family_queue.py: even index -> guest, odd index -> fa706g3."""
    names = family_rows(repo)
    return {"guest": [n for i, n in enumerate(names) if i % 2 == 0],
            "fa706g3": [n for i, n in enumerate(names) if i % 2 == 1]}


def assigned_side(repo):
    """{scenario name: the half it was assigned to} of the 42 parameter rows."""
    return {scenario: side for side, names in family_queues(repo).items() for _, _, scenario in names}


def feishu_row_of(scenario, family):
    """The Feishu row a scenario name belongs to, or None (a save-only baseline, the Mac goals).

    A twin keeps its row: `<scenario>_shapes`, `<scenario>_tol`, `<scenario>_fdmt2` ... all belong to
    the longest registered scenario name they extend."""
    found = re.match(r"compare_(\d+)_(quality|strength)$", scenario)
    if found:
        return int(found.group(1))
    if scenario in family:
        return family[scenario]
    best = ""
    for key in family:
        if scenario.startswith(key + "_") and len(key) > len(best):
            best = key
    return family.get(best) if best else None


def load_snapshot(path):
    """{feishu row: record_id, title, Feishu automation status} of the committed 216-row snapshot."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            status = row.get("自动化状态")
            out[int(row["用例编号"])] = {"record_id": row["record_id"], "title": row.get("用例标题"),
                                        "status": status[0] if isinstance(status, list) and status else status}
    return out
