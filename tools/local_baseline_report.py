#!/usr/bin/env python3
"""Emit the live-Feishu-table ↔ implemented-case mapping report."""
import json
import re
import sys
import collections
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")
sys.path.insert(0, str(ROOT))
import cases  # noqa: E402

live = [json.loads(l) for l in (ROOT / "artifacts" / "feishu_baseline_v2.ndjson")
        .read_text(encoding="utf-8").splitlines() if l.strip()]


def one(rec, key):
    v = rec.get(key)
    return (v[0] if isinstance(v, list) and v else v) or ""


live_by_id = {}
for r in live:
    n = one(r, "用例编号").strip()
    if n:
        live_by_id[n] = r

doc = (ROOT / "FEISHU_BASELINE.md").read_text(encoding="utf-8")
mapped = {}
for line in doc.splitlines():
    if not line.startswith("|"):
        continue
    c = [x.strip() for x in line.strip().strip("|").split("|")]
    if len(c) >= 5 and c[0].isdigit():
        mapped[c[0]] = {"标题": c[1], "优先级": c[2], "处置": c[3],
                        "映射": c[4] if len(c) > 4 else ""}

reg = set(cases.enabled_cases("regression"))
smoke = set(cases.enabled_cases("smoke"))


def resolve(name):
    """Resolve a doc case reference (short or full) to a registry key."""
    if name in cases.CASES:
        return name
    cands = [k for k in cases.CASES if k == name or k.startswith(name + "_")]
    return cands[0] if cands else None


CASE_RE = re.compile(r"\b(m\d+[a-z0-9]*)\b")

rows = []
for num in sorted(live_by_id, key=lambda x: int(x)):
    rec = live_by_id[num]
    title = one(rec, "用例标题")
    fld = one(rec, "功能域")
    prio = one(rec, "优先级")
    m = mapped.get(num)
    if not m:
        rows.append({"num": num, "title": title, "fld": fld, "prio": prio,
                     "state": "新增/未映射", "cases": [], "note": ""})
        continue
    disp = m["处置"]
    refs = CASE_RE.findall(m["处置"]) + CASE_RE.findall(m["映射"]) + CASE_RE.findall(m["标题"])
    keys = [resolve(r) for r in refs]
    keys = [k for k in keys if k]
    seen, uniq = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    if "COVERED" in disp or "NEW->" in disp:
        if uniq and not any(k in reg for k in uniq):
            state = "已实现·未纳入套件"
        elif uniq:
            state = "已实现"
        else:
            state = "已实现(用例未标注)"
    elif "PARTIAL" in disp:
        state = "部分实现"
    elif "OUT-OF-SCOPE" in disp:
        state = "范围外"
    else:
        state = "未实现"
    rows.append({"num": num, "title": title, "fld": fld, "prio": prio,
                 "state": state, "cases": uniq, "note": m["映射"][:70]})

cnt = collections.Counter(r["state"] for r in rows)
rep = []
rep.append("# 飞书「Orca回归基线用例集」↔ vision-gui 黑盒套件 对照报告")
rep.append("")
rep.append(f"- 飞书实时表: {len(rows)} 条（wiki `VtS3wy9WpiNKoRkFJJYcNvPSnZb` / base `RJKPbW7fTaMkNnsPx3LcFQISnmd` / table `tbl2WmD8AtG9yH1i`）")
rep.append(f"- 仓库映射快照: FEISHU_BASELINE.md（107 条，09-16）")
rep.append(f"- 套件注册表: {len(cases.CASES)} 个用例（regression {len(reg)} / smoke {len(smoke)}）")
rep.append(f"- 飞书侧 `自动化状态` 字段: **全部仍为「未覆盖」**（尚未回填自动化进展）")
rep.append("")
rep.append("## 汇总")
rep.append("")
rep.append("| 状态 | 条数 |")
rep.append("|---|---|")
for k in ("已实现", "已实现·未纳入套件", "部分实现", "未实现", "范围外", "新增/未映射", "已实现(用例未标注)"):
    if cnt.get(k):
        rep.append(f"| {k} | {cnt[k]} |")
rep.append(f"| **合计** | **{len(rows)}** |")
rep.append("")

rep.append("## 按功能域")
rep.append("")
rep.append("| 功能域 | 已实现 | 部分 | 未实现/范围外 | 合计 |")
rep.append("|---|---|---|---|---|")
dom = collections.defaultdict(collections.Counter)
for r in rows:
    dom[r["fld"]][r["state"]] += 1
for fld in sorted(dom, key=lambda k: -sum(dom[k].values())):
    c = dom[fld]
    done = c["已实现"] + c["已实现·未纳入套件"] + c["已实现(用例未标注)"]
    part = c["部分实现"]
    notd = c["未实现"] + c["范围外"] + c["新增/未映射"]
    rep.append(f"| {fld or '(空)'} | {done} | {part} | {notd} | {done+part+notd} |")
rep.append("")

for state in ("未实现", "范围外", "部分实现", "已实现·未纳入套件", "新增/未映射"):
    sel = [r for r in rows if r["state"] == state]
    if not sel:
        continue
    rep.append(f"## {state}（{len(sel)} 条）")
    rep.append("")
    for r in sel:
        cs = ",".join(r["cases"]) or "-"
        rep.append(f"- **#{r['num']}** [{r['prio']}] {r['fld']} — {r['title'][:40]}"
                   + (f"  → `{cs}`" if r["cases"] else "")
                   + (f"  _{r['note']}_" if r["note"] else ""))
    rep.append("")

out = ROOT / "artifacts" / "feishu_baseline_report.md"
out.write_text("\n".join(rep), encoding="utf-8")
print("\n".join(rep[:40]))
print(f"\n... (完整报告 {len(rep)} 行已写入 {out})")
