#!/usr/bin/env python3
"""Join the LIVE Feishu baseline table (artifacts/feishu_baseline.ndjson) with the
repo's mapping snapshot (FEISHU_BASELINE.md) and the implemented case registry
(cases.py), and report implemented / partial / not-implemented per record."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")
sys.path.insert(0, str(ROOT))

# --- live table ---
live = [json.loads(l) for l in (ROOT / "artifacts" / "feishu_baseline.ndjson")
        .read_text(encoding="utf-8").splitlines() if l.strip()]


def one(rec, key):
    v = rec.get(key)
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


live_by_id = {}
for r in live:
    num = one(r, "用例编号").strip()
    if not num:
        continue
    live_by_id[num] = r

# --- repo mapping snapshot ---
doc = (ROOT / "FEISHU_BASELINE.md").read_text(encoding="utf-8")
mapped = {}
for line in doc.splitlines():
    if not line.startswith("|"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 5 or cells[0] in ("#", "") or set(cells[0]) <= set("-: "):
        continue
    if not cells[0].isdigit():
        continue
    num = cells[0]
    mapped[num] = {"标题": cells[1], "优先级": cells[2], "处置": cells[3],
                   "映射": cells[4] if len(cells) > 4 else ""}

# --- implemented cases ---
import cases  # noqa: E402
implemented = set()
for name in cases.CASES:
    implemented.add(name)
enabled = set(cases.enabled_cases(None))
regression = set(cases.enabled_cases("regression"))
smoke = set(cases.enabled_cases("smoke"))

CASE_RE = re.compile(r"\b(m\d+[a-z0-9_]*)\b")


def cases_in(text):
    return sorted({m for m in CASE_RE.findall(text or "")})


print(f"实时表记录: {len(live_by_id)}   仓库映射快照: {len(mapped)}   已注册用例: {len(implemented)}")
print()

# --- join ---
covered, partial, notimpl, newrec = [], [], [], []
for num in sorted(live_by_id, key=lambda x: int(x) if x.isdigit() else 1 << 30):
    rec = live_by_id[num]
    title = one(rec, "用例标题")
    fld = one(rec, "功能域")
    prio = one(rec, "优先级")
    m = mapped.get(num)
    if not m:
        newrec.append((num, title, fld, prio))
        continue
    disp = m["处置"]
    cs = cases_in(m["映射"]) or cases_in(m["标题"])
    missing_cases = [c for c in cs if c not in implemented]
    if "COVERED" in disp or "NEW->" in disp:
        covered.append((num, title, fld, prio, disp, cs, missing_cases))
    elif "PARTIAL" in disp:
        partial.append((num, title, fld, prio, disp, cs))
    else:  # MANUAL / SKIP / OUT-OF-SCOPE
        notimpl.append((num, title, fld, prio, disp, m["映射"]))

print("=== A. 已实现（COVERED / NEW->m8x）===")
print(f"共 {len(covered)} 条")
for num, title, fld, prio, disp, cs, missing in covered:
    flag = "" if not missing else f"  ⚠ 映射中的用例不在注册表: {missing}"
    print(f"  #{num:>4} [{prio}] {fld} | {title[:34]} | {disp[:16]} | {','.join(cs) or '-'}{flag}")
print()

print("=== B. 部分实现（PARTIAL）===")
print(f"共 {len(partial)} 条")
for num, title, fld, prio, disp, cs in partial:
    print(f"  #{num:>4} [{prio}] {fld} | {title[:34]} | {','.join(cs) or '-'}")
print()

print("=== C. 未实现（MANUAL / SKIP / OUT-OF-SCOPE）===")
print(f"共 {len(notimpl)} 条")
for num, title, fld, prio, disp, note in notimpl:
    print(f"  #{num:>4} [{prio}] {fld} | {title[:30]} | {disp[:24]} | {note[:40]}")
print()

print("=== D. 实时表里有、仓库快照里没有的记录 ===")
print(f"共 {len(newrec)} 条")
for num, title, fld, prio in newrec:
    print(f"  #{num:>4} [{prio}] {fld} | {title[:44]}")
print()

# per-domain summary
import collections  # noqa: E402
dom = collections.defaultdict(lambda: collections.Counter())
for group, label in ((covered, "covered"), (partial, "partial"), (notimpl, "notimpl")):
    for item in group:
        dom[item[2]][label] += 1
for num, title, fld, prio in newrec:
    dom[fld]["new"] += 1
print("=== E. 按功能域汇总 ===")
for fld in sorted(dom, key=lambda k: -sum(dom[k].values())):
    c = dom[fld]
    print(f"  {fld}: 已实现 {c['covered']} / 部分 {c['partial']} / 未实现 {c['notimpl']} / 新增未映射 {c['new']}")
print()
print("=== F. 注册表里属于 regression/smoke 的用例数 ===")
print(f"  regression={len(regression)}  smoke={len(smoke)}  全部启用={len(enabled)}")
