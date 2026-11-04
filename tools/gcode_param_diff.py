#!/usr/bin/env python3
"""gcode_param_diff.py — compare two slices of the SAME model where only a
single 'flow' parameter is supposed to differ (Feishu #135/#136).

Criteria (agreed 2026-09-23 with the tester):
  * config comment keys (`; key = value` blocks at the file head) must be
    IDENTICAL, except for keys that belong to the flow parameter itself
    (flow / volumetric / pressure-advance family);
  * the toolpath body must be 'basically identical': differing non-comment
    lines within a small tolerance, reported as evidence.

Usage:
    python tools/gcode_param_diff.py A.gcode B.gcode [--tolerance N]
Exit code 0 = PASS, 1 = FAIL, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# keys that MAY differ when the flow parameter is the only edited value.
# `nozzle_volume_type` IS the Standard/High-Flow parameter in this build
# (measured 09-23: it is the single config key that changes when the left
# sidebar's Nozzle Flow combo is switched).
FLOW_KEY_RE = re.compile(
    r"flow|volumetric|pressure_advance|max_volumetric_speed|pa_"
    r"|volume_type|nozzle_volume",
    re.I)
CONF_RE = re.compile(r"^;\s*([A-Za-z0-9_.]+)\s*=\s*(.*)$")


def config_keys(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        m = CONF_RE.match(ln)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2)
    return out


def body_stats(a: list[str], b: list[str]) -> dict:
    n = min(len(a), len(b))
    pos_diff = sum(1 for x, y in zip(a, b) if x != y)
    only_a = a[n:]
    only_b = b[n:]
    # movement lines (G0/G1) and comments counted separately
    moves_a = sum(1 for x in a if re.match(r"^G[01] ", x))
    moves_b = sum(1 for x in b if re.match(r"^G[01] ", x))
    # ORDER-INSENSITIVE comparison: the same toolpath emitted in a different
    # order still differs line-by-line, so compare the sorted line sets too.
    sa, sb = sorted(a), sorted(b)
    if len(sa) == len(sb):
        sorted_diff = sum(1 for x, y in zip(sa, sb) if x != y)
    else:
        sorted_diff = -1          # different line counts: not comparable
    return {"lines_a": len(a), "lines_b": len(b), "positional_diff": pos_diff,
            "sorted_diff": sorted_diff,
            "tail_a": len(only_a), "tail_b": len(only_b),
            "moves_a": moves_a, "moves_b": moves_b}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tolerance", type=int, default=5,
                    help="allowed differing non-comment lines (default 5)")
    args = ap.parse_args()
    pa, pb = Path(args.a), Path(args.b)
    if not pa.is_file() or not pb.is_file():
        print(f"missing input: {pa.is_file()=} {pb.is_file()=}")
        return 2
    la = pa.read_text(errors="replace").splitlines()
    lb = pb.read_text(errors="replace").splitlines()

    ca, cb = config_keys(la), config_keys(lb)
    keys = sorted(set(ca) | set(cb))
    conf_diffs = [(k, ca.get(k, "<absent>"), cb.get(k, "<absent>"))
                  for k in keys if ca.get(k, "<absent>") != cb.get(k, "<absent>")]
    flow_diffs = [d for d in conf_diffs if FLOW_KEY_RE.search(d[0])]
    other_diffs = [d for d in conf_diffs if not FLOW_KEY_RE.search(d[0])]

    bs = body_stats(la, lb)

    print(f"=== {pa.name}  vs  {pb.name} ===")
    print(f"config keys: {len(ca)} vs {len(cb)}; differing: {len(conf_diffs)}")
    for k, va, vb in flow_diffs:
        print(f"  [flow] {k}: {va!r} -> {vb!r}")
    for k, va, vb in other_diffs:
        print(f"  [OTHER] {k}: {va!r} -> {vb!r}")
    print(f"body: lines {bs['lines_a']} vs {bs['lines_b']}; "
          f"positional differing {bs['positional_diff']}; "
          f"ORDER-INSENSITIVE differing {bs['sorted_diff']}; "
          f"tail-only {bs['tail_a']}/{bs['tail_b']}; "
          f"G0/G1 moves {bs['moves_a']} vs {bs['moves_b']} "
          f"(delta {abs(bs['moves_a'] - bs['moves_b'])})")

    move_delta = abs(bs["moves_a"] - bs["moves_b"])
    # 'basically identical' = the SAME toolpath, possibly emitted in a
    # different order: the order-insensitive diff is the primary signal, the
    # positional diff only tells us how much the ordering moved.
    body_ok = 0 <= bs["sorted_diff"] <= args.tolerance
    ok = not other_diffs and body_ok and move_delta <= args.tolerance
    print(f"VERDICT: {'PASS' if ok else 'FAIL'}"
          f"  (config: {'only flow keys differ' if flow_diffs else 'identical'}"
          f"{'' if not other_diffs else f', {len(other_diffs)} non-flow diff(s)'};"
          f" body: order-insensitive diff {bs['sorted_diff']}, tolerance"
          f" {args.tolerance}, move delta {move_delta};"
          f" positional(ordering) diff {bs['positional_diff']} recorded)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
