"""Exploration 3 for #271: shape of the loops that run at F3000.

    python -B explore_speeds3.py
"""
import collections
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402

r, b = gparse.load("301dcb07"), gparse.load("5994d5e6")
Sr, Sb = r["S"], b["S"]


def chain_by_start(g):
    S = g["S"]
    d = {}
    for layer in range(2, len(g["layers"]) + 1):
        for name in ("Outer wall", "Inner wall"):
            for ch in an.chains(g, layer, name):
                d[(layer, name, round(S["x0"][ch[0]], 1), round(S["y0"][ch[0]], 1))] = ch
    return d


dr, db = chain_by_start(r), chain_by_start(b)
# every closed loop in the run: length, main feed; boundary of the 3000 zone
rows = []
for key, ch in dr.items():
    if an.chain_closed(r, ch, 0.06):
        L = an.chain_len(r, ch)
        mf = float(collections.Counter("%.0f" % Sr["fd"][i] for i in ch).most_common(1)[0][0])
        mb = float(collections.Counter("%.0f" % Sb["fd"][i] for i in db[key]).most_common(1)[0][0]) if key in db else None
        xs = [Sr["x0"][i] for i in ch] + [Sr["x1"][ch[-1]]]
        ys = [Sr["y0"][i] for i in ch] + [Sr["y1"][ch[-1]]]
        rows.append((L, mf, mb, key[1], len(ch), max(xs) - min(xs), max(ys) - min(ys), key[0]))
rows.sort()
print("closed loops (run) sorted by perimeter: L, run feed, base feed, feature, moves, bbox w, bbox h, layer")
for lo, hi in ((9.0, 12.0), (12.0, 16.0), (16.0, 25.0), (25.0, 70.0), (70.0, 200.0), (200.0, 2000.0)):
    sub = [x for x in rows if lo <= x[0] < hi]
    c = collections.Counter(x[1] for x in sub)
    print("  L in [%g,%g): %d loops; run main feed %s" % (lo, hi, len(sub), dict(c.most_common(8))))
print("  detail 9..16 mm:")
for x in rows:
    if 9.0 <= x[0] < 16.0:
        print("    L=%.2f run %4.0f base %s %s moves %d bbox %.1fx%.1f layer %d" % x)
# how many loops < 10 mm are NOT at 3000 and why (their feed vs the same loop in base)
print("  loops < 10 mm not at 3000:")
for x in rows:
    if x[0] < 10.0 and x[1] != 3000:
        print("    L=%.2f run %4.0f base %s %s moves %d layer %d" % (x[0], x[1], x[2], x[3], x[4], x[7]))
