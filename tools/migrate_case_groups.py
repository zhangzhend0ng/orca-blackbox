#!/usr/bin/env python3
"""Migrate case scripts into per-二级分类 folders (Feishu baseline classification).

Layout: tests/<slug>/<case>.py for classified cases, tests/engine/ for the rest.
Shared helpers (m3_common / m5_common / m7_common / m8_common / conftest /
test_blackbox / m9_baseline) stay in tests/.

Usage:
    python tools/migrate_case_groups.py            # dry run: print the plan
    python tools/migrate_case_groups.py --apply    # git mv + patch bootstraps
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")
sys.path.insert(0, str(ROOT))
import cases  # noqa: E402

# slug <-> Feishu 二级分类
GROUPS = {
    "mixing_match": "混色匹配映射",
    "mixing": "混色功能",
    "mainflow": "主流程-用例",
    "gui": "GUI业务",
    "topcap": "顶盖1.4.0",
    "filament": "耗材管理",
    "fit_view": "一键还原视图",
    "high_flow": "高流量热端",
    "engine": "(无基线映射 / 引擎与链路用例)",
}

# Explicit placements whose doc entry is a PARTIAL cross-reference rather than the
# case's primary identity (decided 2026-09-21):
#   m4d/m4i map to 混色功能 (COVERED) AND 主流程-用例 (PARTIAL) -> the feature group
#   m4e is the mixing-paint implementation (only a PARTIAL mainflow note) -> mixing
#   m2_slice_chain is the slice ENGINE referenced from a 耗材管理 PARTIAL note -> engine
OVERRIDES = {
    "m4d_mixing_filops": "mixing",
    "m4i_mixing_slice": "mixing",
    "m4e_mixing_paint": "mixing",
    "m2_slice_chain": "engine",
}

SHARED = {"conftest.py", "m3_common.py", "m5_common.py", "m7_common.py",
          "m8_common.py", "m9_baseline.py", "test_blackbox.py"}


def one(rec, key):
    v = rec.get(key)
    return (v[0] if isinstance(v, list) and v else v) or ""


def build_assignment():
    import json
    table = {}
    for line in (ROOT / "artifacts" / "feishu_baseline_full.ndjson").read_text(
            encoding="utf-8").splitlines():
        r = json.loads(line)
        table[one(r, "用例编号")] = one(r, "二级分类")

    slug_of_label = {v: k for k, v in GROUPS.items()}
    # A case is grouped by the Feishu record(s) it implements. COVERED / NEW->
    # rows win over PARTIAL-only references (which are cross-references, e.g. the
    # mainflow rows that name a mixing case); OVERRIDES settle the rest.
    primary_hit, partial_hit = {}, {}
    for line in (ROOT / "FEISHU_BASELINE.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 5 or not c[0].isdigit():
            continue
        num, disp, note = c[0], c[3], c[4]
        primary = ("COVERED" in disp or "NEW->" in disp)
        label = table.get(num, "")
        slug = slug_of_label.get(label)
        if not slug:
            continue
        for name in re.findall(r"\b(m\d+[a-z0-9]*)\b", disp + " " + note):
            key = name if name in cases.CASES else next(
                (k for k in cases.CASES if k.startswith(name + "_")), None)
            if not key:
                continue
            if primary:
                primary_hit.setdefault(key, slug)
            else:
                partial_hit.setdefault(key, slug)
    assign = dict(partial_hit)
    assign.update(primary_hit)
    for k, v in OVERRIDES.items():
        assign[k] = v
    return {k: assign.get(k, "engine") for k in cases.CASES}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    assign = build_assignment()

    by_group = {}
    for k, g in assign.items():
        by_group.setdefault(g, []).append(k)

    print("=== 分组方案 ===")
    for g in list(GROUPS):
        ks = sorted(by_group.get(g, []))
        if ks:
            print(f"\n[{'engine' if g == 'engine' else 'tests/' + g}] {GROUPS[g]} — {len(ks)} 个")
            print("   " + ", ".join(ks))
    total = sum(len(v) for v in by_group.values())
    print(f"\n合计 {total} 个用例")

    if not args.apply:
        print("\n(空跑；加 --apply 执行迁移)")
        return 0

    # --- move ---
    moved = 0
    for g, ks in by_group.items():
        if g == "engine":
            d = ROOT / "tests" / "engine"
        else:
            d = ROOT / "tests" / g
        d.mkdir(parents=True, exist_ok=True)
        for k in ks:
            src = ROOT / "tests" / f"{k}.py"
            dst = d / f"{k}.py"
            if not src.exists():
                print(f"  !! missing {src}")
                continue
            subprocess.run(["git", "mv", str(src.relative_to(ROOT)),
                            str(dst.relative_to(ROOT))], cwd=ROOT, check=True)
            moved += 1
    print(f"moved {moved} files")

    # --- patch bootstraps ---
    GROUP_PATH_BLOCK = (
        '# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in\n'
        '# tests/, and cases import each other across groups — put every group\n'
        '# dir on the path.\n'
        'for _g in sorted((HERE / "tests").iterdir()):\n'
        '    if _g.is_dir() and not _g.name.startswith("__"):\n'
        '        sys.path.insert(0, str(_g))')
    OLD_LINE = 'sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))'

    patched = 0
    for g, ks in by_group.items():
        d = ROOT / "tests" / ("engine" if g == "engine" else g)
        for k in ks:
            p = d / f"{k}.py"
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8")
            orig = txt
            txt = txt.replace("Path(__file__).resolve().parent.parent",
                              "Path(__file__).resolve().parents[2]")
            if OLD_LINE in txt:
                txt = txt.replace(OLD_LINE, OLD_LINE + "\n" + GROUP_PATH_BLOCK)
            if txt != orig:
                p.write_text(txt, encoding="utf-8")
                patched += 1
    print(f"patched {patched} case files")

    # shared helpers stay in tests/ but import cases (m3_common -> m1/m2), so they
    # need the group dirs on the path as well
    shared_patched = 0
    for f in sorted((ROOT / "tests").glob("*.py")):
        if f.name not in SHARED:
            continue
        txt = f.read_text(encoding="utf-8")
        if OLD_LINE in txt and "for _g in sorted" not in txt:
            f.write_text(txt.replace(OLD_LINE, OLD_LINE + "\n" + GROUP_PATH_BLOCK),
                         encoding="utf-8")
            shared_patched += 1
    print(f"patched {shared_patched} shared modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
