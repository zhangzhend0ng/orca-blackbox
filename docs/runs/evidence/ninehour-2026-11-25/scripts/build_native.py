"""The native model runs of the nine-hour run (2026-11-25) and the Script runs they were to be paired with.

    set PYTHONDONTWRITEBYTECODE=1
    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_native.py [--evidence <folder>]

Reads ledger.jsonl and receipts/<run_id>.json of the evidence folder and, through the run_dir a
receipt names, <artifacts>/windows_mcp_host/<run_id>/host.json - read-only. Writes
native-pairing.json next to scripts/. A run is the LAST ledger line written for its run id.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

from build_common import EVIDENCE, dump, load_ledger, load_receipts, read_json, role_of, write


def build(ledger, receipts):
    runs = []
    native = sorted((run_id for run_id in ledger if role_of(ledger[run_id].get("label")) == "native"),
                    key=lambda run_id: (ledger[run_id].get("started") or "", run_id))
    for run_id in native:
        entry, receipt = ledger[run_id], receipts.get(run_id)
        if receipt is None:
            continue
        host_path = Path(receipt["run_dir"]).parent.parent / "windows_mcp_host" / run_id / "host.json"
        host = read_json(host_path)
        calls = host.get("native_tool_calls") or []
        guest, comparison = host.get("guest_result") or {}, receipt["verdicts"]["comparison"] or {}
        runs.append({
            "run_id": run_id, "label": entry.get("label"), "scenario": entry["scenario"],
            "feishu_row": re.search(r"compare_(\d+)_", entry["scenario"]).group(1),
            "engine_commit": entry.get("commit"), "actor": host.get("actor"),
            "provider_id": host.get("provider_id"), "provider_name": host.get("provider_name"),
            "model_id": host.get("model_id"), "endpoint_host": host.get("endpoint_host"),
            "prompt_mode": host.get("prompt_mode"), "toolset_verified": host.get("toolset_verified"),
            "tool_calls": len(calls),
            "tool_calls_by_tool": dict(sorted(collections.Counter(c.get("tool") for c in calls).items())),
            "tool_calls_by_status": dict(sorted(collections.Counter(c.get("status") for c in calls).items())),
            "host_wall_seconds": entry.get("host_wall_seconds"),
            "guest_process_seconds": round(receipt["seconds"]["guest"], 3),
            "ledger_orchestration_seconds": entry.get("process_seconds"),
            "failure_signature": host.get("error"),
            "comparison_status": comparison.get("status"),
            "comparison_unmet_expectations": comparison.get("unmet_expectations"),
            "release_verdict": guest.get("release_verdict") or receipt["verdicts"]["release_verdict"],
            "reasons": guest.get("reasons"), "verified_pass": guest.get("verified_pass"),
            "cleanup_confirmed": guest.get("cleanup_confirmed"),
            "paired": False,
            "pairing_note": "没有经独立验证的 GUI 结果，未进入与 Script 的配对。",
            "sources": ["docs/runs/evidence/ninehour-2026-11-25/receipts/%s.json" % run_id, host_path.as_posix()],
        })
    scripts = {}
    for run_id, entry in ledger.items():
        if entry["scenario"].startswith("compare_") and role_of(entry.get("label")) in ("baseline", "wait276", "final"):
            scripts.setdefault(entry["scenario"], []).append(run_id)
    return {
        "schema": "ninehour_native_pairing/1", "generated_by": "scripts/build_native.py",
        "note": "原生模型 actor（ZCode）与 Script 共用保存件、重开切片和基线判据。本轮两次原生运行都没有取得经独立验证的 GUI 结果，配对 0 次。",
        "runs": runs,
        "script_runs_of_the_same_scenarios": {
            key: sorted(value, key=lambda run_id: (ledger[run_id].get("started") or "", run_id))
            for key, value in sorted(scripts.items())},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", default=str(EVIDENCE))
    args = parser.parse_args(argv)
    evidence = Path(args.evidence)
    write(evidence, "native-pairing.json", dump(build(load_ledger(evidence / "ledger.jsonl"), load_receipts(evidence))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
