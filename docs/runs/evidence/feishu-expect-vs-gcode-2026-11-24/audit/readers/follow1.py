"""Follow-up checks: #261 travel crossing, #256 wipe moves, #266 loops per layer, #295 inner-wall Hausdorff,
#280 outer-wall geometry, #281 per-column interface layers and Z gap.

    python -B follow1.py
"""
import collections
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def ccw(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def travel_chains(g, layer):
    """travel chains of one layer: each = list of move indices (TRAVEL moves; Z-only and F-only skipped)."""
    S = g["S"]
    res, cur = [], []
    for i in range(len(S["k"])):
        L = S["L"][i]
        if L < layer:
            continue
        if L > layer:
            break
        k = S["k"][i]
        if k == an.TRAVEL:
            cur.append(i)
        elif k in (an.ZONLY, an.FONLY):
            continue
        else:
            if cur:
                res.append(cur)
            cur = []
    if cur:
        res.append(cur)
    return res


def crossing_stats(g, step):
    S = g["S"]
    n_ch = n_cross = n_detour = 0
    excess = []
    cross_len = []
    for layer in range(2, len(g["layers"]) + 1, step):
        ow = an.segs_of(g, layer, ["Outer wall"])
        if len(ow) == 0:
            continue
        A, B = ow[:, :2], ow[:, 2:]
        for ch in travel_chains(g, layer):
            pts_ = [(S["x0"][i], S["y0"][i]) for i in ch] + [(S["x1"][ch[-1]], S["y1"][ch[-1]])]
            path = sum(math.hypot(pts_[j + 1][0] - pts_[j][0], pts_[j + 1][1] - pts_[j][1]) for j in range(len(pts_) - 1))
            straight = math.hypot(pts_[-1][0] - pts_[0][0], pts_[-1][1] - pts_[0][1])
            if path < 1.0:
                continue
            n_ch += 1
            hit = False
            for j in range(len(pts_) - 1):
                p, q = pts_[j], pts_[j + 1]
                d1 = ccw(p[0], p[1], q[0], q[1], A[:, 0], A[:, 1])
                d2 = ccw(p[0], p[1], q[0], q[1], B[:, 0], B[:, 1])
                d3 = ccw(A[:, 0], A[:, 1], B[:, 0], B[:, 1], p[0], p[1])
                d4 = ccw(A[:, 0], A[:, 1], B[:, 0], B[:, 1], q[0], q[1])
                if ((((d1 > 1e-9) != (d2 > 1e-9)) & ((d3 > 1e-9) != (d4 > 1e-9)) & (np.abs(d1) > 1e-9) & (np.abs(d2) > 1e-9)
                     & (np.abs(d3) > 1e-9) & (np.abs(d4) > 1e-9))).any():
                    hit = True
                    break
            if hit:
                n_cross += 1
                cross_len.append(path)
            if path - straight > 0.3:
                n_detour += 1
                excess.append((path - straight, path, layer))
    ex = sorted(e[0] for e in excess)
    big = sorted(excess, key=lambda e: -e[0])[:6]
    return (n_ch, n_cross, n_detour, (ex[len(ex) // 2] if ex else 0), (ex[int(len(ex) * .95)] if ex else 0), (ex[-1] if ex else 0),
            sum(1 for e in ex if e > 2.2), big)


print("#261 travel crossing (chains >= 1 mm, layers >= 2)")
r, b = gparse.load("bdf3dd93"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    res = crossing_stats(g, 2)
    print("  [%s] chains %d; straight path crossing an outer wall of the layer: %d; detoured (>0.3 mm longer than straight): %d; excess median %.2f p95 %.2f max %.2f; >2.2 mm: %d" % (
        (tag,) + res[:7]))
    print("       largest detours (excess, path, layer): %s" % [(round(e, 2), round(p, 2), l) for e, p, l in res[7]])
    S = g["S"]
    tl = sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.TRAVEL and S["L"][i] >= 2)
    print("       total XY travel length on layers >= 2: %.0f mm; travel moves %d" % (
        tl, sum(1 for i in range(len(S["k"])) if S["k"][i] == an.TRAVEL and S["L"][i] >= 2)))
for L in (228, 232, 236, 239, 240):
    for tag, g in (("run", r), ("base", b)):
        S = g["S"]
        row = []
        for name in ("Outer wall", "Inner wall", "Gap infill", "Sparse infill", "Internal solid infill", "Top surface"):
            f = an.feat(g, name)
            mv = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f]
            row.append("%s: %d chains %.0f mm" % (name[:6], len(an.chains(g, L, name)), sum(an.seg_len(S, i) for i in mv)))
        print("  L%d %s: %s" % (L, tag, " | ".join(row)))
print("  paths run vs base:", {n: "%d vs %d" % (sum(1 for i in range(len(r["S"]["k"])) if r["S"]["k"][i] == an.X and r["S"]["F"][i] == an.feat(r, n)),
                                                 sum(1 for i in range(len(b["S"]["k"])) if b["S"]["k"][i] == an.X and b["S"]["F"][i] == an.feat(b, n)))
                               for n in ("Outer wall", "Inner wall", "Gap infill", "Sparse infill", "Internal solid infill", "Top surface", "Bottom surface")})

print("\n#256 wipe-on-loop moves")
r, b = gparse.load("fd0abb31"), gparse.load("818ecfc6")
S, Sb = r["S"], b["S"]
for tag, SS in (("run", S), ("base", Sb)):
    tr = collections.Counter()
    for i in range(len(SS["k"])):
        if SS["k"][i] == an.TRAVEL and SS["L"][i] >= 2 and SS["fd"][i] < 20000:
            tr["%.0f" % SS["fd"][i]] += 1
    print("  [%s] non-extruding XY moves on layers>=2 slower than F20000: %s" % (tag, dict(sorted(tr.items(), key=lambda kv: float(kv[0])))))
idx = [i for i in range(len(S["k"])) if S["k"][i] == an.TRAVEL and S["L"][i] >= 2 and S["fd"][i] < 20000]
lens = [an.seg_len(S, i) for i in idx]
print("  run: %d such moves; length min %.3f median %.3f max %.3f; feeds mm/s: %s" % (
    len(idx), min(lens), sorted(lens)[len(lens) // 2], max(lens), sorted(set(round(S["fd"][i] / 60, 2) for i in idx))[:8]))
i0 = idx[3]
print("  context (run):")
for j in range(i0 - 4, i0 + 4):
    print("     L%d %-14s %s x%.3f y%.3f -> x%.3f y%.3f E%.5f F%.0f" % (
        S["L"][j], r["feat_names"][S["F"][j]] if S["F"][j] is not None else "-", "k%d" % S["k"][j], S["x0"][j], S["y0"][j], S["x1"][j], S["y1"][j], S["e"][j], S["fd"][j]))
# wall feed on those layers vs the wipe feed
wall = collections.Counter("%.1f" % S["fd"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(r, "Outer wall") and S["L"][i] >= 2)
print("  outer-wall extruding feeds (mm/s) run: %s" % sorted(set(round(float(k) / 60, 2) for k in wall))[:10])

print("\n#266 loops per layer")
r, b = gparse.load("1ffdefee"), gparse.load("5994d5e6")
for L in (100, 110, 120, 130, 140, 150):
    for tag, g in (("run", r), ("base", b)):
        print("  L%d %s OW chains %s | IW chains %s" % (
            L, tag, [round(an.chain_len(g, c), 1) for c in an.chains(g, L, "Outer wall")][:8],
            [round(an.chain_len(g, c), 1) for c in an.chains(g, L, "Inner wall")][:14]))
S = r["S"]
op = []
for L in range(2, len(r["layers"]) + 1):
    for name in ("Outer wall", "Inner wall"):
        for ch in an.chains(r, L, name):
            ln = an.chain_len(r, ch)
            if ln > 2.0 and not an.chain_closed(r, ch, 0.12):
                gap = math.hypot(S["x1"][ch[-1]] - S["x0"][ch[0]], S["y1"][ch[-1]] - S["y0"][ch[0]])
                op.append((name[:2], round(ln, 1), round(gap, 3)))
c = collections.Counter("open" if o[2] > 0.5 else "gap<=0.5" for o in op)
print("  run open wall chains > 2 mm: %d; by end-to-start distance: %s; sample %s" % (len(op), dict(c), op[:12]))
print("  gap infill moves: run %d base %d" % (sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(r, "Gap infill")),
                                          sum(1 for i in range(len(b["S"]["k"])) if b["S"]["k"][i] == an.X and b["S"]["F"][i] == an.feat(b, "Gap infill"))))

print("\n#295 inner wall Hausdorff (run vs base)")
r, b = gparse.load("d3191da6"), gparse.load("71c5f8fc")
S, Sb = r["S"], b["S"]
d1, d2 = [], []
for L in range(2, 101, 4):
    A = an.segs_of(r, L, ["Inner wall"])
    B = an.segs_of(b, L, ["Inner wall"])
    if len(A) == 0 or len(B) == 0:
        continue
    pa = np.vstack([A[:, :2], A[:, 2:]])
    pb = np.vstack([B[:, :2], B[:, 2:]])
    d1.append(an.point_seg_dist(pa, B))
    d2.append(an.point_seg_dist(pb, A))
d = np.concatenate(d1 + d2)
print("  vertex-to-other-path distance of inner walls: max %.4f p99 %.4f" % (d.max(), float(np.percentile(d, 99))))

print("\n#280 outer-wall geometry run vs base")
r, b = gparse.load("f366c4c9"), gparse.load("0cccce4a")


def segset(g, name):
    S = g["S"]
    f = an.feat(g, name)
    c = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f:
            a = (round(S["x0"][i], 3), round(S["y0"][i], 3))
            bb = (round(S["x1"][i], 3), round(S["y1"][i], 3))
            c[(S["L"][i],) + min(a, bb) + max(a, bb)] += 1
    return c


for name in ("Outer wall", "Inner wall", "Top surface", "Internal solid infill", "Sparse infill", "Bridge"):
    A, B = segset(r, name), segset(b, name)
    print("  %-20s segments %d vs %d, only-in-run %d, only-in-base %d" % (name, sum(A.values()), sum(B.values()), sum((A - B).values()), sum((B - A).values())))

print("\n#281 per-column interface layers and Z gap")
r = gparse.load("99f34ea9")
S = r["S"]
fi, fs = an.feat(r, "Support interface"), an.feat(r, "Support")
sup_lay = sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] in (fi, fs)))
model = collections.defaultdict(list)
for i in range(len(S["k"])):
    if S["k"][i] == an.X and S["F"][i] not in (fi, fs):
        model[S["L"][i]].append((S["x0"][i], S["y0"][i], S["x1"][i], S["y1"][i]))
# columns: on each layer, cluster support start points on a coarse 8 mm grid; follow each cell up
starts_above = []
for L in sup_lay[1:]:
    below = an.segs_of(r, L - 1, ["Support", "Support interface"]) if L > 1 else np.zeros((0, 4))
    cur = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == fs]
    if not cur or len(below) == 0:
        continue
    # support body chunks (chains) whose start is > 1.2 mm away from any support of the layer below -> starts on the model
    pts_ = np.array([(S["x0"][i], S["y0"][i]) for i in cur])
    ends = np.vstack([below[:, :2], below[:, 2:]])
    far = []
    for p in pts_:
        dd = an.point_seg_dist(p[None, :], below)[0]
        if dd > 1.5:
            far.append(p)
    if far:
        starts_above.append((L, len(far)))
print("  layers >=2 where a support body move starts > 1.5 mm from every support line of the layer below: %d; sample (layer, moves): %s" % (
    len(starts_above), starts_above[:10]))
# top-interface columns: for each layer L with interface and no interface at L+1: first model layer above within 3 mm of that interface
gaps = collections.Counter()
nl = collections.Counter()
for L in sup_lay:
    i_ids = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == fi]
    if not i_ids:
        continue
    ni = 0
    M = L
    while M in sup_lay and any(S["k"][i] == an.X and S["L"][i] == M and S["F"][i] == fi for i in an.idx(r).get((M, fi), [])):
        ni += 1
        M += 1
    seg = np.array([(S["x0"][i], S["y0"][i], S["x1"][i], S["y1"][i]) for i in i_ids])
    # model segments within 2.5 mm horizontally of this interface, in layers L+1 .. L+4
    found = None
    for m in range(L + 1, L + 5):
        if not model.get(m):
            continue
        mm = np.array(model[m])
        ends = np.vstack([seg[:, :2], seg[:, 2:]])
        d = an.point_seg_dist(ends, mm)
        if (d < 1.0).any():
            found = m
            break
    if found:
        zi = r["layers"][L - 1]["z"]
        zm = r["layers"][found - 1]["z"]
        hm = r["layers"][found - 1]["height"]
        gaps["%d layers above, gap %.2f" % (found - L, zm - hm - zi)] += 1
        nl["%d" % ni] += 1
print("  per interface-top layer: model layer found above and its Z gap: %s" % dict(gaps))
print("  interface layers stacked at those tops: %s" % dict(nl))
