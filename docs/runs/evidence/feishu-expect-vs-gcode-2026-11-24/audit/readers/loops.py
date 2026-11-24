"""Loops / travel / seam / fuzzy rows: 256, 260, 261, 266, 295 (+ follow-ups for 280, 281).

    python -B loops.py <out.txt>
"""
import collections
import io
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402

out = io.open(sys.argv[1], "w", encoding="utf-8")


def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


def cfg(g, b, keys):
    for k in keys:
        P("  config %-30s run %s | base %s" % (k, an.config(g, k), an.config(b, k) if b else ""))


def geom_equal(ga, gb, name, layers=None, nd=3):
    """same multiset of rounded extruding segments (order ignored)"""
    def segs(g):
        S = g["S"]
        f = an.feat(g, name)
        if f is None:
            return collections.Counter()
        c = collections.Counter()
        for i in an.idx(g).get(None, []) if False else []:
            pass
        for i in range(len(S["k"])):
            if S["k"][i] == an.X and S["F"][i] == f and (layers is None or S["L"][i] in layers):
                a = (round(S["x0"][i], nd), round(S["y0"][i], nd))
                b = (round(S["x1"][i], nd), round(S["y1"][i], nd))
                c[(S["L"][i],) + min(a, b) + max(a, b)] += 1
        return c
    A, B = segs(ga), segs(gb)
    return "segments %d vs %d, only-in-run %d, only-in-base %d" % (sum(A.values()), sum(B.values()), sum((A - B).values()), sum((B - A).values()))


def bbox_of(g, name):
    S = g["S"]
    f = an.feat(g, name)
    xs, ys = [], []
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f:
            xs += [S["x0"][i], S["x1"][i]]
            ys += [S["y0"][i], S["y1"][i]]
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


# ---------------------------------------------------------------- #256
P("=" * 90, "\n#256 seam / wipe  run fd0abb31  base 818ecfc6")
r, b = gparse.load("fd0abb31"), gparse.load("818ecfc6")
cfg(r, b, ["seam_position", "seam_gap", "wipe_on_loops", "wipe_speed", "role_based_wipe_speed", "wipe_distance", "wipe_before_external_loop",
           "staggered_inner_seams", "seam_slope_type", "outer_wall_speed", "note: wipe_speed written as absolute 50 while role_based=1"])
P("  markers with WIPE/SEAM in run: %s | base: %s" % ({k: v for k, v in r["markers"].items() if "WIPE" in k or "SEAM" in k},
                                                    {k: v for k, v in b["markers"].items() if "WIPE" in k or "SEAM" in k}))
S, Sb = r["S"], b["S"]
for tag, SS, g in (("run", S, r), ("base", Sb, b)):
    wi = [i for i in range(len(SS["k"])) if SS["wi"][i] and SS["k"][i] in (an.TRAVEL, an.WIPERET, an.X)]
    P("  [%s] moves inside WIPE_START..END: %d; kinds %s; feeds %s; E sum %.2f; total XY len %.1f mm" % (
        tag, len(wi), dict(collections.Counter(SS["k"][i] for i in wi)),
        dict(collections.Counter("%.0f" % SS["fd"][i] for i in wi).most_common(5)), sum(SS["e"][i] for i in wi),
        sum(an.seg_len(SS, i) for i in wi)))
fo = an.feat(r, "Outer wall")
ow_feeds_run = collections.Counter("%.0f" % S["fd"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fo)
ow_feeds_base = collections.Counter("%.0f" % Sb["fd"][i] for i in range(len(Sb["k"])) if Sb["k"][i] == an.X and Sb["F"][i] == an.feat(b, "Outer wall"))
P("  outer-wall feed histogram identical to base: %s (run %s)" % (ow_feeds_run == ow_feeds_base, dict(ow_feeds_run.most_common(4))))
for name in ("Outer wall", "Inner wall", "Sparse infill", "Top surface", "Bottom surface"):
    P("  paths %-14s %s" % (name, geom_equal(r, b, name)))
# seam: start point of the outer-wall loop per layer, and the gap between the loop's last end and its start
starts, gaps = [], []
for layer in range(1, 41):
    for ch in an.chains(r, layer, "Outer wall"):
        L = an.chain_len(r, ch)
        if L > 20:
            x0, y0 = S["x0"][ch[0]], S["y0"][ch[0]]
            x1, y1 = S["x1"][ch[-1]], S["y1"][ch[-1]]
            starts.append((layer, round(x0, 2), round(y0, 2)))
            gaps.append(math.hypot(x1 - x0, y1 - y0))
xs = [s[1] for s in starts]
ys = [s[2] for s in starts]
P("  outer-wall loop start (seam) on layers 1..40: x %.2f..%.2f y %.2f..%.2f (spread x %.3f y %.3f); first 6: %s" % (
    min(xs), max(xs), min(ys), max(ys), max(xs) - min(xs), max(ys) - min(ys), starts[:6]))
P("  loops found on layers 1..40: %d; seam gap (end minus start): min %.4f median %.4f max %.4f ; 15%% of 0.42 = %.4f, 15%% of 0.5 = %.4f" % (
    len(gaps), min(gaps), sorted(gaps)[len(gaps) // 2], max(gaps), 0.15 * 0.42, 0.15 * 0.5))
gaps_b = []
for layer in range(1, 41):
    for ch in an.chains(b, layer, "Outer wall"):
        if an.chain_len(b, ch) > 20:
            gaps_b.append(math.hypot(Sb["x1"][ch[-1]] - Sb["x0"][ch[0]], Sb["y1"][ch[-1]] - Sb["y0"][ch[0]]))
P("  (base) seam gap: min %.4f median %.4f max %.4f" % (min(gaps_b), sorted(gaps_b)[len(gaps_b) // 2], max(gaps_b)))
# one OW block per layer?
per = collections.Counter(layer for (layer, _, _) in starts)
P("  outer-wall loops > 20 mm per layer (layers 1..40): %s" % dict(collections.Counter(per.values())))
lines = open(r["path"], encoding="utf-8", errors="replace").read().split("\n")
k = next(i for i, l in enumerate(lines) if l.startswith(";WIPE_START"))
P("  raw sample around first WIPE_START:")
for l in lines[k - 6:k + 8]:
    P("     " + l[:100])

# ---------------------------------------------------------------- #260
P("=" * 90, "\n#260 Arachne  run 433b83c4  base 78f01bb0")
r, b = gparse.load("433b83c4"), gparse.load("78f01bb0")
cfg(r, b, ["wall_generator", "min_bead_width", "min_feature_size", "wall_distribution_count", "wall_transition_angle", "wall_transition_length",
           "wall_transition_filter_deviation", "wall_loops", "detect_thin_wall"])
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    ws = [S["w"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] in (an.feat(g, "Outer wall"), an.feat(g, "Inner wall"))]
    nonom = [w for w in ws if w]
    P("  [%s] wall moves with a ;WIDTH: comment: %d of %d; width min %.3f median %.3f max %.3f; moves with width < 0.10: %d; == 0: %d" % (
        tag, len(nonom), len(ws), min(nonom) if nonom else float("nan"), float(np.median(nonom)) if nonom else float("nan"),
        max(nonom) if nonom else float("nan"), sum(1 for w in nonom if w < 0.10), sum(1 for w in nonom if w == 0)))
    # outer contour continuity: chains of the outer wall on a few layers, closed?
    open_, closed_, n = 0, 0, 0
    for layer in (2, 5, 10, 15, 19):
        for ch in an.chains(g, layer, "Outer wall"):
            n += 1
            if an.chain_closed(g, ch, 0.12):
                closed_ += 1
            else:
                open_ += 1
    P("       outer-wall chains on layers 2,5,10,15,19: %d (closed %d, open %d)" % (n, closed_, open_))
    tot = collections.Counter()
    for layer in (2, 5, 10, 15, 19):
        for name in ("Outer wall", "Inner wall"):
            tot[name] += len(an.chains(g, layer, name))
        tot["moves"] += sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == layer and S["F"][i] in (an.feat(g, "Outer wall"), an.feat(g, "Inner wall")))
        tot["len"] += round(sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == layer and S["F"][i] in (an.feat(g, "Outer wall"), an.feat(g, "Inner wall"))), 1)
    P("       walls on layers 2,5,10,15,19: %s" % dict(tot))
    for name in ("Gap infill", "Sparse infill", "Top surface"):
        if an.feat(g, name) is not None:
            f_ = an.feat(g, name)
            mv = sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f_)
            ln = sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f_)
            P("       %-13s blocks %d moves %d len %.1f" % (name, g["types"].get(name, 0), mv, ln))
    P("       outer-wall bbox x %.2f..%.2f y %.2f..%.2f" % bbox_of(g, "Outer wall"))

# ---------------------------------------------------------------- #261
P("=" * 90, "\n#261 one wall / avoid crossing  run bdf3dd93  base 5994d5e6")
r, b = gparse.load("bdf3dd93"), gparse.load("5994d5e6")
cfg(r, b, ["only_one_wall_top", "min_width_top_surface", "only_one_wall_first_layer", "reduce_crossing_wall", "max_travel_detour_distance", "wall_loops"])
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    fi = an.feat(g, "Inner wall")
    iw1 = sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == 1 and S["F"][i] == fi)
    top_layers = set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(g, "Top surface"))
    iw_top = sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi and S["L"][i] in top_layers)
    iw_all = sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)
    iw_len_top = sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi and S["L"][i] in top_layers)
    lay_with_iw = len(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi))
    P("  [%s] inner-wall moves on layer 1: %d | layers with any inner wall: %d of %d | inner-wall moves on top-surface layers (%d layers): %d of %d (%.1f%%), len %.0f" % (
        tag, iw1, lay_with_iw, len(g["layers"]), len(top_layers), iw_top, iw_all, 100.0 * iw_top / iw_all, iw_len_top))
    # per-layer IW chains on a range of top layers
    cnt = collections.Counter()
    for L in range(225, 241):
        cnt[L] = len(an.chains(g, L, "Inner wall"))
    P("       inner-wall chains per layer 225..240: %s" % dict(cnt))

def crossing(g, layer):
    """(number of travel chains on the layer, how many of them cross an outer-wall loop of that layer, their excess lengths)"""
    S = g["S"]
    ow = an.segs_of(g, layer, ["Outer wall"])
    ids = an.idx(g)
    # travel chains: consecutive TRAVEL moves (possibly with Z-only/E-only between) between two extruding moves on this layer
    res = []
    cur = []
    for i in range(len(S["k"])):
        if S["L"][i] != layer:
            if cur and S["L"][i] > layer:
                break
            continue
        k = S["k"][i]
        if k == an.TRAVEL:
            cur.append(i)
        elif k == an.X:
            if cur:
                res.append(cur)
            cur = []
        elif k in (an.ZONLY, an.FONLY):
            continue
        else:
            if cur:
                res.append(cur)
            cur = []
    return res, ow


def seg_cross(a, b, c, d):
    def ccw(p, q, s):
        return (q[0] - p[0]) * (s[1] - p[1]) - (q[1] - p[1]) * (s[0] - p[0])
    d1, d2, d3, d4 = ccw(a, b, c), ccw(a, b, d), ccw(c, d, a), ccw(c, d, b)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and all(abs(x) > 1e-9 for x in (d1, d2, d3, d4))


    A_ow, B_ow = ow[:, :2], ow[:, 2:]

    def crosses_any(p, q):
        def ccw(ax, ay, bx, by, cx, cy):
            return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        d1 = ccw(p[0], p[1], q[0], q[1], A_ow[:, 0], A_ow[:, 1])
        d2 = ccw(p[0], p[1], q[0], q[1], B_ow[:, 0], B_ow[:, 1])
        d3 = ccw(A_ow[:, 0], A_ow[:, 1], B_ow[:, 0], B_ow[:, 1], p[0], p[1])
        d4 = ccw(A_ow[:, 0], A_ow[:, 1], B_ow[:, 0], B_ow[:, 1], q[0], q[1])
        return bool((((d1 > 1e-9) != (d2 > 1e-9)) & ((d3 > 1e-9) != (d4 > 1e-9)) & (np.abs(d1) > 1e-9) & (np.abs(d2) > 1e-9) & (np.abs(d3) > 1e-9) & (np.abs(d4) > 1e-9)).any())

    for tag, g in (("run", r), ("base", b)):
        S = g["S"]
        n_ch = n_cross = n_detour = 0
        excess = []
        for layer in range(2, len(g["layers"]) + 1, 3):
            chains, ow = crossing(g, layer)
            if len(ow) == 0:
                continue
            A_ow, B_ow = ow[:, :2], ow[:, 2:]
            for ch in chains:
                pts_ = [(S["x0"][i], S["y0"][i]) for i in ch] + [(S["x1"][ch[-1]], S["y1"][ch[-1]])]
                path = sum(math.hypot(pts_[j + 1][0] - pts_[j][0], pts_[j + 1][1] - pts_[j][1]) for j in range(len(pts_) - 1))
                straight = math.hypot(pts_[-1][0] - pts_[0][0], pts_[-1][1] - pts_[0][1])
                if path < 1.0:
                    continue
                n_ch += 1
                if any(crosses_any(pts_[j], pts_[j + 1]) for j in range(len(pts_) - 1)):
                    n_cross += 1
                if path - straight > 0.3:
                    n_detour += 1
                    excess.append(path - straight)
    ex = sorted(excess)
    P("  [%s] travel chains (>=1 mm, every 3rd layer): %d; straight ones crossing an outer wall of the layer: %d; chains longer than the straight line by >0.3 mm: %d (excess median %.2f, p95 %.2f, max %.2f; >2.2 mm: %d)" % (
        tag, n_ch, n_cross, n_detour, ex[len(ex) // 2] if ex else 0, ex[int(len(ex) * .95)] if ex else 0, ex[-1] if ex else 0, sum(1 for e in ex if e > 2.2)))

# ---------------------------------------------------------------- #266
P("=" * 90, "\n#266 wall loops / thin wall  run 1ffdefee  base 5994d5e6")
r, b = gparse.load("1ffdefee"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    fo, fi = an.feat(g, "Outer wall"), an.feat(g, "Inner wall")
    per = []
    for L in (150, 160, 170, 180, 190, 200, 210):
        per.append((L, len(an.chains(g, L, "Outer wall")), len(an.chains(g, L, "Inner wall"))))
    P("  [%s] (layer, outer-wall chains, inner-wall chains) for mid layers: %s" % (tag, per))
    ws = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] in (fo, fi) and S["w"][i]:
            ws["%.3f" % S["w"][i]] += 1
    tot = sum(ws.values())
    small = sum(v for k, v in ws.items() if float(k) < 0.4)
    P("       wall moves with ;WIDTH: %d; width<0.40: %d (min %.3f); distinct widths %d; most common %s" % (
        tot, small, min(float(k) for k in ws) if ws else float("nan"), len(ws), ws.most_common(5)))
    thin = [(S["L"][i], round(S["w"][i], 3), round(an.seg_len(S, i), 2)) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] in (fo, fi) and 0 < S["w"][i] < 0.36]
    P("       moves with width < 0.36 (single-line thin walls): %d; sample (layer, width, len) %s" % (len(thin), thin[:10]))
    op = cl = 0
    for L in range(2, len(g["layers"]) + 1):
        for name in ("Outer wall", "Inner wall"):
            for ch in an.chains(g, L, name):
                if an.chain_len(g, ch) > 2.0:
                    if an.chain_closed(g, ch, 0.12):
                        cl += 1
                    else:
                        op += 1
    P("       wall chains > 2 mm (layers>=2): closed %d, open %d" % (cl, op))
    P("       outer-wall bbox x %.2f..%.2f y %.2f..%.2f" % bbox_of(g, "Outer wall"))
    tops = len(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fo))
    P("       layers with outer wall: %d; with inner wall: %d; layers with gap infill: %d; total len outer %.0f inner %.0f" % (
        tops, len(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)),
        len(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(g, "Gap infill"))) if an.feat(g, "Gap infill") is not None else 0,
        sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fo), sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)))

# ---------------------------------------------------------------- #295
P("=" * 90, "\n#295 fuzzy skin  run d3191da6  base 71c5f8fc")
r, b = gparse.load("d3191da6"), gparse.load("71c5f8fc")
cfg(r, b, ["fuzzy_skin", "fuzzy_skin_point_distance", "fuzzy_skin_thickness", "outer_wall_speed"])
S, Sb = r["S"], b["S"]
for tag, g, SS in (("run", r, S), ("base", b, Sb)):
    for name in ("Outer wall", "Overhang wall", "Inner wall"):
        f = an.feat(g, name)
        ls = sorted(an.seg_len(SS, i) for i in range(len(SS["k"])) if SS["k"][i] == an.X and SS["F"][i] == f and SS["L"][i] >= 2)
        P("  [%s] %-13s moves %d; segment length min %.3f median %.3f p90 %.3f max %.3f" % (
            tag, name, len(ls), ls[0], ls[len(ls) // 2], ls[int(len(ls) * .9)], ls[-1]) if ls else "  [%s] %s none" % (tag, name))
# deviation of the run's outer-wall path from the baseline outer-wall path, same layer
devs = []
inside = 0
outside = 0
for L in range(2, 101, 5):
    base = an.segs_of(b, L, ["Outer wall", "Overhang wall"])
    if len(base) == 0:
        continue
    f = [an.feat(r, "Outer wall"), an.feat(r, "Overhang wall")]
    ids = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] in f]
    pts_ = np.array([(S["x0"][i], S["y0"][i]) for i in ids] + [(S["x1"][i], S["y1"][i]) for i in ids])
    d = an.point_seg_dist(pts_, base)
    devs.append(d)
d = np.concatenate(devs)
P("  distance of run outer-wall vertices from the baseline outer wall (layers 2..100 step 5): max %.3f, p99 %.3f, median %.3f; share <= 0.31: %.1f%%" % (
    d.max(), float(np.percentile(d, 99)), float(np.median(d)), 100.0 * (d <= 0.31).mean()))
for name in ("Inner wall", "Sparse infill", "Top surface", "Internal solid infill", "Internal Bridge", "Bridge", "Bottom surface", "Brim"):
    P("  paths %-20s %s" % (name, geom_equal(r, b, name)))
out.close()
