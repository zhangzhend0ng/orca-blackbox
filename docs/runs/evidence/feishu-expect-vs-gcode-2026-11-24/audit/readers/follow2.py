"""Follow-up checks 2: #281 Z gap / interface layers per column, #277/#282 support start & continuity,
#266 nested wall loops, #261 same-island travel crossing.

    python -B follow2.py
"""
import collections
import math
import os
import sys

import numpy as np
from shapely.geometry import LineString, Polygon, Point
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def layer_segments(g, L, feats=None):
    S = g["S"]
    rows = []
    for i in an.idx(g):
        pass
    for (l, f), ids in an.idx(g).items():
        if l != L:
            continue
        name = g["feat_names"][f]
        if feats is not None and name not in feats:
            continue
        for i in ids:
            if S["k"][i] == an.X:
                rows.append((S["x0"][i], S["y0"][i], S["x1"][i], S["y1"][i]))
    return np.array(rows, dtype=float) if rows else np.zeros((0, 4))


print("#281 support interface: Z gap and interface layers per column")
r = gparse.load("99f34ea9")
S = r["S"]
fi = an.feat(r, "Support interface")
tops = []
for L in range(1, len(r["layers"]) + 1):
    seg = an.segs_of(r, L, ["Support interface"])
    if len(seg) and len(an.segs_of(r, L + 1, ["Support interface"])) == 0:
        tops.append(L)
gaps = collections.Counter()
nints = collections.Counter()
used = 0
for L in tops:
    seg = an.segs_of(r, L, ["Support interface"])
    d = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
    long_ = seg[d >= 2.5]
    if len(long_) == 0:
        continue
    for row in long_[:: max(1, len(long_) // 6)][:6]:
        p = np.array([[(row[0] + row[2]) / 2.0, (row[1] + row[3]) / 2.0]])
        used += 1
        first = None
        for m in range(L + 1, min(L + 6, len(r["layers"]) + 1)):
            mod = layer_segments(r, m)
            if len(mod) and an.point_seg_dist(p, mod)[0] < 0.12:
                first = m
                break
        if first is None:
            gaps["no model above within 5 layers"] += 1
        else:
            zi, zm, hm = r["layers"][L - 1]["z"], r["layers"][first - 1]["z"], r["layers"][first - 1]["height"]
            gaps["model %d layer(s) above, gap %.2f" % (first - L, zm - hm - zi)] += 1
        n = 0
        for j in range(0, 12):
            segs = an.segs_of(r, L - j, ["Support interface"])
            if len(segs) and an.point_seg_dist(p, segs)[0] < 0.3:
                n += 1
            else:
                break
        nints["%d" % n] += 1
print("  top-interface layers: %d; sample points: %d" % (len(tops), used))
print("  model above the top interface (gap = model bottom - interface top Z): %s" % dict(gaps.most_common()))
print("  consecutive interface layers under the top, at the same XY: %s" % dict(sorted(nints.items(), key=lambda kv: int(kv[0]))))
# what is directly above at L+1 : support? nothing?
above = collections.Counter()
for L in tops:
    seg = an.segs_of(r, L, ["Support interface"])
    d = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
    long_ = seg[d >= 2.5]
    if len(long_) == 0:
        continue
    for row in long_[:: max(1, len(long_) // 6)][:6]:
        p = np.array([[(row[0] + row[2]) / 2.0, (row[1] + row[3]) / 2.0]])
        for m in (L + 1, L + 2):
            for name in ("Support", "Support interface"):
                s2 = an.segs_of(r, m, [name])
                if len(s2) and an.point_seg_dist(p, s2)[0] < 0.3:
                    above["L+%d has %s" % (m - L, name)] += 1
print("  support still present directly above the top interface: %s" % dict(above))

print("\n#277 normal support: where it starts")
r = gparse.load("06c69298")
S = r["S"]
fs, fi = an.feat(r, "Support"), an.feat(r, "Support interface")
sup_lay = sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] in (fs, fi)))
print("  support layers %d..%d (%d layers); model layers %d; support Z %.2f..%.2f" % (
    sup_lay[0], sup_lay[-1], len(sup_lay), len(r["layers"]), r["layers"][sup_lay[0] - 1]["z"], r["layers"][sup_lay[-1] - 1]["z"]))
start_far = collections.Counter()
for L in sup_lay:
    cur = an.segs_of(r, L, ["Support", "Support interface"])
    if L == 1:
        continue
    below = an.segs_of(r, L - 1, ["Support", "Support interface"])
    if len(below) == 0:
        start_far[L] = int(len(cur))
        continue
    mids = (cur[:, :2] + cur[:, 2:]) / 2.0
    dd = an.point_seg_dist(mids, below)
    n_new = int((dd > 2.0).sum())
    if n_new:
        start_far[L] = n_new
on_bed = [L for L in sup_lay if L == 1]
print("  layers where support appears with NO support at all on the layer below: %s" % [L for L in start_far if L not in sup_lay or (L - 1) not in sup_lay])
print("  layers with support segments > 2 mm away from any support of the layer below (count of such segments): %s" % sorted(start_far.items())[:14])
# support direction / pattern on a mid layer
for L in (100, 200):
    seg = an.segs_of(r, L, ["Support"])
    d = seg[:, 2:] - seg[:, :2]
    ang = collections.Counter()
    for (dx, dy) in d:
        a = int(round((math.degrees(math.atan2(dy, dx)) % 180.0) / 5.0)) * 5 % 180
        ang[a] += math.hypot(dx, dy)
    tot = sum(ang.values())
    print("  support body direction (layer %d, by length): %s ; interface layers: %s" % (
        L, " ".join("%d:%.0f%%" % (a, 100 * v / tot) for a, v in ang.most_common(4)),
        L in set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)))
# does support sit under every overhang (Overhang wall present but no support below within 2 layers)?
miss = tot = 0
for L in range(2, len(r["layers"])):
    ov = an.segs_of(r, L, ["Overhang wall"])
    if len(ov) == 0:
        continue
    mids = (ov[:, :2] + ov[:, 2:]) / 2.0
    found = np.zeros(len(mids), dtype=bool)
    for m in (L - 1, L - 2):
        for name in ("Support", "Support interface"):
            s2 = an.segs_of(r, m, [name])
            if len(s2):
                found |= an.point_seg_dist(mids, s2) < 1.2
    tot += len(mids)
    miss += int((~found).sum())
print("  overhang-wall segments (100%%-overhang walls) with support within 1.2 mm on the 1-2 layers below: %d of %d (without: %d)" % (tot - miss, tot, miss))

print("\n#282 tree support: continuity, layer heights, width")
r = gparse.load("c4eb7a29")
S = r["S"]
fs, fi = an.feat(r, "Support"), an.feat(r, "Support interface")
sup_lay = sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] in (fs, fi)))
print("  support layers %d..%d (%d); heights used on those layers: %s" % (
    sup_lay[0], sup_lay[-1], len(sup_lay), dict(collections.Counter("%.3g" % r["layers"][L - 1]["height"] for L in sup_lay).most_common(5))))
breaks = collections.Counter()
for L in sup_lay[1:]:
    if (L - 1) in sup_lay:
        continue
    breaks[L] += 1
print("  gaps in the support layer sequence (a support layer whose previous layer has none): %s" % sorted(breaks.items())[:10])
# continuity: share of support segments on layer L that have support below within 1.2 mm
tot = ok = 0
for L in sup_lay[5::7]:
    cur = an.segs_of(r, L, ["Support", "Support interface"])
    below = an.segs_of(r, L - 1, ["Support", "Support interface"])
    if len(below) == 0:
        continue
    mids = (cur[:, :2] + cur[:, 2:]) / 2.0
    d = an.point_seg_dist(mids, below)
    tot += len(mids)
    ok += int((d < 1.2).sum())
print("  support segments with support within 1.2 mm on the layer below (sampled layers): %d of %d = %.1f%%" % (ok, tot, 100.0 * ok / max(tot, 1)))
# lateral drift per layer of branch tips: centroid of small support chains between consecutive layers
drifts = []
prev = None
for L in sup_lay[::10]:
    ch = an.chains(r, L, "Support")
    cents = [np.array([(S["x0"][c[0]] + S["x1"][c[-1]]) / 2.0, (S["y0"][c[0]] + S["y1"][c[-1]]) / 2.0]) for c in ch if an.chain_len(r, c) < 6.0]
    if prev is not None and cents and prev:
        A, B = np.array(cents), np.array(prev)
        dd = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(axis=2))
        drifts += list(dd.min(axis=1))
    prev = cents
drifts = np.array(drifts)
print("  nearest branch-centre displacement between sampled layers (10 layers apart = 2.0 mm in Z): median %.3f, p95 %.3f, max %.3f; tan(40)=%0.3f per mm" % (
    float(np.median(drifts)), float(np.percentile(drifts, 95)), drifts.max(), math.tan(math.radians(40))))
ws = collections.Counter("%.2f" % S["w"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fs)
seg = sorted(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fs)
print("  support move lengths: median %.3f; ;WIDTH: values %s; support E/mm %.5f" % (
    seg[len(seg) // 2], ws.most_common(4), sum(S["e"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fs) / sum(seg)))
# width of branches: typical spacing between the two sides of a branch (distance from a support midpoint to the nearest non-collinear support segment)
for L in (60, 150, 300, 450):
    cur = an.segs_of(r, L, ["Support"])
    if len(cur) < 2:
        continue
    mids = (cur[:, :2] + cur[:, 2:]) / 2.0
    sp = an.spacing_parallel(cur)
    sp = np.array(sp)
    print("  layer %d: %d support moves; across-branch nearest distance median %.3f p10 %.3f p90 %.3f" % (
        L, len(cur), float(np.median(sp)), float(np.percentile(sp, 10)), float(np.percentile(sp, 90))) if len(sp) else "  layer %d: no spacing" % L)
bl = an.segs_of(r, 0, ["Bridge"])
print("  Bridge blocks %d; longest bridge move %.1f mm (span > 30 mm would need support)" % (
    r["types"].get("Bridge", 0), max(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(r, "Bridge"))))

print("\n#266 nested wall loops per outer loop (shapely)")
r, b = gparse.load("1ffdefee"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    depth = collections.Counter()
    maxd = 0
    ex = None
    for L in range(3, len(g["layers"]), 2):
        outers = []
        for ch in an.chains(g, L, "Outer wall"):
            if an.chain_len(g, ch) < 4.0 or not an.chain_closed(g, ch, 0.12):
                continue
            try:
                poly = Polygon(an.pts(g, ch))
                if poly.is_valid and poly.area > 3.0:
                    outers.append(poly)
            except Exception:
                pass
        if not outers:
            continue
        tree = STRtree(outers)
        for ch in an.chains(g, L, "Inner wall"):
            if an.chain_len(g, ch) < 2.0:
                continue
            p = Point((S["x0"][ch[0]] + S["x1"][ch[0]]) / 2.0, (S["y0"][ch[0]] + S["y1"][ch[0]]) / 2.0)
            hits = [j for j in tree.query(p) if outers[j].contains(p)]
            if not hits:
                continue
            # the innermost containing outer loop = smallest area
            poly = min((outers[j] for j in hits), key=lambda q: q.area)
            # depth = number of inner-wall loops around p: nest by containment among chains in the same outer loop
            d = 0
            for ch2 in an.chains(g, L, "Inner wall"):
                if an.chain_len(g, ch2) < 2.0 or not an.chain_closed(g, ch2, 0.12):
                    continue
                try:
                    q = Polygon(an.pts(g, ch2))
                except Exception:
                    continue
                if q.is_valid and q.area < poly.area and q.contains(p) and (poly.area - q.area) > 1e-6:
                    d += 1
            depth[d] += 1
            if d > maxd:
                maxd = d
                ex = (L, round(poly.area, 1))
    print("  [%s] inner-wall loops by how many further inner-wall loops enclose them (0 = innermost): %s ; max %d at %s" % (tag, dict(sorted(depth.items())), maxd, ex))

print("\n#261 same-island travel crossing")
r, b = gparse.load("bdf3dd93"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    same = cross_same = 0
    for L in range(2, len(g["layers"]), 2):
        polys = []
        for ch in an.chains(g, L, "Outer wall"):
            if an.chain_len(g, ch) >= 2.0 and an.chain_closed(g, ch, 0.12):
                try:
                    p = Polygon(an.pts(g, ch))
                    if p.is_valid:
                        polys.append(p)
                except Exception:
                    pass
        if not polys:
            continue
        tree = STRtree(polys)
        ow = an.segs_of(g, L, ["Outer wall"])
        A, B = ow[:, :2], ow[:, 2:]
        for tch in travel_chains(g, L) if False else []:
            pass
    print("  [%s] (see follow3)" % tag)
