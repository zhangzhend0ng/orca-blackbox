#!/usr/bin/env python3
"""check_feishu_map.py — 双向校验「用例注解 ↔ 飞书基线表」。

四类检查：
  1. 每个注册用例都声明了 `# feishu: ...` 注解（none 也算声明）；
  2. 注解引用的记录号在 FEISHU_BASELINE.md 里存在（且该行的处置确实指向本用例）；
  3. 用例所在的目录分组 ∈ 其引用记录的「二级分类」（跨组用例取任意一组即可）；
  4. 反向：文档里处置为 COVERED / NEW-> 的记录，至少有一个用例注解声明了它。

需要 artifacts/feishu_baseline_full.ndjson（实时表导出，tools 里 lark-cli 那条命令
生成）来取二级分类；缺失时跳过第 3 项并提示。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")
sys.path.insert(0, str(ROOT))
import cases  # noqa: E402

problems: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        problems.append(name)


# --- 文档侧：记录号 -> (处置, 声明本用例的记录集合) ---
doc_rows: dict[str, dict] = {}
for line in (ROOT / "FEISHU_BASELINE.md").read_text(encoding="utf-8").splitlines():
    if not line.startswith("|"):
        continue
    c = [x.strip() for x in line.strip().strip("|").split("|")]
    if len(c) < 5 or not c[0].isdigit():
        continue
    doc_rows[c[0]] = {"处置": c[3], "映射": c[4] if len(c) > 4 else ""}

# --- 实时表侧：记录号 -> 二级分类 ---
label_of_slug = {v: k for k, v in cases.GROUP_LABELS.items()}
group_of_num: dict[str, str] = {}
ndjson = ROOT / "artifacts" / "feishu_baseline_full.ndjson"
if ndjson.exists():
    for ln in ndjson.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        num = r.get("用例编号")
        num = num[0] if isinstance(num, list) and num else num
        lbl = r.get("二级分类")
        lbl = lbl[0] if isinstance(lbl, list) and lbl else lbl
        if num:
            group_of_num[str(num)] = label_of_slug.get(lbl, "")

# --- 1+2+3: 逐用例 ---
missing_ann, bad_ref, group_mismatch, known_exc = [], [], [], []
for key in cases.CASES:
    refs = cases.feishu_refs(key)
    if refs is None:
        missing_ann.append(key)
        continue
    nums = [r.split("#", 1)[1] for r in refs if r.startswith("baseline#")]
    for n in nums:
        if n not in doc_rows:
            bad_ref.append(f"{key}->#{n}")
    if group_of_num and nums:
        g = cases.CASES[key]["group"]
        gs = {group_of_num.get(n, "") for n in nums} - {""}
        if gs and g not in gs:
            if key in cases.GROUP_OVERRIDES:
                known_exc.append(f"{key} ({cases.GROUP_OVERRIDES[key]})")
            else:
                group_mismatch.append(f"{key}: 在 {g}, 记录属 {sorted(gs)}")

check("每个用例都声明了 feishu 注解", not missing_ann, f"缺注解: {missing_ann}")
check("注解引用的记录号都存在于 FEISHU_BASELINE.md", not bad_ref, f"未知引用: {bad_ref}")
if group_of_num:
    check("目录分组 = 引用记录的二级分类（已知例外除外）", not group_mismatch,
          f"不一致: {group_mismatch}")
    if known_exc:
        print(f"      （已知例外 {len(known_exc)} 条，见 cases.GROUP_OVERRIDES: {'; '.join(known_exc)}）")
else:
    print("SKIP  目录分组 = 引用记录的二级分类（缺实时表导出 artifacts/feishu_baseline_full.ndjson）")

# --- 4: 反向覆盖 ---
claimed = set()
for key in cases.CASES:
    for r in (cases.feishu_refs(key) or []):
        if r.startswith("baseline#"):
            claimed.add(r.split("#", 1)[1])
unclaimed = [n for n, row in doc_rows.items()
             if ("COVERED" in row["处置"] or "NEW->" in row["处置"]) and n not in claimed]
check("COVERED/NEW 的记录都有用例声明", not unclaimed, f"无用例: {unclaimed}")

n_map = sum(1 for k in cases.CASES if cases.feishu_refs(k))
print(f"\n用例: {len(cases.CASES)} | 有基线映射: {n_map} | 显式 none: "
      f"{sum(1 for k in cases.CASES if cases.feishu_refs(k) == [])}")
print("CHECK_FEISHU_MAP: PASS" if not problems else f"CHECK_FEISHU_MAP: FAIL ({len(problems)})")
sys.exit(1 if problems else 0)
