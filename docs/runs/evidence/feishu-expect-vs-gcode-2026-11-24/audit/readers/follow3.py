"""Follow-up checks 3: #266 wall lines crossed inward, #261 same-island travel crossing, #282 branch drift / width,
#277 unsupported overhang walls.

    python -B follow3.py
"""
import collections
import math
import os
import sys

import numpy as np
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def ow_polys(g, L, min_area=2.0, min_len=4.0):
    S = g["S"]
    out = []
    for ch in an.chains(g, L, "Outer wall"):
        if an.chain_len(g, ch) >= min_len and an.chain_closed(g, ch, 0.12):
            try:
                p = Polygon(an.pts(g, ch))
                if p.is_valid and p.area >= min_area:
                    out.append(p)
            except Exception:
                pass
    return out


print("#266 inner wall lines crossed when walking 2.6 mm inward from the longest outer-wall edge")
r, b = gparse.load("1ffdefee"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    res = collections.Counter()
    for L in range(3, len(g["layers"]), 2):
        polys = ow_polys(g, L, 8.0)
        if not polys:
            continue
        iw = an.segs_of(g, L, ["Inner wall"])
        if len(iw) == 0:
            continue
        for poly in polys:
            ring = np.array(poly.exterior.coords)
            # longest edge (in G-code resolution ~0.2 mm the edges are short): use the polygon's straight skeleton-free proxy:
            # take the point on the boundary farthest from the centroid's opposite... simpler: sample boundary points, walk toward the centroid
            c = np.array(poly.centroid.coords[0])
            for t in (0.25, 0.5, 0.75):
                p0 = np.array(poly.exterior.interpolate(t, normalized=True).coords[0])
                d = c - p0
                n = np.linalg.norm(d)
                if n < 2.6:
                    continue
                u = d / n
                walk = p0[None, :] + u[None, :] * np.arange(0.3, 2.61, 0.02)[:, None]
                inside = np.array([poly.contains(Point(q)) for q in walk])
                if not inside.all():
                    continue
                dd = an.point_seg_dist(walk, iw)
                hit = dd < 0.06
                n_lines = 0
                prev = False
                for h in hit:
                    if h and not prev:
                        n_lines += 1
                    prev = h
                res[n_lines] += 1
    print("  [%s] inner wall lines crossed (total loops = lines + 1): %s" % (tag, dict(sorted(res.items()))))


def travel_chains(g, layer):
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


def ccw(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


print("\n#261 travel chains whose start and end lie inside the same outer-wall loop")
r, b = gparse.load("bdf3dd93"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    same = cross = det = 0
    for L in range(2, len(g["layers"]), 2):
        polys = ow_polys(g, L, 1.0, 2.0)
        if not polys:
            continue
        tree = STRtree(polys)
        ow = an.segs_of(g, L, ["Outer wall"])
        A, B = ow[:, :2], ow[:, 2:]
        for ch in travel_chains(g, L):
            pts_ = [(S["x0"][i], S["y0"][i]) for i in ch] + [(S["x1"][ch[-1]], S["y1"][ch[-1]])]
            if len(pts_) < 3:
                continue
            path = sum(math.hypot(pts_[j + 1][0] - pts_[j][0], pts_[j + 1][1] - pts_[j][1]) for j in range(len(pts_) - 1))
            if path < 0.5:
                continue
            ps, pe = Point(pts_[0]), Point(pts_[-1])

            def smallest(p):
                hits = [j for j in tree.query(p) if polys[j].contains(p)]
                return min((polys[j] for j in hits), key=lambda q: q.area) if hits else None
            a, bb = smallest(ps), smallest(pe)
            if a is None or bb is None or a is not bb:
                continue
            same += 1
            straight = math.hypot(pts_[-1][0] - pts_[0][0], pts_[-1][1] - pts_[0][1])
            if path - straight > 0.3:
                det += 1
            p, q = pts_[0], pts_[-1]
            d1 = ccw(p[0], p[1], q[0], q[1], A[:, 0], A[:, 1])
            d2 = ccw(p[0], p[1], q[0], q[1], B[:, 0], B[:, 1])
            d3 = ccw(A[:, 0], A[:, 1], B[:, 0], B[:, 1], p[0], p[1])
            d4 = ccw(A[:, 0], A[:, 1], B[:, 0], B[:, 1], q[0], q[1])
            if ((((d1 > 1e-9) != (d2 > 1e-9)) & ((d3 > 1e-9) != (d4 > 1e-9)))).any():
                cross += 1
    print("  [%s] chains inside one loop: %d; of which the straight line crosses an outer wall: %d; detoured (path > straight + 0.3): %d" % (tag, same, cross, det))

print("\n#282 tree support: lateral growth per layer and branch width")
r = gparse.load("c4eb7a29")
S = r["S"]
mx = []
p95 = []
for L in range(3, 503, 4):
    cur = an.segs_of(r, L, ["Support", "Support interface"])
    below = an.segs_of(r, L - 1, ["Support", "Support interface"])
    if len(cur) == 0 or len(below) == 0:
        continue
    mids = (cur[:, :2] + cur[:, 2:]) / 2.0
    d = an.point_seg_dist(mids, below)
    if (d > 0.6).sum() >= 5:
        mx.append(float((d > 0.6).max()))
        p95.append(float(np.percentile(d[d > 0.6], 95)))
print("  lateral offset of a layer's support lines to the nearest support line of the layer below (0.2 mm lower), layers with new growth: %d" % len(mx))
print("  per-layer max: median %.3f p90 %.3f max %.3f | p95 within layer: median %.3f max %.3f ; tan(40)*0.2 = %.3f, tan(45)*0.2 = %.3f, tan(30)*0.2 = %.3f" % (
    float(np.median(mx)), float(np.percentile(mx, 90)), max(mx), float(np.median(p95)), max(p95), math.tan(math.radians(40)) * 0.2, 0.2, math.tan(math.radians(30)) * 0.2))
wid = []
for L in (80, 160, 240, 320, 400, 480):
    for ch in an.chains(r, L, "Support"):
        if an.chain_len(r, ch) < 1.5 or not an.chain_closed(r, ch, 0.3):
            continue
        try:
            p = Polygon(an.pts(r, ch))
            if p.is_valid and p.area > 0.2:
                wid.append(2.0 * p.area / p.length)
        except Exception:
            pass
wid = np.array(wid)
print("  equivalent width (2*area/perimeter) of closed support loops on sampled layers: n=%d min %.2f p10 %.2f median %.2f p90 %.2f max %.2f" % (
    len(wid), wid.min(), float(np.percentile(wid, 10)), float(np.median(wid)), float(np.percentile(wid, 90)), wid.max()))
tip = []
for L in range(5, 500, 3):
    seg = an.segs_of(r, L, ["Support"])
    below = an.segs_of(r, L - 1, ["Support", "Support interface"])
    if len(below) == 0:
        continue
    mids = (seg[:, :2] + seg[:, 2:]) / 2.0
    d = an.point_seg_dist(mids, below)
    new = seg[d > 0.6]
    for row in new:
        tip.append(math.hypot(row[2] - row[0], row[3] - row[1]))
tip = np.array(tip)
if len(tip):
    print("  length of the support lines that start a new branch (no support below): n=%d median %.2f p90 %.2f max %.2f" % (len(tip), float(np.median(tip)), float(np.percentile(tip, 90)), tip.max()))
for k in ("support_type", "support_style", "tree_support_branch_angle", "tree_support_branch_angle_organic", "tree_support_branch_diameter",
          "tree_support_branch_diameter_organic", "tree_support_tip_diameter", "tree_support_adaptive_layer_height", "tree_support_wall_count",
          "max_bridge_length", "tree_support_branch_distance", "tree_support_branch_distance_organic"):
    print("  config %-38s %s" % (k, an.config(r, k)))

print("\n#277 overhang walls without support below")
r = gparse.load("06c69298")
S = r["S"]
miss = collections.Counter()
tot = collections.Counter()
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
    tot["%d" % (L // 50 * 50)] += len(mids)
    miss["%d" % (L // 50 * 50)] += int((~found).sum())
print("  by layer band (start layer): overhang-wall segments total / without support within 1.2 mm below: %s" % {
    k: "%d/%d" % (tot[k], miss[k]) for k in sorted(tot, key=int)})
print("  support body top layer Z: %.2f ; model height %.2f" % (
    max(r["layers"][L - 1]["z"] for L in set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(r, "Support"))), r["layers"][-1]["z"]))
