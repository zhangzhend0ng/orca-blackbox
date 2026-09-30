#!/usr/bin/env python3
"""Remap the writeback plan's record_ids from one table instance to another.

Both tables carry the same 用例编号 ↔ 用例标题 set (verified 107/107), so the
status plan built against the old table applies verbatim — only the record_ids
differ. Reads the old/new record-list exports and rewrites plan.json for the
target table.

用法：
    python tools/feishu_remap_plan.py \
        --from-export artifacts/feishu_baseline_full.ndjson \
        --to-export   artifacts/feishu_baseline_new.ndjson \
        --out         artifacts/feishu_base/plan_new.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")


def load(path: Path) -> dict[str, str]:
    """number -> record_id"""
    out: dict[str, str] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        num = r.get("用例编号")
        num = num[0] if isinstance(num, list) and num else num
        if num is not None:
            out[str(num)] = r["record_id"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path,
                    default=ROOT / "artifacts" / "feishu_base" / "plan.json")
    ap.add_argument("--from-export", type=Path,
                    default=ROOT / "artifacts" / "feishu_baseline_full.ndjson")
    ap.add_argument("--to-export", type=Path,
                    default=ROOT / "artifacts" / "feishu_baseline_new.ndjson")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "feishu_base" / "plan_new.json")
    args = ap.parse_args()

    src = json.loads(args.plan.read_text(encoding="utf-8"))
    old, new = load(args.from_export), load(args.to_export)
    back = {rid: num for num, rid in old.items()}

    plan_new: dict[str, list[str]] = {}
    detail_new: dict[str, list[str]] = {}
    missing = 0
    for cat, idlist in (src.get("plan") or {}).items():
        plan_new[cat] = []
        for rid in idlist:
            num = back.get(rid)
            if num is None or num not in new:
                missing += 1
                continue
            plan_new[cat].append(new[num])
        detail_new[cat] = (src.get("detail") or {}).get(cat, [])
        print(f"{cat}: {len(plan_new[cat])} 条")
    if missing:
        print(f"⚠ {missing} 条在目标表里找不到对应记录")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"plan": plan_new, "detail": detail_new},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"plan -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
