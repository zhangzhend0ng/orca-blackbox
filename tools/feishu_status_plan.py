#!/usr/bin/env python3
"""Feishu 自动化状态 写回计划：按处置把记录分成三档。

  GREEN 用例覆盖的记录           -> 已自动化   （需外部传入 GREEN 用例名）
  处置 PARTIAL 的记录            -> 待实现
  处置 MANUAL / SKIP / OUT-OF-SCOPE 的记录 -> 不适用（黑盒不可达/范围外）

输出 artifacts/feishu_base/plan.json：
  {"已自动化": [record_id...], "待实现": [...], "不适用": [...]}

用法：
    python tools/feishu_status_plan.py m6a_transform_verify m8e_purifier_weakcool ...
    python tools/feishu_status_plan.py --green-from-file artifacts/green.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")
sys.path.insert(0, str(ROOT))
import cases  # noqa: E402

ND = ROOT / "artifacts" / "feishu_baseline_full.ndjson"


def load_records() -> tuple[dict[str, str], dict[str, str]]:
    """(num -> record_id, num -> title)"""
    rid, title = {}, {}
    for ln in ND.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        num = r.get("用例编号")
        num = num[0] if isinstance(num, list) and num else num
        t = r.get("用例标题")
        t = t[0] if isinstance(t, list) and t else t
        if num:
            rid[str(num)] = r["record_id"]
            title[str(num)] = t or ""
    return rid, title


def load_dispositions() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "FEISHU_BASELINE.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 5 or not c[0].isdigit():
            continue
        out[c[0]] = c[3]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("green_cases", nargs="*", help="最近跑绿、可写『已自动化』的用例名")
    ap.add_argument("--green-from-file", type=Path, help="一行一个用例名")
    args = ap.parse_args()

    green = list(args.green_cases)
    if args.green_from_file and args.green_from_file.exists():
        green += [ln.strip() for ln in args.green_from_file.read_text(
            encoding="utf-8").splitlines() if ln.strip()]

    rid, title = load_records()
    disp = load_dispositions()

    plan = {"已自动化": [], "待实现": [], "不适用": []}
    detail = {"已自动化": [], "待实现": [], "不适用": []}

    claimed: set[str] = set()
    for case in green:
        for ref in (cases.feishu_refs(case) or []):
            if not ref.startswith("baseline#"):
                continue
            n = ref.split("#", 1)[1]
            if n in rid and n not in claimed:
                claimed.add(n)
                plan["已自动化"].append(rid[n])
                detail["已自动化"].append(f"#{n} {case}")

    for num, d in sorted(disp.items(), key=lambda kv: int(kv[0])):
        if num in claimed or num not in rid:
            continue
        if "PARTIAL" in d:
            plan["待实现"].append(rid[num])
            detail["待实现"].append(f"#{num} {title.get(num,'')[:28]}")
        elif any(k in d for k in ("MANUAL", "SKIP", "OUT-OF-SCOPE")):
            plan["不适用"].append(rid[num])
            detail["不适用"].append(f"#{num} {title.get(num,'')[:28]}")

    out = ROOT / "artifacts" / "feishu_base" / "plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"plan": plan, "detail": detail}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    for k in plan:
        print(f"{k}: {len(plan[k])} 条")
    print(f"plan -> {out}")
    if not plan["已自动化"]:
        print("(提示：没有传入 GREEN 用例，『已自动化』为空)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
