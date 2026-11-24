"""Exploration for #271 (small perimeters) and #264/#272 (overhang bands). Kept output short.

    python -B explore_speeds.py
"""
import collections
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def topfeeds(g, name, lo=2):
    S = g["S"]
    f = an.feat(g, name)
    c = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f and S["L"][i] >= lo:
            c["%.2f" % S["fd"][i]] += 1
    return c


print("#271 run 301dcb07: max feeds")
r, b = gparse.load("301dcb07"), gparse.load("5994d5e6")
for name in ("Outer wall", "Inner wall", "Sparse infill", "Top surface", "Internal solid infill"):
    c = topfeeds(r, name)
    vals = sorted(float(k) for k in c)
    print("  %-20s n=%d min %.1f max %.1f | top: %s" % (name, sum(c.values()), vals[0], vals[-1],
          " ".join("%s x%d" % kv for kv in c.most_common(6))))
    print("  %-20s   moves within 3%% of: %s" % ("", " ".join(
        "F%d:%d" % (e, sum(v for k, v in c.items() if abs(float(k) - e) <= 0.03 * e)) for e in (6000, 9000, 12000, 7200, 11052))))

# small perimeters, closed loops only
def loop_table(g, tag):
    S = g["S"]
    closed_small = collections.Counter()
    closed_big = collections.Counter()
    open_small = collections.Counter()
    big3000 = []
    for layer in range(2, len(g["layers"]) + 1):
        for name in ("Outer wall", "Inner wall"):
            for ch in an.chains(g, layer, name):
                L = an.chain_len(g, ch)
                feeds = collections.Counter("%.0f" % S["fd"][i] for i in ch)
                main = feeds.most_common(1)[0][0]
                cl = an.chain_closed(g, ch, 0.06)
                if L < 10.0:
                    (closed_small if cl else open_small)[main] += 1
                elif cl:
                    closed_big[main] += 1
                    if main == "3000":
                        big3000.append((layer, name, round(L, 1), dict(feeds), cl))
    print("  [%s] CLOSED loops < 10 mm: %d, main feed %s" % (tag, sum(closed_small.values()), dict(closed_small.most_common(8))))
    print("  [%s] OPEN chains  < 10 mm: %d, main feed %s" % (tag, sum(open_small.values()), dict(open_small.most_common(8))))
    print("  [%s] CLOSED loops >= 10 mm: %d, main feed %s" % (tag, sum(closed_big.values()), dict(closed_big.most_common(10))))
    return big3000


big = loop_table(r, "run")
loop_table(b, "base")
print("  run closed loops >= 10 mm whose main feed is 3000: %d; examples %s" % (len(big), big[:14]))
# a baseline loop starting at the same point on the same layer: its feeds
Sb = b["S"]
import numpy as np
starts = {}
for layer in range(2, len(b["layers"]) + 1):
    for name in ("Outer wall", "Inner wall"):
        for ch in an.chains(b, layer, name):
            starts.setdefault((layer, name), []).append((round(Sb["x0"][ch[0]], 2), round(Sb["y0"][ch[0]], 2)), ch)
Sr = r["S"]
cmp_ = collections.Counter()
for layer, name, L, feeds, cl in big:
    key = (round(Sr["x0"][0], 2), 0)
    best = None
    for (sx, sy), ch in starts.get((layer, name), []):
        pass
# simpler: per layer compare the feed of the first move of each chain by matching start point
def chain_by_start(g):
    S = g["S"]
    d = {}
    for layer in range(2, len(g["layers"]) + 1):
        for name in ("Outer wall", "Inner wall"):
            for ch in an.chains(g, layer, name):
                d[(layer, name, round(S["x0"][ch[0]], 1), round(S["y0"][ch[0]], 1))] = ch
    return d
dr, db = chain_by_start(r), chain_by_start(b)
pairs = collections.Counter()
exs = []
for layer, name, L, feeds, cl in big:
    k = (layer, name, round(Sr["x0"][0], 1), 0)
    # find by any start point of the chain
    ch = None
    for (l2, n2, sx, sy), c2 in dr.items():
        pass
for key, ch in dr.items():
    if key in db:
        L = an.chain_len(r, ch)
        if L >= 10.0 and an.chain_closed(r, ch, 0.06):
            fr = collections.Counter("%.0f" % Sr["fd"][i] for i in ch)
            fb = collections.Counter("%.0f" % Sb["fd"][i] for i in db[key])
            mr, mb = fr.most_common(1)[0][0], fb.most_common(1)[0][0]
            pairs[(mr, mb)] += 1
print("  closed loops >= 10 mm matched by start point: (run main feed, base main feed) -> %s" % dict(pairs.most_common(16)))

# what is the layer-level wall speed (cooling cap) for a big loop at 3000?
print("\n#264 run cb8d8859: config keys with 'overhang'")
r2 = gparse.load("cb8d8859")
for k in sorted(r2["config"]):
    if "overhang" in k or "bridge" in k:
        print("   %-34s %s" % (k, r2["config"][k]))
S = r2["S"]
f_ow = an.feat(r2, "Outer wall")
f_ov = an.feat(r2, "Overhang wall")
# per layer: distinct OW feeds (rounded) and count, for a stretch of layers
print("  per-layer outer-wall feeds (run), layers 100..130:")
for layer in range(100, 131):
    c = collections.Counter("%.0f" % S["fd"][i] for i in an.idx(r2).get((layer, f_ow), []) if S["k"][i] == an.X)
    c2 = collections.Counter("%.0f" % S["fd"][i] for i in an.idx(r2).get((layer, f_ov), []) if S["k"][i] == an.X)
    print("   L%d OW %s | OvW %s" % (layer, " ".join("%s x%d" % kv for kv in sorted(c.items(), key=lambda kv: float(kv[0]))[:12]),
                                   " ".join("%s x%d" % kv for kv in c2.items())))
