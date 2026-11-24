"""Geometry rows: 257 (precision), 258 (arcs), 278 (raft), 293 (spiral vase).

    python -B geom.py
"""
import collections
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def cfg(g, keys, b=None):
    for k in keys:
        print("  config %-30s %s | base %s" % (k, an.config(g, k), an.config(b, k) if b else ""))


def verts(g, L, name):
    S = g["S"]
    f = an.feat(g, name)
    p = np.array([(S["x0"][i], S["y0"][i]) for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f and S["arc"][i] == 0]
                 + [(S["x1"][i], S["y1"][i]) for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f and S["arc"][i] == 0])
    return p


print("#257 precision compensation  run 3f239cab  base 0d6777e0")
r, b = gparse.load("3f239cab"), gparse.load("0d6777e0")
cfg(r, ["elefant_foot_compensation", "elefant_foot_compensation_layers", "xy_contour_compensation", "xy_hole_compensation", "precise_outer_wall",
        "xy_inner_hole_compensation", "outer_wall_line_width", "initial_layer_line_width"], b)
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    v2 = verts(g, 2, "Outer wall")
    v1 = verts(g, 1, "Outer wall")
    v3 = verts(g, 3, "Outer wall")
    d21 = an.point_seg_dist(v1, an.segs_of(g, 2, ["Outer wall"]))
    d23 = an.point_seg_dist(v3, an.segs_of(g, 2, ["Outer wall"]))
    print("  [%s] layer-1 outer-wall vertices to the layer-2 outer wall (same cross-section): distance median %.4f p90 %.4f max %.4f | layer-3 to layer-2: median %.4f" % (
        tag, float(np.median(d21)), float(np.percentile(d21, 90)), d21.max(), float(np.median(d23))))
    # first layer line width
    w1 = [S["w"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == 1 and S["F"][i] == an.feat(g, "Outer wall")][:1]
    print("       first-layer outer-wall width %s ; 0.15 - (0.5-0.42)/2 = %.3f" % (w1, 0.15 - 0.04))
vr = verts(r, 5, "Outer wall")
vb = verts(b, 5, "Outer wall")
d = an.point_seg_dist(vr, an.segs_of(b, 5, ["Outer wall"]))
db = an.point_seg_dist(vb, an.segs_of(r, 5, ["Outer wall"]))
print("  run outer-wall vertices (layer 5) to the baseline outer wall: median %.4f p10 %.4f p90 %.4f max %.4f (n=%d); base vertices to run wall median %.4f p90 %.4f" % (
    float(np.median(d)), float(np.percentile(d, 10)), float(np.percentile(d, 90)), d.max(), len(d), float(np.median(db)), float(np.percentile(db, 90))))
# separate outer contours and holes: signed test by bbox growth / hole shrink
for tag, g in (("run", r), ("base", b)):
    xs, ys = [], []
    S = g["S"]
    f = an.feat(g, "Outer wall")
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["L"][i] == 5 and S["F"][i] == f:
            xs += [S["x0"][i], S["x1"][i]]
            ys += [S["y0"][i], S["y1"][i]]
    loops = [c for c in an.chains(g, 5, "Outer wall") if an.chain_len(g, c) > 1.0]
    areas = []
    for c in loops:
        p = an.pts(g, c)
        a = 0.5 * abs(sum(p[j][0] * p[j + 1][1] - p[j + 1][0] * p[j][1] for j in range(len(p) - 1)))
        areas.append(a)
    print("  [%s] layer-5 outer-wall bbox x %.3f..%.3f y %.3f..%.3f (w %.3f h %.3f); wall loops %d; signed area of loops: positive %d (sum %.1f), negative %d (sum %.1f)" % (
        tag, min(xs), max(xs), min(ys), max(ys), max(xs) - min(xs), max(ys) - min(ys), len(loops),
        sum(1 for a in areas if a > 0), sum(a for a in areas if a > 0), sum(1 for a in areas if a < 0), -sum(a for a in areas if a < 0)))
# hole sizes: per hole loop on layer 5, compare perimeter run vs base (matched by centroid)
def hole_table(g):
    out = {}
    S = g["S"]
    for c in an.chains(g, 5, "Outer wall"):
        p = an.pts(g, c)
        a = 0.5 * sum(p[j][0] * p[j + 1][1] - p[j + 1][0] * p[j][1] for j in range(len(p) - 1))
        if a < -0.5:
            cx = sum(q[0] for q in p[:-1]) / (len(p) - 1)
            cy = sum(q[1] for q in p[:-1]) / (len(p) - 1)
            out[(round(cx, 1), round(cy, 1))] = (-a, an.chain_len(g, c))
    return out
hr, hb = hole_table(r), hole_table(b)
common = sorted(set(hr) & set(hb))
print("  hole loops on layer 5: run %d base %d matched %d; hole area run/base for the first 8: %s" % (
    len(hr), len(hb), len(common), [(k, round(hb[k][0], 3), round(hr[k][0], 3)) for k in common[:8]]))
ratios = [hr[k][0] / hb[k][0] for k in common if hb[k][0] > 0.5]
if ratios:
    print("  hole area ratio run/base (holes > 0.5 mm2): min %.4f median %.4f max %.4f (n=%d); perimeter ratio median %.4f" % (
        min(ratios), float(np.median(ratios)), max(ratios), len(ratios), float(np.median([hr[k][1] / hb[k][1] for k in common]))))
for name in ("Gap infill", "Bottom surface", "Internal solid infill", "Sparse infill", "Top surface"):
    print("  %-20s blocks run %d base %d" % (name, r["types"].get(name, 0), b["types"].get(name, 0)))

print("\n#258 arcs / resolution  run dc0f42c3  base 0d6777e0")
r, b = gparse.load("dc0f42c3"), gparse.load("0d6777e0")
cfg(r, ["enable_arc_fitting", "precise_z_height", "resolution", "slice_closing_radius", "layer_height", "first_layer_height", "arc_fitting_radius_limit"], b)
S = r["S"]
arcs = collections.Counter()
rad = []
by_feat = collections.Counter()
for i in range(len(S["k"])):
    if S["arc"][i]:
        by_feat[r["feat_names"][S["F"][i]]] += 1
        cx, cy = S["cx"][i], S["cy"][i]
        rad.append(math.hypot(S["x0"][i] - cx, S["y0"][i] - cy))
rad = np.array(rad)
print("  G2/G3 moves: %d (by feature %s); radius min %.3f median %.3f max %.3f; distinct radii (0.01): %d" % (
    len(rad), dict(by_feat), rad.min(), float(np.median(rad)), rad.max(), len(set(np.round(rad, 2).tolist()))))
print("  comment markers with ARC in run: %s" % {k: v for k, v in r["markers"].items() if "ARC" in k.upper()})
# contour error: baseline vertices (polyline) near each arc should lie on the arc circle within resolution
Sb = b["S"]
errs = []
for i in range(len(S["k"])):
    if not S["arc"][i] or S["k"][i] != an.X:
        continue
    L = S["L"][i]
    if L not in (2, 6, 10, 15, 20):
        continue
    cx, cy = S["cx"][i], S["cy"][i]
    R = math.hypot(S["x0"][i] - cx, S["y0"][i] - cy)
    # baseline extruding vertices of the same layer and feature within 1.5R of the centre
    f = an.feat(b, r["feat_names"][S["F"][i]])
    xs = np.array([(Sb["x0"][j], Sb["y0"][j]) for j in range(len(Sb["k"])) if Sb["k"][j] == an.X and Sb["L"][j] == L and Sb["F"][j] == f])
    dd = np.hypot(xs[:, 0] - cx, xs[:, 1] - cy)
    near = dd[(dd > 0.5 * R) & (dd < 1.5 * R)]
    # keep only those close to this circle
    near = near[np.abs(near - R) < 0.15]
    errs += list(np.abs(near - R))
errs = np.array(errs)
print("  radial error of baseline polyline vertices against the fitted arcs (5 layers): n=%d median %.4f p90 %.4f max %.4f ; share <= 0.012: %.1f%%" % (
    len(errs), float(np.median(errs)), float(np.percentile(errs, 90)), errs.max(), 100.0 * (errs <= 0.012).mean()))
for tag, g in (("run", r), ("base", b)):
    zs = [(l["z"], l["height"]) for l in g["layers"]]
    print("  [%s] layers %d; first (z,h) %s %s; last %s %s; last Z %.3f; heights %s" % (
        tag, len(zs), zs[0], zs[1], zs[-2], zs[-1], zs[-1][0], dict(collections.Counter("%.3g" % h for _, h in zs))))
    print("       wall loops per layer (outer+inner) on layers 2,10,20: %s ; OW+IW moves %d" % (
        [len(an.chains(g, L, "Outer wall")) + len(an.chains(g, L, "Inner wall")) for L in (2, 10, 20)],
        sum(1 for i in range(len(g["S"]["k"])) if g["S"]["k"][i] == an.X and g["S"]["F"][i] in (an.feat(g, "Outer wall"), an.feat(g, "Inner wall")))))

print("\n#278 raft  run 0c5eda6b  base 5994d5e6")
r, b = gparse.load("0c5eda6b"), gparse.load("5994d5e6")
cfg(r, ["raft_layers", "raft_contact_distance", "raft_expansion", "raft_first_layer_density", "raft_first_layer_expansion", "raft_airgap",
        "support_type", "enable_support", "support_top_z_distance", "support_bottom_z_distance", "support_line_width", "first_layer_height"], b)
for L in range(1, 9):
    info = r["layers"][L - 1]
    S = r["S"]
    row = []
    for f in info["feats"]:
        ids = [i for i in an.idx(r).get((L, f), []) if S["k"][i] == an.X]
        if ids:
            xs = [S["x0"][i] for i in ids] + [S["x1"][i] for i in ids]
            ys = [S["y0"][i] for i in ids] + [S["y1"][i] for i in ids]
            row.append("%s %d mv %.0f mm x %.1f..%.1f y %.1f..%.1f" % (r["feat_names"][f][:10], len(ids), sum(an.seg_len(S, i) for i in ids), min(xs), max(xs), min(ys), max(ys)))
    print("  layer %d z %s h %s: %s" % (L, info["z"], info["height"], " | ".join(row)))
Sb = b["S"]
fb = an.feat(b, "Outer wall")
xs = [Sb["x0"][i] for i in range(len(Sb["k"])) if Sb["k"][i] == an.X and Sb["L"][i] == 1 and Sb["F"][i] == fb] + [Sb["x1"][i] for i in range(len(Sb["k"])) if Sb["k"][i] == an.X and Sb["L"][i] == 1 and Sb["F"][i] == fb]
ys = [Sb["y0"][i] for i in range(len(Sb["k"])) if Sb["k"][i] == an.X and Sb["L"][i] == 1 and Sb["F"][i] == fb] + [Sb["y1"][i] for i in range(len(Sb["k"])) if Sb["k"][i] == an.X and Sb["L"][i] == 1 and Sb["F"][i] == fb]
print("  model first-layer outer-wall bbox in the baseline: x %.2f..%.2f y %.2f..%.2f" % (min(xs), max(xs), min(ys), max(ys)))
for L, name in ((1, "Support"), (2, "Support"), (3, "Support interface"), (4, "Support interface"), (5, "Support interface")):
    seg = an.segs_of(r, L, [name])
    if len(seg):
        sp = an.spacing_parallel(seg)
        print("  layer %d %s: %d moves, across-line spacing median %s (n=%d)" % (L, name, len(seg), ("%.3f" % float(np.median(sp))) if sp else "-", len(sp)))
print("  bed_shape %s ; bbox of everything on layer 1: x %.1f..%.1f y %.1f..%.1f" % (
    an.config(r, "bed_shape"), min(S["x0"][i] for i in range(len(S["k"])) if S["L"][i] == 1 and S["k"][i] == an.X),
    max(S["x1"][i] for i in range(len(S["k"])) if S["L"][i] == 1 and S["k"][i] == an.X),
    min(S["y0"][i] for i in range(len(S["k"])) if S["L"][i] == 1 and S["k"][i] == an.X), max(S["y1"][i] for i in range(len(S["k"])) if S["L"][i] == 1 and S["k"][i] == an.X)))

print("\n#293 spiral vase  run 4efcad2b  base 818ecfc6")
r, b = gparse.load("4efcad2b"), gparse.load("818ecfc6")
cfg(r, ["spiral_mode", "seam_position", "wall_loops", "top_shell_layers", "sparse_infill_density", "retract_when_changing_layer", "spiral_mode_smooth",
        "spiral_mode_max_xy_smoothing", "spiral_starting_flow_ratio", "spiral_finishing_flow_ratio", "outer_wall_speed"], b)
S = r["S"]
print("  layers: " + "; ".join("L%d z=%s h=%s %s" % (l["n"], l["z"], l["height"], [r["feat_names"][f][:6] for f in l["feats"]]) for l in r["layers"][:4])
      + " ... " + "; ".join("L%d z=%s h=%s %s" % (l["n"], l["z"], l["height"], [r["feat_names"][f][:6] for f in l["feats"]]) for l in r["layers"][-3:]))
dz = collections.Counter()
nz = 0
flat = 0
zt = []
for i in range(len(S["k"])):
    if S["k"][i] == an.X and S["L"][i] >= 2:
        if S["Z"][i] != S["Z"][i - 1] if i else True:
            pass
# Z carried by extruding moves: compare consecutive extruding moves' Z
ids = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] >= 3]
steps = [round(S["Z"][ids[j + 1]] - S["Z"][ids[j]], 5) for j in range(len(ids) - 1) if abs(S["Z"][ids[j + 1]] - S["Z"][ids[j]]) > 1e-6]
flat = sum(1 for j in range(len(ids) - 1) if abs(S["Z"][ids[j + 1]] - S["Z"][ids[j]]) <= 1e-6)
print("  extruding moves on layers >= 3: %d; consecutive pairs with a Z change: %d (step median %.5f, min %.5f, max %.5f); pairs without Z change: %d" % (
    len(ids), len(steps), float(np.median(steps)), min(steps), max(steps), flat))
print("  Z range of those moves %.3f..%.3f; monotonic non-decreasing: %s" % (
    min(S["Z"][i] for i in ids), max(S["Z"][i] for i in ids), all(S["Z"][ids[j + 1]] >= S["Z"][ids[j]] - 1e-9 for j in range(len(ids) - 1))))
ret = collections.Counter()
for i in range(len(S["k"])):
    if S["k"][i] == an.EONLY:
        ret[(S["L"][i], "retract" if S["e"][i] < 0 else "prime")] += 1
print("  retract/prime (E-only) by layer: %s" % dict(sorted(ret.items())))
tr = collections.Counter(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.TRAVEL)
print("  travel moves by layer: %s" % dict(sorted(tr.items())))
print("  features in run: %s" % dict(r["types"]))
print("  comment markers: %s" % {k: v for k, v in r["markers"].items() if k in ("SPIRAL", "LAYER_CHANGE", "HEIGHT", "Z", "TYPE")})
