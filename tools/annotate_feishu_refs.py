#!/usr/bin/env python3
"""Annotate case scripts with their Feishu baseline record refs.

Inserts a structured header line (idempotent):

    # feishu: baseline#164 baseline#156 baseline#152

Source of truth for the refs is FEISHU_BASELINE.md (record # -> 处置/映射 ->
case names); records it maps to no case are simply absent. Cases with no
baseline mapping get `# feishu: none` so the checker can tell "declared
unmapped" from "forgot to annotate".

Usage:
    python tools/annotate_feishu_refs.py            # dry run
    python tools/annotate_feishu_refs.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\code\orca_blackbox")
sys.path.insert(0, str(ROOT))
import cases  # noqa: E402

REF_RE = re.compile(r"^#\s*feishu:\s*(.+)$")


def build_refs():
    """case -> sorted [record numbers] from FEISHU_BASELINE.md."""
    refs: dict[str, list[str]] = {}
    for line in (ROOT / "FEISHU_BASELINE.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 5 or not c[0].isdigit():
            continue
        num, disp, note = c[0], c[3], c[4]
        for name in re.findall(r"\b(m\d+[a-z0-9]*)\b", disp + " " + note):
            key = name if name in cases.CASES else next(
                (k for k in cases.CASES if k.startswith(name + "_")), None)
            if not key:
                continue
            refs.setdefault(key, [])
            if num not in refs[key]:
                refs[key].append(num)
    return {k: sorted(v, key=int) for k, v in refs.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    refs = build_refs()
    changed = skipped = 0
    for key in cases.CASES:
        path = cases.case_path(key)
        if not path or not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if any(REF_RE.match(ln.strip()) for ln in lines[:8]):
            skipped += 1
            continue
        nums = refs.get(key, [])
        ann = ("# feishu: " + " ".join(f"baseline#{n}" for n in nums)) if nums \
            else "# feishu: none  (无基线表映射)"
        # insert right after the "— Feishu ..." / title comment line (line 2)
        insert_at = 2 if len(lines) > 2 else len(lines)
        lines.insert(insert_at, ann + "\n")
        if args.apply:
            path.write_text("".join(lines), encoding="utf-8")
        changed += 1
    print(f"annotated {changed} files, skipped {skipped} (already annotated)")
    print(f"refs found for {len(refs)} cases; "
          f"{len([k for k in cases.CASES if k not in refs])} cases have no baseline mapping")
    if not args.apply:
        print("(dry run — pass --apply)")


if __name__ == "__main__":
    main()
